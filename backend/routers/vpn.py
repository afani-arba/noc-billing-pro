"""
NOC Billing Pro — VPN Router
Proxy API frontend ke L2TP Agent (port 8011) dan SSTP Agent (port 8001)
yang berjalan langsung di HOST (bukan container).

Routes:
  GET  /api/l2tp/status       → http://172.17.0.1:8011/status
  GET  /api/l2tp/config       → DB config
  PUT  /api/l2tp/config       → Simpan config
  POST /api/l2tp/connect      → http://172.17.0.1:8011/connect
  POST /api/l2tp/disconnect   → http://172.17.0.1:8011/disconnect
  GET  /api/l2tp/health       → http://172.17.0.1:8011/health

  GET  /api/sstp/status       → http://172.17.0.1:8001/status
  GET  /api/sstp/config       → DB config
  PUT  /api/sstp/config       → Simpan config
  POST /api/sstp/connect      → http://172.17.0.1:8001/connect
  POST /api/sstp/disconnect   → http://172.17.0.1:8001/disconnect
  GET  /api/sstp/health       → http://172.17.0.1:8001/health
"""

import os
import logging
import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from core.db import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="", tags=["VPN"])

# Agent URLs — menggunakan Docker bridge gateway ke host
# 172.17.0.1 = docker0 gateway (selalu ada sebagai IP host dari dalam container)
# Port 8011 = L2TP Agent (l2tp_agent.py), Port 8001 = SSTP Agent (sstp_agent.py)
_DOCKER_GATEWAY = os.environ.get("VPN_AGENT_HOST", "172.18.0.1")
L2TP_AGENT_URL  = os.environ.get("L2TP_AGENT_URL",  f"http://{_DOCKER_GATEWAY}:8011")
SSTP_AGENT_URL  = os.environ.get("SSTP_AGENT_URL",  f"http://{_DOCKER_GATEWAY}:8001")

TIMEOUT = httpx.Timeout(25.0)


# ── Pydantic models ────────────────────────────────────────────────────────────

class VpnConfig(BaseModel):
    server:     str
    username:   str
    password:   str
    auto_routes: Optional[str] = ""
    enabled:    Optional[bool] = False


class ConnectRequest(BaseModel):
    server:     str
    username:   str
    password:   str
    auto_routes: Optional[str] = ""


# ── Helper ─────────────────────────────────────────────────────────────────────

async def _proxy_get(url: str) -> dict:
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            r = await client.get(url)
            return r.json()
    except httpx.ConnectError:
        return {"ok": False, "error": "Agent tidak bisa dihubungi. Pastikan l2tp-agent/sstp-agent berjalan di host."}
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def _proxy_post(url: str, data: dict) -> dict:
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            r = await client.post(url, json=data)
            return r.json()
    except httpx.ConnectError:
        return {"ok": False, "error": "Agent tidak bisa dihubungi. Pastikan l2tp-agent/sstp-agent berjalan di host."}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ─────────────────────────────────────────────────────────────────────────────
# L2TP ROUTES
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/l2tp/health")
@router.get("/l2tp/agent-health")  # alias
async def l2tp_health():
    return await _proxy_get(f"{L2TP_AGENT_URL}/health")


@router.get("/l2tp/status")
async def l2tp_status():
    """Ambil status koneksi L2TP dari agent.
    Jika belum dikonfigurasi (fresh install), return disabled.
    """
    db = get_db()
    cfg = await db.system_settings.find_one({"_id": "vpn_l2tp_config"})
    if not cfg or not cfg.get("enabled"):
        # Fresh install / belum dikonfigurasi → tampilkan status disabled (bukan error)
        return {"status": "disabled", "endpoint": "", "rx_bytes": 0, "tx_bytes": 0}
    return await _proxy_get(f"{L2TP_AGENT_URL}/status")


@router.get("/l2tp/config")
async def l2tp_get_config():
    """Ambil konfigurasi L2TP dari database."""
    db = get_db()
    cfg = await db.system_settings.find_one({"_id": "vpn_l2tp_config"})
    if not cfg:
        return {"server": "", "username": "", "password": "", "auto_routes": "", "enabled": False}
    cfg.pop("_id", None)
    cfg.pop("password", None)   # Jangan kirim password ke frontend
    return cfg


