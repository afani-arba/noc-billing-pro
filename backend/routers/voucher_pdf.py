"""
Voucher Hotspot PDF Generator
Endpoint prefix: /voucher

Menggunakan reportlab (Python native, ringan tanpa headless browser).
Layout: 4, 8, atau 16 voucher per halaman A4.
Setiap voucher: SSID, Username, Password, Harga, Masa Berlaku, QR Code.
"""
import io
import logging
import math
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Depends
from fastapi.responses import StreamingResponse
from core.db import get_db
from core.auth import get_current_user, require_write

router = APIRouter(
    prefix="/voucher",
    tags=["voucher"],
)

logger = logging.getLogger(__name__)


# ── Layout Presets ──────────────────────────────────────────────────────────

LAYOUTS = {
    4: {
        "cols": 2,
        "rows": 2,
        "card_w_pt": 270,
        "card_h_pt": 380,
        "margin": 18,
        "h_gap": 14,
        "v_gap": 14,
    },
    8: {
        "cols": 2,
        "rows": 4,
        "card_w_pt": 270,
        "card_h_pt": 184,
        "margin": 15,
        "h_gap": 12,
        "v_gap": 8,
    },
    16: {
        "cols": 4,
        "rows": 4,
        "card_w_pt": 130,
        "card_h_pt": 184,
        "margin": 10,
        "h_gap": 6,
        "v_gap": 6,
    },
}


def _rupiah(amount) -> str:
    try:
        return f"Rp {int(amount):,.0f}".replace(",", ".")
    except Exception:
        return str(amount)


def _try_import_pdf_libs():
    """Lazy-import reportlab & qrcode — gemblokir error jika belum install."""
    try:
        from reportlab.pdfgen import canvas as rl_canvas
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.colors import HexColor, white, black
        from reportlab.lib.utils import ImageReader
        import qrcode
        from PIL import Image
        return rl_canvas, A4, HexColor, white, black, ImageReader, qrcode, Image
    except ImportError as e:
        raise HTTPException(
            status_code=500,
            detail=f"Modul PDF belum terpasang: {e}. Jalankan: pip install reportlab qrcode[pil]"
        )


def _generate_qr_image(data: str, size: int = 80):
    """Hasilkan QR code sebagai bytes PNG."""
    try:
        import qrcode
        from PIL import Image
        import io as _io

        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=3,
            border=1,
        )
        qr.add_data(data)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
        img = img.resize((size, size), Image.LANCZOS)
        buf = _io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        return buf
    except Exception as e:
        logger.warning(f"QR generate error: {e}")
        return None


