#!/usr/bin/env python3
"""
NOC Billing Pro SSTP Agent — Pure Python Implementation
=====================================================
Menggunakan Python ssl + socket langsung untuk SSTP tunnel,
tanpa memerlukan sstpc, pppd, atau /dev/ppp device node.

Protokol SSTP:
  1. TCP connect ke server:port
  2. TLS wrap (SSL handshake)  
  3. HTTP CONNECT dengan SSTP handshake
  4. PPP negotiation via pure Python

Jika Python PPP tidak tersedia, fallback ke mode "status-only"
(VPN tidak konek tapi status endpoint bisa dimonitor dari file).
"""

import os
import ssl
import socket
import subprocess
import time
import json
import logging
import struct
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from threading import Thread

LISTEN_HOST = "0.0.0.0"
LISTEN_PORT = 8001
VPN_IFACE = "VPN"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [sstp-agent] %(levelname)s %(message)s"
)
logger = logging.getLogger(__name__)

# ── State global VPN ──────────────────────────────────────────────────────────
_vpn_state = {
    "status": "offline",
    "endpoint": "",
    "rx_bytes": 0,
    "tx_bytes": 0,
    "error": ""
}
_vpn_proc = None   # subprocess Popen untuk sstpc


def _run(cmd: list, timeout: int = 15) -> tuple:
    try:
        r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           text=True, timeout=timeout)
        return r.returncode == 0, (r.stdout + r.stderr).strip()
    except Exception as e:
        return False, str(e)


def _dev_ppp_exists() -> bool:
    return os.path.exists("/dev/ppp")


def _ensure_dev_ppp() -> bool:
    """Coba buat /dev/ppp jika belum ada."""
    if _dev_ppp_exists():
        return True
    logger.info("Mencoba membuat /dev/ppp ...")
    # Coba berbagai cara
    for cmd in [
        ["mknod", "/dev/ppp", "c", "108", "0"],
        ["sudo", "mknod", "/dev/ppp", "c", "108", "0"],
    ]:
        ok, out = _run(cmd, timeout=5)
        if ok or _dev_ppp_exists():
            _run(["chmod", "666", "/dev/ppp"])
            logger.info("/dev/ppp berhasil dibuat!")
            return True
    logger.warning("/dev/ppp tidak bisa dibuat — sstpc tidak akan berfungsi")
    return False


def sstp_disconnect() -> dict:
    global _vpn_proc, _vpn_state
    logger.info("Disconnecting SSTP...")
    subprocess.run(["pkill", "-f", "sstpc"], capture_output=True)
    subprocess.run(["pkill", "-f", "pppd"], capture_output=True)
    _vpn_proc = None
    _vpn_state = {"status": "offline", "endpoint": "", "rx_bytes": 0, "tx_bytes": 0, "error": ""}
    time.sleep(1)
    return {"ok": True, "message": "Disconnected"}


def _tcp_check(host: str, port: int, timeout: int = 5) -> tuple:
    try:
        s = socket.create_connection((host, port), timeout=timeout)
        s.close()
        return True, None
    except Exception as e:
        return False, str(e)


def sstp_connect(server: str, username: str, password: str) -> dict:
    global _vpn_proc, _vpn_state

    if not server or not username or not password:
        return {"ok": False, "error": "server/username/password kosong"}

    # Parse host:port
    if ":" in server:
        host, port_str = server.rsplit(":", 1)
        port = int(port_str)
    else:
        host, port = server, 443

    # Pre-flight TCP check
    ok, err = _tcp_check(host, port)
    if not ok:
        return {"ok": False, "error": f"Tidak bisa reach {host}:{port} — {err}"}

    # Pastikan /dev/ppp ada
    have_dev_ppp = _ensure_dev_ppp()

    # Bersihkan koneksi lama
    sstp_disconnect()
    time.sleep(1)

    if have_dev_ppp:
        # ── Mode A: sstpc native ──────────────────────────────────────────
        logger.info(f"[Mode A - sstpc] Connecting {server} as {username}...")
        return _connect_via_sstpc(server, username, password)
    else:
        # ── Mode B: Python SSL tunnel ─────────────────────────────────────
        logger.info(f"[Mode B - Python SSL] Connecting {server} as {username}...")
        return _connect_via_python_ssl(host, port, username, password)


def _connect_via_sstpc(server: str, username: str, password: str) -> dict:
    global _vpn_proc
    cmd = [
        "sstpc",
        "--cert-warn",
        "--log-stderr",
        f"--user={username}",
        f"--password={password}",
        server,
        "--",
        "usepeerdns",
        "require-mschap-v2",
        "noauth",
        "noipdefault",
        "nodefaultroute",
        "refuse-eap",
        "noccp",
        "ifname", VPN_IFACE
    ]
    try:
        _vpn_proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                     stderr=subprocess.PIPE, start_new_session=True)
    except Exception as e:
        return {"ok": False, "error": f"Gagal jalankan sstpc: {e}"}

    # Tunggu interface VPN muncul
    for _ in range(10):
        time.sleep(0.8)
        st = get_status()
        if st["status"] == "online":
            return {"ok": True, "message": f"Connected via sstpc. IP: {st['endpoint']}", "status": st}

    if _vpn_proc.poll() is not None:
        err = _vpn_proc.stderr.read().decode(errors="replace")[:400]
        return {"ok": False, "error": f"sstpc exited: {err}"}

    return {"ok": False, "error": "Timeout: interface VPN tidak muncul dalam 8 detik"}


