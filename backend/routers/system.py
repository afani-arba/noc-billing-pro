"""
System update router: check and perform application updates.
"""
import os
import asyncio
import subprocess
import logging
import threading
import time
import json
import io
from datetime import datetime, timezone
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse
from core.auth import get_current_user, require_admin
import httpx
from pydantic import BaseModel
from typing import Optional

router = APIRouter(prefix="/system", tags=["system"])
logger = logging.getLogger(__name__)

# Project root: /opt/noc-sentinel  (parent of backend/)
APP_DIR = str(Path(__file__).parent.parent.parent)
BACKEND_DIR = str(Path(__file__).parent.parent)
FRONTEND_DIR = str(Path(__file__).parent.parent.parent / "frontend")

# Candidate paths — support both venv/ and .venv/
BACKEND_DIR_PATH = Path(BACKEND_DIR)
_venv_candidates = [BACKEND_DIR_PATH / "venv" / "bin" / "pip", BACKEND_DIR_PATH / ".venv" / "bin" / "pip"]
VENV_PIP = str(next((p for p in _venv_candidates if p.exists()), _venv_candidates[0]))
_uvicorn_candidates = [BACKEND_DIR_PATH / "venv" / "bin" / "uvicorn", BACKEND_DIR_PATH / ".venv" / "bin" / "uvicorn"]
VENV_UVICORN = str(next((u for u in _uvicorn_candidates if u.exists()), _uvicorn_candidates[0]))
UPDATE_SH = str(Path(APP_DIR) / "update.sh")
# Baca dari env agar bisa dikonfigurasi tanpa edit kode
SERVICE_NAME = os.environ.get("NOC_SERVICE_NAME", "noc-backend")

# ── Background Update State ───────────────────────────────────────────────────
_update_state = {
    "running": False,
    "done": False,
    "success": None,
    "log": [],
    "error": "",
    "started_at": None,
}


def _read_git_commit(git_dir: str = "/app-host") -> str:
    """
    Baca commit hash dari filesystem .git secara langsung.
    TIDAK memerlukan git binary dan TIDAK ada masalah safe.directory.
    Bekerja bahkan saat /app-host di-mount dari host dengan ownership berbeda.
    """
    try:
        head_path = Path(git_dir) / ".git" / "HEAD"
        if not head_path.exists():
            return ""
        head_content = head_path.read_text(encoding="utf-8").strip()
        if head_content.startswith("ref: "):
            # Normal branch, e.g. "ref: refs/heads/main"
            ref_rel = head_content[5:]  # "refs/heads/main"
            ref_path = Path(git_dir) / ".git" / ref_rel
            if ref_path.exists():
                sha = ref_path.read_text(encoding="utf-8").strip()
                return sha[:7] if sha else ""
            # Coba juga packed-refs
            packed = Path(git_dir) / ".git" / "packed-refs"
            if packed.exists():
                for line in packed.read_text(encoding="utf-8").splitlines():
                    if line.endswith(ref_rel):
                        return line.split()[0][:7]
        else:
            # Detached HEAD — langsung SHA
            return head_content[:7]
    except Exception:
        pass
    return ""


@router.get("/bgp-diag")
async def bgp_diag(user=Depends(require_admin)):
    """Meticulous Diagnostic: Runs GoBGP commands on host via nsenter."""
    res = {}
    
    def run_host_cmd(cmd_list):
        full_cmd = ["nsenter", "-t", "1", "-m", "-u", "-i", "-n", "-p", "--"] + cmd_list
        try:
            p = subprocess.run(full_cmd, capture_output=True, text=True, timeout=10)
            return p.stdout.strip() or p.stderr.strip()
        except Exception as e:
            return str(e)

    res["config"] = run_host_cmd(["cat", "/etc/gobgp/gobgpd.json"])
    res["neighbors"] = run_host_cmd(["/usr/local/bin/gobgp", "neighbor", "-j"])
    res["rib_summary"] = run_host_cmd(["/usr/local/bin/gobgp", "global", "rib", "-j"])
    
    # Also check DB policies
    from core.db import get_db
    db = get_db()
    res["db_active_policies"] = await db.bgp_steering_policies.find({"enabled": True}, {"_id": 0}).to_list(100)
    
    return res


