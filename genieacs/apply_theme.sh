#!/bin/bash
# =====================================================================
# GenieACS UI Theme Applicator
# =====================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" &> /dev/null && pwd)"
THEME_FILE="$SCRIPT_DIR/custom-grafana-theme.css"
CUSTOM_CSS="$SCRIPT_DIR/app-custom.css"
CONTAINER_NAME="noc-billing-pro-genieacs-ui"

# We must ensure the css file exists so Docker doesn't map it as a directory
touch "$CUSTOM_CSS"

echo "Mengekstrak CSS asli dari container $CONTAINER_NAME..."
# Jalankan silent fail jika container belum up (saat fresh install pertama)
docker exec $CONTAINER_NAME cat /usr/local/lib/node_modules/genieacs/public/app-LU66VFYW.css > "$SCRIPT_DIR/app-original.css" 2>/dev/null

if [ -s "$SCRIPT_DIR/app-original.css" ]; then
    echo "CSS asli berhasil diekstrak."
    cat "$SCRIPT_DIR/app-original.css" > "$CUSTOM_CSS"
else
    echo "[WARN] Gagal menyalin CSS asli. Pastikan image/container berjalan."
    # Fallback jika gagal ekstrak, kita tetap buat file agar map docker tidak error
    if [ ! -s "$CUSTOM_CSS" ]; then
        echo "/* Fallback CSS */" > "$CUSTOM_CSS"
    fi
fi

# Sisipkan tema Grafana ke bagian dalam CSS kustom
if [ -f "$THEME_FILE" ]; then
    echo "Menyuntikkan tema Grafana Dark Mode ke dalam CSS UI..."
    echo "" >> "$CUSTOM_CSS"
    cat "$THEME_FILE" >> "$CUSTOM_CSS"
    echo "Tema berhasil diaplikasikan ke app-custom.css"
else
    echo "[WARN] File $THEME_FILE tidak ditemukan!"
fi