def _draw_voucher_card(
    c,
    x: float,
    y: float,
    w: float,
    h: float,
    voucher: dict,
    layout_count: int,
    template: str,
    ImageReader,
    HexColor,
    white,
    black,
):
    """Gambar satu kartu voucher di posisi (x, y) dengan ukuran (w, h)."""

    ssid = voucher.get("ssid", "WiFi-Hotspot")
    username = voucher.get("username", "")
    password = voucher.get("password", "")
    price = voucher.get("price", 0)
    validity = voucher.get("validity", "")
    uptime_limit = voucher.get("uptime_limit", "")
    profile_name = voucher.get("profile_name", "")
    login_url = voucher.get("login_url", "http://hotspot.login")

    # Warna berdasarkan template
    if template == "branded":
        header_color = HexColor("#1a56db")   # biru
        accent_color = HexColor("#3b82f6")
        border_color = HexColor("#1a56db")
        header_text_color = white
    elif template == "minimal":
        header_color = HexColor("#1f2937")   # dark
        accent_color = HexColor("#6b7280")
        border_color = HexColor("#374151")
        header_text_color = white
    else:  # basic
        header_color = HexColor("#047857")   # hijau
        accent_color = HexColor("#10b981")
        border_color = HexColor("#059669")
        header_text_color = white

    header_h = min(h * 0.22, 40)
    radius = 4
    padding = min(w * 0.06, 8)

    # ── Border & Background ──────────────────────────────────────────────────
    c.setStrokeColor(border_color)
    c.setLineWidth(1)
    c.setFillColor(white)
    c.roundRect(x, y, w, h, radius, stroke=1, fill=1)

    # ── Header ──────────────────────────────────────────────────────────────
    c.setFillColor(header_color)
    # Rounded rect hanya atas (trik: gambar rect di bawah lalu round di atas)
    c.roundRect(x, y + h - header_h, w, header_h, radius, stroke=0, fill=1)
    c.rect(x, y + h - header_h, w, header_h / 2, stroke=0, fill=1)

    # Header text: SSID
    c.setFillColor(header_text_color)
    c.setFont("Helvetica-Bold", min(w / 12, 11))
    ssid_display = ssid[:22] if len(ssid) > 22 else ssid
    c.drawCentredString(x + w / 2, y + h - header_h + header_h * 0.35, ssid_display)

    # Label "VOUCHER INTERNET"
    c.setFont("Helvetica", min(w / 18, 7))
    c.drawCentredString(x + w / 2, y + h - header_h * 0.35, "VOUCHER INTERNET")

    # ── Content Area ─────────────────────────────────────────────────────────
    content_y = y + h - header_h - padding
    line_h = min(h / 10, 14)
    font_size_label = min(w / 22, 7)
    font_size_value = min(w / 14, 9.5)
    font_size_cred = min(w / 10, 13)

    def _draw_kv(label: str, value: str, cy: float, bold_val: bool = False):
        c.setFillColor(HexColor("#6b7280"))
        c.setFont("Helvetica", font_size_label)
        c.drawString(x + padding, cy, label)
        c.setFillColor(black)
        c.setFont("Helvetica-Bold" if bold_val else "Helvetica", font_size_value)
        c.drawString(x + padding, cy - line_h * 0.7, value[:28])
        return cy - line_h * 1.7

    # Apakah layout sangat kecil (16 per halaman)
    compact = layout_count == 16

    if not compact:
        cur_y = content_y - 2

        # Username
        c.setFillColor(HexColor("#374151"))
        c.setFont("Helvetica", font_size_label)
        c.drawString(x + padding, cur_y, "Username")
        cur_y -= line_h * 0.5
        c.setFillColor(HexColor("#1a56db"))
        c.setFont("Helvetica-Bold", font_size_cred)
        c.drawString(x + padding, cur_y, username)
        cur_y -= line_h * 1.2

        # Password
        c.setFillColor(HexColor("#374151"))
        c.setFont("Helvetica", font_size_label)
        c.drawString(x + padding, cur_y, "Password")
        cur_y -= line_h * 0.5
        c.setFillColor(HexColor("#dc2626"))
        c.setFont("Helvetica-Bold", font_size_cred)
        c.drawString(x + padding, cur_y, password)
        cur_y -= line_h * 1.5

        # Divider
        c.setStrokeColor(HexColor("#e5e7eb"))
        c.setLineWidth(0.5)
        c.line(x + padding, cur_y, x + w - padding, cur_y)
        cur_y -= line_h * 0.6

        # Harga & Masa berlaku side by side
        if price:
            c.setFillColor(HexColor("#6b7280"))
            c.setFont("Helvetica", font_size_label)
            c.drawString(x + padding, cur_y, "Harga")
            c.setFillColor(HexColor("#047857"))
            c.setFont("Helvetica-Bold", font_size_value)
            c.drawString(x + padding, cur_y - line_h * 0.7, _rupiah(price))

        if validity or uptime_limit:
            val_text = uptime_limit or validity
            c.setFillColor(HexColor("#6b7280"))
            c.setFont("Helvetica", font_size_label)
            c.drawString(x + w / 2, cur_y, "Masa Berlaku")
            c.setFillColor(black)
            c.setFont("Helvetica-Bold", font_size_value)
            c.drawString(x + w / 2, cur_y - line_h * 0.7, val_text[:15])

        cur_y -= line_h * 1.8

        # QR Code
        qr_size = min(int(w * 0.28), 70)
        qr_buf = _generate_qr_image(login_url, size=qr_size)
        if qr_buf:
            from reportlab.lib.utils import ImageReader
            qr_x = x + w - qr_size - padding
            qr_y = y + padding + 8
            c.drawImage(
                ImageReader(qr_buf),
                qr_x, qr_y,
                width=qr_size, height=qr_size,
            )
            c.setFont("Helvetica", 5)
            c.setFillColor(HexColor("#9ca3af"))
            c.drawCentredString(qr_x + qr_size / 2, qr_y - 6, "Scan to Login")

        # Profile
        if profile_name:
            c.setFont("Helvetica", font_size_label - 0.5)
            c.setFillColor(HexColor("#9ca3af"))
            c.drawString(x + padding, y + padding + 4, f"Profile: {profile_name}")

    else:
        # Compact mode (16 per hal)
        cur_y = content_y - 2
        c.setFillColor(HexColor("#374151"))
        c.setFont("Helvetica", font_size_label - 0.5)
        c.drawString(x + padding, cur_y, "User")
        cur_y -= line_h * 0.45
        c.setFillColor(HexColor("#1a56db"))
        c.setFont("Helvetica-Bold", font_size_value - 1)
        c.drawString(x + padding, cur_y, username[:16])
        cur_y -= line_h * 1.0

        c.setFillColor(HexColor("#374151"))
        c.setFont("Helvetica", font_size_label - 0.5)
        c.drawString(x + padding, cur_y, "Pass")
        cur_y -= line_h * 0.45
        c.setFillColor(HexColor("#dc2626"))
        c.setFont("Helvetica-Bold", font_size_value - 1)
        c.drawString(x + padding, cur_y, password[:16])
        cur_y -= line_h

        if price:
            c.setFillColor(HexColor("#047857"))
            c.setFont("Helvetica-Bold", font_size_label)
            c.drawString(x + padding, cur_y, _rupiah(price))
        if validity or uptime_limit:
            c.setFillColor(black)
            c.setFont("Helvetica", font_size_label - 0.5)
            c.drawString(x + w * 0.5, cur_y, (uptime_limit or validity)[:10])


