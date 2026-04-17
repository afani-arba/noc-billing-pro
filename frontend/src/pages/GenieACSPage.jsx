import { useState, useEffect, useCallback, useRef, useMemo } from "react";
import { useAuth } from "@/App";
import api from "@/lib/api";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import {
  Cpu, RefreshCw, Search, RotateCcw, AlertTriangle, CheckCircle2,
  Wifi, WifiOff, Zap, Settings2, Trash2, TriangleAlert, Save,
  Eye, EyeOff, LinkIcon, ServerIcon, AlertCircle, X, Radio,
  Gauge, Users, MonitorSmartphone, Signal, Network, ChevronRight,
  ListChecks, Check, Square, CheckSquare, Info, UserPlus, Loader2,
  ShieldCheck, Sparkles, Phone, MapPin, CalendarDays, Package
} from "lucide-react";

// â”€â”€ Helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

function timeAgo(isoStr) {
  if (!isoStr) return "—";
  const diff = Math.floor((Date.now() - new Date(isoStr).getTime()) / 1000);
  if (diff < 60) return `${diff}dtk lalu`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m lalu`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}j lalu`;
  return `${Math.floor(diff / 86400)}h lalu`;
}

function formatUptime(seconds) {
  if (!seconds && seconds !== 0) return "—";
  const secs = parseInt(seconds, 10);
  if (isNaN(secs) || secs <= 0) return "—";
  const d = Math.floor(secs / 86400);
  const h = Math.floor((secs % 86400) / 3600);
  const m = Math.floor((secs % 3600) / 60);
  if (d > 0) return `${d}h ${h}j`;
  if (h > 0) return `${h}j ${m}m`;
  return `${m} menit`;
}

function RxPowerBadge({ value }) {
  // FIX: cek lebih robust — handle "0", "0.0", angka nol, string kosong, N/A
  if (!value) return <span className="text-muted-foreground">—</span>;
  const num = parseFloat(value);
  if (isNaN(num)) return <span className="font-mono text-xs text-muted-foreground">—</span>;
  if (num === 0) return <span className="text-muted-foreground">—</span>;
  let color = "text-green-400";
  if (num < -27) color = "text-red-400";
  else if (num < -25) color = "text-yellow-400";
  return (
    <span className={`font-mono text-xs font-semibold ${color}`}>
      {num.toFixed(2)} <span className="text-[10px] font-normal opacity-70">dBm</span>
    </span>
  );
}

// â”€â”€ Stats Bar â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

function StatsBar({ stats, loading }) {
  const items = [
    { label: "Total CPE", value: stats?.total ?? "—", color: "text-foreground" },
    { label: "Online", value: stats?.online ?? "—", color: "text-green-400" },
    { label: "Offline", value: stats?.offline ?? "—", color: "text-red-400" },
    { label: "Faults", value: stats?.faults ?? "—", color: "text-yellow-400" },
  ];
  return (
    <div className="flex flex-wrap gap-3">
      {items.map((s) => (
        <div key={s.label} className="bg-secondary/30 border border-border rounded-sm px-4 py-2 flex flex-col items-center min-w-[80px]">
          <span className={`text-xl font-bold font-mono ${s.color} ${loading ? "animate-pulse" : ""}`}>{s.value}</span>
          <span className="text-[10px] text-muted-foreground uppercase tracking-wider">{s.label}</span>
        </div>
      ))}
    </div>
  );
}

// â”€â”€ Device Detail / Edit Modal â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