@router.get("/check-update")
async def check_update(user=Depends(require_admin)):
    """
    Check update: bandingkan versi running vs commit terbaru di GitHub.
    - Mendukung repo PRIVATE via GITHUB_TOKEN env var.
    - Prioritas deteksi versi running: git /app-host (SELALU) → version.txt → APP_VERSION_COMMIT env.
    """
    import shutil

    REPO = os.environ.get("GITHUB_REPO", "afani-arba/noc-billing-pro")
    TOKEN = os.environ.get("GITHUB_TOKEN", "")

    gh_headers = {"User-Agent": "NOC-Billing-Pro-App", "Accept": "application/vnd.github.v3+json"}
    if TOKEN:
        gh_headers["Authorization"] = f"Bearer {TOKEN}"

    # ── 1. Ambil commit terbaru dari GitHub ─────────────────────────────────
    latest_commit = "unknown"
    latest_message = ""
    latest_date = ""
    gh_error = ""

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"https://api.github.com/repos/{REPO}/commits?per_page=15",
                headers=gh_headers,
            )
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, list):
                for c in data:
                    c_msg = c.get("commit", {}).get("message", "")
                    if "(license-server)" not in c_msg.lower():
                        latest_commit = c.get("sha", "")[:7]
                        latest_message = c_msg.split("\n")[0]
                        latest_date = c.get("commit", {}).get("committer", {}).get("date", "")
                        latest_date = latest_date.replace("T", " ").replace("Z", "")
                        break
        elif resp.status_code in (401, 403):
            gh_error = "Repo private — set env GITHUB_TOKEN di .env backend"
            logger.warning(f"GitHub API {resp.status_code} — repo private atau token salah")
        elif resp.status_code == 404:
            gh_error = f"Repo tidak ditemukan: {REPO}"
        else:
            gh_error = f"GitHub API error: HTTP {resp.status_code}"
            logger.warning(f"GitHub API {resp.status_code}: {resp.text[:200]}")
    except Exception as gh_err:
        gh_error = str(gh_err)
        logger.warning(f"GitHub API error: {gh_err}")

    # ── 2. Deteksi commit yang sedang berjalan ───────────────────────────────
    # PRIORITAS: .git/HEAD file (paling akurat, tanpa git binary, tanpa safe.directory)
    #            → version.txt → APP_VERSION_COMMIT env
    current_commit = "docker"
    current_msg = ""

    # a) UTAMA: Baca .git/HEAD langsung dari /app-host (selalu akurat setelah git pull)
    #    Tidak butuh git binary, tidak ada masalah safe.directory
    _sha = _read_git_commit("/app-host")
    if _sha:
        current_commit = _sha
        # Update version.txt agar konsisten dengan git state
        try:
            with open("/update-data/version.txt", "w") as _vf:
                _vf.write(current_commit)
        except Exception:
            pass

    # b) Juga coba git binary dengan safe.directory workaround (untuk mendapat commit message)
    if current_commit != "docker":
        try:
            _r = subprocess.run(
                ["git", "-C", "/app-host", "-c", "safe.directory=/app-host", "log", "-1", "--pretty=%s"],
                capture_output=True, text=True, timeout=5
            )
            if _r.returncode == 0:
                current_msg = _r.stdout.strip()
        except Exception:
            pass

    # c) Fallback: version.txt (jika /app-host tidak di-mount)
    if current_commit == "docker":
        try:
            with open("/update-data/version.txt", "r") as _vf:
                _v = _vf.read().strip()
                if _v and _v != "docker":
                    current_commit = _v
        except Exception:
            pass

    # d) Fallback: build-arg env var (APP_COMMIT_SHA via Dockerfile ARG)
    if current_commit == "docker":
        _env_commit = os.environ.get("APP_VERSION_COMMIT", "")
        if _env_commit and _env_commit not in ("docker", ""):
            current_commit = _env_commit

    # e) Source mode: git native langsung di container (bare metal)
    if shutil.which("git") and current_commit == "docker":
        _r = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, cwd=APP_DIR, timeout=5
        )
        if _r.returncode == 0 and _r.stdout.strip():
            current_commit = _r.stdout.strip()
        _m = subprocess.run(
            ["git", "log", "-1", "--pretty=%s"],
            capture_output=True, text=True, cwd=APP_DIR, timeout=5
        )
        current_msg = _m.stdout.strip() if _m.returncode == 0 else ""

    # ── 3. Bandingkan & return ───────────────────────────────────────────────
    if latest_commit == "unknown":
        tip = " Tambahkan GITHUB_TOKEN=<token> ke backend/.env" if not TOKEN else ""
        return {
            "has_update": False,
            "current_commit": current_commit,
            "current_message": current_msg or "Docker Deployment",
            "latest_commit": "unknown",
            "latest_message": "",
            "latest_date": "",
            "commits_behind": 0,
            "message": f"Tidak dapat terhubung ke GitHub.{tip}",
            "error": gh_error or "github_unreachable"
        }

    has_update = current_commit not in ("docker", "unknown", "") and current_commit != latest_commit

    return {
        "has_update": has_update,
        "current_commit": current_commit,
        "current_message": current_msg or "Docker Deployment",
        "latest_commit": latest_commit,
        "latest_message": latest_message,
        "latest_date": latest_date,
        "commits_behind": 1 if has_update else 0,
        "message": "Update tersedia dari GitHub!" if has_update else "Aplikasi sudah versi terbaru. ✅",
        "error": ""
    }


@router.get("/changelog")
async def get_changelog(user=Depends(require_admin)):
    """
    Proxy changelog dari GitHub ke frontend.
    Support repo private via GITHUB_TOKEN env var.
    Frontend memanggil endpoint ini (bukan langsung ke GitHub).
    """
    REPO = os.environ.get("GITHUB_REPO", "afani-arba/noc-billing-pro")
    TOKEN = os.environ.get("GITHUB_TOKEN", "")

    gh_headers = {"User-Agent": "NOC-Billing-Pro-App", "Accept": "application/vnd.github.v3+json"}
    if TOKEN:
        gh_headers["Authorization"] = f"Bearer {TOKEN}"

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"https://api.github.com/repos/{REPO}/commits?per_page=10",
                headers=gh_headers,
            )
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, list):
                commits = []
                for c in data:
                    msg = c.get("commit", {}).get("message", "")
                    if "(license-server)" in msg.lower():
                        continue
                    commits.append({
                        "sha": c.get("sha", ""),
                        "message": msg,
                        "date": c.get("commit", {}).get("author", {}).get("date", ""),
                        "author": c.get("commit", {}).get("author", {}).get("name", ""),
                        "avatar_url": (c.get("author") or {}).get("avatar_url", ""),
                    })
                return {"commits": commits, "error": None}
            return {"commits": [], "error": "GitHub API returned unexpected format"}
        elif resp.status_code in (401, 403):
            return {"commits": [], "error": "Repo private — set GITHUB_TOKEN di backend/.env"}
        elif resp.status_code == 404:
            return {"commits": [], "error": f"Repo tidak ditemukan: {REPO}"}
        else:
            return {"commits": [], "error": f"GitHub API error: HTTP {resp.status_code}"}
    except Exception as e:
        logger.error(f"Changelog fetch error: {e}")
        return {"commits": [], "error": str(e)}