@router.put("/l2tp/config")
async def l2tp_save_config(body: VpnConfig):
    """Simpan konfigurasi L2TP ke database dan connect/disconnect."""
    db = get_db()
    data = body.dict()
    data["_id"] = "vpn_l2tp_config"
    await db.system_settings.replace_one({"_id": "vpn_l2tp_config"}, data, upsert=True)
    
    if body.enabled:
        # Trigger connect di agent
        resp = await _proxy_post(
            f"{L2TP_AGENT_URL}/connect",
            {"server": body.server, "username": body.username,
             "password": body.password, "auto_routes": body.auto_routes}
        )
        if not resp.get("ok"):
            raise HTTPException(status_code=500, detail=resp.get("error", "Gagal memulai l2tp-agent"))
    else:
        # Trigger disconnect di agent
        await _proxy_post(f"{L2TP_AGENT_URL}/disconnect", {})

    return {"ok": True, "message": "Konfigurasi L2TP disimpan"}


@router.post("/l2tp/connect")
async def l2tp_connect(body: ConnectRequest):
    """Hubungkan L2TP VPN via agent di host."""
    return await _proxy_post(
        f"{L2TP_AGENT_URL}/connect",
        {"server": body.server, "username": body.username,
         "password": body.password, "auto_routes": body.auto_routes}
    )


@router.post("/l2tp/disconnect")
async def l2tp_disconnect():
    """Putuskan koneksi L2TP."""
    return await _proxy_post(f"{L2TP_AGENT_URL}/disconnect", {})


# ─────────────────────────────────────────────────────────────────────────────
# SSTP ROUTES
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/sstp/health")
async def sstp_health():
    return await _proxy_get(f"{SSTP_AGENT_URL}/health")


@router.get("/sstp/status")
async def sstp_status():
    db = get_db()
    cfg = await db.system_settings.find_one({"_id": "vpn_sstp_config"})
    if not cfg or not cfg.get("enabled"):
        return {"status": "disabled"}
    return await _proxy_get(f"{SSTP_AGENT_URL}/status")


@router.get("/sstp/config")
async def sstp_get_config():
    """Ambil konfigurasi SSTP dari database."""
    db = get_db()
    cfg = await db.system_settings.find_one({"_id": "vpn_sstp_config"})
    if not cfg:
        return {"server": "", "username": "", "password": "", "enabled": False}
    cfg.pop("_id", None)
    cfg.pop("password", None)
    return cfg


@router.put("/sstp/config")
async def sstp_save_config(body: VpnConfig):
    """Simpan konfigurasi SSTP ke database dan connect/disconnect."""
    db = get_db()
    data = body.dict()
    data["_id"] = "vpn_sstp_config"
    await db.system_settings.replace_one({"_id": "vpn_sstp_config"}, data, upsert=True)
    
    if body.enabled:
        # Trigger connect di agent
        resp = await _proxy_post(
            f"{SSTP_AGENT_URL}/connect",
            {"server": body.server, "username": body.username, "password": body.password}
        )
        if not resp.get("ok"):
            raise HTTPException(status_code=500, detail=resp.get("error", "Gagal memulai sstp-agent"))
    else:
        # Trigger disconnect di agent
        await _proxy_post(f"{SSTP_AGENT_URL}/disconnect", {})

    return {"ok": True, "message": "Konfigurasi SSTP disimpan"}


@router.post("/sstp/connect")
async def sstp_connect(body: ConnectRequest):
    """Hubungkan SSTP VPN via agent di host."""
    return await _proxy_post(
        f"{SSTP_AGENT_URL}/connect",
        {"server": body.server, "username": body.username, "password": body.password}
    )


@router.post("/sstp/disconnect")
async def sstp_disconnect():
    """Putuskan koneksi SSTP."""
    return await _proxy_post(f"{SSTP_AGENT_URL}/disconnect", {})


# ─────────────────────────────────────────────────────────────────────────────
# CLOUDFLARE TUNNEL ROUTES
# Menggunakan shared volume /update-data untuk trigger noc-updater container
# ─────────────────────────────────────────────────────────────────────────────

import asyncio
import json
from pathlib import Path

UPDATE_DATA = Path("/update-data")          # shared volume dengan noc-updater