def _build_pdf_bytes(vouchers: list, layout: int, template: str, isp_name: str = "") -> bytes:
    """Build PDF bytes dari list voucher."""
    rl_canvas, A4, HexColor, white, black, ImageReader, qrcode, Image = _try_import_pdf_libs()

    lp = LAYOUTS[layout]
    cols = lp["cols"]
    rows = lp["rows"]
    card_w = lp["card_w_pt"]
    card_h = lp["card_h_pt"]
    margin = lp["margin"]
    h_gap = lp["h_gap"]
    v_gap = lp["v_gap"]

    page_w, page_h = A4  # 595.28, 841.89 pt

    buf = io.BytesIO()
    c = rl_canvas.Canvas(buf, pagesize=A4)
    c.setTitle(f"Voucher Hotspot — {isp_name}")

    per_page = cols * rows
    total_pages = math.ceil(len(vouchers) / per_page)

    for page_idx in range(total_pages):
        page_vouchers = vouchers[page_idx * per_page: (page_idx + 1) * per_page]

        # Header halaman (nama ISP + tanggal cetak)
        c.setFont("Helvetica-Bold", 8)
        c.setFillColor(HexColor("#374151"))
        if isp_name:
            c.drawString(margin, page_h - margin + 2, isp_name)
        c.setFont("Helvetica", 7)
        c.setFillColor(HexColor("#9ca3af"))
        date_str = datetime.now().strftime("%d/%m/%Y %H:%M")
        c.drawRightString(page_w - margin, page_h - margin + 2, f"Dicetak: {date_str}")

        # Gambar kartu voucher
        for idx, voucher in enumerate(page_vouchers):
            col = idx % cols
            row = idx // cols

            card_x = margin + col * (card_w + h_gap)
            card_y = page_h - margin - 12 - (row + 1) * card_h - row * v_gap

            _draw_voucher_card(
                c, card_x, card_y, card_w, card_h,
                voucher, layout, template,
                ImageReader, HexColor, white, black,
            )

        c.showPage()

    c.save()
    buf.seek(0)
    return buf.read()


# ══════════════════════════════════════════════════════════════════════════════
# ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/templates")
async def list_voucher_templates(user=Depends(get_current_user)):
    """Daftar template voucher yang tersedia."""
    return {
        "templates": [
            {
                "id": "basic",
                "name": "Basic (Hijau)",
                "description": "Template sederhana dengan header hijau, cocok untuk semua brand."
            },
            {
                "id": "branded",
                "name": "Branded (Biru)",
                "description": "Template premium dengan warna biru, cocok untuk ISP corporate."
            },
            {
                "id": "minimal",
                "name": "Minimal (Gelap)",
                "description": "Template minimalis dark theme, elegan dan modern."
            },
        ],
        "layouts": [
            {"count": 4, "label": "4 voucher/halaman (Besar)", "description": "Ideal untuk voucher premium"},
            {"count": 8, "label": "8 voucher/halaman (Sedang)", "description": "Standar, mudah dipotong"},
            {"count": 16, "label": "16 voucher/halaman (Kecil)", "description": "Ekonomis, untuk event/warnet"},
        ]
    }


