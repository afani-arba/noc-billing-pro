import { useState, useEffect, useRef } from "react";
import api from "@/lib/api";
import { Shield, Wifi, WifiOff, Save, Info, RefreshCw, Palette, Download, Upload, Database, CheckCircle, AlertTriangle, FileJson, CreditCard, Building } from "lucide-react";
import { useTheme } from "@/context/ThemeContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { toast } from "sonner";

// --- SSTP VPN Client Section ---
function SstpSection() {
  const [cfg, setCfg] = useState({ server: "", username: "", password: "", enabled: false });
  const [status, setStatus] = useState(null);
  const [saving, setSaving] = useState(false);
  const [disconnecting, setDisconnecting] = useState(false);
  const [showPass, setShowPass] = useState(false);

  const fetchStatus = () => {
    api.get("/sstp/status").then(r => setStatus(r.data)).catch(() => {});
  };

  useEffect(() => {
    api.get("/sstp/config").then(r => setCfg(c => ({ ...c, ...r.data }))).catch(() => {});
    fetchStatus();
    const iv = setInterval(fetchStatus, 8000);
    return () => clearInterval(iv);
  }, []);

  const handleSave = async () => {
    if (!cfg.server || !cfg.username || !cfg.password) {
      toast.error("Server Host, Username, dan Password harus diisi");
      return;
    }
    setSaving(true);
    try {
      const r = await api.put("/sstp/config", { ...cfg, enabled: true });
      toast.success(r.data.message || "SSTP VPN berhasil disambungkan!");
      setCfg(c => ({ ...c, enabled: true }));
      setTimeout(fetchStatus, 3000);
    } catch (e) {
      toast.error(e.response?.data?.detail || "Gagal menyambungkan SSTP VPN");
    }
    setSaving(false);
  };

  const handleDisconnect = async () => {
    if (!confirm("Putuskan koneksi SSTP VPN?")) return;
    setDisconnecting(true);
    try {
      await api.post("/sstp/disconnect");
      await api.put("/sstp/config", { ...cfg, enabled: false });
      setCfg(c => ({ ...c, enabled: false }));
      toast.success("SSTP VPN berhasil dimatikan.");
      setTimeout(fetchStatus, 2000);
    } catch (e) {
      toast.error(e.response?.data?.detail || "Gagal memutus SSTP VPN");
    }
    setDisconnecting(false);
  };

  const isOnline = status?.status === "online";
  const isDisabled = !status || status?.status === "disabled";

  return (
    <div className="bg-card border border-border rounded-sm p-4 sm:p-6 space-y-4" data-testid="sstp-section">
      <div className="flex items-start justify-between flex-wrap gap-2">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-sm bg-purple-500/10 flex items-center justify-center">
            <Shield className="w-4 h-4 text-purple-400" />
          </div>
          <div>
            <h2 className="text-base sm:text-lg font-semibold">SSTP VPN Client</h2>
            <p className="text-[10px] sm:text-xs text-muted-foreground">Koneksikan Server NOC-Sentinel ke MikroTik via SSTP (TCP/443) — aman untuk LXC/Docker</p>
          </div>
        </div>
        <div className={`flex items-center gap-2 px-3 py-1.5 rounded-md text-xs font-bold border transition-all ${
          isOnline
            ? "bg-green-500/10 text-green-400 border-green-500/20"
            : isDisabled
            ? "bg-secondary text-muted-foreground border-border"
            : "bg-red-500/10 text-red-400 border-red-500/20"
        }`}>
          {isOnline ? <Wifi className="w-4 h-4 animate-pulse" /> : <WifiOff className="w-4 h-4" />}
          <span>{isOnline ? `CONNECTED ${status?.endpoint ? "· " + status.endpoint : ""}` : isDisabled ? "DISABLED" : "DISCONNECTED"}</span>
        </div>
      </div>

      {isOnline && (
        <div className="grid grid-cols-2 gap-2">
          <div className="bg-green-500/5 border border-green-500/20 rounded-sm p-2.5 text-center">
            <p className="text-[10px] text-muted-foreground">VPN IP (interface: VPN)</p>
            <p className="text-sm font-mono font-bold text-green-400">{status?.endpoint || "—"}</p>
          </div>
          <div className="bg-secondary/30 border border-border rounded-sm p-2.5 text-center">
            <p className="text-[10px] text-muted-foreground">RX / TX</p>
            <p className="text-sm font-mono font-bold text-blue-400">
              {status?.rx_bytes ? `${(status.rx_bytes / 1024 / 1024).toFixed(1)} MB` : "—"}{" / "}
              {status?.tx_bytes ? `${(status.tx_bytes / 1024 / 1024).toFixed(1)} MB` : "—"}
            </p>
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <div className="sm:col-span-2 space-y-1.5">
          <Label className="text-xs text-muted-foreground">Server Host / IP MikroTik (dengan port bila bukan 443)</Label>
          <Input
            value={cfg.server}
            onChange={e => setCfg(c => ({ ...c, server: e.target.value }))}
            placeholder="vpn.mikrotik.id  atau  103.x.x.x:443"
            className="rounded-sm bg-background font-mono text-xs"
          />
          <p className="text-[10px] text-muted-foreground">SSTP berjalan di TCP — tidak butuh port UDP. Default port 443.</p>
        </div>
        <div className="space-y-1.5">
          <Label className="text-xs text-muted-foreground">Username VPN</Label>
          <Input
            value={cfg.username}
            onChange={e => setCfg(c => ({ ...c, username: e.target.value }))}
            placeholder="sstp-user"
            autoComplete="off"
            className="rounded-sm bg-background font-mono text-xs"
          />
        </div>
        <div className="space-y-1.5">
          <Label className="text-xs text-muted-foreground flex gap-1 justify-between">
            <span>Password VPN</span>
            <span
              className="text-[10px] text-muted-foreground cursor-pointer hover:underline"
              onClick={() => setShowPass(v => !v)}
            >
              {showPass ? "Sembunyikan" : "Tampilkan"}
            </span>
          </Label>
          <Input
            type={showPass ? "text" : "password"}
            value={cfg.password}
            onChange={e => setCfg(c => ({ ...c, password: e.target.value }))}
            placeholder="Password VPN MikroTik"
            autoComplete="new-password"
            className="rounded-sm bg-background font-mono text-xs"
          />
        </div>
      </div>

      <div className="flex gap-2 pt-2 border-t border-border/50">
        <Button
          onClick={handleSave}
          disabled={saving || disconnecting}
          size="sm"
          className="rounded-sm gap-2 bg-purple-600 hover:bg-purple-700 text-white"
        >
          <Wifi className="w-3.5 h-3.5" />
          {saving ? "Menyambungkan SSTP..." : isOnline ? "Reconnect / Update" : "Simpan & Connect"}
        </Button>
        {(isOnline || cfg.enabled) && (
          <Button
            onClick={handleDisconnect}
            disabled={saving || disconnecting}
            variant="outline"
            size="sm"
            className="rounded-sm gap-2 border-red-500/30 text-red-400 hover:bg-red-500/10"
          >
            <WifiOff className="w-3.5 h-3.5" />
            {disconnecting ? "Memutus..." : "Disconnect"}
          </Button>
        )}
      </div>

      <div className="mt-6 pt-4 border-t border-border/30">
        <div className="flex items-center gap-2 mb-3">
          <Info className="w-4 h-4 text-purple-400" />
          <h3 className="text-sm font-semibold text-slate-200">Cara Setting SSTP Server di MikroTik RouterOS</h3>
        </div>
        <p className="text-xs text-muted-foreground mb-4">
          Terapkan konfigurasi berikut di Terminal MikroTik agar server NOC-Sentinel dapat terhubung via SSTP.
        </p>

        {/* Step 1: Cert - WAJIB */}
        <div className="mb-3 p-3 rounded-sm bg-red-500/10 border border-red-500/30 text-red-400 text-xs flex gap-2">
          <Info className="w-4 h-4 flex-shrink-0 mt-0.5" />
          <div>
            <p className="font-bold mb-1">⚠️ WAJIB: Buat Sertifikat SSL dulu sebelum SSTP bisa konek!</p>
            <p className="text-muted-foreground">SSTP membutuhkan TLS — MikroTik dengan <code className="bg-black/30 px-1 rounded text-red-300">certificate=none</code> akan menyebabkan <strong>SSL handshake failure</strong>. Jalankan perintah berikut di Terminal MikroTik:</p>
          </div>
        </div>

        <div className="bg-black/40 border border-white/10 rounded-md p-3 font-mono text-[10px] sm:text-xs text-green-400/90 overflow-x-auto space-y-2">
          <p className="text-slate-500"># LANGKAH 1 — Buat Self-Signed Certificate (WAJIB untuk SSTP)</p>
          <p>/certificate add name=sstp-cert country=ID common-name=sstp-server key-usage=key-cert-sign,crl-sign,digital-signature,key-encipherment,tls-server</p>
          <p>/certificate sign sstp-cert</p>
          <p className="text-slate-500 mt-2"># LANGKAH 2 — Aktifkan SSTP Server dengan certificate</p>
          <p>/interface sstp-server server set enabled=yes certificate=sstp-cert</p>
          <p className="text-slate-500 mt-2"># LANGKAH 3 — Buat user PPP untuk NOC-Sentinel</p>
          <p>/ppp secret add name={cfg.username || "NOC"} password=****** service=sstp local-address=10.10.10.1 remote-address=10.10.10.2</p>
          <p className="text-slate-500 mt-2"># LANGKAH 4 — Izinkan port SSTP di firewall</p>
          <p>/ip firewall filter add chain=input protocol=tcp dst-port={cfg.server?.split(":")?.[1] || "443"} action=accept place-before=0 comment="Allow SSTP NOC"</p>
          <p className="text-slate-500 mt-2"># LANGKAH 5 — Verifikasi (setelah connect)</p>
          <p className="text-blue-400/80">ip addr show VPN  # interface bernama "VPN" (bukan ppp0)</p>
        </div>

        <div className="mt-3 p-3 rounded-sm bg-amber-500/10 border border-amber-500/20 text-amber-400 text-xs flex gap-2">
          <Info className="w-4 h-4 flex-shrink-0 mt-0.5" />
          <div>
            <p className="font-semibold mb-1">Mengapa SSTP lebih baik dari WireGuard untuk Docker/LXC?</p>
            <p className="text-muted-foreground leading-relaxed">
              SSTP berjalan di atas TCP/443 dan menggunakan parameter{" "}
              <code className="bg-black/30 px-1 rounded text-amber-300">nodefaultroute</code>{" "}
              yang memastikan koneksi VPN{" "}
              <strong>tidak membajak default gateway</strong> container. Ini menghilangkan
              penyebab utama error 502 Bad Gateway pada WireGuard di LXC.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}


// --- L2TP VPN Client Section ---
function L2tpSection() {
  const [cfg, setCfg] = useState({ server: "", username: "", password: "", enabled: false, auto_routes: "" });
  const [status, setStatus] = useState(null);
  const [saving, setSaving] = useState(false);
  const [disconnecting, setDisconnecting] = useState(false);
  const [showPass, setShowPass] = useState(false);

  const fetchStatus = () => {
    api.get("/l2tp/status").then(r => setStatus(r.data)).catch(() => {});
  };

  useEffect(() => {
    api.get("/l2tp/config").then(r => setCfg(c => ({ ...c, ...r.data }))).catch(() => {});
    fetchStatus();
    const iv = setInterval(fetchStatus, 8000);
    return () => clearInterval(iv);
  }, []);

  const handleSave = async () => {
    if (!cfg.server || !cfg.username || !cfg.password) {
      toast.error("Server Host, Username, dan Password harus diisi");
      return;
    }
    setSaving(true);
    try {
      const r = await api.put("/l2tp/config", { ...cfg, enabled: true });
      toast.success(r.data.message || "L2TP VPN berhasil disambungkan!");
      setCfg(c => ({ ...c, enabled: true }));
      setTimeout(fetchStatus, 3000);
    } catch (e) {
      toast.error(e.response?.data?.detail || "Gagal menyambungkan L2TP VPN");
    }
    setSaving(false);
  };

  const handleDisconnect = async () => {
    if (!confirm("Putuskan koneksi L2TP VPN?")) return;
    setDisconnecting(true);
    try {
      await api.post("/l2tp/disconnect");
      await api.put("/l2tp/config", { ...cfg, enabled: false });
      setCfg(c => ({ ...c, enabled: false }));
      toast.success("L2TP VPN berhasil dimatikan.");
      setTimeout(fetchStatus, 2000);
    } catch (e) {
      toast.error(e.response?.data?.detail || "Gagal memutus L2TP VPN");
    }
    setDisconnecting(false);
  };

  const isOnline = status?.status === "online";
  const isDisabled = !status || status?.status === "disabled";

  return (
    <div className="bg-card border border-border rounded-sm p-4 sm:p-6 space-y-4 shadow-sm" data-testid="l2tp-section">
      <div className="flex items-start justify-between flex-wrap gap-2">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-md bg-blue-500/10 flex items-center justify-center">
            <Wifi className="w-5 h-5 text-blue-400" />
          </div>
          <div>
            <h2 className="text-lg sm:text-xl font-bold text-slate-100 tracking-tight">L2TP VPN Client (Plain)</h2>
            <p className="text-xs text-muted-foreground mt-0.5">Koneksikan Server NOC-Sentinel ke MikroTik via L2TP (UDP/1701) — Tanpa IPsec</p>
          </div>
        </div>
        <div className={`flex items-center gap-2 px-3 py-1.5 rounded-md text-xs font-bold border transition-all ${
          isOnline
            ? "bg-green-500/10 text-green-400 border-green-500/20"
            : isDisabled
            ? "bg-secondary text-muted-foreground border-border"
            : "bg-red-500/10 text-red-400 border-red-500/20"
        }`}>
          {isOnline ? <Wifi className="w-4 h-4 animate-pulse" /> : <WifiOff className="w-4 h-4" />}
          <span>{isOnline ? `CONNECTED ${status?.endpoint ? "· " + status.endpoint : ""}` : isDisabled ? "DISABLED" : "DISCONNECTED"}</span>
        </div>
      </div>

      {isOnline && (
        <div className="grid grid-cols-2 gap-2">
          <div className="bg-green-500/5 border border-green-500/20 rounded-sm p-2.5 text-center">
            <p className="text-[10px] text-muted-foreground">VPN IP (ppp interface)</p>
            <p className="text-sm font-mono font-bold text-green-400">{status?.endpoint || "—"}</p>
          </div>
          <div className="bg-secondary/30 border border-border rounded-sm p-2.5 text-center">
            <p className="text-[10px] text-muted-foreground">RX / TX</p>
            <p className="text-sm font-mono font-bold text-blue-400">
              {status?.rx_bytes ? `${(status.rx_bytes / 1024 / 1024).toFixed(1)} MB` : "—"}{" / "}
              {status?.tx_bytes ? `${(status.tx_bytes / 1024 / 1024).toFixed(1)} MB` : "—"}
            </p>
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <div className="sm:col-span-2 space-y-1.5">
          <Label className="text-sm font-semibold text-slate-300">Server Host / IP MikroTik VPS</Label>
          <Input
            value={cfg.server}
            onChange={e => setCfg(c => ({ ...c, server: e.target.value }))}
            placeholder="vps.mikrotik.id atau 103.x.x.x"
            className="h-11 rounded-md bg-background/50 font-mono text-sm border-border/50 focus:border-blue-500/50"
          />
        </div>

        <div className="sm:col-span-2 space-y-1.5">
          <Label className="text-sm font-semibold text-slate-300">L2TP Auto Routes (Subnet Lokal)</Label>
          <Input
            value={cfg.auto_routes}
            onChange={e => setCfg(c => ({ ...c, auto_routes: e.target.value }))}
            placeholder="Contoh: 10.254.254.0/24, 192.168.1.0/24"
            className="h-11 rounded-md bg-background/50 font-mono text-sm border-border/50 focus:border-blue-500/50"
          />
          <p className="text-[10px] text-muted-foreground italic">Pisahkan dengan koma jika lebih dari satu subnet.</p>
        </div>

        <div className="space-y-1.5">
          <Label className="text-xs text-muted-foreground">Username L2TP</Label>
          <Input
            value={cfg.username}
            onChange={e => setCfg(c => ({ ...c, username: e.target.value }))}
            placeholder="l2tp-user"
            autoComplete="off"
            className="rounded-sm bg-background font-mono text-xs"
          />
        </div>
        <div className="space-y-1.5">
          <Label className="text-xs text-muted-foreground flex gap-1 justify-between">
            <span>Password L2TP</span>
            <span
              className="text-[10px] text-muted-foreground cursor-pointer hover:underline"
              onClick={() => setShowPass(v => !v)}
            >
              {showPass ? "Sembunyikan" : "Tampilkan"}
            </span>
          </Label>
          <Input
            type={showPass ? "text" : "password"}
            value={cfg.password}
            onChange={e => setCfg(c => ({ ...c, password: e.target.value }))}
            placeholder="Password L2TP"
            autoComplete="new-password"
            className="rounded-sm bg-background font-mono text-xs"
          />
        </div>
      </div>

      <div className="flex gap-2 pt-2 border-t border-border/50">
        <Button
          onClick={handleSave}
          disabled={saving || disconnecting}
          size="sm"
          className="rounded-sm gap-2 bg-blue-600 hover:bg-blue-700 text-white"
        >
          <Wifi className="w-3.5 h-3.5" />
          {saving ? "Menyambungkan L2TP..." : isOnline ? "Reconnect / Update" : "Simpan & Connect"}
        </Button>
        {(isOnline || cfg.enabled) && (
          <Button
            onClick={handleDisconnect}
            disabled={saving || disconnecting}
            variant="outline"
            size="sm"
            className="rounded-sm gap-2 border-red-500/30 text-red-400 hover:bg-red-500/10"
          >
            <WifiOff className="w-3.5 h-3.5" />
            {disconnecting ? "Memutus..." : "Disconnect"}
          </Button>
        )}
      </div>

      <div className="mt-4 p-3 rounded-sm bg-blue-500/10 border border-blue-500/30 text-blue-400 text-[11px] flex gap-2">
        <Info className="w-4 h-4 flex-shrink-0" />
        <p><strong>Note:</strong> L2TP ini berjalan secara native di host Ubuntu menggunakan xl2tpd. Pastikan port 1701 UDP di MikroTik VPS terbuka.</p>
      </div>
    </div>
  );
}


// --- Theme Section ---
function ThemeSection() {
  const { theme, setTheme, themes } = useTheme();
  return (
    <div className="bg-card border border-border rounded-sm p-4 sm:p-6 space-y-4" data-testid="theme-section">
      <div className="flex items-center gap-3">
        <div className="w-8 h-8 rounded-sm bg-blue-500/10 flex items-center justify-center">
          <Palette className="w-4 h-4 text-blue-400" />
        </div>
        <div>
          <h2 className="text-base sm:text-lg font-semibold">Tampilan (Global Theme)</h2>
          <p className="text-[10px] sm:text-xs text-muted-foreground">Pilih tema antarmuka NOC Billing Pro Anda</p>
        </div>
      </div>
      <div className="flex flex-col sm:flex-row gap-4 pt-2">
        {/* Cyber Glassmorphism */}
        <button onClick={() => setTheme('cyber')}
          className={`flex-1 p-4 rounded-sm border text-left transition-all relative overflow-hidden ${
            theme === 'cyber'
              ? 'border-[rgba(0,230,118,0.4)] bg-[rgba(0,230,118,0.06)]'
              : 'border-border bg-secondary/30 hover:border-[rgba(0,230,118,0.3)]'
          }`}>
          {theme === 'cyber' && (
            <div className="absolute top-0 left-0 right-0 h-0.5 bg-gradient-to-r from-[hsl(162,100%,50%)] to-[hsl(185,100%,50%)]" />
          )}
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-2">
              <div className="flex gap-1">
                <div className="w-2.5 h-2.5 rounded-full bg-[hsl(162,100%,50%)] shadow-[0_0_6px_rgba(0,230,118,0.8)]" />
                <div className="w-2.5 h-2.5 rounded-full bg-[hsl(185,100%,55%)] shadow-[0_0_6px_rgba(0,229,255,0.8)]" />
              </div>
              <h3 className="text-sm font-bold font-mono" style={{ color: "hsl(162,100%,60%)" }}>
                Cyber Glassmorphism
              </h3>
            </div>
            {theme === 'cyber' && (
              <span className="text-[9px] font-mono uppercase tracking-wider px-1.5 py-0.5 rounded"
                style={{ background: "rgba(0,230,118,0.1)", border: "1px solid rgba(0,230,118,0.3)", color: "hsl(162,100%,50%)" }}>
                AKTIF
              </span>
            )}
          </div>
          <p className="text-xs text-muted-foreground">Neon Green &amp; Cyan — NOC / Network Engineer aesthetic dengan glass effect.</p>
          <div className="mt-3 flex gap-1.5">
            {["hsl(162,100%,50%)", "hsl(185,100%,50%)", "hsl(270,70%,60%)", "hsl(38,90%,55%)", "hsl(0,80%,55%)"].map((c, i) => (
              <div key={i} className="w-3 h-3 rounded-full" style={{ backgroundColor: c, boxShadow: `0 0 4px ${c}` }} />
            ))}
          </div>
        </button>

        {/* Classic Navy */}
        <button onClick={() => setTheme('classic')}
          className={`flex-1 p-4 rounded-sm border text-left transition-all relative overflow-hidden ${
            theme === 'classic'
              ? 'border-primary bg-primary/10'
              : 'border-border bg-secondary/30 hover:border-primary/50'
          }`}>
          {theme === 'classic' && (
            <div className="absolute top-0 left-0 right-0 h-0.5 bg-primary" />
          )}
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-2">
              <div className="flex gap-1">
                <div className="w-2.5 h-2.5 rounded-full bg-blue-500" />
                <div className="w-2.5 h-2.5 rounded-full bg-blue-400/60" />
              </div>
              <h3 className="text-sm font-semibold">Classic Navy</h3>
            </div>
            {theme === 'classic' && (
              <span className="text-[9px] font-mono uppercase tracking-wider px-1.5 py-0.5 rounded bg-primary/10 border border-primary/30 text-primary">
                AKTIF
              </span>
            )}
          </div>
          <p className="text-xs text-muted-foreground">Corporate dark navy — tampilan clean dan profesional.</p>
          <div className="mt-3 flex gap-1.5">
            {["hsl(217,89%,56%)", "hsl(142,60%,42%)", "hsl(38,85%,52%)", "hsl(262,72%,58%)", "hsl(0,70%,52%)"].map((c, i) => (
              <div key={i} className="w-3 h-3 rounded-full" style={{ backgroundColor: c }} />
            ))}
          </div>
        </button>
      </div>
    </div>
  );
}

function SnmpPollingSection() {
  const [intervalVal, setIntervalVal] = useState(5);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api.get("/system/snmp-config").then(r => {
      if (r.data?.interval) setIntervalVal(r.data.interval);
    }).catch(e => console.error("Failed to fetch SNMP config", e));
  }, []);

  const handleSave = async () => {
    setSaving(true);
    try {
      const r = await api.put("/system/snmp-config", { interval: parseInt(intervalVal, 10) });
      toast.success(r.data.message || "Interval Polling berhasil diperbarui.");
    } catch (e) {
      toast.error(e.response?.data?.detail || "Gagal menyimpan interval Polling");
    }
    setSaving(false);
  };

  return (
    <div className="bg-card border border-border rounded-sm p-4 sm:p-6 space-y-4 shadow-sm" data-testid="snmp-polling-section">
      <div className="flex items-start justify-between flex-wrap gap-2">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-sm bg-blue-500/10 flex items-center justify-center">
            <RefreshCw className="w-4 h-4 text-blue-400" />
          </div>
          <div>
            <h2 className="text-base sm:text-lg font-semibold ">Kecepatan Polling Grafik (Live Traffic)</h2>
            <p className="text-[10px] sm:text-xs text-muted-foreground">Atur seberapa cepat / ringan tarikan data SNMP ke seluruh MikroTik Anda.</p>
          </div>
        </div>
      </div>

      <div className="pt-2">
        <div className="flex items-center gap-4">
          <input
            type="range" min="5" max="600" step="5"
            value={intervalVal} onChange={(e) => setIntervalVal(Number(e.target.value))}
            className="flex-1 accent-blue-500 hover:accent-blue-400 cursor-pointer"
          />
          <div className="w-[110px] text-right font-mono font-bold text-blue-400 text-sm bg-blue-950/30 px-3 py-1.5 rounded border border-blue-500/30">
            {intervalVal < 60 ? `${intervalVal} Detik` : `${Math.floor(intervalVal/60)} Mnt ${intervalVal%60 > 0 ? (intervalVal%60)+' Dtk' : ''}`}
          </div>
        </div>

        <div className="flex justify-between text-[10px] font-semibold text-muted-foreground mt-2 px-1">
          <span>5x Cepat (5s)</span>
          <span>Normal (30s)</span>
          <span>Ringan (10m)</span>
        </div>

        <div className="bg-amber-950/20 border border-amber-500/20 text-amber-500/80 p-3 rounded-md text-[11px] mt-4 flex gap-2">
          <Info className="w-4 h-4 flex-none shrink-0" />
          <p className="leading-relaxed"><strong>Rekomendasi:</strong> Jika Anda memiliki lebih dari 100 Mikrotik dan server CPU Anda kepanasan, geser tuas ini ke arah kanan arah angka <strong>30 Detik</strong> atau lebih. Jika dirasa masih kuat, biarkan di <strong>5 Detik</strong> agar pergerakan grafik Anda secepat kilat (Real-Time)!</p>
        </div>
      </div>

      <div className="flex gap-2 pt-3 border-t border-border/50">
        <Button onClick={handleSave} disabled={saving} size="sm" className="rounded-sm gap-2 bg-blue-600 hover:bg-blue-700 text-white">
          <Save className="w-3.5 h-3.5" /> {saving ? "Menyimpan Config..." : "Simpan Polling Interval"}
        </Button>
      </div>
    </div>
  );
}

// --- Device Backup & Restore Section ---
function DeviceBackupSection() {
  const [preview, setPreview] = useState(null);
  const [loading, setLoading] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [restoring, setRestoring] = useState(false);
  const [restoreMode, setRestoreMode] = useState("merge");
  const [restoreFile, setRestoreFile] = useState(null);
  const [restoreResult, setRestoreResult] = useState(null);
  const [dragging, setDragging] = useState(false);
  const fileInputRef = useRef(null);

  useEffect(() => { loadPreview(); }, []);

  const loadPreview = async () => {
    setLoading(true);
    try { const r = await api.get("/system/backup-preview"); setPreview(r.data); }
    catch (e) { console.error("Preview error", e); }
    setLoading(false);
  };

  const handleDownload = async () => {
    setDownloading(true);
    try {
      const r = await api.get("/system/backup-data", { responseType: "blob" });
      const url = window.URL.createObjectURL(new Blob([r.data]));
      const a = document.createElement("a");
      const ts = new Date().toISOString().slice(0, 19).replace(/[:T]/g, "-");
      a.href = url; a.download = `noc_sentinel_backup_${ts}.json`;
      document.body.appendChild(a); a.click(); a.remove();
      window.URL.revokeObjectURL(url);
      toast.success("Backup berhasil didownload!");
    } catch (e) { toast.error("Gagal download: " + (e.response?.data?.detail || e.message)); }
    setDownloading(false);
  };

  const handleFileChange = (file) => {
    if (!file) return;
    if (!file.name.endsWith(".json")) { toast.error("Pilih file .json backup NOC Sentinel"); return; }
    setRestoreFile(file); setRestoreResult(null);
  };

  const handleRestore = async () => {
    if (!restoreFile) { toast.error("Pilih file backup terlebih dahulu"); return; }
    const confirmMsg = restoreMode === "replace"
      ? "MODE REPLACE: Semua device AKAN DIHAPUS dan diganti. Lanjutkan?"
      : "Mode Merge: Device baru ditambahkan, yang ada diperbarui. Lanjutkan?";
    if (!confirm(confirmMsg)) return;
    setRestoring(true); setRestoreResult(null);
    try {
      const formData = new FormData();
      formData.append("file", restoreFile);
      const r = await api.post(`/system/restore-data?mode=${restoreMode}`, formData, {
        headers: { "Content-Type": "multipart/form-data" }
      });
      setRestoreResult({ success: true, ...r.data });
      toast.success(r.data.message);
      loadPreview(); setRestoreFile(null);
      if (fileInputRef.current) fileInputRef.current.value = "";
    } catch (e) {
      const errMsg = e.response?.data?.detail || "Gagal restore data";
      setRestoreResult({ success: false, message: errMsg });
      toast.error(errMsg);
    }
    setRestoring(false);
  };

  return (
    <div className="bg-card border border-border rounded-sm p-4 sm:p-6 space-y-5" data-testid="backup-section">
      <div className="flex items-center gap-3">
        <div className="w-8 h-8 rounded-sm bg-emerald-500/10 flex items-center justify-center">
          <Database className="w-4 h-4 text-emerald-400" />
        </div>
        <div>
          <h2 className="text-base sm:text-lg font-semibold">Backup &amp; Restore Data Device</h2>
          <p className="text-[10px] sm:text-xs text-muted-foreground">Export dan import seluruh data device NOC Sentinel ke/dari file JSON</p>
        </div>
        <button onClick={loadPreview} className="ml-auto text-muted-foreground hover:text-foreground transition-colors">
          <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />
        </button>
      </div>

      {preview && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          {[
            { label: "Total Device", value: preview.total_devices, color: "text-blue-400", bg: "bg-blue-500/10 border-blue-500/20" },
            { label: "Credential Preset", value: preview.total_credentials, color: "text-purple-400", bg: "bg-purple-500/10 border-purple-500/20" },
            { label: "Est. Ukuran File", value: `~${preview.estimated_size_kb} KB`, color: "text-amber-400", bg: "bg-amber-500/10 border-amber-500/20" },
            { label: "Format", value: "JSON v3.0", color: "text-emerald-400", bg: "bg-emerald-500/10 border-emerald-500/20" },
          ].map(s => (
            <div key={s.label} className={`border rounded-sm p-3 ${s.bg}`}>
              <div className={`text-lg font-bold ${s.color}`}>{s.value}</div>
              <div className="text-[10px] text-muted-foreground mt-0.5">{s.label}</div>
            </div>
          ))}
        </div>
      )}

      {preview?.sample_devices?.length > 0 && (
        <div className="bg-secondary/30 border border-border rounded-sm p-3">
          <p className="text-[10px] text-muted-foreground mb-2 font-semibold uppercase tracking-wider">Preview Device (5 pertama)</p>
          {preview.sample_devices.map((d) => (
            <div key={d.id} className="flex items-center gap-2 text-xs py-0.5">
              <div className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${d.status === "online" ? "bg-green-400" : "bg-red-400"}`} />
              <span className="font-medium truncate">{d.name}</span>
              <span className="text-muted-foreground ml-auto font-mono text-[10px]">{d.host}</span>
            </div>
          ))}
        </div>
      )}

      <div className="border border-emerald-500/20 rounded-sm p-4 space-y-3 bg-emerald-500/5">
        <div className="flex items-center gap-2">
          <Download className="w-4 h-4 text-emerald-400" />
          <h3 className="text-sm font-semibold text-emerald-400">Export Backup</h3>
        </div>
        <p className="text-xs text-muted-foreground">Download seluruh data device dan credential preset sebagai file JSON.</p>
        <Button id="btn-download-backup" onClick={handleDownload} disabled={downloading || !preview?.total_devices}
          size="sm" className="rounded-sm gap-2 bg-emerald-600 hover:bg-emerald-700 text-white">
          <Download className="w-3.5 h-3.5" />
          {downloading ? "Mengekspor..." : `Download Backup (${preview?.total_devices || 0} Device)`}
        </Button>
      </div>

      <div className="border border-blue-500/20 rounded-sm p-4 space-y-3 bg-blue-500/5">
        <div className="flex items-center gap-2">
          <Upload className="w-4 h-4 text-blue-400" />
          <h3 className="text-sm font-semibold text-blue-400">Import / Restore</h3>
        </div>
        <div className="flex gap-3">
          {[
            { val: "merge", label: "Merge", desc: "Tambah & update, tidak hapus yang ada", activeClass: "border-blue-500 bg-blue-500/10 text-blue-400" },
            { val: "replace", label: "Replace", desc: "Hapus semua, lalu import dari backup", activeClass: "border-red-500 bg-red-500/10 text-red-400" },
          ].map(m => (
            <button key={m.val} onClick={() => setRestoreMode(m.val)}
              className={`flex-1 p-2.5 rounded-sm border text-left transition-all text-xs ${restoreMode === m.val ? m.activeClass : "border-border bg-secondary/30 text-muted-foreground"}`}>
              <div className="font-semibold mb-0.5">{m.label}</div>
              <div className="text-[10px] opacity-80">{m.desc}</div>
            </button>
          ))}
        </div>
        <div
          onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => { e.preventDefault(); setDragging(false); handleFileChange(e.dataTransfer.files[0]); }}
          onClick={() => fileInputRef.current?.click()}
          className={`border-2 border-dashed rounded-sm p-6 text-center cursor-pointer transition-all ${
            dragging ? "border-blue-400 bg-blue-500/10" :
            restoreFile ? "border-emerald-500/50 bg-emerald-500/5" :
            "border-border hover:border-primary/40 hover:bg-secondary/20"}`}>
          <input ref={fileInputRef} type="file" accept=".json" className="hidden"
            onChange={(e) => handleFileChange(e.target.files[0])} />
          {restoreFile ? (
            <div className="flex items-center justify-center gap-2 text-sm">
              <FileJson className="w-5 h-5 text-emerald-400" />
              <span className="font-medium text-emerald-400">{restoreFile.name}</span>
              <span className="text-muted-foreground text-xs">({(restoreFile.size / 1024).toFixed(1)} KB)</span>
            </div>
          ) : (
            <div>
              <Upload className="w-6 h-6 text-muted-foreground mx-auto mb-2" />
              <p className="text-xs text-muted-foreground">Drag &amp; drop atau <span className="text-primary underline">klik pilih file</span></p>
              <p className="text-[10px] text-muted-foreground mt-1">noc_sentinel_backup_*.json</p>
            </div>
          )}
        </div>
        {restoreResult && (
          <div className={`flex gap-2 p-3 rounded-sm border text-xs ${restoreResult.success ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-400" : "bg-red-500/10 border-red-500/30 text-red-400"}`}>
            {restoreResult.success ? <CheckCircle className="w-4 h-4 flex-shrink-0" /> : <AlertTriangle className="w-4 h-4 flex-shrink-0" />}
            <div>
              <p className="font-semibold">{restoreResult.message}</p>
              {restoreResult.success && (
                <p className="text-[10px] mt-0.5 opacity-80">{restoreResult.restored_devices} device &bull; {restoreResult.skipped_devices} dilewati &bull; {restoreResult.restored_credentials} credential</p>
              )}
            </div>
          </div>
        )}
        {restoreMode === "replace" && (
          <div className="flex gap-2 p-3 rounded-sm bg-red-950/30 border border-red-500/30 text-red-400 text-xs">
            <AlertTriangle className="w-4 h-4 flex-shrink-0" />
            <p><strong>Peringatan:</strong> Mode Replace akan <strong>MENGHAPUS SEMUA device yang ada</strong> sebelum import!</p>
          </div>
        )}
        <Button id="btn-restore-backup" onClick={handleRestore} disabled={!restoreFile || restoring} size="sm"
          className={`rounded-sm gap-2 text-white ${restoreMode === "replace" ? "bg-red-600 hover:bg-red-700" : "bg-blue-600 hover:bg-blue-700"}`}>
          <Upload className="w-3.5 h-3.5" />
          {restoring ? "Merestore..." : `Restore (${restoreMode === "merge" ? "Merge" : "Replace Semua"})`}
        </Button>
      </div>
    </div>
  );
}

// --- Bank Account Section (untuk AI CS Tagihan Otomatis) ---
function BankAccountSection() {
  const [bankAccount, setBankAccount] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api.get("/system/bank-account").then(r => {
      if (r.data?.bank_account) setBankAccount(r.data.bank_account);
    }).catch(() => {});
  }, []);

  const handleSave = async () => {
    if (!bankAccount.trim()) { toast.error("Info rekening tidak boleh kosong"); return; }
    setSaving(true);
    try {
      const r = await api.put("/system/bank-account", { bank_account: bankAccount });
      toast.success(r.data.message || "Rekening bank berhasil disimpan!");
    } catch (e) {
      toast.error(e.response?.data?.detail || "Gagal menyimpan rekening bank");
    }
    setSaving(false);
  };

  return (
    <div className="bg-card border border-border rounded-sm p-4 sm:p-6 space-y-4" data-testid="bank-account-section">
      <div className="flex items-center gap-3">
        <div className="w-8 h-8 rounded-sm bg-green-500/10 flex items-center justify-center">
          <CreditCard className="w-4 h-4 text-green-400" />
        </div>
        <div>
          <h2 className="text-base sm:text-lg font-semibold">Rekening Bank Pembayaran</h2>
          <p className="text-[10px] sm:text-xs text-muted-foreground">Info rekening yang dikirim oleh AI Customer Service (Nova/Sherly) kepada pelanggan saat membuat tagihan voucher otomatis.</p>
        </div>
      </div>

      <div className="space-y-2">
        <Label className="text-xs text-muted-foreground">Format: [Nama Bank] [Nomor Rekening] a.n [Nama Pemilik]</Label>
        <Input
          value={bankAccount}
          onChange={e => setBankAccount(e.target.value)}
          placeholder="BCA 8520480189 a.n PT ARSYA BAROKAH ABADI"
          className="rounded-sm bg-background font-mono text-xs"
        />
        <p className="text-[10px] text-muted-foreground">Contoh: <span className="font-mono text-green-400">BCA 8520480189 a.n PT ARSYA BAROKAH ABADI</span></p>
      </div>

      <div className="flex gap-2 pt-2 border-t border-border/50">
        <Button onClick={handleSave} disabled={saving} size="sm" className="rounded-sm gap-2 bg-green-600 hover:bg-green-700 text-white">
          <Save className="w-3.5 h-3.5" />
          {saving ? "Menyimpan..." : "Simpan Rekening Bank"}
        </Button>
      </div>
    </div>
  );
}

function CompanyProfileSection() {
  const [profile, setProfile] = useState({ company_name: "", product_name: "", address: "", whatsapp_number: "", logo_base64: "" });
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api.get("/system/company-profile").then(r => {
      setProfile(p => ({ ...p, ...r.data }));
    }).catch(() => {});
  }, []);

  const handleSave = async () => {
    if (!profile.product_name.trim() || !profile.address.trim() || !profile.whatsapp_number.trim()) {
      toast.error("Nama Produk, Alamat, dan No WA wajib diisi.");
      return;
    }
    setSaving(true);
    try {
      const r = await api.put("/system/company-profile", profile);
      toast.success(r.data.message || "Profil Perusahaan berhasil disimpan!");
    } catch (e) {
      toast.error(e.response?.data?.detail || "Gagal menyimpan Profil Perusahaan");
    }
    setSaving(false);
  };

  const handleLogoUpload = (e) => {
    const file = e.target.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (ev) => {
      setProfile(p => ({ ...p, logo_base64: ev.target.result }));
    };
    reader.readAsDataURL(file);
  };

  return (
    <div className="bg-card border border-border rounded-sm p-4 sm:p-6 space-y-4" data-testid="company-profile-section">
      <div className="flex items-center gap-3">
        <div className="w-8 h-8 rounded-sm bg-orange-500/10 flex items-center justify-center">
          <Building className="w-4 h-4 text-orange-400" />
        </div>
        <div>
          <h2 className="text-base sm:text-lg font-semibold">Data Perusahaan</h2>
          <p className="text-[10px] sm:text-xs text-muted-foreground">Detail perusahaan untuk ditampilkan pada halaman Login Pelanggan.</p>
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-2">
        <div className="space-y-1.5">
          <Label className="text-xs text-muted-foreground">Nama Perusahaan (Opsional)</Label>
          <Input
            value={profile.company_name}
            onChange={e => setProfile(p => ({ ...p, company_name: e.target.value }))}
            placeholder="PT Arsya Barokah Abadi"
            className="rounded-sm bg-background text-xs"
          />
        </div>
        <div className="space-y-1.5">
          <Label className="text-xs text-muted-foreground">Nama Produk <span className="text-red-400">*</span></Label>
          <Input
            value={profile.product_name}
            onChange={e => setProfile(p => ({ ...p, product_name: e.target.value }))}
            placeholder="Bintang.Net"
            className="rounded-sm bg-background text-xs"
          />
        </div>
        <div className="sm:col-span-2 space-y-1.5">
          <Label className="text-xs text-muted-foreground">Alamat Perusahaan <span className="text-red-400">*</span></Label>
          <Input
            value={profile.address}
            onChange={e => setProfile(p => ({ ...p, address: e.target.value }))}
            placeholder="Kecamatan, Kabupaten, Provinsi"
            className="rounded-sm bg-background text-xs"
          />
        </div>
        <div className="sm:col-span-2 space-y-1.5">
          <Label className="text-xs text-muted-foreground">No WhatsApp CS (Pusat Bantuan) <span className="text-red-400">*</span></Label>
          <Input
            value={profile.whatsapp_number}
            onChange={e => setProfile(p => ({ ...p, whatsapp_number: e.target.value }))}
            placeholder="081234567890"
            className="rounded-sm bg-background text-xs"
          />
        </div>
        <div className="sm:col-span-2 space-y-1.5">
          <Label className="text-xs text-muted-foreground">Logo Perusahaan (Digunakan untuk cetak tagihan & kuitansi)</Label>
          <div className="flex items-center gap-4 mt-2">
            {profile.logo_base64 ? (
               <img src={profile.logo_base64} alt="Logo" className="w-16 h-16 object-contain bg-white rounded-md p-1 border" />
            ) : (
               <div className="w-16 h-16 flex items-center justify-center bg-secondary/50 rounded-md border border-dashed text-[10px] text-muted-foreground text-center px-1">Tanpa Logo</div>
            )}
            <div className="flex-1 max-w-sm">
              <Input type="file" accept="image/*" onChange={handleLogoUpload} className="text-xs cursor-pointer" />
              <p className="text-[10px] text-muted-foreground mt-1">Format gambar (PNG/JPG). Ukuran disarankan maksimal 500x500px.</p>
            </div>
            {profile.logo_base64 && (
              <Button size="sm" variant="outline" className="h-8 border-red-500/30 text-red-400 hover:bg-red-500/10 text-xs" onClick={() => setProfile(p => ({ ...p, logo_base64: "" }))}>Hapus</Button>
            )}
          </div>
        </div>
      </div>

      <div className="flex gap-2 pt-2 border-t border-border/50">
        <Button onClick={handleSave} disabled={saving} size="sm" className="rounded-sm gap-2 bg-orange-600 hover:bg-orange-700 text-white">
          <Save className="w-3.5 h-3.5" />
          {saving ? "Menyimpan..." : "Simpan Data Perusahaan"}
        </Button>
      </div>
    </div>
  );
}

export default function SettingsPage() {
  return (
    <div className="space-y-4 pb-16" data-testid="settings-page">
      <div>
        <h1 className="text-xl sm:text-2xl md:text-3xl font-bold tracking-tight">Pengaturan</h1>
        <p className="text-xs sm:text-sm text-muted-foreground">Pengaturan tampilan, koneksi VPN, dan manajemen data</p>
      </div>
      <ThemeSection />
      <CompanyProfileSection />
      <BankAccountSection />
      <SnmpPollingSection />
      <DeviceBackupSection />
      <SstpSection />
      <L2tpSection />
    </div>
  );
}