function DeviceModal({ device, onClose, isAdmin, onRefreshed }) {
  const [form, setForm] = useState({
    ssid: device.ssid || "",
    wpa_key: "",
    pppoe_username: device.pppoe_username || "",
    pppoe_password: "",
  });
  const [showWpa, setShowWpa] = useState(false);
  const [showPppPwd, setShowPppPwd] = useState(false);
  const [saving, setSaving] = useState(false);
  const [summoning, setSummoning] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [rebooting, setRebooting] = useState(false);
  const [isolatingWlan, setIsolatingWlan] = useState(false);
  const overlayRef = useRef(null);

  const encId = encodeURIComponent(device.id);

  const setParam = async (name, value, type = "xsd:string") => {
    await api.post(`/genieacs/devices/${encId}/set-parameter`, { name, value, type });
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      if (form.wpa_key && form.wpa_key.length < 8) {
        toast.error("Password WiFi (WPA Key) minimal 8 karakter!");
        setSaving(false);
        return;
      }

      const tasks = [];
      if (form.ssid && form.ssid !== device.ssid) {
        tasks.push(setParam(
          "InternetGatewayDevice.LANDevice.1.WLANConfiguration.1.SSID",
          form.ssid
        ));
      }
      if (form.wpa_key) {
        tasks.push(setParam(
          "InternetGatewayDevice.LANDevice.1.WLANConfiguration.1.PreSharedKey.1.KeyPassphrase",
          form.wpa_key
        ));
      }
      if (form.pppoe_username && form.pppoe_username !== device.pppoe_username) {
        tasks.push(setParam(
          "InternetGatewayDevice.WANDevice.1.WANConnectionDevice.1.WANPPPConnection.1.Username",
          form.pppoe_username
        ));
      }
      if (form.pppoe_password) {
        tasks.push(setParam(
          "InternetGatewayDevice.WANDevice.1.WANConnectionDevice.1.WANPPPConnection.1.Password",
          form.pppoe_password
        ));
      }
      if (tasks.length === 0) { toast.info("Tidak ada perubahan yang disimpan"); setSaving(false); return; }
      await Promise.all(tasks);
      toast.success(`${tasks.length} parameter berhasil diset ke ${device.model || device.id}`);
      onRefreshed?.();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Gagal menyimpan parameter");
    }
    setSaving(false);
  };

  const doAction = async (action, label, setLoading) => {
    setLoading(true);
    try {
      await api.post(`/genieacs/devices/${encId}/${action}`);
      toast.success(`${label} dikirim ke ${device.model || device.id}`);
      if (action === "refresh") onRefreshed?.();
    } catch (e) {
      toast.error(e.response?.data?.detail || `${label} gagal`);
    }
    setLoading(false);
  };

  const toggleHardIsolate = async (enable) => {
    setIsolatingWlan(true);
    try {
      await api.post(`/genieacs/devices/${encId}/hard-isolate`, { enable });
      toast.success(enable ? "Perintah matikan WiFi dikirim (Hard Isolate)" : "Perintah nyalakan WiFi dikirim");
      onRefreshed?.();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Gagal mengatur status WiFi");
    }
    setIsolatingWlan(false);
  };

  const infoRows = [
    { label: "Device ID", value: device.id, mono: true },
    { label: "Manufacturer", value: device.manufacturer || "—" },
    { label: "Model", value: device.model || "—" },
    { label: "Product Class", value: device.product_class || "—" },
    { label: "Serial", value: device.serial || "—", mono: true },
    { label: "Firmware", value: device.firmware || "—", mono: true },
    { label: "IP PPPoE", value: device.pppoe_ip || "—", mono: true },
    { label: "ID PPPoE", value: device.pppoe_username || "—", mono: true },
    { label: "SSID", value: device.ssid || "—" },
    { label: "Active Device", value: device.active_devices ?? "—" },
    { label: "Redaman ONT", value: device.rx_power ? `${parseFloat(device.rx_power).toFixed(2)} dBm` : "—", mono: true },
    { label: "Uptime", value: device.uptime || "—" },
    { label: "Terakhir Aktif", value: timeAgo(device.last_inform) },
    { label: "Registered", value: timeAgo(device.registered) },
  ];

  return (
    <div
      ref={overlayRef}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4"
      onClick={(e) => { if (e.target === overlayRef.current) onClose(); }}
    >
      <div className="bg-card border border-border rounded-sm w-full max-w-2xl max-h-[90vh] overflow-y-auto shadow-2xl">
        {/* Header */}
        <div className="sticky top-0 bg-card border-b border-border px-4 py-3 flex items-center justify-between z-10">
          <div className="flex items-center gap-2">
            <div className={`w-2 h-2 rounded-full flex-shrink-0 ${device.online ? "bg-green-500 animate-pulse" : "bg-red-500"}`} />
            <span className="font-semibold text-sm tracking-wide">
              {device.model || "Device"} — Detail &amp; Edit
            </span>
            <Badge variant="outline" className={`text-[10px] rounded-sm ml-1 ${device.online ? "border-green-500/40 text-green-400" : "border-red-500/40 text-red-400"}`}>
              {device.online ? "Online" : "Offline"}
            </Badge>
          </div>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground transition-colors">
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="p-4 space-y-5">
          {/* Quick Actions */}
          <div className="flex flex-wrap gap-2">
            <Button size="sm" variant="outline" className="rounded-sm h-8 text-xs gap-1.5 border-cyan-500/30 text-cyan-400 hover:bg-cyan-500/10"
              disabled={summoning} onClick={() => doAction("summon", "Summon", setSummoning)}>
              <Zap className={`w-3.5 h-3.5 ${summoning ? "animate-pulse" : ""}`} />
              {summoning ? "Summoning..." : "Summon"}
            </Button>
            <Button size="sm" variant="outline" className="rounded-sm h-8 text-xs gap-1.5"
              disabled={refreshing} onClick={() => doAction("refresh", "Refresh", setRefreshing)}>
              <RefreshCw className={`w-3.5 h-3.5 ${refreshing ? "animate-spin" : ""}`} />
              {refreshing ? "Refreshing..." : "Refresh"}
            </Button>
            {isAdmin && (
              <>
                <Button size="sm" variant="outline" className="rounded-sm h-8 text-xs gap-1.5 border-orange-500/30 text-orange-400 hover:bg-orange-500/10"
                  disabled={rebooting} onClick={() => doAction("reboot", "Reboot", setRebooting)}>
                  <RotateCcw className={`w-3.5 h-3.5 ${rebooting ? "animate-spin" : ""}`} />
                  {rebooting ? "Rebooting..." : "Reboot"}
                </Button>
                <Button size="sm" variant="outline" className="rounded-sm h-8 text-xs gap-1.5 border-red-500/30 text-red-400 hover:bg-red-500/10"
                  title="Matikan akses pemancar WiFi WLAN pada perangkat pelanggan"
                  disabled={isolatingWlan} onClick={() => toggleHardIsolate(true)}>
                  <WifiOff className={`w-3.5 h-3.5 ${isolatingWlan ? "animate-pulse" : ""}`} />
                  {isolatingWlan ? "Memproses..." : "Matikan WiFi"}
                </Button>
                <Button size="sm" variant="outline" className="rounded-sm h-8 text-xs gap-1.5 border-green-500/30 text-green-400 hover:bg-green-500/10"
                  title="Aktifkan kembali pemancar WiFi WLAN pada perangkat pelanggan"
                  disabled={isolatingWlan} onClick={() => toggleHardIsolate(false)}>
                  <Wifi className={`w-3.5 h-3.5 ${isolatingWlan ? "animate-pulse" : ""}`} />
                  Nyalakan WiFi
                </Button>
              </>
            )}
          </div>

          {/* Info Grid */}
          <div>
            <p className="text-[10px] uppercase tracking-widest text-muted-foreground mb-2 font-medium">Informasi Perangkat</p>
            <div className="grid grid-cols-2 gap-x-4 gap-y-1.5">
              {infoRows.map(r => (
                <div key={r.label} className="flex items-start justify-between py-1 border-b border-border/30 last:border-0 col-span-1">
                  <span className="text-[11px] text-muted-foreground flex-shrink-0">{r.label}</span>
                  <span className={`text-[11px] text-right max-w-[180px] truncate ${r.mono ? "font-mono" : ""} ${
                    r.label === "Redaman ONT" && device.rx_power
                      // FIX: pastikan rx_power ada dan bukan nol sebelum cek threshold
                      ? (parseFloat(device.rx_power) < -27 ? "text-red-400"
                          : parseFloat(device.rx_power) < -25 ? "text-yellow-400"
                          : "text-green-400")
                      : "text-foreground"
                  }`}>
                    {r.value}
                  </span>
                </div>
              ))}
            </div>
          </div>

          {/* Edit Form — Admin only */}
          {isAdmin && (
            <div>
              <p className="text-[10px] uppercase tracking-widest text-muted-foreground mb-3 font-medium">Edit Parameter</p>
              <div className="space-y-3">
                {/* WiFi */}
                <div className="p-3 bg-secondary/20 border border-border/50 rounded-sm space-y-3">
                  <p className="text-xs font-semibold text-foreground flex items-center gap-1.5">
                    <Radio className="w-3.5 h-3.5 text-primary" /> WiFi
                  </p>
                  <div className="grid grid-cols-2 gap-3">
                    <div className="space-y-1">
                      <Label className="text-[10px] text-muted-foreground uppercase tracking-wide">SSID</Label>
                      <Input value={form.ssid} onChange={e => setForm(f => ({ ...f, ssid: e.target.value }))}
                        placeholder="Nama WiFi" className="rounded-sm text-xs h-8" />
                    </div>
                    <div className="space-y-1">
                      <Label className="text-[10px] text-muted-foreground uppercase tracking-wide">WPA Key / Password</Label>
                      <div className="relative">
                        <Input value={form.wpa_key} onChange={e => setForm(f => ({ ...f, wpa_key: e.target.value }))}
                          type={showWpa ? "text" : "password"}
                          placeholder="(kosong = tidak diganti)" className="rounded-sm text-xs h-8 pr-8" />
                        <button type="button" onClick={() => setShowWpa(v => !v)}
                          className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground">
                          {showWpa ? <EyeOff className="w-3 h-3" /> : <Eye className="w-3 h-3" />}
                        </button>
                      </div>
                    </div>
                  </div>
                </div>

                {/* PPPoE */}
                <div className="p-3 bg-secondary/20 border border-border/50 rounded-sm space-y-3">
                  <p className="text-xs font-semibold text-foreground flex items-center gap-1.5">
                    <Network className="w-3.5 h-3.5 text-primary" /> PPPoE
                  </p>
                  <div className="grid grid-cols-2 gap-3">
                    <div className="space-y-1">
                      <Label className="text-[10px] text-muted-foreground uppercase tracking-wide">Username PPPoE</Label>
                      <Input value={form.pppoe_username} onChange={e => setForm(f => ({ ...f, pppoe_username: e.target.value }))}
                        placeholder="username@isp" className="rounded-sm text-xs h-8 font-mono" />
                    </div>
                    <div className="space-y-1">
                      <Label className="text-[10px] text-muted-foreground uppercase tracking-wide">Password PPPoE</Label>
                      <div className="relative">
                        <Input value={form.pppoe_password} onChange={e => setForm(f => ({ ...f, pppoe_password: e.target.value }))}
                          type={showPppPwd ? "text" : "password"}
                          placeholder="(kosong = tidak diganti)" className="rounded-sm text-xs h-8 pr-8" />
                        <button type="button" onClick={() => setShowPppPwd(v => !v)}
                          className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground">
                          {showPppPwd ? <EyeOff className="w-3 h-3" /> : <Eye className="w-3 h-3" />}
                        </button>
                      </div>
                    </div>
                  </div>
                </div>

                <Button onClick={handleSave} disabled={saving} className="rounded-sm gap-2 h-9 text-xs w-full">
                  <Save className="w-3.5 h-3.5" />{saving ? "Menyimpan..." : "Simpan Perubahan"}
                </Button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ── ZTP Modal: Aktivasi Pelanggan Baru ──────────────────────────────────────────────

function generatePassword(len = 10) {
  const chars = "abcdefghjkmnpqrstuvwxyz23456789";
  return Array.from({ length: len }, () => chars[Math.floor(Math.random() * chars.length)]).join("");
}

function toSlug(name) {
  return name
    .toLowerCase()
    .normalize("NFD").replace(/[\u0300-\u036f]/g, "")
    .replace(/\s+/g, "_")
    .replace(/[^a-z0-9_]/g, "")
    .slice(0, 20);
}

function ZTPModal({ device, onClose, onSuccess }) {
  const overlayRef = useRef(null);
  const [options, setOptions] = useState({ mikrotik_devices: [], billing_packages: [] });
  const [loadingOptions, setLoadingOptions] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [steps, setSteps] = useState(null);
  const [result, setResult] = useState(null);
  const [showPppPwd, setShowPppPwd] = useState(false);
  const [showWifiPwd, setShowWifiPwd] = useState(false);
  const [mtProfiles, setMtProfiles] = useState([]);
  const [loadingProfiles, setLoadingProfiles] = useState(false);

  const [form, setForm] = useState({
    customer_name: "",
    phone: "",
    address: "",
    pppoe_username: "",
    pppoe_password: generatePassword(),
    mikrotik_device_id: "",
    mikrotik_profile: "",
    package_id: "",
    due_day: 10,
    ssid: device.ssid || "",
    wifi_password: generatePassword(12),
    vlan_id: "",
    installation_fee: "",
    billing_type: "prepaid",
    payment_status: "belum_bayar",
    use_radius: true,
  });

  useEffect(() => {
    if (form.mikrotik_device_id) {
      setLoadingProfiles(true);
      api.get(`/genieacs/mikrotik-profiles/${form.mikrotik_device_id}`)
        .then(r => {
          setMtProfiles(r.data || []);
          setLoadingProfiles(false);
        })
        .catch(() => setLoadingProfiles(false));
    } else {
      setMtProfiles([]);
    }
  }, [form.mikrotik_device_id]);

  // Auto-select PPP Profile when package changes
  useEffect(() => {
    if (form.package_id && options.billing_packages.length > 0) {
      const pkg = options.billing_packages.find(p => p.id === form.package_id);
      if (pkg && pkg.profile_name) {
        setForm(f => ({ ...f, mikrotik_profile: pkg.profile_name }));
      }
    }
  }, [form.package_id, options.billing_packages]);

  const handleNameChange = (val) => {
    setForm(f => ({
      ...f,
      customer_name: val,
      pppoe_username: f.pppoe_username || toSlug(val),
      ssid: f.ssid || (val.split(" ")[0] + " Home"),
    }));
  };

  useEffect(() => {
    api.get("/genieacs/activation-options")
      .then(r => setOptions(r.data))
      .catch(() => toast.error("Gagal memuat opsi aktivasi"))
      .finally(() => setLoadingOptions(false));
  }, []);

  const handleSubmit = async () => {
    if (!form.customer_name.trim()) return toast.error("Nama pelanggan wajib diisi");
    if (!form.pppoe_username.trim()) return toast.error("Username PPPoE wajib diisi");
    if (!form.pppoe_password.trim()) return toast.error("Password PPPoE wajib diisi");
    if (!form.mikrotik_device_id) return toast.error("Pilih router MikroTik terlebih dahulu");
    if (!form.mikrotik_profile) return toast.error("Pilih profile PPP MikroTik");

    setSubmitting(true);
    setSteps([
      { step: "MikroTik PPPoE Secret", ok: null, message: "Menghubungi MikroTik..." },
      { step: "GenieACS / TR-069 Provision", ok: null, message: "Mengirim konfigurasi ke ONT..." },
      { step: "Billing \u2014 Pendaftaran Pelanggan", ok: null, message: "Mendaftarkan ke sistem billing..." },
    ]);
    try {
      const encId = encodeURIComponent(device.id);
      const payload = { ...form, installation_fee: Number(form.installation_fee) || 0 };
      const r = await api.post(`/genieacs/devices/${encId}/activate-customer`, payload);
      setSteps(r.data.steps);
      setResult(r.data);
      if (r.data.success) {
        toast.success("Aktivasi pelanggan berhasil!");
        onSuccess?.();
      } else {
        toast.warning("Aktivasi selesai dengan beberapa kegagalan. Periksa detail di bawah.");
      }
    } catch (e) {
      toast.error(e.response?.data?.detail || "Aktivasi gagal");
      setSteps(null);
    }
    setSubmitting(false);
  };

  return (
    <div
      ref={overlayRef}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4"
      onClick={(e) => { if (e.target === overlayRef.current && !submitting) onClose(); }}
    >
      <div className="bg-card border border-border rounded-sm w-full max-w-2xl max-h-[92vh] overflow-y-auto shadow-2xl">
        {/* Header */}
        <div className="sticky top-0 bg-card border-b border-border px-4 py-3 flex items-center justify-between z-10">
          <div className="flex items-center gap-2">
            <div className="w-7 h-7 rounded-sm bg-green-500/20 flex items-center justify-center flex-shrink-0">
              <UserPlus className="w-4 h-4 text-green-400" />
            </div>
            <div>
              <p className="font-semibold text-sm">Aktivasi Pelanggan Baru &mdash; ZTP</p>
              <p className="text-[10px] text-muted-foreground">
                {device.manufacturer || ""} {device.model || device.id} {device.serial ? `· SN: ${device.serial}` : ""}
              </p>
            </div>
          </div>
          <button onClick={onClose} disabled={submitting} className="text-muted-foreground hover:text-foreground transition-colors disabled:opacity-30">
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="p-4 space-y-4">
          {/* Step Result Display */}
          {steps && (
            <div className="space-y-2">
              <p className="text-[10px] uppercase tracking-widest text-muted-foreground font-medium">Status Proses</p>
              {steps.map((s, i) => (
                <div key={i} className={`flex items-start gap-3 p-2.5 rounded-sm border text-xs ${
                  s.ok === null ? "bg-secondary/20 border-border text-muted-foreground" :
                  s.ok ? "bg-green-500/10 border-green-500/30 text-green-300" :
                  "bg-red-500/10 border-red-500/30 text-red-300"
                }`}>
                  <div className="flex-shrink-0 mt-0.5">
                    {s.ok === null ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> :
                     s.ok ? <CheckCircle2 className="w-3.5 h-3.5" /> :
                     <AlertCircle className="w-3.5 h-3.5" />}
                  </div>
                  <div>
                    <p className="font-semibold">{s.step}</p>
                    <p className="opacity-80 mt-0.5">{s.message}</p>
                  </div>
                </div>
              ))}
              {result && (
                <div className={`p-3 rounded-sm border text-xs font-semibold ${
                  result.success
                    ? "bg-green-500/10 border-green-500/30 text-green-300"
                    : "bg-yellow-500/10 border-yellow-500/30 text-yellow-300"
                }`}>
                  {result.summary}
                  {result.client_id && (
                    <p className="font-normal mt-1 text-muted-foreground">
                      Client ID: <span className="font-mono text-foreground">{result.client_id}</span>
                    </p>
                  )}
                </div>
              )}
            </div>
          )}

          {/* Form (hide when done) */}
          {!result && (
            <>
              {/* ONT Info */}
              <div className="p-3 bg-primary/5 border border-primary/20 rounded-sm">
                <p className="text-[10px] uppercase tracking-widest text-primary/70 font-medium mb-2">ONT yang Akan Dikonfigurasi</p>
                <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-[11px]">
                  <div className="flex justify-between"><span className="text-muted-foreground">Model</span><span>{device.model || "—"}</span></div>
                  <div className="flex justify-between"><span className="text-muted-foreground">Serial</span><span className="font-mono">{device.serial || "—"}</span></div>
                  <div className="flex justify-between"><span className="text-muted-foreground">Manufacturer</span><span>{device.manufacturer || "—"}</span></div>
                  <div className="flex justify-between"><span className="text-muted-foreground">Status</span>
                    <span className={device.online ? "text-green-400" : "text-yellow-400"}>
                      {device.online ? "Online ✓" : "Offline (config akan dikirim saat ONT online)"}
                    </span>
                  </div>
                </div>
              </div>

              {/* Section 1: Customer Info */}
              <div className="space-y-3">
                <p className="text-[10px] uppercase tracking-widest text-muted-foreground font-medium flex items-center gap-1.5">
                  <Users className="w-3.5 h-3.5" /> Data Pelanggan
                </p>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div className="space-y-1 sm:col-span-2">
                    <Label className="text-[10px] text-muted-foreground uppercase">Nama Lengkap <span className="text-destructive">*</span></Label>
                    <Input
                      value={form.customer_name}
                      onChange={e => handleNameChange(e.target.value)}
                      placeholder="Budi Santoso"
                      className="rounded-sm text-xs h-8"
                    />
                  </div>
                  <div className="space-y-1">
                    <Label className="text-[10px] text-muted-foreground uppercase flex items-center gap-1"><Phone className="w-3 h-3" /> No. HP</Label>
                    <Input value={form.phone} onChange={e => setForm(f => ({ ...f, phone: e.target.value }))}
                      placeholder="0812xxxx" className="rounded-sm text-xs h-8" />
                  </div>
                  <div className="space-y-1">
                    <Label className="text-[10px] text-muted-foreground uppercase flex items-center gap-1"><CalendarDays className="w-3 h-3" /> Tanggal Jatuh Tempo</Label>
                    <Input type="number" min={1} max={28} value={form.due_day}
                      onChange={e => setForm(f => ({ ...f, due_day: parseInt(e.target.value) || 10 }))}
                      className="rounded-sm text-xs h-8" placeholder="10" />
                    <p className="text-[9px] text-muted-foreground">Hari tagihan tiap bulan (1-28)</p>
                  </div>
                  <div className="space-y-1 sm:col-span-2">
                    <Label className="text-[10px] text-muted-foreground uppercase flex items-center gap-1"><MapPin className="w-3 h-3" /> Alamat</Label>
                    <Input value={form.address} onChange={e => setForm(f => ({ ...f, address: e.target.value }))}
                      placeholder="Jl. Merdeka No. 1" className="rounded-sm text-xs h-8" />
                  </div>
                </div>
              </div>

              {/* Section 2: Network / MikroTik */}
              <div className="space-y-3">
                <p className="text-[10px] uppercase tracking-widest text-muted-foreground font-medium flex items-center gap-1.5">
                  <Network className="w-3.5 h-3.5" /> Konfigurasi PPPoE
                </p>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div className="space-y-1">
                    <Label className="text-[10px] text-muted-foreground uppercase">Router MikroTik <span className="text-destructive">*</span></Label>
                    {loadingOptions ? (
                      <div className="h-8 bg-secondary/30 rounded-sm animate-pulse" />
                    ) : (
                      <select
                        value={form.mikrotik_device_id}
                        onChange={e => setForm(f => ({ ...f, mikrotik_device_id: e.target.value, mikrotik_profile: "" }))}
                        className="w-full h-8 text-xs rounded-sm border border-input bg-background px-2 text-foreground"
                      >
                        <option value="">-- Pilih Router --</option>
                        {options.mikrotik_devices.map(d => (
                          <option key={d.id} value={d.id}>{d.name} ({d.ip_address})</option>
                        ))}
                      </select>
                    )}
                  </div>
                  <div className="space-y-1">
                    <Label className="text-[10px] text-muted-foreground uppercase">PPP Profile (MikroTik) <span className="text-destructive">*</span></Label>
                    {loadingProfiles ? (
                      <div className="h-8 bg-secondary/30 rounded-sm animate-pulse" />
                    ) : (
                      <select
                        value={form.mikrotik_profile}
                        disabled={!form.mikrotik_device_id}
                        onChange={e => setForm(f => ({ ...f, mikrotik_profile: e.target.value }))}
                        className="w-full h-8 text-xs rounded-sm border border-input bg-background px-2 text-foreground"
                      >
                        <option value="">-- Pilih Profile --</option>
                        {mtProfiles.map(p => (
                          <option key={p.name} value={p.name}>{p.name}</option>
                        ))}
                      </select>
                    )}
                  </div>
                  <div className="space-y-1">
                    <Label className="text-[10px] text-muted-foreground uppercase">Username PPPoE <span className="text-destructive">*</span></Label>
                    <Input value={form.pppoe_username} onChange={e => setForm(f => ({ ...f, pppoe_username: e.target.value }))}
                      placeholder="username_pppoe" className="rounded-sm text-xs h-8 font-mono" />
                  </div>
                  <div className="space-y-1">
                    <Label className="text-[10px] text-muted-foreground uppercase">Password PPPoE <span className="text-destructive">*</span></Label>
                    <div className="relative">
                      <Input value={form.pppoe_password} onChange={e => setForm(f => ({ ...f, pppoe_password: e.target.value }))}
                        type={showPppPwd ? "text" : "password"}
                        className="rounded-sm text-xs h-8 font-mono pr-8" />
                      <button type="button" onClick={() => setShowPppPwd(v => !v)}
                        className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground">
                        {showPppPwd ? <EyeOff className="w-3 h-3" /> : <Eye className="w-3 h-3" />}
                      </button>
                    </div>
                  </div>
                  <div className="space-y-1 sm:col-span-2 p-2.5 bg-secondary/10 border border-border rounded-sm flex items-start gap-2 mt-2">
                    <input
                      type="checkbox"
                      id="use_radius_ztp"
                      checked={form.use_radius}
                      onChange={(e) => setForm(f => ({ ...f, use_radius: e.target.checked }))}
                      className="mt-1 flex-shrink-0"
                    />
                    <div>
                      <Label htmlFor="use_radius_ztp" className="text-xs font-semibold cursor-pointer">Gunakan RADIUS Server (Rekomendasi)</Label>
                      <p className="text-[10px] text-muted-foreground leading-relaxed mt-0.5">
                        Jika dicentang, authentikasi dan pemutusan (isolir) tagihan akan ditangani secara terpusat oleh RADIUS server NOC Sentinel. PPPoE Secret Mikrotik tidak akan dibuat, sehingga router lebih ringan.
                      </p>
                    </div>
                  </div>

                  {/* VLAN ID */}
                  <div className="space-y-1">
                    <Label className="text-[10px] text-muted-foreground uppercase flex items-center gap-1">VLAN ID <span className="text-muted-foreground/50">(Opsional)</span></Label>
                    <Input value={form.vlan_id} onChange={e => setForm(f => ({ ...f, vlan_id: e.target.value }))}
                      placeholder="100" className="rounded-sm text-xs h-8 font-mono" />
                    <p className="text-[9px] text-muted-foreground">VLAN ID untuk WAN PPPoE di ONT ZTE. Kosongkan jika tidak digunakan.</p>
                  </div>

                  {/* SSID cepat (duplikat dari section WiFi agar mudah diisi sekalian) */}
                  <div className="space-y-1">
                    <Label className="text-[10px] text-muted-foreground uppercase flex items-center gap-1">SSID (Nama WiFi)</Label>
                    <Input value={form.ssid} onChange={e => setForm(f => ({ ...f, ssid: e.target.value }))}
                      placeholder="Budi Home" className="rounded-sm text-xs h-8" />
                  </div>
                </div>
              </div>

              {/* Section 3: Package & Biaya */}
              <div className="space-y-3">
                <p className="text-[10px] uppercase tracking-widest text-muted-foreground font-medium flex items-center gap-1.5">
                  <Package className="w-3.5 h-3.5" /> Paket & Biaya Langganan
                </p>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div className="space-y-1 sm:col-span-2">
                    <Label className="text-[10px] text-muted-foreground uppercase">Paket Berlangganan</Label>
                    {loadingOptions ? (
                      <div className="h-8 bg-secondary/30 rounded-sm animate-pulse" />
                    ) : (
                      <select
                        value={form.package_id}
                        onChange={e => setForm(f => ({ ...f, package_id: e.target.value }))}
                        className="w-full h-8 text-xs rounded-sm border border-input bg-background px-2 text-foreground"
                      >
                        <option value="">-- Pilih Paket (opsional) --</option>
                        {options.billing_packages.map(p => (
                          <option key={p.id} value={p.id}>
                            {p.name} — {p.speed_down}/{p.speed_up} — Rp {p.price?.toLocaleString("id-ID")}
                          </option>
                        ))}
                      </select>
                    )}
                  </div>
                  
                  <div className="space-y-1">
                    <Label className="text-[10px] text-muted-foreground uppercase">Biaya Pasang (Rp)</Label>
                    <Input 
                      type="number" min="0" 
                      value={form.installation_fee} 
                      onChange={e => setForm(f => ({ ...f, installation_fee: e.target.value }))}
                      placeholder="0" className="rounded-sm text-xs h-8" 
                    />
                  </div>

                  <div className="space-y-1">
                    <Label className="text-[10px] text-muted-foreground uppercase">Sistem Tagihan</Label>
                    <select
                      value={form.billing_type}
                      onChange={e => setForm(f => ({ ...f, billing_type: e.target.value }))}
                      className="w-full h-8 text-xs rounded-sm border border-input bg-background px-2 text-foreground"
                    >
                      <option value="prepaid">Prepaid (Bayar Dulu Baru Pakai)</option>
                      <option value="postpaid">Postpaid (Pakai Dulu Baru Bayar)</option>
                    </select>
                  </div>

                  {form.billing_type === "prepaid" && (
                    <div className="space-y-1 sm:col-span-2 p-2.5 bg-secondary/20 border border-border rounded-sm">
                      <Label className="text-[10px] text-muted-foreground uppercase flex items-center gap-1.5 mb-2">
                        <CheckCircle2 className="w-3 h-3 text-cyan-400" /> Status Pembayaran Awal
                      </Label>
                      <select
                        value={form.payment_status}
                        onChange={e => setForm(f => ({ ...f, payment_status: e.target.value }))}
                        className="w-full h-8 text-xs rounded-sm border border-input bg-background px-2 text-foreground"
                      >
                        <option value="sudah_bayar">Sudah Bayar Lunas (Internet langsung aktif)</option>
                        <option value="belum_bayar">Belum Bayar (Internet di-isolir otomatis di awal)</option>
                      </select>
                      <p className="text-[10px] text-muted-foreground mt-2 leading-relaxed">
                        Tagihan Invoice awal (Biaya Pasang + Langganan Paket pertama) otomatis dibuat. Karena sistem Prepaid,
                        jika diset <strong>Belum Bayar</strong>, ONT tidak akan bisa digunakan sampai invoice dilunasi.
                      </p>
                    </div>
                  )}
                </div>
              </div>

              {/* Section 4: WiFi ONT */}
              <div className="space-y-3">
                <p className="text-[10px] uppercase tracking-widest text-muted-foreground font-medium flex items-center gap-1.5">
                  <Wifi className="w-3.5 h-3.5" /> Konfigurasi WiFi ONT
                </p>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div className="space-y-1">
                    <Label className="text-[10px] text-muted-foreground uppercase">SSID (Nama WiFi)</Label>
                    <Input value={form.ssid} onChange={e => setForm(f => ({ ...f, ssid: e.target.value }))}
                      placeholder="Budi Home" className="rounded-sm text-xs h-8" />
                  </div>
                  <div className="space-y-1">
                    <Label className="text-[10px] text-muted-foreground uppercase">Password WiFi</Label>
                    <div className="relative">
                      <Input value={form.wifi_password} onChange={e => setForm(f => ({ ...f, wifi_password: e.target.value }))}
                        type={showWifiPwd ? "text" : "password"}
                        className="rounded-sm text-xs h-8 font-mono pr-8" />
                      <button type="button" onClick={() => setShowWifiPwd(v => !v)}
                        className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground">
                        {showWifiPwd ? <EyeOff className="w-3 h-3" /> : <Eye className="w-3 h-3" />}
                      </button>
                    </div>
                  </div>
                </div>
                <p className="text-[10px] text-muted-foreground">
                  Biarkan kosong jika tidak ingin mengubah konfigurasi WiFi ONT.
                </p>
              </div>

              {/* Disclaimer */}
              {!device.online && (
                <div className="flex items-start gap-2 p-2.5 bg-yellow-500/10 border border-yellow-500/20 rounded-sm">
                  <AlertTriangle className="w-3.5 h-3.5 text-yellow-400 flex-shrink-0 mt-0.5" />
                  <p className="text-[11px] text-yellow-300">
                    ONT saat ini <strong>offline</strong>. MikroTik Secret tetap akan dibuat dan data billing
                    tetap tersimpan. Konfigurasi ke ONT (step 2) akan diantrekan dan dikirim
                    secara otomatis oleh GenieACS saat ONT pertama kali online.
                  </p>
                </div>
              )}

              {/* Submit */}
              <Button
                onClick={handleSubmit}
                disabled={submitting}
                className="w-full rounded-sm gap-2 h-9 bg-green-600 hover:bg-green-700 text-white"
              >
                {submitting
                  ? <><Loader2 className="w-4 h-4 animate-spin" /> Mengaktifkan...</>
                  : <><Sparkles className="w-4 h-4" /> Aktifkan Sekarang (ZTP)</>}
              </Button>
            </>
          )}

          {/* Done: close/retry buttons */}
          {result && (
            <div className="flex gap-2 justify-end pt-2">
              <Button variant="outline" size="sm" className="rounded-sm gap-1.5 text-xs"
                onClick={() => { setResult(null); setSteps(null); }}>
                <RefreshCw className="w-3.5 h-3.5" /> Coba Lagi
              </Button>
              <Button size="sm" className="rounded-sm gap-1.5 text-xs" onClick={onClose}>
                <Check className="w-3.5 h-3.5" /> Selesai
              </Button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ── Device Row ────────────────────────────────────────────────────────────────

function DeviceRow({ device, isAdmin, onOpenModal, onActivate }) {
  const [acting, setActing] = useState(null);

  // Deteksi ONT belum dikonfigurasi
  const isNew = !device.pppoe_username ||
    String(device.pppoe_username).startsWith("user") ||
    !device.ssid ||
    String(device.ssid).toLowerCase() === String(device.model || "").toLowerCase() ||
    String(device.ssid).startsWith("ZTE-") ||
    String(device.ssid).startsWith("F663");

  const doAction = async (action, label) => {
    setActing(action);
    try {
      await api.post(`/genieacs/devices/${encodeURIComponent(device.id)}/${action}`);
      toast.success(`${label} dikirim ke ${device.model || device.id}`);
    } catch (e) {
      toast.error(e.response?.data?.detail || `${label} gagal`);
    }
    setActing(null);
  };

  return (
    <>
      {/* ID PPPoE */}
      <td className="px-3 py-2.5">
        <div className="flex items-center gap-1.5">
          <div className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${device.online ? "bg-green-500 animate-pulse" : "bg-red-500"}`} />
          {isNew ? (
            <span className="text-[10px] italic text-yellow-400/80">Belum dikonfigurasi</span>
          ) : (
            <span className="text-[11px] font-mono text-cyan-400">{device.pppoe_username}</span>
          )}
        </div>
      </td>

      {/* Status */}
      <td className="px-3 py-2.5">
        <Badge variant="outline" className={`text-[10px] rounded-sm ${device.online ? "border-green-500/40 text-green-400" : "border-red-500/40 text-red-400"}`}>
          {device.online
            ? <><Wifi className="w-2.5 h-2.5 mr-1" />Online</>
            : <><WifiOff className="w-2.5 h-2.5 mr-1" />Offline</>}
        </Badge>
        <p className="text-[9px] text-muted-foreground mt-0.5">{timeAgo(device.last_inform)}</p>
      </td>

      {/* Redaman ONT */}
      <td className="px-3 py-2.5">
        <RxPowerBadge value={device.rx_power} />
      </td>

      {/* Product Class */}
      <td className="px-3 py-2.5">
        <span className="text-[11px] text-muted-foreground">{device.product_class || "—"}</span>
      </td>

      {/* SSID */}
      <td className="px-3 py-2.5">
        <div className="flex items-center gap-1">
          {device.ssid && <Radio className="w-3 h-3 text-muted-foreground flex-shrink-0" />}
          <span className="text-[11px] text-foreground truncate max-w-[120px]" title={device.ssid}>{device.ssid || "—"}</span>
        </div>
      </td>

      {/* Active Device */}
      <td className="px-3 py-2.5">
        <div className="flex items-center gap-1">
          <Users className="w-3 h-3 text-muted-foreground" />
          <span className="text-[11px] font-mono">{device.active_devices ?? "—"}</span>
        </div>
      </td>

      {/* Uptime */}
      <td className="px-3 py-2.5">
        <span className="text-[11px] font-mono text-sky-400">
          {device.uptime ? formatUptime(device.uptime) : "—"}
        </span>
      </td>

      {/* Suhu ONT */}
      <td className="px-3 py-2.5">
        {device.ont_temp && parseFloat(device.ont_temp) > 0 ? (
          <span className={`text-[11px] font-mono font-semibold ${
            parseFloat(device.ont_temp) > 70 ? "text-red-400" :
            parseFloat(device.ont_temp) > 55 ? "text-yellow-400" : "text-orange-400"
          }`}>{parseFloat(device.ont_temp).toFixed(0)}°C</span>
        ) : (
          <span className="text-muted-foreground">—</span>
        )}
      </td>

      {/* IP PPPoE */}
      <td className="px-3 py-2.5">
        <span className="text-[11px] font-mono text-foreground">{device.pppoe_ip || "—"}</span>
      </td>

      {/* Actions */}
      <td className="px-3 py-2.5">
        <div className="flex items-center gap-1">
          {/* Aktivasi ZTP — hanya tampil jika admin DAN belum dikonfigurasi */}
          {isAdmin && isNew && (
            <Button size="icon" variant="ghost"
              className="h-6 w-6 text-green-400 hover:bg-green-500/20"
              title="Aktivasi Pelanggan Baru (ZTP)"
              onClick={() => onActivate(device)}>
              <UserPlus className="w-3.5 h-3.5" />
            </Button>
          )}

          {/* Summon */}
          <Button size="icon" variant="ghost" className="h-6 w-6 text-cyan-400 hover:bg-cyan-500/10" title="Summon"
            disabled={acting !== null} onClick={() => doAction("summon", "Summon")}>
            <Zap className={`w-3 h-3 ${acting === "summon" ? "animate-pulse" : ""}`} />
          </Button>

          {/* Detail / Edit */}
          <Button size="icon" variant="ghost" className="h-6 w-6" title="Detail & Edit"
            onClick={onOpenModal}>
            <ChevronRight className="w-3 h-3" />
          </Button>

          {isAdmin && (
            <>
              <Button size="icon" variant="ghost" className="h-6 w-6" title="Refresh Parameter"
                disabled={acting !== null} onClick={() => doAction("refresh", "Refresh")}>
                <RefreshCw className={`w-3 h-3 ${acting === "refresh" ? "animate-spin" : ""}`} />
              </Button>
              <Button size="icon" variant="ghost" className="h-6 w-6 text-orange-400 hover:bg-orange-500/10" title="Reboot"
                disabled={acting !== null} onClick={() => doAction("reboot", "Reboot")}>
                <RotateCcw className={`w-3 h-3 ${acting === "reboot" ? "animate-spin" : ""}`} />
              </Button>
            </>
          )}
        </div>
      </td>
    </>
  );
}

// â”€â”€ Faults Tab â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

function FaultsTab() {
  const [faults, setFaults] = useState([]);
  const [loading, setLoading] = useState(false);
  const [clearing, setClearing] = useState(false);
  const { user } = useAuth();
  const READONLY_ROLES = ["viewer", "helpdesk"];
  const isAdmin = !READONLY_ROLES.includes(user?.role);

  const loadFaults = () => {
    setLoading(true);
    api.get("/genieacs/faults")
      .then(r => setFaults(r.data))
      .catch(() => toast.error("Gagal memuat faults"))
      .finally(() => setLoading(false));
  };

  useEffect(() => { loadFaults(); }, []);

  const deleteFault = async (id) => {
    try {
      await api.delete(`/genieacs/faults/${encodeURIComponent(id)}`);
      setFaults(f => f.filter(x => x._id !== id));
      toast.success("Fault dihapus");
    } catch { toast.error("Gagal hapus fault"); }
  };

  const clearAllFaults = async () => {
    if (!window.confirm(`Hapus semua ${faults.length} fault?`)) return;
    setClearing(true);
    let ok = 0, fail = 0;
    for (const f of faults) {
      try {
        await api.delete(`/genieacs/faults/${encodeURIComponent(f._id)}`);
        ok++;
      } catch { fail++; }
    }
    toast.success(`Dihapus: ${ok} fault${fail ? `, gagal: ${fail}` : ""}`);
    loadFaults();
    setClearing(false);
  };

  // Friendly explanation for common cwmp error codes
  const cwmpDesc = (code) => {
    const map = {
      "8002": "Internal Error — device gagal eksekusi task (biasanya parameter tidak valid atau tidak tersedia di firmware ini)",
      "8003": "Invalid arguments — parameter salah atau tipe data tidak sesuai",
      "8004": "Resources exceeded — memory device penuh",
      "8005": "Retry request — device minta coba ulang",
      "8007": "Download failure — firmware download gagal",
      "9001": "Request denied — device menolak request",
      "9002": "Internal error — operasi internal gagal",
    };
    const num = code?.split(":")?.[1] || code;
    return map[num] || null;
  };

  return (
    <div className="space-y-3">
      {/* Header with clear-all */}
      {isAdmin && faults.length > 0 && (
        <div className="flex items-center justify-between">
          <p className="text-xs text-muted-foreground">{faults.length} fault aktif</p>
          <Button
            size="sm" variant="outline"
            className="h-7 text-xs rounded-sm border-red-500/30 text-red-400 hover:bg-red-500/10 gap-1.5"
            onClick={clearAllFaults} disabled={clearing}
          >
            <Trash2 className="w-3 h-3" />
            {clearing ? "Menghapus..." : "Hapus Semua"}
          </Button>
        </div>
      )}

      {loading && <p className="text-muted-foreground text-sm py-4 text-center animate-pulse">Memuat faults...</p>}

      {!loading && faults.length === 0 && (
        <div className="text-center py-12">
          <CheckCircle2 className="w-10 h-10 text-green-500 mx-auto mb-2" />
          <p className="text-muted-foreground text-sm">Tidak ada fault aktif 🎉</p>
        </div>
      )}

      {faults.length > 0 && (
        <div className="space-y-2">
          {faults.map(f => {
            const code = f.code || "";
            const desc = cwmpDesc(code);
            return (
              <div key={f._id} className="flex items-start gap-3 p-3 bg-red-500/5 border border-red-500/20 rounded-sm">
                <TriangleAlert className="w-4 h-4 text-red-400 flex-shrink-0 mt-0.5" />
                <div className="flex-1 min-w-0">
                  <p className="text-xs font-mono text-foreground truncate">{f.device || f._id}</p>
                  <p className="text-[10px] text-red-400 mt-0.5 font-medium">
                    {code} — {f.message || JSON.stringify(f).slice(0, 80)}
                  </p>
                  {desc && (
                    <p className="text-[10px] text-yellow-500/80 mt-0.5">💡 {desc}</p>
                  )}
                  <p className="text-[10px] text-muted-foreground mt-0.5">{timeAgo(f.timestamp)}</p>
                </div>
                {isAdmin && (
                  <Button size="icon" variant="ghost" className="h-6 w-6 flex-shrink-0" onClick={() => deleteFault(f._id)}>
                    <Trash2 className="w-3 h-3 text-red-400" />
                  </Button>
                )}
              </div>
            );
          })}
        </div>
      )}

      <div className="mt-4 p-3 bg-blue-500/5 border border-blue-500/20 rounded-sm">
        <p className="text-[10px] text-blue-400 font-medium mb-1">ℹ️ Tentang Fault cwmp:8002</p>
        <p className="text-[10px] text-muted-foreground leading-relaxed">
          Error <code className="text-yellow-400">cwmp:8002 Internal Error</code> sering muncul pada ONT ZTE EG8145V5 / Huawei
          ketika GenieACS mengirim <code className="text-yellow-400">refreshObject</code> dengan objectName kosong.
          <strong className="text-foreground"> Ini sudah diperbaiki</strong> — Summon sekarang mengirim connection request murni tanpa body task.
          Fault lama di atas dapat dihapus dengan aman.
        </p>
      </div>
    </div>
  );
}


// â”€â”€ Server Config Tab â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

function ServerConfigTab() {
  const [cfg, setCfg] = useState({ url: "", username: "", password: "", sync_interval_mins: 30 });
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [showPwd, setShowPwd] = useState(false);
  const [testResult, setTestResult] = useState(null);
  const [passwordSet, setPasswordSet] = useState(false);

  useEffect(() => {
    api.get("/system/genieacs-config")
      .then(r => {
        setCfg(c => ({
          ...c,
          url: r.data.url || "",
          username: r.data.username || "",
          sync_interval_mins: r.data.sync_interval_mins ?? 30
        }));
        setPasswordSet(!!r.data.password_set);
      })
      .catch(() => {});
  }, []);

  const handleSave = async () => {
    if (!cfg.url) { toast.error("URL GenieACS wajib diisi"); return; }
    setSaving(true);
    try {
      const r = await api.post("/system/save-genieacs-config", cfg);
      toast.success(r.data.message || "Konfigurasi disimpan");
    } catch (e) { toast.error(e.response?.data?.detail || "Gagal menyimpan"); }
    setSaving(false);
  };

  const handleTest = async () => {
    if (!cfg.url) { toast.error("Isi URL GenieACS dahulu"); return; }
    setTesting(true);
    setTestResult(null);
    try {
      await api.post("/system/save-genieacs-config", cfg);
      const r = await api.get("/genieacs/test-connection");
      setTestResult(r.data);
      if (r.data.success) toast.success(r.data.message);
      else toast.error(r.data.error || "Koneksi ke GenieACS gagal");
    } catch (e) {
      toast.error(e.response?.data?.detail || "Test koneksi gagal");
    }
    setTesting(false);
  };

  return (
    <div className="space-y-5 max-w-xl">
      <div className="flex items-start gap-3 p-3 bg-cyan-500/10 border border-cyan-500/20 rounded-sm">
        <ServerIcon className="w-4 h-4 text-cyan-400 flex-shrink-0 mt-0.5" />
        <div className="text-xs text-cyan-300">
          <p className="font-semibold mb-0.5">Konfigurasi GenieACS NBI Server</p>
          <p className="text-cyan-300/70">Isi URL, username, dan password server GenieACS lalu klik <strong>Test Koneksi</strong> untuk memverifikasi, kemudian <strong>Simpan</strong>.</p>
        </div>
      </div>

      <div className="space-y-4">
        <div className="space-y-1.5">
          <Label className="text-xs text-muted-foreground">
            GenieACS URL (NBI) <span className="text-destructive">*</span>
          </Label>
          <Input value={cfg.url} onChange={e => setCfg(c => ({ ...c, url: e.target.value }))}
            placeholder="http://genieacs-nbi:7557" className="rounded-sm font-mono text-xs" />
          <p className="text-[10px] text-muted-foreground">URL internal NBI GenieACS harus menggunakan <code className="bg-secondary px-1 rounded">http://genieacs-nbi:7557</code></p>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-1.5">
            <Label className="text-xs text-muted-foreground">Username</Label>
            <Input value={cfg.username} onChange={e => setCfg(c => ({ ...c, username: e.target.value }))}
              placeholder="admin" className="rounded-sm text-xs" />
          </div>
          <div className="space-y-1.5">
            <Label className="text-xs text-muted-foreground flex items-center justify-between">
              <span>Password</span>
              {passwordSet && (
                <Badge variant="outline" className="text-[9px] py-0 px-1 border-green-500/30 text-green-400 bg-green-500/5">
                  Tersimpan ✓
                </Badge>
              )}
            </Label>
            <div className="relative">
              <Input value={cfg.password} onChange={e => setCfg(c => ({ ...c, password: e.target.value }))}
                type={showPwd ? "text" : "password"}
                placeholder={cfg.url ? "(biarkan kosong jika tidak berubah)" : ""}
                className="rounded-sm text-xs pr-9" />
              <button type="button"
                className="absolute right-2.5 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                onClick={() => setShowPwd(v => !v)}>
                {showPwd ? <EyeOff className="w-3.5 h-3.5" /> : <Eye className="w-3.5 h-3.5" />}
              </button>
            </div>
          </div>
        </div>

        {/* Sync Interval */}
        <div className="space-y-1.5">
          <Label className="text-xs text-muted-foreground flex items-center gap-1.5">
            <RefreshCw className="w-3 h-3" /> Interval Sinkronisasi Otomatis (Menit)
          </Label>
          <div className="flex items-center gap-2">
            <Input
              type="number" min="5" max="1440"
              value={cfg.sync_interval_mins}
              onChange={e => setCfg(c => ({ ...c, sync_interval_mins: parseInt(e.target.value) || 30 }))}
              className="rounded-sm text-xs w-28 font-mono"
            />
            <p className="text-[10px] text-muted-foreground">
              Data ONT (PPPoE, Redaman, SSID, Uptime, Suhu) disinkronkan setiap{" "}
              <strong>{cfg.sync_interval_mins} menit</strong>, 50 CPE per batch.
            </p>
          </div>
        </div>
      </div>

      {testResult && (
        <div className={`flex items-start gap-2 p-3 rounded-sm border text-xs ${
          testResult.success
            ? "bg-green-500/10 border-green-500/20 text-green-300"
            : "bg-red-500/10 border-red-500/20 text-red-300"
        }`}>
          {testResult.success
            ? <CheckCircle2 className="w-4 h-4 flex-shrink-0 mt-0.5" />
            : <AlertCircle className="w-4 h-4 flex-shrink-0 mt-0.5" />}
          <div>
            <p className="font-semibold">{testResult.success ? "Berhasil terhubung!" : "Koneksi gagal"}</p>
            <p className="mt-0.5 opacity-80">{testResult.success ? testResult.message : testResult.error}</p>
            {testResult.success && testResult.stats && (
              <div className="flex gap-4 mt-2 font-mono text-[11px]">
                <span>Total: <strong>{testResult.stats.total}</strong></span>
                <span className="text-green-400">Online: <strong>{testResult.stats.online}</strong></span>
                <span className="text-red-400">Offline: <strong>{testResult.stats.offline}</strong></span>
              </div>
            )}
          </div>
        </div>
      )}

      <div className="flex gap-2">
        <Button onClick={handleTest} variant="outline" disabled={testing || saving} className="rounded-sm gap-2 h-9 text-xs">
          <Zap className="w-3.5 h-3.5" />{testing ? "Testing..." : "Test Koneksi"}
        </Button>
        <Button onClick={handleSave} disabled={saving || testing} className="rounded-sm gap-2 h-9 text-xs">
          <Save className="w-3.5 h-3.5" />{saving ? "Menyimpan..." : "Simpan"}
        </Button>
      </div>

      <details className="text-xs border border-border rounded-sm">
        <summary className="cursor-pointer px-3 py-2 text-muted-foreground hover:text-foreground transition-colors select-none">
          Cara setup GenieACS NBI &gt;
        </summary>
        <div className="px-3 pb-3 space-y-2 font-mono text-[11px] border-t border-border mt-0 pt-3">
          <p className="font-sans text-muted-foreground font-semibold">1. Cek status genieacs-nbi di server GenieACS:</p>
          <p className="text-green-400 bg-secondary/30 px-2 py-1 rounded">systemctl status genieacs-nbi</p>
          <p className="font-sans text-muted-foreground font-semibold">2. Test akses dari server NOC ke GenieACS:</p>
          <p className="text-green-400 bg-secondary/30 px-2 py-1 rounded">curl http://10.x.x.x:7557/devices?limit=1</p>
          <p className="font-sans text-[10px] text-muted-foreground">Jika mendapat response JSON → isi form di atas → Test Koneksi</p>
        </div>
      </details>
    </div>
  );
}

// â”€â”€ Guide Tab (Advanced Features) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

function GuideTab() {
  return (
    <div className="space-y-4 max-w-3xl text-sm text-muted-foreground">
      <div className="p-4 bg-cyan-500/5 rounded-sm border border-cyan-500/20">
        <h3 className="text-cyan-400 font-semibold mb-2 flex items-center gap-2">
          <Zap className="w-4 h-4" /> 1. Cara Konfigurasi MikroTik (DHCP Option 43) untuk Auto-Config / ZTP
        </h3>
        <p className="mb-2 text-cyan-50/80">Agar modem/ONT baru langsung terhubung ke layanan TR-069 (GenieACS) saat dicolokkan tanpa perlu disetting teknisi secara manual, Anda harus menambahkan <strong>DHCP Option 43</strong> di MikroTik pada jaringan Management VLAN OLT Anda.</p>
        <div className="bg-secondary/40 border border-border/50 p-3 rounded-sm space-y-2 mt-3">
          <p className="font-semibold text-[11px] text-muted-foreground uppercase tracking-widest">Step-by-Step MikroTik Terminal:</p>
          <ol className="list-decimal pl-4 space-y-2 font-mono text-[11px] text-foreground/90">
            <li>
              <span className="text-muted-foreground">Buat option 43 (Ganti URL dengan IP GenieACS Anda):</span><br/>
              /ip dhcp-server option add code=43 name=TR069_ACS value="'http://10.10.10.2:7547/'"
            </li>
            <li>
              <span className="text-muted-foreground">Terapkan option tersebut ke DHCP Server network OLT Anda:</span><br/>
              /ip dhcp-server network set [find address=10.10.10.0/24] dhcp-option=TR069_ACS
            </li>
          </ol>
        </div>
        <p className="mt-3 text-[11px]"><strong>Penting:</strong> Pastikan Anda menggunakan tanda kutip tunggal di dalam tanda kutip ganda <code className="bg-background px-1 py-0.5 rounded">"'http...'"</code> agar string dikenali dengan benar oleh tipe data MikroTik.</p>
      </div>
      
      <div className="p-4 bg-secondary/20 rounded-sm border border-border">
        <h3 className="text-foreground font-semibold mb-2">2. Apakah Service ini Berjalan Otomatis?</h3>
        <p className="mb-2"><strong>Saat ini:</strong> Fitur ZTP (Kirim Username PPPoE & WiFi) dan Ubah Password WiFi sudah tersedia secara utuh sebagai <strong>API Endpoint backend (`/genieacs/devices/&#123;id&#125;/provision`)</strong>.</p>
        <p>Anda dapat mengintegrasikan API ini dengan <strong>N8N</strong> atau bot Telegram untuk berjalan sepenuhnya 100% otomatis. Ketika N8N menerima form aktivasi pelanggan baru dari sales, N8N tinggal "menembak" sistem NOC Sentinel, dan NOC Sentinel akan meremote ONT secara massal.</p>
      </div>
      
      <div className="p-4 bg-orange-500/5 rounded-sm border border-orange-500/20">
        <h3 className="text-orange-400 font-semibold mb-2 flex items-center gap-2">
          <AlertTriangle className="w-4 h-4" /> 3. Deteksi Kabel Bengkok (RX Power)
        </h3>
        <p>NOC Sentinel sudah mengenali redaman optik berbagai merek (ZTE/Fiberhome). Karena membaca Redaman optik massal sangat memberatkan CPU OLT/GenieACS, sistem ini dirancang untuk dijalankan (di-trigger) via Auto-Cron pada NOC Sentinel saat tengah malam (contoh: Pukul 02:00 Pagi) untuk merekap CPE ber-redaman buruk (&lt; -26 dBm).</p>
      </div>
      
      <div className="p-4 bg-red-500/5 rounded-sm border border-red-500/20">
        <h3 className="text-red-400 font-semibold mb-2 flex items-center gap-2">
          <WifiOff className="w-4 h-4" /> 4. Isolasi Hardcore (Mematikan WiFi)
        </h3>
        <p>Bisa dijalankan manual lewat menu Aksi tabel di atas (jika UI tombolnya ditambahkan), atau Anda jadikan fitur ini sebagai perpanjangan dari modul Billing PPPoE. Contoh: Saat router PPPoE meng-isolasi koneksi via MikroTik, API NOC Sentinel juga memanggil TR-069 untuk mematikan SSID pelanggannya.</p>
      </div>
    </div>
  );
}

// â”€â”€ Main Page â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

export default function GenieACSPage() {
  const { user } = useAuth();
  // ZTP tersedia untuk semua role kecuali viewer/helpdesk read-only
  const READONLY_ROLES = ["viewer", "helpdesk"];
  const isAdmin = !READONLY_ROLES.includes(user?.role);
  // Hanya super_admin yang bisa hapus perangkat
  const canDelete = ["super_admin", "administrator"].includes(user?.role);

  const [tab, setTab] = useState("devices");
  const [devices, setDevices] = useState([]);
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(false);
  const [search, setSearch] = useState("");
  const [searchInput, setSearchInput] = useState("");
  const [connectionOk, setConnectionOk] = useState(null);
  const [selectedDevice, setSelectedDevice] = useState(null);
  const [ztpDevice, setZtpDevice] = useState(null); // ONT yang akan diaktivasi via ZTP

  // â”€â”€â”€ Bulk Reboot state â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
  const [selectedIds, setSelectedIds] = useState(new Set());
  const [bulkRebooting, setBulkRebooting] = useState(false);
  const [bulkResult, setBulkResult] = useState(null);
  const [confirmBulk, setConfirmBulk] = useState(null); // { mode: 'selected'|'offline' }
  const [page, setPage] = useState(1);
  const PAGE_SIZE = 100;

  const newDevices = useMemo(() => {
    return devices.filter(d => 
      d.online && (
        !d.ssid || 
        String(d.ssid).toLowerCase() === String(d.model || "").toLowerCase() || 
        String(d.ssid).startsWith("ZTE-") ||
        String(d.ssid).startsWith("F663") ||
        !d.pppoe_username || 
        String(d.pppoe_username).startsWith("user")
      )
    );
  }, [devices]);

  const badRxDevices = useMemo(() => {
    return devices.filter(d => {
      if (!d.rx_power) return false;
      const rx = parseFloat(d.rx_power);
      return !isNaN(rx) && rx < -26.99;
    });
  }, [devices]);
  // â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

  const fetchDevices = useCallback(async () => {
    setLoading(true);
    setPage(1); // reset halaman saat fetch ulang
    try {
      const [devRes, statsRes] = await Promise.all([
        api.get("/genieacs/devices", { params: { limit: 1500, search } }),
        api.get("/genieacs/stats"),
      ]);
      setDevices(devRes.data);
      setStats(statsRes.data);
      setConnectionOk(true);
    } catch (e) {
      let msg = e.response?.data?.detail || "Gagal terhubung ke GenieACS";
      if (typeof msg === 'object') msg = "Parameter API tidak valid atau error server.";
      if (connectionOk !== false) toast.error(msg);
      setConnectionOk(false);
    }
    setLoading(false);
  }, [search]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => { fetchDevices(); }, [fetchDevices]);

  const handleSearch = (e) => {
    e.preventDefault();
    setSearch(searchInput.trim());
  };

  // â”€â”€â”€ Bulk selection helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
  const offlineDevices = devices.filter(d => !d.online);

  const toggleSelect = (id) => {
    setSelectedIds(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  };

  const selectAllVisible = () => setSelectedIds(new Set(devices.map(d => d.id)));
  const selectAllOffline = () => setSelectedIds(new Set(offlineDevices.map(d => d.id)));
  const clearSelection = () => setSelectedIds(new Set());

  const executeBulkReboot = async (mode) => {
    setBulkRebooting(true);
    setBulkResult(null);
    setConfirmBulk(null);
    try {
      const body = mode === "selected"
        ? { device_ids: [...selectedIds] }
        : { filter: "offline" };
      const r = await api.post("/genieacs/bulk-reboot", body);
      setBulkResult(r.data);
      toast.success(`Bulk reboot: ${r.data.success} berhasil, ${r.data.failed} gagal`);
      clearSelection();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Bulk reboot gagal");
    }
    setBulkRebooting(false);
  };
  // â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

  const tabs = [
    { id: "devices", label: "CPE Devices", icon: Cpu },
    { id: "faults", label: "Faults", icon: AlertTriangle },
    ...(isAdmin ? [{ id: "config", label: "Konfigurasi Server", icon: Settings2 }] : []),
    { id: "guide", label: "Panduan Fitur", icon: Info },
  ];

  // Column headers — tambah checkbox di kiri jika admin
  const headers = isAdmin
    ? ["", "ID PPPoE", "Status", "Redaman", "Product Class", "SSID", "Devices", "Uptime", "Suhu", "IP PPPoE", "Aksi"]
    : ["ID PPPoE", "Status", "Redaman", "Product Class", "SSID", "Devices", "Uptime", "Suhu", "IP PPPoE", "Aksi"];

  return (
    <div className="space-y-4 pb-16">
      {/* Confirm Bulk Reboot Dialog */}
      {confirmBulk && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
          <div className="bg-card border border-border rounded-sm w-full max-w-sm p-5 space-y-4 shadow-2xl">
            <div className="flex items-center gap-3">
              <div className="w-9 h-9 rounded-sm bg-orange-500/20 flex items-center justify-center flex-shrink-0">
                <RotateCcw className="w-5 h-5 text-orange-400" />
              </div>
              <div>
                <p className="font-semibold text-sm">Konfirmasi Bulk Reboot</p>
                <p className="text-[11px] text-muted-foreground mt-0.5">
                  {confirmBulk.mode === "selected"
                    ? `Reboot ${selectedIds.size} ONT yang dipilih?`
                    : `Reboot semua ${offlineDevices.length} ONT offline?`
                  }
                </p>
              </div>
            </div>
            <div className="flex gap-2 justify-end">
              <Button variant="outline" size="sm" className="rounded-sm" onClick={() => setConfirmBulk(null)}>Batal</Button>
              <Button size="sm" className="rounded-sm gap-1.5 bg-orange-500 hover:bg-orange-600"
                onClick={() => executeBulkReboot(confirmBulk.mode)}>
                <RotateCcw className="w-3.5 h-3.5" /> Ya, Reboot
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* Bulk Result Banner */}
      {bulkResult && (
        <div className="flex items-start gap-3 p-3 bg-card border border-border rounded-sm">
          <CheckCircle2 className="w-4 h-4 text-green-400 flex-shrink-0 mt-0.5" />
          <div className="flex-1">
            <p className="text-xs font-semibold">{bulkResult.message}</p>
            <div className="flex gap-3 mt-1">
              <span className="text-[11px] text-green-400 font-mono">{bulkResult.success} berhasil</span>
              {bulkResult.failed > 0 && <span className="text-[11px] text-red-400 font-mono">{bulkResult.failed} gagal</span>}
            </div>
          </div>
          <button onClick={() => setBulkResult(null)} className="text-muted-foreground hover:text-foreground"><X className="w-3.5 h-3.5" /></button>
        </div>
      )}
      {/* ZTP Modal */}
      {ztpDevice && (
        <ZTPModal
          device={ztpDevice}
          onClose={() => setZtpDevice(null)}
          onSuccess={() => {
            setZtpDevice(null);
            const tId = toast.loading("Sinkronisasi ONT...");
            setTimeout(() => {
              fetchDevices();
              toast.dismiss(tId);
              toast.success("List perangkat diperbarui");
            }, 2500);
          }}
        />
      )}

      {/* Modal */}
      {selectedDevice && (
        <DeviceModal
          device={selectedDevice}
          isAdmin={isAdmin}
          onClose={() => setSelectedDevice(null)}
          onRefreshed={() => { fetchDevices(); setSelectedDevice(null); }}
        />
      )}

      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <h1 className="text-xl sm:text-2xl font-bold tracking-tight flex items-center gap-2">
            <Cpu className="w-6 h-6 text-primary" /> GenieACS / TR-069
          </h1>
          <p className="text-xs text-muted-foreground">Manajemen CPE (modem/router pelanggan) via protocol TR-069</p>
        </div>
        <div className="flex items-center gap-2 self-start">
          {connectionOk !== null && (
            <div className={`flex items-center gap-1.5 px-2.5 py-1 rounded-sm text-[10px] font-medium border ${
              connectionOk
                ? "bg-green-500/10 text-green-400 border-green-500/20"
                : "bg-red-500/10 text-red-400 border-red-500/20"
            }`}>
              {connectionOk ? <Wifi className="w-3 h-3" /> : <WifiOff className="w-3 h-3" />}
              {connectionOk ? "Terhubung" : "Tidak terhubung"}
            </div>
          )}
          <Button variant="outline" size="sm" className="rounded-sm gap-2" onClick={fetchDevices} disabled={loading}>
            <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />
            Refresh
          </Button>
          {isAdmin && (
            <Button variant={tab === "config" ? "default" : "outline"} size="sm"
              className="rounded-sm gap-2"
              onClick={() => setTab("config")}>
              <Settings2 className="w-4 h-4" /> Konfigurasi
            </Button>
          )}
        </div>
      </div>

      {/* Stats */}
      {tab !== "config" && <StatsBar stats={stats} loading={loading} />}

      {/* Tabs */}
      <div className="flex border-b border-border gap-1">
        {tabs.map(t => (
          <button key={t.id} onClick={() => setTab(t.id)}
            className={`flex items-center gap-1.5 px-4 py-2 text-sm border-b-2 transition-colors ${
              tab === t.id ? "border-primary text-primary" : "border-transparent text-muted-foreground hover:text-foreground"
            }`}>
            <t.icon className="w-3.5 h-3.5" />
            {t.label}
            {t.id === "faults" && stats?.faults > 0 && (
              <span className="ml-1 bg-red-500/20 text-red-400 text-[10px] px-1.5 py-0.5 rounded-full font-mono">{stats.faults}</span>
            )}
          </button>
        ))}
      </div>

      {/* Tab Content */}
      <div className="bg-card border border-border rounded-sm p-4">

        {/* Devices Tab */}
        {tab === "devices" && (
          <>
            {/* Not connected banner */}
            {connectionOk === false && (
              <div className="flex items-center gap-3 p-3 mb-4 bg-yellow-500/10 border border-yellow-500/20 rounded-sm">
                <AlertCircle className="w-4 h-4 text-yellow-400 flex-shrink-0" />
                <div className="flex-1">
                  <p className="text-xs text-yellow-300 font-semibold">GenieACS belum terkonfigurasi</p>
                  <p className="text-[11px] text-yellow-300/70">
                    {isAdmin
                      ? <>Klik tab <strong>Konfigurasi Server</strong> untuk menambahkan URL &amp; kredensial GenieACS.</>
                      : "Hubungi administrator untuk mengatur koneksi GenieACS."}
                  </p>
                </div>
                {isAdmin && (
                  <Button size="sm" variant="outline" className="rounded-sm h-7 text-xs gap-1 border-yellow-500/30 text-yellow-400 hover:bg-yellow-500/10"
                    onClick={() => setTab("config")}>
                    <Settings2 className="w-3 h-3" /> Setup
                  </Button>
                )}
              </div>
            )}

            {/* New Devices Notification */}
            {newDevices.length > 0 && (
              <div className="flex items-start gap-3 p-3 mb-4 bg-green-500/10 border border-green-500/20 rounded-sm">
                <Sparkles className="w-5 h-5 text-green-400 flex-shrink-0 mt-0.5 animate-pulse" />
                <div className="flex-1">
                  <p className="text-xs text-green-300 font-semibold">{newDevices.length} ONT Baru Siap Diaktivasi</p>
                  <p className="text-[11px] text-green-300/70 mt-0.5">
                    Terdeteksi {newDevices.length} perangkat dengan konfigurasi bawaan pabrik.
                    Klik tombol <strong>Aktivasi</strong> ({<UserPlus className="inline w-3 h-3" />}) di baris tabel untuk mulai proses ZTP.
                  </p>
                  {isAdmin && (
                    <Button size="sm" variant="outline"
                      className="mt-2 h-7 text-[11px] rounded-sm gap-1.5 border-green-500/40 text-green-400 hover:bg-green-500/10"
                      onClick={() => setZtpDevice(newDevices[0])}>
                      <UserPlus className="w-3 h-3" /> Aktivasi {newDevices[0].model || "ONT"} Sekarang
                    </Button>
                  )}
                </div>
                <span className="text-[10px] font-mono bg-green-500/20 text-green-300 px-2 py-1 rounded-sm">{newDevices.length}</span>
              </div>
            )}

            {/* Bad RX Power Notification */}
            {badRxDevices.length > 0 && (
              <div className="flex items-start gap-3 p-3 mb-4 bg-red-500/10 border border-red-500/20 rounded-sm">
                <AlertTriangle className="w-5 h-5 text-red-500 flex-shrink-0 mt-0.5" />
                <div className="flex-1">
                  <p className="text-xs text-red-400 font-semibold">Redaman ONT Buruk (<span className="font-mono">&lt; -27 dBm</span>)</p>
                  <p className="text-[11px] text-red-400/80 mt-0.5">
                    Ada <strong>{badRxDevices.length}</strong> pelanggan dengan sinyal optik sangat lemah (kemungkinan kabel bengkok / konektor kotor).
                  </p>
                  <div className="flex flex-wrap gap-2 mt-2">
                    {badRxDevices.slice(0, 5).map(d => (
                      <span key={d.id} className="text-[10px] bg-red-500/20 text-red-300 px-2 py-0.5 rounded border border-red-500/30 font-mono cursor-pointer hover:bg-red-500/40"
                        title="Klik untuk detail" onClick={() => setSelectedDevice(d)}>
                        {d.pppoe_username || d.id.slice(-6)} ({parseFloat(d.rx_power).toFixed(2)})
                      </span>
                    ))}
                    {badRxDevices.length > 5 && <span className="text-[10px] text-red-400/80 self-center">+{badRxDevices.length - 5} lainnya</span>}
                  </div>
                </div>
              </div>
            )}

            {/* Search */}
            <form onSubmit={handleSearch} className="flex gap-2 mb-4">
              <div className="relative flex-1">
                <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
                <Input value={searchInput} onChange={e => setSearchInput(e.target.value)}
                  placeholder="Cari ID, PPPoE, SSID, IP..." className="pl-8 h-8 rounded-sm text-xs" />
              </div>
              <Button type="submit" size="sm" className="rounded-sm h-8 text-xs">Cari</Button>
              {search && (
                <Button type="button" size="sm" variant="outline" className="rounded-sm h-8 text-xs"
                  onClick={() => { setSearch(""); setSearchInput(""); }}>Reset</Button>
              )}
            </form>

            {/* Bulk Action Toolbar */}
            {isAdmin && (
              <div className={`flex flex-wrap items-center gap-2 mb-3 p-2.5 rounded-sm border transition-all ${
                selectedIds.size > 0
                  ? "bg-orange-500/5 border-orange-500/30"
                  : "bg-secondary/10 border-border"
              }`}>
                {selectedIds.size > 0 && (
                  <>
                    <ListChecks className="w-3.5 h-3.5 text-orange-400 flex-shrink-0" />
                    <span className="text-xs font-semibold text-orange-300">{selectedIds.size} dipilih</span>
                    <div className="flex gap-1.5 ml-auto flex-wrap">
                      <Button size="sm" variant="outline" className="rounded-sm h-7 text-[11px] gap-1 border-orange-500/30 text-orange-300 hover:bg-orange-500/10"
                        disabled={bulkRebooting}
                        onClick={() => setConfirmBulk({ mode: "selected" })}>
                        <RotateCcw className={`w-3 h-3 ${bulkRebooting ? "animate-spin" : ""}`} />
                        Reboot Selected ({selectedIds.size})
                      </Button>
                      <Button size="sm" variant="ghost" className="rounded-sm h-7 text-[11px] gap-1 text-muted-foreground"
                        onClick={clearSelection}>
                        <X className="w-3 h-3" /> Clear
                      </Button>
                    </div>
                  </>
                )}
                {selectedIds.size === 0 && (
                  <>
                    <span className="text-[11px] text-muted-foreground">Bulk Actions:</span>
                    <Button size="sm" variant="outline" className="rounded-sm h-7 text-[11px] gap-1"
                      onClick={selectAllVisible}>
                      <CheckSquare className="w-3 h-3" /> Pilih Semua
                    </Button>
                    {offlineDevices.length > 0 && (
                      <Button size="sm" variant="outline" className="rounded-sm h-7 text-[11px] gap-1 border-red-500/30 text-red-300 hover:bg-red-500/10"
                        disabled={bulkRebooting}
                        onClick={() => { selectAllOffline(); setTimeout(() => setConfirmBulk({ mode: "offline" }), 50); }}>
                        <WifiOff className="w-3 h-3" />
                        Reboot All Offline ({offlineDevices.length})
                      </Button>
                    )}
                  </>
                )}
              </div>
            )}

            {/* Table */}
            {loading ? (
              <p className="text-muted-foreground text-sm text-center py-8 animate-pulse">Memuat perangkat...</p>
            ) : devices.length === 0 ? (
              <div className="text-center py-12">
                <Cpu className="w-10 h-10 text-muted-foreground/30 mx-auto mb-3" />
                <p className="text-muted-foreground text-sm">Tidak ada perangkat ditemukan</p>
                {isAdmin && (
                  <Button size="sm" variant="outline" className="rounded-sm mt-3 text-xs gap-1"
                    onClick={() => setTab("config")}>
                    <Settings2 className="w-3 h-3" /> Setup GenieACS Server
                  </Button>
                )}
              </div>
            ) : (
              <div className="overflow-x-auto">
                <div className="overflow-y-auto" style={{ maxHeight: "60vh" }}>
                <table className="w-full text-left" style={{ minWidth: isAdmin ? 960 : 900 }}>
                  <thead className="sticky top-0 z-10 bg-card">
                    <tr className="border-b border-border">
                      {isAdmin && (
                        <th className="px-3 py-2 w-8">
                          <button
                            className="text-muted-foreground hover:text-foreground transition-colors"
                            onClick={selectedIds.size === devices.length ? clearSelection : selectAllVisible}
                            title={selectedIds.size === devices.length ? "Deselect all" : "Select all"}
                          >
                            {selectedIds.size > 0 && selectedIds.size === devices.length
                              ? <CheckSquare className="w-3.5 h-3.5 text-primary" />
                              : selectedIds.size > 0
                                ? <Square className="w-3.5 h-3.5 text-primary/50" />
                                : <Square className="w-3.5 h-3.5" />
                            }
                          </button>
                        </th>
                      )}
                      {headers.slice(isAdmin ? 1 : 0).map(h => (
                        <th key={h} className="px-3 py-2 text-[10px] text-muted-foreground uppercase tracking-wider font-medium whitespace-nowrap">{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {devices.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE).map(d => (
                      <tr key={d.id} className={`border-b border-border/30 hover:bg-secondary/20 transition-colors group ${
                        selectedIds.has(d.id) ? "bg-primary/5" : ""
                      }`}>
                        {isAdmin && (
                          <td className="px-3 py-2.5">
                            <button className="text-muted-foreground hover:text-foreground" onClick={() => toggleSelect(d.id)}>
                              {selectedIds.has(d.id)
                                ? <CheckSquare className="w-3.5 h-3.5 text-primary" />
                                : <Square className="w-3.5 h-3.5" />
                              }
                            </button>
                          </td>
                        )}
                        <DeviceRow
                          key={d.id}
                          device={d}
                          isAdmin={isAdmin}
                          onOpenModal={() => setSelectedDevice(d)}
                          onActivate={(dev) => setZtpDevice(dev)}
                        />
                      </tr>
                    ))}
                  </tbody>
                </table>
                </div>
                {/* Pagination */}
                <div className="flex items-center justify-between mt-3 px-1">
                  <p className="text-[10px] text-muted-foreground font-mono">
                    Menampilkan {Math.min((page - 1) * PAGE_SIZE + 1, devices.length)}–{Math.min(page * PAGE_SIZE, devices.length)} dari {devices.length} perangkat
                  </p>
                  {devices.length > PAGE_SIZE && (
                    <div className="flex items-center gap-1">
                      <button
                        disabled={page === 1}
                        onClick={() => setPage(p => p - 1)}
                        className="px-2.5 py-1 rounded text-[11px] border border-border disabled:opacity-30 hover:bg-secondary/50 transition-colors"
                      >← Prev</button>
                      <span className="text-[11px] text-muted-foreground px-2">
                        {page} / {Math.ceil(devices.length / PAGE_SIZE)}
                      </span>
                      <button
                        disabled={page >= Math.ceil(devices.length / PAGE_SIZE)}
                        onClick={() => setPage(p => p + 1)}
                        className="px-2.5 py-1 rounded text-[11px] border border-border disabled:opacity-30 hover:bg-secondary/50 transition-colors"
                      >Next →</button>
                    </div>
                  )}
                </div>
              </div>
            )}
          </>
        )}

        {tab === "faults" && <FaultsTab />}

        {tab === "config" && isAdmin && <ServerConfigTab />}

        {tab === "config" && !isAdmin && (
          <p className="text-muted-foreground text-sm text-center py-8">Hanya administrator yang dapat mengubah konfigurasi.</p>
        )}

        {tab === "guide" && <GuideTab />}
      </div>
    </div>
  );
}

