# 📡 GoBGP Setup — NOC Billing Pro

## Arsitektur BGP Content Steering

```
HOST Ubuntu VPS
├─ gobgpd (systemd)  ← listen port 179/tcp BGP
│    ├─ BGP Peer: MikroTik-1 (10.x.x.x)
│    └─ BGP Peer: MikroTik-2 (10.x.x.x)
│
└─ Docker Network (172.17.0.1)
     └─ noc-billing-pro-backend (container)
          └─ nsenter → gobgp global rib add [prefix] community 65000:251
```

GoBGP **bukan container** — diinstall langsung di HOST agar backend bisa meng-inject route via `nsenter` (masuk ke namespace proses host).

---

## 📦 File yang Tersedia

| File | Fungsi |
|---|---|
| `install-gobgp.sh` | Script instalasi otomatis (recommended) |
| `gobgpd.conf` | Konfigurasi GoBGP utama (edit sesuai topologi) |
| `gobgpd.service` | Systemd unit file |
| `mikrotik-bgp-setup.rsc` | Script konfigurasi BGP peer di MikroTik |
| `gobgpd.conf_final` | Contoh config dengan 2 peer (referensi) |
| `gobgpd_minimalist_local.conf` | Contoh config minimalis |

---

## 🚀 Langkah Cepat (Quick Start)

### Prasyarat
- VPS Ubuntu 22.04 LTS
- Root access
- Port 179/tcp terbuka di firewall/cloud provider

### Step 1 — Edit konfigurasi GoBGP

Buka `gobgpd.conf` dan sesuaikan:

```toml
[global.config]
  as = 65000              # ← Ganti: AS Number server Anda
  router-id = "1.2.3.4"  # ← Ganti: IP publik / loopback VPS

[[neighbors]]
  [neighbors.config]
    neighbor-address = "10.0.0.1"  # ← Ganti: IP MikroTik
    peer-as = 65001                # ← Ganti: AS Number MikroTik
    description = "MikroTik-GW"
```

### Step 2 — Jalankan installer

```bash
cd /opt/noc-billing-pro/gobgp
sudo bash install-gobgp.sh
```

Script otomatis akan:
- ✅ Download GoBGP binary dari GitHub
- ✅ Install ke `/usr/local/bin/`
- ✅ Copy config ke `/etc/gobgpd/gobgpd.conf`
- ✅ Install & enable systemd service
- ✅ Buka port 179/tcp di UFW
- ✅ Start gobgpd

### Step 3 — Deploy NOC Billing Pro

```bash
cd /opt/noc-billing-pro
docker compose up -d
```

### Step 4 — Konfigurasi BGP peer di MikroTik

**MikroTik ROS v6:**
```routeros
/routing bgp peer add \
    name=noc-billing-pro \
    remote-address=IP-VPS \
    remote-as=65000 \
    multihop=yes \
    ttl=10 \
    update-source=IP-MIKROTIK
```

**MikroTik ROS v7:**
```routeros
/routing bgp connection add \
    name=noc-billing-pro \
    local.role=ebgp \
    local.address=IP-MIKROTIK \
    remote.address=IP-VPS/32 \
    remote.as=65000 \
    multihop=yes
```

---

## 🔧 Perintah Berguna

```bash
# Status daemon
sudo systemctl status gobgpd

# Lihat log real-time
sudo journalctl -u gobgpd -f

# Cek BGP peers dan status sesi
gobgp neighbor

# Lihat prefix yang sudah di-inject
gobgp global rib

# Restart setelah edit config
sudo systemctl restart gobgpd

# Reload config tanpa restart (SIGHUP)
sudo systemctl reload gobgpd

# Monitor log langsung
sudo tail -f /var/log/gobgpd.log
```

---

## 📊 Cara Kerja BGP Content Steering

1. **Toggle ON** policy di dashboard NOC Billing Pro (Peering Eye → Content Steering)
2. Backend resolve ASN/domain → dapat list prefix IPv4
3. Backend inject prefix ke GoBGP via `nsenter`:
   ```
   gobgp global rib add 1.2.3.0/24 nexthop IP-GATEWAY community 65000:251
   ```
4. GoBGP advertise prefix ke MikroTik via BGP dengan community tag
5. Export policy di GoBGP filter prefix per-peer (community match)
6. MikroTik menerima prefix → memasukkan ke routing table → traffic steering aktif

---

## 🗺️ Mapping Community ke Peer

| Community | MikroTik Peer |
|---|---|
| `65000:251` | Peer 1 (neighbor `10.x.x.251`) |
| `65000:252` | Peer 2 (neighbor `10.x.x.252`) |
| `65000:NNN` | Peer ke-N (sesuaikan di gobgpd.conf) |

---

## ❗ Troubleshooting

**GoBGP tidak start:**
```bash
sudo journalctl -u gobgpd -n 30 --no-pager
sudo gobgpd -f /etc/gobgpd/gobgpd.conf --log-level debug
```

**BGP session tidak Established:**
```bash
gobgp neighbor                        # cek state
telnet IP-MIKROTIK 179                # cek konektivitas
sudo tcpdump -i any port 179 -n       # cek paket BGP
```

**Prefix tidak masuk MikroTik:**
```bash
gobgp global rib                      # cek prefix ada di GoBGP
gobgp neighbor IP-MIKROTIK adj-out   # cek prefix dikirim ke peer
# Di MikroTik:
# /ip route print where bgp
```

**nsenter gagal dari container:**
```bash
# Pastikan docker-compose.yml punya:
# pid: "host"
# privileged: true
docker inspect noc-billing-pro-backend | grep -i pid
```
