#!/usr/bin/env python3
"""Patch system.py to fix check-update and add /changelog endpoint."""
import re

# Read file
with open('backend/routers/system.py', 'rb') as f:
    content = f.read().decode('utf-8')

# ── 1. Replace check_update function ─────────────────────────────────────────
OLD_CHECK_UPDATE = '''@router.get("/check-update")
async def check_update(user=Depends(require_admin)):
    """Check if there are updates available from GitHub."""
    import httpx
    try:
        # Check current version from git (if source-based) or assume Docker
        import shutil
        is_docker = not shutil.which("git")
        
        # Ambil latest commit dari GitHub API agar jalan tanpa git CLI (Docker)
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://api.github.com/repos/afani-arba/noc-billing-pro/commits?per_page=10",
                timeout=10,
                headers={"User-Agent": "NOC-Billing-Pro-App"}
            )
            
        latest_commit = "unknown"
        latest_message = ""
        latest_date = ""
        
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, list):
                for c in data:
                    c_msg = c.get("commit", {}).get("message", "")
                    if "(license-server)" not in c_msg.lower():
                        latest_commit = c.get("sha", "")[:7]
                        latest_message = c_msg
                        latest_date = c.get("commit", {}).get("committer", {}).get("date", "")
                        latest_date = latest_date.replace("T", " ").replace("Z", "")
                        break
        
        try:
            with open("/update-data/version.txt", "r") as f:
                container_commit = f.read().strip()
        except Exception:
            container_commit = os.environ.get("APP_VERSION_COMMIT", "docker")
        
        if is_docker:
            # Jika hash commit container sama dengan github, tidak ada update
            has_update = True
            if container_commit != "docker" and latest_commit != "unknown":
                has_update = str(container_commit).strip() != str(latest_commit).strip()
                
            return {
                "has_update": has_update,
                "current_commit": container_commit,
                "current_message": "Mode Pre-built Image (Immutable)",
                "latest_commit": latest_commit,
                "latest_message": latest_message,
                "latest_date": latest_date,
                "commits_behind": 1 if has_update else 0,
                "message": "Klik update untuk memerintahkan host menarik Container terbaru." if has_update else "Aplikasi sudah versi terbaru.",
                "error": ""
            }

        # Source-based check
        current = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=APP_DIR, timeout=10)
        current_commit = current.stdout.strip() if current.returncode == 0 else "unknown"

        msg_result = subprocess.run(["git", "log", "-1", "--pretty=%s"], capture_output=True, text=True, cwd=APP_DIR, timeout=10)
        current_msg = msg_result.stdout.strip() if msg_result.returncode == 0 else ""

        has_update = current_commit != latest_commit if latest_commit != "unknown" else False

        return {
            "has_update": has_update,
            "current_commit": current_commit,
            "current_message": current_msg,
            "latest_commit": latest_commit,
            "latest_message": latest_message,
            "latest_date": latest_date,
            "commits_behind": 1 if has_update else 0,
            "message": "Update tersedia!" if has_update else "Aplikasi sudah versi terbaru."
        }
    except Exception as e:
        logger.error(f"Check update error: {e}")
        return {"has_update": False, "message": f"Koneksi ke GitHub gagal: {str(e)}", "error": str(e)}'''

