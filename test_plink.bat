@echo off
echo y | "C:\Program Files\PuTTY\plink.exe" -ssh noc@172.16.1.1 -pw 123123 "echo 123123 | sudo -S docker logs noc-billing-pro-backend --tail 50"