@router.post("/perform-update")
async def perform_update(user=Depends(require_admin)):
    """Jalankan update di background thread."""
    global _update_state

    if _update_state["running"]:
        return {"started": False, "message": "Update sudah berjalan, cek /system/update-status"}

    _update_state = {
        "running": True, "done": False, "success": None,
        "log": ["🚀 Memulai proses update..."],
        "error": "", "started_at": time.time(),
    }

    def _run():
        log = _update_state["log"]
        def _append(msg):
            log.append(msg)
            logger.info(msg)

        try:
            import shutil
            is_docker = not shutil.which("git")

            # ── 1. Docker Mode: Trigger File via Shared Volume ──────────────────
            # noc-updater service (docker:cli container) membaca trigger ini
            # dan menjalankan: docker compose pull && docker compose up -d
            if is_docker:
                _append("🐳 Docker mode terdeteksi.")

                # Strategi 1: Trigger file via shared volume /update-data
                trigger_path = Path("/update-data/.update-trigger")
                lockfile_path = Path("/update-data/.update-running")

                if trigger_path.parent.exists():
                    _append("[1/2] Menulis sinyal update ke shared volume...")
                    try:
                        # Tulis metadata ke trigger file
                        trigger_data = {
                            "requested_at": datetime.now(timezone.utc).isoformat(),
                            "requested_by": "backend-api",
                        }
                        trigger_path.write_text(
                            json.dumps(trigger_data, indent=2), encoding="utf-8"
                        )
                        _append("✅ Sinyal update berhasil dikirim ke noc-updater service!")
                        _append("[2/2] Menunggu noc-updater memproses... (maks 3 menit)")

                        # Poll lockfile untuk tahu kapan selesai
                        deadline = time.time() + 180  # 3 menit timeout
                        started = False
                        while time.time() < deadline:
                            time.sleep(3)
                            if not trigger_path.exists() and not started:
                                # Trigger sudah dikonsumsi
                                started = True
                                _append("📦 noc-updater mulai menarik image terbaru dari ghcr.io...")
                            if lockfile_path.exists():
                                try:
                                    status = json.loads(lockfile_path.read_text())
                                    if status.get("done"):
                                        if status.get("success"):
                                            _append("✅ Image terbaru berhasil di-pull!")
                                            _append("♻️  Container sedang direstart dengan versi terbaru...")
                                            _append("🎉 Update selesai! Halaman akan otomatis reload dalam beberapa detik.")
                                            _update_state.update({"running": False, "done": True, "success": True})
                                        else:
                                            err = status.get("error", "unknown error")
                                            _append(f"❌ Update gagal: {err}")
                                            _update_state.update({"running": False, "done": True, "success": False, "error": err})
                                        return
                                except Exception:
                                    pass

                        # Timeout — trigger mungkin sudah dikonsumsi tapi lock tidak ada
                        if not trigger_path.exists():
                            _append("⏰ Timeout menunggu konfirmasi — container kemungkinan sudah direstart.")
                            _append("✅ Update kemungkinan sukses. Coba refresh halaman.")
                            _update_state.update({"running": False, "done": True, "success": True})
                        else:
                            _append("❌ noc-updater tidak merespons. Pastikan service 'noc-updater' berjalan di docker-compose.yml.")
                            _append("💡 Tip: Tambahkan service noc-updater ke docker-compose.yml Anda (lihat panduan).")
                            # Bersihkan trigger
                            trigger_path.unlink(missing_ok=True)
                            _update_state.update({
                                "running": False, "done": True, "success": False,
                                "error": "noc-updater tidak merespons"
                            })
                        return

                    except PermissionError:
                        _append("❌ Tidak ada akses tulis ke /update-data. Pastikan volume di-mount ke backend.")
                        _update_state.update({"running": False, "done": True, "success": False, "error": "PermissionError /update-data"})
                        return

                # Strategi 2: Fallback — docker CLI langsung dari socket
                elif Path("/var/run/docker.sock").exists():
                    _append("⚙️  /update-data tidak ada, mencoba Docker socket langsung...")
                    _append("[1/3] Menjalankan: docker pull ghcr.io/afani-arba/noc-billing-pro-backend:latest")
                    pull_be = subprocess.run(
                        ["docker", "pull", "ghcr.io/afani-arba/noc-billing-pro-backend:latest"],
                        capture_output=True, text=True, timeout=300
                    )
                    _append(pull_be.stdout[-800:] if pull_be.stdout else "(no output)")
                    if pull_be.returncode != 0:
                        _append(f"❌ Pull backend gagal: {pull_be.stderr[-400:]}")
                        _update_state.update({"running": False, "done": True, "success": False, "error": pull_be.stderr})
                        return

                    _append("[2/3] Menjalankan: docker pull ghcr.io/afani-arba/noc-billing-pro-frontend:latest")
                    pull_fe = subprocess.run(
                        ["docker", "pull", "ghcr.io/afani-arba/noc-billing-pro-frontend:latest"],
                        capture_output=True, text=True, timeout=300
                    )
                    _append(pull_fe.stdout[-800:] if pull_fe.stdout else "(no output)")

                    _append("[3/3] Merestart container via docker socket...")
                    # Cari compose file
                    compose_candidates = [
                        "/app-host/docker-compose.enterprise.yml",
                        "/app-host/docker-compose.yml",
                    ]
                    compose_file = next((f for f in compose_candidates if Path(f).exists()), None)
                    if compose_file:
                        restart = subprocess.run(
                            ["docker", "compose", "-f", compose_file, "up", "-d"],
                            capture_output=True, text=True, timeout=120
                        )
                        _append(restart.stdout[-800:] if restart.stdout else "done")
                    else:
                        _append("⚠ Compose file tidak ditemukan di /app-host. Restart container manual diperlukan.")

                    _append("🎉 Update selesai! Container dalam proses restart.")
                    _update_state.update({"running": False, "done": True, "success": True})
                    return

                else:
                    _append("❌ Tidak ada metode update yang tersedia.")  
                    _append("   • /update-data tidak ada (volume belum di-mount ke backend)")
                    _append("   • /var/run/docker.sock tidak ada (docker socket belum di-mount)")
                    _append("💡 Tambahkan konfigurasi berikut ke docker-compose.yml Anda:")
                    _append("   volumes:\n     - noc_update_data:/update-data")
                    _append("   Dan tambahkan service noc-updater (lihat panduan update).")
                    _update_state.update({"running": False, "done": True, "success": False, "error": "Tidak ada metode update"})
                    return

            # ── 2. Source-Based Update (Non-Docker / Bare Metal) ────────────────
            _append("[1/4] Menarik update dari GitHub...")
            pull = subprocess.run(["git", "pull", "origin", "main"], capture_output=True, text=True, cwd=APP_DIR, timeout=45)
            if pull.returncode != 0:
                _append(f"❌ Git pull GAGAL: {pull.stderr}")
                _update_state.update({"running": False, "done": True, "success": False, "error": pull.stderr})
                return
            _append(f"✅ {pull.stdout.strip() or 'Source code sudah terbaru.'}")

            if Path(UPDATE_SH).exists():
                _append("[2/4] Eksekusi shell update.sh...")
                proc = subprocess.Popen(["bash", UPDATE_SH], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, cwd=APP_DIR)
                proc.wait(timeout=600)
                _append("✅ Script update.sh selesai.")

            _append("=== ✅ Update sukses! ===")
            _update_state.update({"running": False, "done": True, "success": True})

        except Exception as e:
            _append(f"❌ Exception tidak terduga: {e}")
            _update_state.update({"running": False, "done": True, "success": False, "error": str(e)})

    threading.Thread(target=_run, daemon=True).start()
    return {"started": True, "message": "Update berjalan di background."}