class CloudflareConfig(BaseModel):
    token: str
    enabled: bool = True


@router.get("/cloudflare/status")
async def cloudflare_status():
    """Cek status Cloudflare Tunnel — baca dari trigger-result file."""
    db = get_db()
    cfg = await db.system_settings.find_one({"_id": "cloudflare_tunnel"})
    enabled = bool(cfg and cfg.get("enabled"))

    # Baca status dari file yang ditulis noc-updater
    status_file = UPDATE_DATA / ".cf-status"
    container_status = "unknown"
    try:
        if status_file.exists():
            data = json.loads(status_file.read_text())
            container_status = data.get("status", "unknown")
    except Exception:
        pass

    # Jika token masih ada tapi belum di-start, cek apakah container berjalan
    return {
        "enabled": enabled,
        "status": container_status,
        "has_token": bool(cfg and cfg.get("token")),
    }


@router.get("/cloudflare/config")
async def cloudflare_get_config():
    """Ambil konfigurasi Cloudflare Tunnel (token tidak dikembalikan plaintext)."""
    db = get_db()
    cfg = await db.system_settings.find_one({"_id": "cloudflare_tunnel"})
    if not cfg:
        return {"token": "", "enabled": False, "token_set": False}
    return {
        "token": "••••••••" if cfg.get("token") else "",
        "token_set": bool(cfg.get("token")),
        "enabled": cfg.get("enabled", False),
    }


@router.put("/cloudflare/config")
async def cloudflare_save_config(body: CloudflareConfig):
    """Simpan token Cloudflare Tunnel dan jalankan/hentikan tunnel."""
    db = get_db()

    # Jika token dikirim sebagai masked, ambil yang tersimpan
    real_token = body.token
    if body.token.startswith("•"):
        existing = await db.system_settings.find_one({"_id": "cloudflare_tunnel"})
        real_token = existing.get("token", "") if existing else ""

    if not real_token and body.enabled:
        raise HTTPException(400, "Token Cloudflare Tunnel wajib diisi")

    data = {"_id": "cloudflare_tunnel", "token": real_token, "enabled": body.enabled}
    await db.system_settings.replace_one({"_id": "cloudflare_tunnel"}, data, upsert=True)

    try:
        if body.enabled and real_token:
            # Tulis token ke file lalu buat trigger start
            (UPDATE_DATA / ".cf-token").write_text(real_token)
            (UPDATE_DATA / ".cf-stop-trigger").unlink(missing_ok=True)
            (UPDATE_DATA / ".cf-start-trigger").write_text("1")
            logger.info("[Cloudflare] Trigger start dikirim ke noc-updater")
        else:
            # Trigger stop
            (UPDATE_DATA / ".cf-token").unlink(missing_ok=True)
            (UPDATE_DATA / ".cf-start-trigger").unlink(missing_ok=True)
            (UPDATE_DATA / ".cf-stop-trigger").write_text("1")
            logger.info("[Cloudflare] Trigger stop dikirim ke noc-updater")
    except Exception as e:
        logger.warning(f"[Cloudflare] Gagal tulis trigger: {e}")
        raise HTTPException(500, f"Gagal mengirim perintah ke updater: {e}")

    return {"ok": True, "message": "Konfigurasi Cloudflare Tunnel disimpan" + (". Tunnel sedang diaktifkan..." if body.enabled else ". Tunnel dihentikan.")}


@router.post("/cloudflare/restart")
async def cloudflare_restart():
    """Restart Cloudflare Tunnel — stop lalu start kembali."""
    db = get_db()
    cfg = await db.system_settings.find_one({"_id": "cloudflare_tunnel"})
    if not cfg or not cfg.get("token"):
        raise HTTPException(400, "Token belum dikonfigurasi")

    try:
        (UPDATE_DATA / ".cf-stop-trigger").write_text("1")
        await asyncio.sleep(6)  # tunggu updater stop dulu
        (UPDATE_DATA / ".cf-token").write_text(cfg["token"])
        (UPDATE_DATA / ".cf-start-trigger").write_text("1")
    except Exception as e:
        raise HTTPException(500, f"Gagal restart: {e}")

    return {"ok": True, "message": "Cloudflare Tunnel sedang di-restart..."}