NEW_CHECK_UPDATE = '''@router.get("/check-update")
async def check_update(user=Depends(require_admin)):
    """
    Check update: bandingkan versi container/source terhadap repo di GitHub.
    - Mendukung repo PRIVATE via GITHUB_TOKEN env var.
    - Di Docker mode: baca version.txt (ditulis noc-updater) ATAU git -C /app-host.
    - Di source mode: jalankan git langsung.
    """
    import shutil

    REPO = os.environ.get("GITHUB_REPO", "afani-arba/noc-billing-pro")
    TOKEN = os.environ.get("GITHUB_TOKEN", "")

    gh_headers = {"User-Agent": "NOC-Billing-Pro-App", "Accept": "application/vnd.github.v3+json"}
    if TOKEN:
        gh_headers["Authorization"] = f"Bearer {TOKEN}"

    # ── 1. Cari commit terbaru di GitHub ────────────────────────────────────
    latest_commit = "unknown"
    latest_message = ""
    latest_date = ""

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
                        latest_message = c_msg.split("\\n")[0]
                        latest_date = c.get("commit", {}).get("committer", {}).get("date", "")
                        latest_date = latest_date.replace("T", " ").replace("Z", "")
                        break
        else:
            logger.warning(f"GitHub API {resp.status_code}: {resp.text[:200]}")
    except Exception as gh_err:
        logger.warning(f"GitHub API error: {gh_err}")

    # ── 2. Cari commit yang sedang berjalan ────────────────────────────────
    # Prioritas: /update-data/version.txt → git -C /app-host → APP_VERSION_COMMIT env
    current_commit = "docker"
    current_msg = ""

    # a) Baca dari shared volume (ditulis noc-updater)
    try:
        with open("/update-data/version.txt", "r") as _f:
            _v = _f.read().strip()
            if _v:
                current_commit = _v
    except Exception:
        pass

    # b) Kalau masih "docker", coba baca git dari /app-host (mount ro di docker-compose)
    if current_commit == "docker":
        try:
            _r = subprocess.run(
                ["git", "-C", "/app-host", "rev-parse", "--short", "HEAD"],
                capture_output=True, text=True, timeout=5
            )
            if _r.returncode == 0 and _r.stdout.strip():
                current_commit = _r.stdout.strip()
                # Tulis ke version.txt agar konsisten berikutnya
                try:
                    with open("/update-data/version.txt", "w") as _f:
                        _f.write(current_commit)
                except Exception:
                    pass
        except Exception:
            pass

    # c) Fallback ke env var (di-set saat docker build via ARG APP_COMMIT_SHA)
    if current_commit == "docker":
        _env_commit = os.environ.get("APP_VERSION_COMMIT", "docker")
        if _env_commit and _env_commit != "docker":
            current_commit = _env_commit

    # d) Jika git tersedia (source mode), gunakan langsung
    if shutil.which("git"):
        _r = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, cwd=APP_DIR, timeout=5
        )
        if _r.returncode == 0:
            current_commit = _r.stdout.strip()
        _m = subprocess.run(
            ["git", "log", "-1", "--pretty=%s"],
            capture_output=True, text=True, cwd=APP_DIR, timeout=5
        )
        current_msg = _m.stdout.strip() if _m.returncode == 0 else ""

    # ── 3. Bandingkan ───────────────────────────────────────────────────────
    # Jika latest_commit masih "unknown" (GitHub tidak accessible), tidak bisa cek update
    if latest_commit == "unknown":
        return {
            "has_update": False,
            "current_commit": current_commit,
            "current_message": current_msg or "Docker Deployment",
            "latest_commit": "unknown",
            "latest_message": "",
            "latest_date": "",
            "commits_behind": 0,
            "message": "Tidak dapat terhubung ke GitHub. Pastikan GITHUB_TOKEN diset untuk repo private.",
            "error": "github_unreachable"
        }

    has_update = current_commit not in ("docker", "unknown") and current_commit != latest_commit

    return {
        "has_update": has_update,
        "current_commit": current_commit,
        "current_message": current_msg or "Docker Deployment",
        "latest_commit": latest_commit,
        "latest_message": latest_message,
        "latest_date": latest_date,
        "commits_behind": 1 if has_update else 0,
        "message": "Update tersedia dari GitHub!" if has_update else "Aplikasi sudah versi terbaru.",
        "error": ""
    }'''

# Normalize line endings for matching
content_normalized = content.replace('\r\n', '\n')
old_normalized = OLD_CHECK_UPDATE.replace('\r\n', '\n')

if old_normalized in content_normalized:
    content_normalized = content_normalized.replace(old_normalized, NEW_CHECK_UPDATE)
    print("✓ check_update function replaced successfully")
else:
    # Try partial match to find the function
    if '@router.get("/check-update")' in content_normalized:
        print("Function found but exact match failed - trying regex approach")
        # Find the function boundaries
        start = content_normalized.find('@router.get("/check-update")')
        # Find the next @router decorator after it
        next_route = content_normalized.find('\n@router.', start + 10)
        if next_route == -1:
            next_route = content_normalized.find('\n\n@router.', start + 10)
        if next_route > start:
            old_fn = content_normalized[start:next_route]
            content_normalized = content_normalized[:start] + NEW_CHECK_UPDATE + content_normalized[next_route:]
            print(f"✓ Replaced via regex approach ({len(old_fn)} chars)")
        else:
            print("✗ Could not find function end")
    else:
        print("✗ check-update function not found at all!")

# ── 2. Add /changelog endpoint before /perform-update ─────────────────────────
CHANGELOG_ENDPOINT = '''
@router.get("/changelog")
async def get_changelog(user=Depends(require_admin)):
    """
    Ambil daftar commit terbaru dari GitHub (proxy backend agar support repo private).
    Gunakan GITHUB_TOKEN env var untuk repo private.
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
                # Filter commit license-server dan sederhanakan payload
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
            return {"commits": [], "error": "GitHub API returned non-array response"}
        elif resp.status_code in (401, 403):
            return {"commits": [], "error": "GitHub token tidak valid atau repo private tanpa token. Set GITHUB_TOKEN di .env"}
        elif resp.status_code == 404:
            return {"commits": [], "error": f"Repo tidak ditemukan: {REPO}"}
        else:
            return {"commits": [], "error": f"GitHub API error: HTTP {resp.status_code}"}
    except Exception as e:
        logger.error(f"Changelog fetch error: {e}")
        return {"commits": [], "error": str(e)}


'''

PERFORM_UPDATE_MARKER = '@router.post("/perform-update")'
if PERFORM_UPDATE_MARKER in content_normalized:
    content_normalized = content_normalized.replace(
        PERFORM_UPDATE_MARKER,
        CHANGELOG_ENDPOINT + PERFORM_UPDATE_MARKER
    )
    print("✓ /changelog endpoint added")
else:
    print("✗ perform-update marker not found")

# Write back
with open('backend/routers/system.py', 'wb') as f:
    f.write(content_normalized.encode('utf-8'))

print("✓ system.py written successfully")
