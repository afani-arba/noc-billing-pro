"""
BGP/OSPF Alert Service: monitor routing protokol di semua device,
kirim notifikasi WA/Telegram jika peer down atau recover.

Cara kerja:
- Cek semua device online setiap 5 menit
- Query BGP peers + OSPF neighbors via MikroTik API
- Bandingkan dengan state sebelumnya di MongoDB (bgp_alert_state collection)
- Jika state berubah (established → down atau down → established): kirim notif
"""
import asyncio
import logging
from datetime import datetime, timezone
from core.db import get_db
from mikrotik_api import get_api_client
from services.notification_service import send_to_all_recipients, _get_settings

logger = logging.getLogger(__name__)

BGP_CHECK_INTERVAL = 300   # cek setiap 5 menit
OSPF_CHECK_INTERVAL = 300  # cek setiap 5 menit


def _bgp_state(peer: dict) -> str:
    """Normalize BGP peer state dari berbagai format ROS."""
    raw = (
        peer.get("_status") or
        peer.get("state") or
        peer.get("status") or
        ""
    ).lower()
    if "established" in raw:
        return "established"
    if "active" in raw:
        return "active"
    if "idle" in raw:
        return "idle"
    return raw or "unknown"


def _ospf_state(neighbor: dict) -> str:
    """Normalize OSPF neighbor state."""
    return (neighbor.get("state") or neighbor.get("_state") or "").lower()


async def _check_bgp_for_device(device: dict, settings: dict, db) -> None:
    """Cek BGP peers satu device, kirim alert jika ada perubahan state."""
    device_id = device["id"]
    device_name = device.get("name", device_id)

    try:
        mt = get_api_client(device)
        peers_raw = await mt.list_bgp_peers()
        sessions_raw = await mt.list_bgp_sessions()
        peers = peers_raw if isinstance(peers_raw, list) else []
        sessions = sessions_raw if isinstance(sessions_raw, list) else []

        # Normalize peers — reuse logic dari routing.py
        from routers.routing import _normalize_bgp_peer
        peers = [_normalize_bgp_peer(p, sessions) for p in peers]

    except Exception as e:
        logger.debug(f"BGP check failed for {device_name}: {e}")
        return

    for peer in peers:
        peer_name = peer.get("name", "")
        remote_as = str(peer.get("remote-as", ""))
        remote_addr = peer.get("remote-address", "")
        current_state = _bgp_state(peer)
        peer_key = f"bgp:{device_id}:{peer_name or remote_addr}"

        # State sebelumnya dari DB
        prev = await db.bgp_alert_state.find_one({"key": peer_key})
        prev_state = prev.get("state", "unknown") if prev else "unknown"

        # Update state di DB
        await db.bgp_alert_state.update_one(
            {"key": peer_key},
            {"$set": {
                "key": peer_key,
                "device_id": device_id,
                "device_name": device_name,
                "peer_name": peer_name,
                "remote_as": remote_as,
                "remote_address": remote_addr,
                "state": current_state,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }},
            upsert=True
        )

        notify_bgp = settings.get("notify_bgp", True)
        if not notify_bgp:
            continue

        # Peer DOWN: sebelumnya established → sekarang bukan
        if prev_state == "established" and current_state != "established":
            msg = (
                f"🔴 *ALERT: BGP Peer Down*\n"
                f"━━━━━━━━━━━━━━\n"
                f"📡 Device: *{device_name}*\n"
                f"🔗 Peer: *{peer_name}* ({remote_addr})\n"
                f"🏷️ AS: {remote_as}\n"
                f"📊 Status: *{current_state}* (was: established)\n"
                f"⏰ {datetime.now(timezone.utc).strftime('%H:%M %Z')}\n"
                f"━━━━━━━━━━━━━━\n"
                f"NOC-Sentinel Monitoring"
            )
            await send_to_all_recipients(msg, settings)
            logger.warning(f"BGP alert sent: {device_name} peer {peer_name} → {current_state}")

            # Simpan ke history
            await db.routing_alert_history.insert_one({
                "type": "bgp_down",
                "device_id": device_id,
                "device_name": device_name,
                "peer_name": peer_name,
                "remote_as": remote_as,
                "remote_address": remote_addr,
                "prev_state": prev_state,
                "current_state": current_state,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })

        # Peer RECOVER: sebelumnya bukan established → sekarang established
        elif prev_state not in ("established", "unknown") and current_state == "established":
            msg = (
                f"🟢 *RECOVER: BGP Peer Established*\n"
                f"━━━━━━━━━━━━━━\n"
                f"📡 Device: *{device_name}*\n"
                f"🔗 Peer: *{peer_name}* ({remote_addr})\n"
                f"🏷️ AS: {remote_as}\n"
                f"📊 Status: *established* ✓\n"
                f"⏰ {datetime.now(timezone.utc).strftime('%H:%M %Z')}\n"
                f"━━━━━━━━━━━━━━\n"
                f"NOC-Sentinel Monitoring"
            )
            await send_to_all_recipients(msg, settings)
            logger.info(f"BGP recover: {device_name} peer {peer_name} → established")

            await db.routing_alert_history.insert_one({
                "type": "bgp_recover",
                "device_id": device_id,
                "device_name": device_name,
                "peer_name": peer_name,
                "remote_as": remote_as,
                "remote_address": remote_addr,
                "prev_state": prev_state,
                "current_state": current_state,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })


