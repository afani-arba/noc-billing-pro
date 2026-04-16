#!/usr/bin/env python3
"""
NOC Billing Pro L2TP Agent — Pure Python + xl2tpd Wrapper
=====================================================
Mengelola xl2tpd di host secara native untuk L2TP VPN (Plain).
Tanpa IPsec sesuai permintaan user.

Endpoints:
  GET  /status      - Status link L2TP (IP, bytes, uptime)
  GET  /health      - Cek kesehatan agent
  POST /connect     - Setup config & dial L2TP
  POST /disconnect  - Putus link L2TP
"""

import os
import subprocess
import time
import json
import logging
from http.server import HTTPServer, BaseHTTPRequestHandler
from threading import Thread

LISTEN_HOST = "0.0.0.0"
LISTEN_PORT = 8002
VPN_IFACE = "VPN_L2TP"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [l2tp-agent] %(levelname)s %(message)s"
)
logger = logging.getLogger(__name__)

def _run(cmd: list, timeout: int = 15) -> tuple:
    try:
        r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           text=True, timeout=timeout)
        return r.returncode == 0, (r.stdout + r.stderr).strip()
    except Exception as e:
        return False, str(e)

def get_status() -> dict:
    """Membaca status interface dari /sys dan ip command."""
    state = {"status": "offline", "endpoint": "", "rx_bytes": 0, "tx_bytes": 0, "uptime": 0}
    
    # Cari interface ppp yang memiliki name VPN_L2TP atau yang aktif
    # xl2tpd biasanya menamai interface pppX. Kita akan memaksa penamaan via ppp-options jika didukung, 
    # atau mencari interface ppp yang up.
    
    # Shortcut: Cek semua interface ppp*
    ok, out = _run(["ip", "-4", "-o", "addr", "show"])
    if ok and out:
        for line in out.splitlines():
            if "ppp" in line:
                parts = line.split()
                iface = parts[1]
                # Jika kita menemukan interface ppp, kita anggap itu L2TP kita (asumsi cuma 1 vpn)
                if "inet" in parts:
                    idx = parts.index("inet")
                    state["endpoint"] = parts[idx + 1].split("/")[0]
                    state["status"] = "online"
                    state["interface"] = iface
                    
                    # Ambil statistik
                    stats_path = f"/sys/class/net/{iface}/statistics"
                    try:
                        with open(f"{stats_path}/rx_bytes") as f: state["rx_bytes"] = int(f.read().strip())
                        with open(f"{stats_path}/tx_bytes") as f: state["tx_bytes"] = int(f.read().strip())
                    except: pass
                    break
    return state

def l2tp_connect(server: str, username: str, password: str, auto_routes: str = "") -> dict:
    """Setup xl2tpd dan ppp options, lalu dial."""
    if not server or not username or not password:
        return {"ok": False, "error": "server/username/password kosong"}

    # 1. Tulis config xl2tpd
    xl2tpd_conf = f"""
[lac myvpn]
lns = {server}
ppp debug = yes
pppoptfile = /etc/ppp/options.l2tp.client
length bit = yes
"""
    try:
        with open("/etc/xl2tpd/xl2tpd.conf", "w") as f:
            f.write(xl2tpd_conf)
    except Exception as e:
        return {"ok": False, "error": f"Gagal tulis xl2tpd.conf: {e}"}

    # 2. Tulis ppp options
    # unit 10 agar interface namanya ppp10 (bisa kita monitor lebih mudah)
    ppp_options = f"""
noauth
proxyarp
name {username}
password {password}
noipdefault
nodefaultroute
usepeerdns
# unit 10
"""
    try:
        os.makedirs("/etc/ppp", exist_ok=True)
        with open("/etc/ppp/options.l2tp.client", "w") as f:
            f.write(ppp_options)
    except Exception as e:
        return {"ok": False, "error": f"Gagal tulis options.l2tp.client: {e}"}

    # 3. Restart xl2tpd service
    logger.info("Restarting xl2tpd...")
    _run(["systemctl", "restart", "xl2tpd"])
    time.sleep(1)

    # 4. Dial via l2tp-control
    logger.info(f"Dialing {server}...")
    control_path = "/var/run/xl2tpd/l2tp-control"
    if not os.path.exists(control_path):
        # Coba start service jika belum ada
        _run(["systemctl", "start", "xl2tpd"])
        time.sleep(1)
        
    try:
        with open(control_path, "w") as f:
            f.write("c myvpn")
    except Exception as e:
        return {"ok": False, "error": f"Gagal dial via l2tp-control: {e}"}

    # 5. Wait for online
    for _ in range(15):
        time.sleep(1)
        st = get_status()
        if st["status"] == "online":
            iface = st.get("interface", "ppp0")
            
            # --- AUTO ROUTING ---
            # Default VPN route (always try to add this)
            _run(["ip", "route", "replace", "10.254.254.0/24", "dev", iface])
            
            # Dynamic Routes from User
            if auto_routes:
                routes = [r.strip() for r in auto_routes.split(",") if r.strip()]
                for r in routes:
                    logger.info(f"[l2tp-agent] Adding dynamic route: {r} via {iface}")
                    _run(["ip", "route", "replace", r, "dev", iface])
                    
            return {"ok": True, "message": f"L2TP Connected! IP: {st['endpoint']}", "status": st}

    return {"ok": False, "error": "Timeout: L2TP interface tidak muncul. Cek syslog host."}

def l2tp_disconnect() -> dict:
    """Putus koneksi L2TP."""
    control_path = "/var/run/xl2tpd/l2tp-control"
    if os.path.exists(control_path):
        try:
            with open(control_path, "w") as f:
                f.write("d myvpn")
        except: pass
    
    _run(["pkill", "-f", "pppd"]) # Force kill pppd just in case
    time.sleep(1)
    return {"ok": True, "message": "L2TP Disconnected"}

class AgentHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args): logger.debug(fmt, *args)

    def _json(self, data: dict, code: int = 200):
        body = json.dumps(data).encode()
        self.send_response(code)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/status":
            self._json(get_status())
        elif self.path == "/health":
            self._json({"ok": True, "agent": "l2tp-agent", "version": "1.0", "xl2tpd": os.path.exists("/usr/sbin/xl2tpd")})
        else:
            self._json({"error": "Not found"}, 404)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)

        if self.path == "/disconnect":
            self._json(l2tp_disconnect())
        elif self.path == "/connect":
            try:
                data = json.loads(body)
            except:
                self._json({"ok": False, "error": "Invalid JSON"}, 400)
                return
            
            result_holder = {}
            def do_connect():
                result_holder["result"] = l2tp_connect(
                    data.get("server", ""),
                    data.get("username", ""),
                    data.get("password", ""),
                    data.get("auto_routes", "")
                )
            t = Thread(target=do_connect)
            t.start()
            t.join(timeout=20)
            self._json(result_holder.get("result", {"ok": False, "error": "Connect Timeout"}))
        else:
            self._json({"error": "Not found"}, 404)

if __name__ == "__main__":
    logger.info(f"NOC Billing Pro L2TP Agent v1.0 starting on {LISTEN_HOST}:{LISTEN_PORT}")
    if not os.path.exists("/usr/sbin/xl2tpd"):
        logger.warning("xl2tpd NOT FOUND! Pastikan install_l2tp_agent.sh dijalankan di host.")
    
    server = HTTPServer((LISTEN_HOST, LISTEN_PORT), AgentHandler)
    logger.info("L2TP Agent ready and listening.")
    server.serve_forever()