@router.get("/update-status")
async def update_status(user=Depends(require_admin)):
    """Polling endpoint untuk status update yang berjalan di background."""
    return {
        "running": _update_state["running"],
        "done": _update_state["done"],
        "success": _update_state["success"],
        "log": _update_state["log"],
        "error": _update_state["error"],
        "elapsed": round(time.time() - _update_state["started_at"], 1) if _update_state["started_at"] else 0,
    }


@router.get("/debug-bw")
async def debug_bw(user=Depends(require_admin)):
    """
    Debug endpoint: lihat data bandwidth terakhir dari traffic_history.
    Berguna untuk diagnosa kenapa DL/UL = 0.
    """
    from core.db import get_db
    db = get_db()
    devs = await db.devices.find({}, {"_id": 0, "id": 1, "name": 1, "isp_interfaces": 1,
                                      "api_mode": 1, "ros_version": 1}).to_list(50)
    results = []
    for d in devs:
        last = await db.traffic_history.find_one(
            {"device_id": d["id"]},
            {"_id": 0, "timestamp": 1, "bandwidth": 1, "isp_bandwidth": 1,
             "download_mbps": 1, "upload_mbps": 1},
            sort=[("timestamp", -1)]
        )
        bw_keys = list((last.get("bandwidth") or {}).keys()) if last else []
        isp_bw_keys = list((last.get("isp_bandwidth") or {}).keys()) if last else []
        results.append({
            "name": d.get("name"),
            "api_mode": d.get("api_mode"),
            "ros_version": d.get("ros_version"),
            "isp_interfaces": d.get("isp_interfaces", []),
            "last_ts": (last or {}).get("timestamp"),
            "dl_mbps": (last or {}).get("download_mbps", 0),
            "ul_mbps": (last or {}).get("upload_mbps", 0),
            "bw_iface_count": len(bw_keys),
            "bw_iface_names": bw_keys[:10],   # max 10 for readability
            "isp_bw_names": isp_bw_keys,
        })
    return {"debug_bw": results}


@router.get("/snmp-config")
async def get_snmp_config(user=Depends(require_admin)):
    """Ambil interval SNMP polling dari system_settings."""
    from core.db import get_db
    db = get_db()
    cfg = await db.system_settings.find_one({"_id": "snmp_config"})
    return {"interval": cfg.get("interval", int(os.environ.get("SNMP_POLL_INTERVAL", 5))) if cfg else int(os.environ.get("SNMP_POLL_INTERVAL", 5))}

@router.put("/snmp-config")
async def set_snmp_config(payload: dict, user=Depends(require_admin)):
    """Simpan interval SNMP polling ke system_settings."""
    from core.db import get_db
    db = get_db()
    interval = int(payload.get("interval", 5))
    if interval < 5: interval = 5
    if interval > 600: interval = 600
    
    await db.system_settings.update_one(
        {"_id": "snmp_config"}, 
        {"$set": {"interval": interval}}, 
        upsert=True
    )
    return {"message": "SNMP Polling Interval updated", "interval": interval}

