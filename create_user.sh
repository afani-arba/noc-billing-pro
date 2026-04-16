#!/bin/bash
# Script untuk membuat atau mereset password Admin User
set -euo pipefail

cd "$(dirname "$0")"

echo "========================================="
echo "   NOC Billing Pro - Manage Users"
echo "========================================="
echo "Pilih opsi:"
echo "1) Buat User & Password Baru"
echo "2) Reset Password User Lama"
echo "3) Keluar"
read -r -p "Pilihan (1/2/3): " OPTION

case $OPTION in
    1)
        docker compose exec noc-backend python manage_user.py --create
        ;;
    2)
        docker compose exec noc-backend python manage_user.py --reset
        ;;
    3)
        exit 0
        ;;
    *)
        echo "Pilihan tidak valid."
        ;;
esac