async def _check_ospf_for_device(device: dict, settings: dict, db) -> None:
    """Cek OSPF neighbors satu device, kirim alert jika ada perubahan."""
    device_id = device["id"]
    device_name = device.get("name", device_id)

    try:
        mt = get_api_client(device)
        neighbors_raw = await mt.list_ospf_neighbors()
        neighbors = neighbors_raw if isinstance(neighbors_raw, list) else []
    except Exception as e:
        logger.debug(f"OSPF check failed for {device_name}: {e}")
        return

    for nb in neighbors:
        nb_addr = nb.get("address", nb.get(".id", ""))
        nb_iface = nb.get("interface", "")
        current_state = _ospf_state(nb)
        is_full = "full" in current_state
        nb_key = f"ospf:{device_id}:{nb_addr}"

        prev = await db.bgp_alert_state.find_one({"key": nb_key})
        prev_state = prev.get("state", "unknown") if prev else "unknown"
        was_full = "full" in prev_state

        await db.bgp_alert_state.update_one(
            {"key": nb_key},
            {"$set": {
                "key": nb_key,
                "device_id": device_id,
                "device_name": device_name,
                "type": "ospf",
                "neighbor_address": nb_addr,
                "interface": nb_iface,
                "state": current_state,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }},
            upsert=True
        )

        notify_ospf = settings.get("notify_ospf", True)
        if not notify_ospf:
            continue

        # OSPF DOWN: sebelumnya Full → sekarang bukan
        if was_full and not is_full:
            msg = (
                f"🔴 *ALERT: OSPF Neighbor Down*\n"
                f"━━━━━━━━━━━━━━\n"
                f"📡 Device: *{device_name}*\n"
                f"🔗 Neighbor: *{nb_addr}* via {nb_iface}\n"
                f"📊 Status: *{current_state}* (was: Full)\n"
                f"⏰ {datetime.now(timezone.utc).strftime('%H:%M %Z')}\n"
                f"━━━━━━━━━━━━━━\n"
                f"NOC-Sentinel Monitoring"
            )
            await send_to_all_recipients(msg, settings)
            await db.routing_alert_history.insert_one({
                "type": "ospf_down",
                "device_id": device_id,
                "device_name": device_name,
                "neighbor_address": nb_addr,
                "interface": nb_iface,
                "prev_state": prev_state,
                "current_state": current_state,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })

        # OSPF RECOVER: sebelumnya bukan Full → sekarang Full
        elif not was_full and prev_state != "unknown" and is_full:
            msg = (
                f"🟢 *RECOVER: OSPF Neighbor Full*\n"
                f"━━━━━━━━━━━━━━\n"
                f"📡 Device: *{device_name}*\n"
                f"🔗 Neighbor: *{nb_addr}* via {nb_iface}\n"
                f"📊 Status: *Full* ✓\n"
                f"⏰ {datetime.now(timezone.utc).strftime('%H:%M %Z')}\n"
                f"━━━━━━━━━━━━━━\n"
                f"NOC-Sentinel Monitoring"
            )
            await send_to_all_recipients(msg, settings)
            await db.routing_alert_history.insert_one({
                "type": "ospf_recover",
                "device_id": device_id,
                "device_name": device_name,
                "neighbor_address": nb_addr,
                "interface": nb_iface,
                "prev_state": prev_state,
                "current_state": current_state,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })


async def bgp_ospf_alert_loop():
    """
    Background task: cek BGP peers + OSPF neighbors semua device setiap 5 menit.
    Kirim notif jika ada perubahan state (down/recover).
    """
    logger.info("BGP/OSPF alert monitor started")

    while True:
        try:
            settings = await _get_settings()

            # Hanya jalan jika notifikasi enabled
            if not settings.get("enabled", False):
                await asyncio.sleep(BGP_CHECK_INTERVAL)
                continue

            db = get_db()
            # Ambil semua device online yang mungkin pakai BGP/OSPF
            devices = await db.devices.find(
                {"status": "online"},
                {"_id": 0}
            ).to_list(1000)

            for device in devices:
                # Cek BGP
                try:
                    await _check_bgp_for_device(device, settings, db)
                except Exception as e:
                    logger.debug(f"BGP check error for {device.get('name')}: {e}")

                # Cek OSPF
                try:
                    await _check_ospf_for_device(device, settings, db)
                except Exception as e:
                    logger.debug(f"OSPF check error for {device.get('name')}: {e}")

                await asyncio.sleep(0.5)  # jeda antar device agar tidak overload

            await asyncio.sleep(BGP_CHECK_INTERVAL)

        except asyncio.CancelledError:
            logger.info("BGP/OSPF alert monitor cancelled")
            break
        except Exception as e:
            logger.error(f"BGP/OSPF alert loop error: {e}")
            await asyncio.sleep(60)