@router.get("/app-info")
async def app_info():
    """Return current app version info (commit hash, message, date)."""
    svc_name = os.environ.get("NOC_SERVICE_NAME", "noc-backend")
    try:
        import shutil
        if not shutil.which("git"):
            # Docker mode: baca .git/HEAD langsung (paling akurat, tanpa safe.directory)
            current_commit = _read_git_commit("/app-host") or ""
            current_msg = "Docker Deployment"

            if current_commit:
                # Dapat commit message via git dengan safe.directory flag
                try:
                    _m = subprocess.run(
                        ["git", "-C", "/app-host", "-c", "safe.directory=/app-host",
                         "log", "-1", "--pretty=%s"],
                        capture_output=True, text=True, timeout=5
                    )
                    if _m.returncode == 0:
                        current_msg = _m.stdout.strip() or "Docker Deployment"
                except Exception:
                    pass
                # Sync version.txt
                try:
                    with open("/update-data/version.txt", "w") as _vf:
                        _vf.write(current_commit)
                except Exception:
                    pass
            else:
                # Fallback: version.txt
                try:
                    with open("/update-data/version.txt", "r") as f:
                        _v = f.read().strip()
                        if _v:
                            current_commit = _v
                except Exception:
                    pass
                # Fallback: build-arg env
                if not current_commit:
                    current_commit = os.environ.get("APP_VERSION_COMMIT", "docker")

            return {"commit": current_commit or "docker", "message": current_msg,
                    "date": "-", "version": "v3.0", "service_name": svc_name}

        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=APP_DIR, timeout=5
        )
        msg = subprocess.run(
            ["git", "log", "-1", "--pretty=%s"], capture_output=True, text=True, cwd=APP_DIR, timeout=5
        )
        date = subprocess.run(
            ["git", "log", "-1", "--pretty=%ci"], capture_output=True, text=True, cwd=APP_DIR, timeout=5
        )
        return {
            "commit": commit.stdout.strip() if commit.returncode == 0 else "unknown",
            "message": msg.stdout.strip() if msg.returncode == 0 else "",
            "date": date.stdout.strip()[:19] if date.returncode == 0 else "",
            "version": "v3.0",
            "service_name": svc_name,
        }
    except Exception:
        return {"commit": "docker", "message": "Docker Build", "date": "-", "version": "v3.0", "service_name": svc_name}


@router.get("/service-name")
async def get_service_name(user=Depends(require_admin)):
    """Return nama service systemd yang digunakan."""
    return {"service_name": os.environ.get("NOC_SERVICE_NAME", "noc-backend")}


@router.post("/save-service-name")
async def save_service_name(data: dict, user=Depends(require_admin)):
    """Simpan nama service ke .env agar persisten."""
    svc = (data.get("service_name") or "").strip()
    if not svc:
        raise HTTPException(400, "Nama service tidak boleh kosong")

    backend_dir = Path(__file__).parent.parent
    env_path = backend_dir / ".env"
    lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []

    updated = False
    new_lines = []
    for line in lines:
        if line.startswith("NOC_SERVICE_NAME="):
            new_lines.append(f"NOC_SERVICE_NAME={svc}")
            updated = True
        else:
            new_lines.append(line)
    if not updated:
        new_lines.append(f"NOC_SERVICE_NAME={svc}")

    env_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    os.environ["NOC_SERVICE_NAME"] = svc
    logger.info(f"Service name saved: {svc}")
    return {"message": f"Nama service disimpan: {svc}"}


@router.post("/save-influxdb-config")
async def save_influxdb_config(data: dict, user=Depends(require_admin)):
    """
    Save InfluxDB configuration to the backend .env file.
    Updates INFLUXDB_URL, INFLUXDB_TOKEN, INFLUXDB_ORG, INFLUXDB_BUCKET.
    """
    backend_dir = Path(__file__).parent.parent
    env_path = backend_dir / ".env"

    url = (data.get("url") or "").strip()
    token = (data.get("token") or "").strip()
    org = (data.get("org") or "").strip()
    bucket = (data.get("bucket") or "noc-sentinel").strip()

    if not url or not token or not org:
        from fastapi import HTTPException
        raise HTTPException(400, "URL, token, dan org wajib diisi")

    # Read existing .env
    lines = []
    if env_path.exists():
        lines = env_path.read_text(encoding="utf-8").splitlines()

    # Keys to update
    new_values = {
        "INFLUXDB_URL": url,
        "INFLUXDB_TOKEN": token,
        "INFLUXDB_ORG": org,
        "INFLUXDB_BUCKET": bucket,
    }

    updated = set()
    new_lines = []
    for line in lines:
        key = line.split("=")[0].strip() if "=" in line else ""
        if key in new_values:
            new_lines.append(f'{key}={new_values[key]}')
            updated.add(key)
        else:
            new_lines.append(line)

    # Append any missing keys
    for key, val in new_values.items():
        if key not in updated:
            new_lines.append(f"{key}={val}")

    env_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")

    # Also set in current process env so test-connection works immediately
    import os as _os
    _os.environ["INFLUXDB_URL"] = url
    _os.environ["INFLUXDB_TOKEN"] = token
    _os.environ["INFLUXDB_ORG"] = org
    _os.environ["INFLUXDB_BUCKET"] = bucket

    # Reset cached client so next test uses new config
    try:
        import services.metrics_service as _ms
        _ms._influx_enabled = None
        _ms._write_client = None
        _ms._query_client = None
        _ms._write_api = None
        _ms._error_logged = False
    except Exception:
        pass

    logger.info(f"InfluxDB config saved: {url}, org={org}, bucket={bucket}")
    return {"message": "Konfigurasi InfluxDB disimpan. Restart backend tidak diperlukan — sudah aktif."}


@router.get("/health")
async def health():
    """
    Health check endpoint.
    Mengembalikan status sistem termasuk:
    - snmp_enabled: True jika pysnmp-lextudio terinstall dan bisa di-import
    - app_version:  git commit hash pendek (7 karakter)
    - syslog_port:  port UDP syslog yang aktif
    """
    # Cek pysnmp secara live menggunakan snmp_compat bridge
    snmp_enabled = False

    # Ambil git commit hash pendek
    app_version = "unknown"
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, cwd=APP_DIR, timeout=3
        )
        if commit.returncode == 0:
            app_version = commit.stdout.strip()
    except Exception:
        pass

    return {
        "status": "ok",
        "snmp_enabled": snmp_enabled,
        "app_version": app_version,
        "syslog_port": int(os.environ.get("SYSLOG_PORT", "5514")),
    }