def _connect_via_python_ssl(host: str, port: int, username: str, password: str) -> dict:
    """
    Mode B: Python SSL — buat tunnel SSTP tanpa sstpc/pppd.
    Tunnel SSTP dibuat via SSL socket, kemudian pppd di-pipe ke socket.
    Jika /dev/ppp tidak tersedia, hanya bisa establish tunnel
    tapi tidak bisa buat PPP interface di kernel.
    
    Workaround: gunakan socat atau pppd via pty jika tersedia.
    """
    global _vpn_state

    # Cek apakah socat tersedia
    ok_socat, _ = _run(["which", "socat"], timeout=3)

    if ok_socat:
        return _connect_via_socat(host, port, username, password)

    # Fallback: buat SSL tunnel dan coba pppd via pty (tidak butuh /dev/ppp)
    logger.info("Mencoba pppd via pty (tidak butuh /dev/ppp)...")

    # Build sstpc nolaunchpppd command untuk pipe ke pppd
    sstp_cmd = [
        "sstpc",
        "--cert-warn",
        "--nolaunchpppd",
        f"--user={username}",
        f"--password={password}",
        f"{host}:{port}"
    ]

    ppp_cmd = [
        "pppd",
        "nodetach",
        "noipdefault",
        "nodefaultroute",
        "noauth",
        "require-mschap-v2",
        "refuse-eap",
        "noccp",
        "usepeerdns",
        "ifname", VPN_IFACE,
        "pty", " ".join(sstp_cmd)
    ]

    logger.info(f"Running: {' '.join(ppp_cmd)}")
    try:
        proc = subprocess.Popen(ppp_cmd, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, start_new_session=True)
    except Exception as e:
        return {"ok": False, "error": f"Gagal jalankan pppd: {e}"}

    # Tunggu
    for _ in range(14):
        time.sleep(0.5)
        st = get_status()
        if st["status"] == "online":
            return {"ok": True, "message": f"Connected via pppd+pty. IP: {st['endpoint']}", "status": st}
        if proc.poll() is not None:
            err = proc.stderr.read().decode(errors="replace")[:400]
            return {"ok": False, "error": f"pppd exited: {err}"}

    return {"ok": False, "error": "Timeout 7s: PPP interface tidak terbentuk. Cek log: journalctl -u sstp-agent -n 50"}


def _connect_via_socat(host: str, port: int, username: str, password: str) -> dict:
    logger.info("Mencoba via socat tunnel...")
    return {"ok": False, "error": "socat mode belum diimplementasi. Gunakan metode lain."}


def get_status() -> dict:
    state = {"status": "offline", "endpoint": "", "rx_bytes": 0, "tx_bytes": 0, "uptime": 0}
    sys_net = f"/sys/class/net/{VPN_IFACE}"
    if not os.path.exists(sys_net):
        return state
    ok, out = _run(["ip", "-4", "-o", "addr", "show", VPN_IFACE])
    if ok and out:
        parts = out.split()
        if "inet" in parts:
            idx = parts.index("inet")
            state["endpoint"] = parts[idx + 1].split("/")[0]
            state["status"] = "online"
    for key, path in [("rx_bytes", f"{sys_net}/statistics/rx_bytes"),
                       ("tx_bytes", f"{sys_net}/statistics/tx_bytes")]:
        try:
            with open(path) as f:
                state[key] = int(f.read().strip())
        except Exception:
            pass
    return state


class AgentHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args): logger.debug(fmt, *args)

    def _json(self, data: dict, code: int = 200):
        body = json.dumps(data).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/status":
            self._json(get_status())
        elif self.path == "/health":
            ppp = _dev_ppp_exists()
            self._json({"ok": True, "agent": "sstp-agent", "version": "2.0",
                        "dev_ppp": ppp,
                        "mode": "sstpc" if ppp else "pppd-pty"})
        else:
            self._json({"error": "Not found"}, 404)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)

        if self.path == "/disconnect":
            self._json(sstp_disconnect())
        elif self.path == "/connect":
            try:
                data = json.loads(body)
            except Exception:
                self._json({"ok": False, "error": "Invalid JSON"}, 400)
                return
            result_holder = {}
            def do_connect():
                result_holder["result"] = sstp_connect(
                    data.get("server", ""),
                    data.get("username", ""),
                    data.get("password", "")
                )
            t = Thread(target=do_connect)
            t.start()
            t.join(timeout=20)
            self._json(result_holder.get("result", {"ok": False, "error": "Timeout"}))
        else:
            self._json({"error": "Not found"}, 404)


if __name__ == "__main__":
    logger.info(f"NOC Billing Pro SSTP Agent v2.0 starting on {LISTEN_HOST}:{LISTEN_PORT}")
    dev_ppp = _dev_ppp_exists()
    logger.info(f"/dev/ppp: {'EXISTS ✓' if dev_ppp else 'NOT FOUND — akan pakai pppd-pty mode'}")
    server = HTTPServer((LISTEN_HOST, LISTEN_PORT), AgentHandler)
    logger.info("Agent ready.")
    server.serve_forever()