@router.get("/generate-pdf")
async def generate_voucher_pdf(
    device_id: str = Query(..., description="ID Device MikroTik"),
    profile: str = Query("", description="Filter nama profile hotspot (kosong = semua)"),
    count: int = Query(8, ge=1, le=200, description="Jumlah voucher dicetak (max 200)"),
    layout: int = Query(8, description="Layout: 4, 8, atau 16 per halaman"),
    template: str = Query("basic", description="Template: basic | branded | minimal"),
    ssid: str = Query("", description="SSID WiFi untuk ditampilkan di voucher"),
    login_url: str = Query("", description="URL Login Hotspot untuk QR Code"),
    user=Depends(get_current_user),
):
    """
    Generate PDF voucher hotspot massal.
    Mengambil voucher dari database (hotspot_vouchers) yang ada,
    atau membuat placeholder voucher jika belum ada data.
    """
    if layout not in (4, 8, 16):
        raise HTTPException(400, "Layout harus 4, 8, atau 16")
    if template not in ("basic", "branded", "minimal"):
        raise HTTPException(400, "Template harus basic, branded, atau minimal")

    db = get_db()

    # Ambil informasi device & ISP name
    device = await db.devices.find_one({"id": device_id}, {"_id": 0}) or {}
    isp_name = device.get("name", device.get("host", "NOC Billing Pro"))

    # Cari SSID dari settings jika tidak diisi
    if not ssid:
        ssid = device.get("ssid", "WiFi-Hotspot")

    # Login URL fallback
    if not login_url:
        # Gunakan IP device sebagai hotspot login page
        device_ip = device.get("host", "192.168.1.1")
        login_url = f"http://{device_ip}/login"

    # Ambil voucher dari DB
    q: dict = {"device_id": device_id}
    if profile:
        q["profile"] = profile

    db_vouchers = await db.hotspot_vouchers.find(q, {"_id": 0}).sort(
        "created_at", -1
    ).to_list(count)

    # Jika voucher DB kurang dari yang diminta, generate placeholder
    voucher_list = []
    for v in db_vouchers[:count]:
        pkg = {}
        if v.get("package_id"):
            pkg = await db.billing_packages.find_one({"id": v["package_id"]}, {"_id": 0}) or {}

        voucher_list.append({
            "ssid": ssid,
            "username": v.get("username", ""),
            "password": v.get("password", ""),
            "price": v.get("price") or pkg.get("price", 0),
            "validity": v.get("validity") or pkg.get("validity", ""),
            "uptime_limit": v.get("uptime_limit") or pkg.get("uptime_limit", ""),
            "profile_name": v.get("profile", profile or ""),
            "login_url": login_url,
        })

    if not voucher_list:
        raise HTTPException(
            404,
            "Tidak ada voucher ditemukan. Buat voucher terlebih dahulu di menu Hotspot Users."
        )

    # Potong sesuai count
    voucher_list = voucher_list[:count]

    # Generate PDF
    try:
        pdf_bytes = _build_pdf_bytes(
            vouchers=voucher_list,
            layout=layout,
            template=template,
            isp_name=isp_name,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[VoucherPDF] Error generate PDF: {e}", exc_info=True)
        raise HTTPException(500, f"Gagal generate PDF: {e}")

    profile_slug = profile.replace(" ", "_") or "all"
    filename = f"voucher_hotspot_{profile_slug}_{count}pcs.pdf"

    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.post("/generate-pdf-from-ids")
async def generate_voucher_pdf_from_ids(
    data: dict,
    user=Depends(require_write),
):
    """
    Generate PDF dari daftar voucher ID spesifik (dipilih user dari tabel).
    Body: { "voucher_ids": [...], "layout": 8, "template": "basic", "ssid": "...", "login_url": "..." }
    """
    voucher_ids: list = data.get("voucher_ids", [])
    layout: int = data.get("layout", 8)
    template: str = data.get("template", "basic")
    ssid: str = data.get("ssid", "WiFi-Hotspot")
    login_url: str = data.get("login_url", "http://hotspot.login")

    if not voucher_ids:
        raise HTTPException(400, "Tidak ada voucher ID")
    if layout not in (4, 8, 16):
        raise HTTPException(400, "Layout harus 4, 8, atau 16")
    if len(voucher_ids) > 200:
        raise HTTPException(400, "Maksimal 200 voucher sekaligus")

    db = get_db()

    voucher_list = []
    for vid in voucher_ids[:200]:
        v = await db.hotspot_vouchers.find_one({"id": vid}, {"_id": 0})
        if not v:
            continue
        pkg = {}
        if v.get("package_id"):
            pkg = await db.billing_packages.find_one({"id": v["package_id"]}, {"_id": 0}) or {}

        voucher_list.append({
            "ssid": ssid,
            "username": v.get("username", ""),
            "password": v.get("password", ""),
            "price": v.get("price") or pkg.get("price", 0),
            "validity": v.get("validity") or pkg.get("validity", ""),
            "uptime_limit": v.get("uptime_limit") or pkg.get("uptime_limit", ""),
            "profile_name": v.get("profile", ""),
            "login_url": login_url,
        })

    if not voucher_list:
        raise HTTPException(404, "Tidak ada voucher valid ditemukan")

    try:
        pdf_bytes = _build_pdf_bytes(
            vouchers=voucher_list,
            layout=layout,
            template=template,
            isp_name="NOC Billing Pro",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[VoucherPDF] Error: {e}", exc_info=True)
        raise HTTPException(500, f"Gagal generate PDF: {e}")

    filename = f"voucher_selected_{len(voucher_list)}pcs.pdf"
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