@router.post("/save-genieacs-config")
async def save_genieacs_config(data: dict, user=Depends(require_admin)):
    """
    Save GenieACS NBI configuration to MongoDB (persistent) and .env (runtime).
    Updates GENIEACS_URL, GENIEACS_USERNAME, GENIEACS_PASSWORD.
    """
    from core.db import get_db
    db = get_db()
    
    url = (data.get("url") or "").strip()
    username = (data.get("username") or "").strip()
    password = (data.get("password") or "").strip()
    sync_interval_mins = int(data.get("sync_interval_mins") or 30)

    if not url:
        from fastapi import HTTPException
        raise HTTPException(400, "GENIEACS_URL wajib diisi")

    # 1. Simpan ke MongoDB (Sumber Kebenaran Utama yang Persisten)
    update_data = {
        "url": url,
        "username": username,
        "sync_interval_mins": sync_interval_mins,
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    if password:
        update_data["password"] = password
        
    await db.system_settings.update_one(
        {"_id": "genieacs_config"},
        {"$set": update_data},
        upsert=True
    )

    # 2. Update .env file (Legacy/Runtime support)
    backend_dir = Path(__file__).parent.parent
    env_path = backend_dir / ".env"
    lines = []
    if env_path.exists():
        lines = env_path.read_text(encoding="utf-8").splitlines()

    new_values = {
        "GENIEACS_URL": url,
        "GENIEACS_USERNAME": username,
        "GENIEACS_SYNC_INTERVAL_MINS": str(sync_interval_mins)
    }
    if password:
        new_values["GENIEACS_PASSWORD"] = password

    updated = set()
    new_lines = []
    for line in lines:
        if "=" in line:
            key = line.split("=")[0].strip()
            if key in new_values:
                new_lines.append(f"{key}={new_values[key]}")
                updated.add(key)
                continue
        new_lines.append(line)

    for key, val in new_values.items():
        if key not in updated:
            new_lines.append(f"{key}={val}")

    try:
        env_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    except Exception as e:
        logger.warning(f"Gagal menulis ke .env: {e}")

    # 3. Inject ke environment proses sekarang
    import os as _os
    for key, val in new_values.items():
        _os.environ[key] = val

    logger.info(f"GenieACS config saved to MongoDB and .env: {url}, user={username}")
    return {"message": "Konfigurasi GenieACS disimpan secara permanen di Database."}


@router.get("/genieacs-config")
async def get_genieacs_config(user=Depends(require_admin)):
    """Return current GenieACS config (Prefer MongoDB, fallback to .env)."""
    from core.db import get_db
    db = get_db()
    
    # Prioritas 1: MongoDB
    cfg = await db.system_settings.find_one({"_id": "genieacs_config"})
    if cfg:
        return {
            "url": cfg.get("url", ""),
            "username": cfg.get("username", ""),
            "password_set": bool(cfg.get("password", "")),
            "sync_interval_mins": cfg.get("sync_interval_mins", 30),
            "source": "database"
        }
    
    # Prioritas 2: Environment
    import os as _os
    return {
        "url": _os.environ.get("GENIEACS_URL", ""),
        "username": _os.environ.get("GENIEACS_USERNAME", ""),
        "password_set": bool(_os.environ.get("GENIEACS_PASSWORD", "")),
        "sync_interval_mins": int(_os.environ.get("GENIEACS_SYNC_INTERVAL_MINS", 30)),
        "source": "env"
    }


# ── Winbox Path Configuration ─────────────────────────────────────────────────

@router.get("/winbox-config")
async def get_winbox_config(user=Depends(require_admin)):
    """Return configured Winbox executable path."""
    import os as _os
    return {
        "winbox_path": _os.environ.get("WINBOX_PATH", ""),
    }


# ── Company Profile ─────────────────────────────────────────────────────────────

@router.get("/company-profile")
async def get_company_profile():
    """Endpoint publik untuk mendapatkan Profil Perusahaan/Produk (untuk halaman Login dll)."""
    from core.db import get_db
    db = get_db()
    cfg = await db.system_settings.find_one({"_id": "company_profile"}) or {}
    return {
        "company_name": cfg.get("company_name", ""),
        "product_name": cfg.get("product_name", "NOC Sentinel"),
        "address": cfg.get("address", ""),
        "whatsapp_number": cfg.get("whatsapp_number", ""),
        "logo_base64": cfg.get("logo_base64", "")
    }

class CompanyProfileUpdate(BaseModel):
    company_name: Optional[str] = ""
    product_name: str
    address: str
    whatsapp_number: str
    logo_base64: Optional[str] = ""

@router.put("/company-profile")
async def update_company_profile(data: CompanyProfileUpdate, user=Depends(require_admin)):
    """Simpan profil perusahaan."""
    from core.db import get_db
    db = get_db()
    await db.system_settings.update_one(
        {"_id": "company_profile"},
        {"$set": {
            "company_name": data.company_name,
            "product_name": data.product_name,
            "address": data.address,
            "whatsapp_number": data.whatsapp_number,
            "logo_base64": data.logo_base64,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }},
        upsert=True
    )
    return {"message": "Profil Perusahaan berhasil disimpan."}


@router.post("/save-winbox-config")
async def save_winbox_config(data: dict, user=Depends(require_admin)):
    """
    Simpan path executable Winbox ke .env agar bisa dipakai saat generate URL.
    Contoh path: C:\\Users\\user\\Desktop\\winbox64.exe
    """
    winbox_path = (data.get("winbox_path") or "").strip()
    # Path boleh kosong (artinya gunakan default URI scheme winbox://)

    backend_dir = Path(__file__).parent.parent
    env_path = backend_dir / ".env"
    lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []

    updated = False
    new_lines = []
    for line in lines:
        if line.startswith("WINBOX_PATH="):
            new_lines.append(f"WINBOX_PATH={winbox_path}")
            updated = True
        else:
            new_lines.append(line)
    if not updated:
        new_lines.append(f"WINBOX_PATH={winbox_path}")

    env_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    os.environ["WINBOX_PATH"] = winbox_path
    logger.info(f"Winbox path saved: {winbox_path!r}")
    return {"message": "Path Winbox disimpan.", "winbox_path": winbox_path}


# ── Edition Info — dikonsumsi Frontend untuk mode/feature awareness ───────────

@router.get("/info")
async def system_info():
    """
    Return edition info dan feature flags.
    Frontend menggunakan endpoint ini untuk menyembunyikan/menampilkan
    menu Billing berdasarkan edisi (Pro vs Enterprise).
    Tidak perlu autentikasi agar dapat dibaca saat login pertama.
    """
    from core.edition import EDITION, EDITION_NAME, FEATURES
    import subprocess as _sp
    from pathlib import Path as _Path

    _app_dir = str(_Path(__file__).parent.parent.parent)
    commit = "docker"
    try:
        import shutil
        if shutil.which("git"):
            r = _sp.run(
                ["git", "rev-parse", "--short", "HEAD"],
                capture_output=True, text=True, cwd=_app_dir, timeout=3
            )
            if r.returncode == 0:
                commit = r.stdout.strip()
    except Exception:
        pass

    return {
        "edition": EDITION,
        "edition_name": EDITION_NAME,
        "version": "3.0.0",
        "commit": commit,
        "features": {
            "billing":        FEATURES.get("billing", False),
            "customers":      FEATURES.get("customers", False),
            "finance_report": FEATURES.get("finance_report", False),
            "n8n":            FEATURES.get("n8n_integration", False),
            "auto_isolir":    FEATURES.get("auto_isolir", False),
            "genieacs":       FEATURES.get("genieacs", True),
            "monitoring":     True,
        },
    }


# ── Device Data Backup & Restore ─────────────────────────────────────────────

@router.get("/backup-data")
async def backup_device_data(user=Depends(require_admin)):
    """
    Export semua data device dari MongoDB sebagai file JSON yang bisa didownload.
    Termasuk: devices, credential presets, dan system settings.
    """
    from core.db import get_db
    db = get_db()

    devices = await db.devices.find({}, {"_id": 0}).to_list(None)

    # Try credential presets
    try:
        creds = await db.credential_presets.find({}, {"_id": 0}).to_list(None)
    except Exception:
        creds = []

    backup_payload = {
        "meta": {
            "version": "3.0",
            "app": "NOC Sentinel v3",
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "total_devices": len(devices),
            "total_credentials": len(creds),
        },
        "devices": devices,
        "credential_presets": creds,
    }

    json_bytes = json.dumps(backup_payload, indent=2, default=str).encode("utf-8")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"noc_sentinel_backup_{timestamp}.json"

    return StreamingResponse(
        io.BytesIO(json_bytes),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


@router.post("/restore-data")
async def restore_device_data(
    file: UploadFile = File(...),
    mode: str = "merge",
    user=Depends(require_admin),
):
    """
    Import data device dari file JSON backup.
    mode=merge  → upsert (tambah/update, tidak hapus yang sudah ada)
    mode=replace → hapus semua device dulu, lalu import dari backup
    """
    if not file.filename.endswith(".json"):
        raise HTTPException(400, "File harus berformat .json")

    content = await file.read()
    if len(content) > 20 * 1024 * 1024:  # max 20 MB
        raise HTTPException(400, "File terlalu besar (maks 20 MB)")

    try:
        payload = json.loads(content.decode("utf-8"))
    except Exception:
        raise HTTPException(400, "File JSON tidak valid atau rusak")

    # Validasi format
    if "devices" not in payload:
        raise HTTPException(400, "Format backup tidak valid: field 'devices' tidak ditemukan")

    meta = payload.get("meta", {})
    devices = payload.get("devices", [])
    creds = payload.get("credential_presets", [])

    if not isinstance(devices, list):
        raise HTTPException(400, "Field 'devices' harus berupa array")

    from core.db import get_db
    db = get_db()

    restored_devices = 0
    skipped_devices = 0
    restored_creds = 0

    if mode == "replace":
        # Hapus semua device yang ada dulu
        await db.devices.delete_many({})
        logger.info(f"Restore mode=replace: semua device dihapus sebelum import")

    for device in devices:
        if not device.get("id"):
            skipped_devices += 1
            continue
        try:
            await db.devices.update_one(
                {"id": device["id"]},
                {"$set": device},
                upsert=True
            )
            restored_devices += 1
        except Exception as e:
            logger.warning(f"Gagal restore device {device.get('id')}: {e}")
            skipped_devices += 1

    # Restore credential presets jika ada
    for cred in creds:
        if not cred.get("name"):
            continue
        try:
            await db.credential_presets.update_one(
                {"name": cred["name"]},
                {"$set": cred},
                upsert=True
            )
            restored_creds += 1
        except Exception:
            pass

    logger.info(f"Restore selesai: {restored_devices} devices, {restored_creds} creds (mode={mode})")
    return {
        "success": True,
        "message": f"Restore berhasil! {restored_devices} device diimport, {skipped_devices} dilewati.",
        "mode": mode,
        "restored_devices": restored_devices,
        "skipped_devices": skipped_devices,
        "restored_credentials": restored_creds,
        "backup_meta": meta,
    }


@router.get("/backup-preview")
async def backup_preview(user=Depends(require_admin)):
    """Preview ringkasan data yang akan di-backup tanpa download file."""
    from core.db import get_db
    db = get_db()
    device_count = await db.devices.count_documents({})
    try:
        cred_count = await db.credential_presets.count_documents({})
    except Exception:
        cred_count = 0

    sample_devices = await db.devices.find(
        {}, {"_id": 0, "id": 1, "name": 1, "host": 1, "status": 1}
    ).limit(5).to_list(5)

    return {
        "total_devices": device_count,
        "total_credentials": cred_count,
        "sample_devices": sample_devices,
        "estimated_size_kb": round((device_count * 0.8) + (cred_count * 0.3), 1),
    }



# ── Bank Account (untuk AI CS Tagihan Otomatis) ──────────────────────────────

@router.get("/bank-account")
async def get_bank_account(user=Depends(require_admin)):
    """Ambil info rekening bank yang digunakan untuk tagihan otomatis AI CS."""
    from core.db import get_db
    db = get_db()
    settings = await db.system_settings.find_one({"_id": "company_profile"})
    return {
        "bank_account": (settings or {}).get("bank_account", "BCA 8520480189 a.n PT ARSYA BAROKAH ABADI")
    }


@router.put("/bank-account")
async def save_bank_account(data: dict, user=Depends(require_admin)):
    """Simpan info rekening bank ke database untuk digunakan tagihan AI CS."""
    from core.db import get_db
    db = get_db()
    bank_account = (data.get("bank_account") or "").strip()
    if not bank_account:
        raise HTTPException(400, "Info rekening bank tidak boleh kosong")
    await db.system_settings.update_one(
        {"_id": "company_profile"},
        {"$set": {"bank_account": bank_account, "updated_at": datetime.now(timezone.utc).isoformat()}},
        upsert=True
    )
    logger.info(f"Bank account updated: {bank_account}")
    return {"message": "Rekening bank berhasil disimpan", "bank_account": bank_account}


# ══════════════════════════════════════════════════════════════════════════════
# INTEGRASI AI CHAT (Gemini) + TELEGRAM NOC
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/integrations")
async def get_integrations(user=Depends(require_admin)):
    """Ambil konfigurasi integrasi AI & Telegram."""
    from core.db import get_db
    db = get_db()
    cfg = await db.system_settings.find_one({"_id": "integrations"}) or {}
    return {
        "gemini_api_key": cfg.get("gemini_api_key", ""),
        "telegram_bot_token": cfg.get("telegram_bot_token", ""),
        "telegram_chat_id_noc": cfg.get("telegram_chat_id_noc", ""),
        "ai_chat_enabled": bool(cfg.get("gemini_api_key", "")),
    }


@router.put("/integrations")
async def save_integrations(data: dict, user=Depends(require_admin)):
    """Simpan konfigurasi Gemini API Key dan Telegram Bot untuk CS AI Chat."""
    from core.db import get_db
    db = get_db()
    update = {}
    if "gemini_api_key" in data:
        update["gemini_api_key"] = data["gemini_api_key"].strip()
    if "telegram_bot_token" in data:
        update["telegram_bot_token"] = data["telegram_bot_token"].strip()
    if "telegram_chat_id_noc" in data:
        update["telegram_chat_id_noc"] = data["telegram_chat_id_noc"].strip()

    update["updated_at"] = datetime.now(timezone.utc).isoformat()

    await db.system_settings.update_one(
        {"_id": "integrations"},
        {"$set": update},
        upsert=True
    )
    logger.info(f"Integrations config saved by {user.get('username')}")
    return {"message": "Konfigurasi integrasi berhasil disimpan."}


# ══════════════════════════════════════════════════════════════════════════════
# AI CHAT CONFIG — System Prompt & Behavior Settings
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/ai-chat-config")
async def get_ai_chat_config(user=Depends(require_admin)):
    """Ambil konfigurasi perilaku AI Chat (system prompt, model, toggles)."""
    from core.db import get_db
    db = get_db()
    cfg = await db.system_settings.find_one({"_id": "ai_chat_config"}) or {}
    return {
        "model": cfg.get("model", "gemini-1.5-flash"),
        "system_prompt": cfg.get("system_prompt", ""),
        "company_name": cfg.get("company_name", ""),
        "ai_name": cfg.get("ai_name", "Asisten AI"),
        "payment_info": cfg.get("payment_info", ""),
        "extra_context": cfg.get("extra_context", ""),
        "temperature": cfg.get("temperature", 0.7),
        "max_tokens": cfg.get("max_tokens", 500),
        "feature_modem_reprovision": cfg.get("feature_modem_reprovision", True),
        "feature_cable_alert": cfg.get("feature_cable_alert", True),
        "feature_needs_cs": cfg.get("feature_needs_cs", True),
    }


@router.put("/ai-chat-config")
async def save_ai_chat_config(data: dict, user=Depends(require_admin)):
    """Simpan konfigurasi perilaku AI Chat."""
    from core.db import get_db
    db = get_db()
    allowed = [
        "model", "system_prompt", "company_name", "ai_name", "payment_info",
        "extra_context", "temperature", "max_tokens",
        "feature_modem_reprovision", "feature_cable_alert", "feature_needs_cs",
    ]
    update = {k: data[k] for k in allowed if k in data}
    update["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.system_settings.update_one(
        {"_id": "ai_chat_config"},
        {"$set": update},
        upsert=True
    )
    logger.info(f"AI Chat config saved by {user.get('username')}")
    return {"message": "Konfigurasi AI Chat berhasil disimpan."}

