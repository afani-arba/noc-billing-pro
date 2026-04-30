"""
Interface Health Monitor Service — NOC Billing Pro
====================================================
Background service yang memantau kesehatan interface fisik
di semua MikroTik router terdaftar setiap 60 detik.

Monitoring:
  - CRC errors, FCS errors, RX/TX drops
  - Interface UP/DOWN state changes
  - SFP module: temperature, TX/RX power
  - Link speed dan duplex mode

Data disimpan ke MongoDB collection: system_settings (key: iface_health_{device_id})
Alert dipicu jika:
  - CRC error rate > 100/menit
  - Interface yang sebelumnya UP menjadi DOWN
  - SFP RX power < -25 dBm
"""
import asyncio
import logging
from datetime import datetime, timezone
from core.db import get_db
from mikrotik_api import get_api_client

logger = logging.getLogger("interface_health_monitor")

POLL_INTERVAL = 60  # detik

# Cache counter sebelumnya untuk menghitung delta (error rate per menit)
_prev_counters: dict = {}  # key: f"{device_id}:{iface_name}" → {rx_error, tx_error, ...}


async def _poll_device_interfaces(dev: dict) -> dict:
    """
    Poll interface health dari satu device MikroTik.
    Return dict siap simpan ke MongoDB.
    """
    device_id = dev.get("id", "")
    device_name = dev.get("name", "Unknown")

    try:
        mt = get_api_client(dev)
    except Exception as e:
        return {
            "device_id": device_id,
            "device_name": device_name,
            "interfaces": [],
            "sfp": [],
            "alerts": [],
            "error": str(e),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

    interfaces = []
    sfp_info = []
    alerts = []

    try:
        # 1. Ambil semua interface + statistik
        ifaces = await mt._async_req("GET", "interface")
        if not isinstance(ifaces, list):
            ifaces = []

        for iface in ifaces:
            name = iface.get("name", "")
            itype = str(iface.get("type", "")).lower()
            if not name:
                continue

            # Skip virtual interfaces
            skip_types = {"bridge", "vlan", "pppoe-out", "pppoe-in", "l2tp", "pptp",
                         "ovpn-client", "ovpn-server", "sstp-client", "sstp-server",
                         "gre", "eoip", "loopback", "veth"}
            if itype in skip_types:
                continue

            running = iface.get("running", "false") == "true"
            disabled = iface.get("disabled", "false") == "true"

            rx_error = int(iface.get("rx-error", 0) or 0)
            tx_error = int(iface.get("tx-error", 0) or 0)
            rx_drop = int(iface.get("rx-drop", 0) or 0)
            tx_drop = int(iface.get("tx-drop", 0) or 0)
            fp_rx_error = int(iface.get("fp-rx-byte", 0) or 0)  # some ROS versions
            rx_fcs = int(iface.get("rx-fcs-error", 0) or 0)

            # Hitung error rate (delta per menit)
            cache_key = f"{device_id}:{name}"
            prev = _prev_counters.get(cache_key, {})
            delta_rx_error = max(0, rx_error - prev.get("rx_error", rx_error))
            delta_tx_error = max(0, tx_error - prev.get("tx_error", tx_error))
            delta_rx_fcs = max(0, rx_fcs - prev.get("rx_fcs", rx_fcs))
            delta_rx_drop = max(0, rx_drop - prev.get("rx_drop", rx_drop))
            delta_tx_drop = max(0, tx_drop - prev.get("tx_drop", tx_drop))

            # Update cache
            _prev_counters[cache_key] = {
                "rx_error": rx_error,
                "tx_error": tx_error,
                "rx_fcs": rx_fcs,
                "rx_drop": rx_drop,
                "tx_drop": tx_drop,
                "running": running,
            }

            # Speed info
            link_speed = iface.get("actual-mtu", "")
            rate = iface.get("rate", "")

            # Status
            status = "down"
            if disabled:
                status = "disabled"
            elif running:
                status = "up"

            iface_data = {
                "name": name,
                "type": itype,
                "status": status,
                "speed": rate,
                "rx_error_total": rx_error,
                "tx_error_total": tx_error,
                "rx_fcs_total": rx_fcs,
                "rx_drop_total": rx_drop,
                "tx_drop_total": tx_drop,
                "error_rate_per_min": delta_rx_error + delta_tx_error + delta_rx_fcs,
                "drop_rate_per_min": delta_rx_drop + delta_tx_drop,
            }
            interfaces.append(iface_data)

            # Alert: CRC/FCS errors meningkat
            total_delta_errors = delta_rx_error + delta_tx_error + delta_rx_fcs
            if total_delta_errors > 100:
                alerts.append({
                    "type": "crc_error",
                    "severity": "critical",
                    "interface": name,
                    "message": f"CRC/FCS errors meningkat {total_delta_errors}/menit pada {name}. Kemungkinan kabel rusak atau konektor longgar.",
                    "value": total_delta_errors,
                })
            elif total_delta_errors > 10:
                alerts.append({
                    "type": "crc_error",
                    "severity": "warning",
                    "interface": name,
                    "message": f"CRC errors terdeteksi {total_delta_errors}/menit pada {name}.",
                    "value": total_delta_errors,
                })

            # Alert: Interface DOWN yang sebelumnya UP
            prev_running = prev.get("running", None)
            if prev_running is True and not running and not disabled:
                alerts.append({
                    "type": "link_down",
                    "severity": "critical",
                    "interface": name,
                    "message": f"Interface {name} DOWN! (sebelumnya UP)",
                    "value": 0,
                })

        # 2. SFP monitoring (jika ada)
        try:
            # Cari interface ethernet yang bertipe sfp
            eth_list = await mt._async_req("GET", "interface/ethernet")
            if isinstance(eth_list, list):
                for eth in eth_list:
                    eth_name = eth.get("name", "")
                    sfp_present = eth.get("sfp-rate", "") or eth.get("sfp-type", "")
                    if not sfp_present and "sfp" not in eth_name.lower():
                        continue

                    # Monitor SFP
                    try:
                        mon = await mt._async_req("POST", "interface/ethernet/monitor", {
                            ".id": eth.get(".id", eth_name),
                            "once": True,
                        })
                        if isinstance(mon, list) and mon:
                            mon = mon[0]
                        if isinstance(mon, dict):
                            sfp_temp = mon.get("sfp-temperature", "")
                            sfp_tx = mon.get("sfp-tx-power", "")
                            sfp_rx = mon.get("sfp-rx-power", "")
                            link_speed = mon.get("rate", mon.get("speed", ""))

                            sfp_data = {
                                "interface": eth_name,
                                "temperature": sfp_temp,
                                "tx_power": sfp_tx,
                                "rx_power": sfp_rx,
                                "rate": link_speed,
                                "status": mon.get("status", ""),
                            }
                            sfp_info.append(sfp_data)

                            # Alert: SFP RX power low
                            try:
                                rx_val = float(str(sfp_rx).replace("dBm", "").strip())
                                if rx_val < -25:
                                    alerts.append({
                                        "type": "sfp_low_power",
                                        "severity": "warning",
                                        "interface": eth_name,
                                        "message": f"SFP RX power rendah: {sfp_rx} pada {eth_name}",
                                        "value": rx_val,
                                    })
                            except (ValueError, TypeError):
                                pass

                    except Exception:
                        pass  # Monitor mungkin tidak support di device ini
        except Exception:
            pass  # Ethernet list tidak tersedia

    except Exception as e:
        logger.warning(f"Interface health poll error for {device_name}: {e}")
        alerts.append({
            "type": "poll_error",
            "severity": "warning",
            "interface": "",
            "message": f"Gagal polling interface: {e}",
            "value": 0,
        })

    return {
        "device_id": device_id,
        "device_name": device_name,
        "interfaces": interfaces,
        "sfp": sfp_info,
        "alerts": alerts,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


async def _poll_all_devices():
    """Poll interface health dari semua device."""
    db = get_db()
    devices = await db.devices.find(
        {"is_disabled": {"$ne": True}},
        {"_id": 0, "id": 1, "name": 1, "ip_address": 1, "api_username": 1,
         "api_password": 1, "api_mode": 1, "use_https": 1, "api_port": 1,
         "api_ssl": 1, "api_plaintext_login": 1}
    ).to_list(50)

    for dev in devices:
        device_id = dev.get("id", "")
        if not device_id:
            continue

        try:
            result = await _poll_device_interfaces(dev)

            # Simpan ke MongoDB
            doc = result.copy()
            doc["_id"] = f"iface_health_{device_id}"
            await db.system_settings.replace_one(
                {"_id": f"iface_health_{device_id}"},
                doc,
                upsert=True
            )

            # Log alerts
            for alert in result.get("alerts", []):
                if alert["severity"] == "critical":
                    logger.warning(f"[IFACE] {result['device_name']}: {alert['message']}")

        except Exception as e:
            logger.error(f"Interface health error for {device_id}: {e}")

        await asyncio.sleep(1)  # Jeda antar device


async def interface_health_monitor_loop():
    """Background loop untuk interface health monitoring."""
    logger.info("Interface Health Monitor service started.")
    await asyncio.sleep(15)  # Delay startup

    while True:
        try:
            await _poll_all_devices()
        except Exception as e:
            logger.error(f"Interface health monitor error: {e}")

        await asyncio.sleep(POLL_INTERVAL)
