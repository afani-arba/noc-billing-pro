import { useState, useEffect, useCallback, useRef, Component } from "react";
import api from "@/lib/api";
import {
  PieChart, Pie, Cell, Tooltip as ReTooltip, ResponsiveContainer,
  LineChart, Line, XAxis, YAxis, CartesianGrid, Legend,
} from "recharts";
import {
  Radar, RefreshCw, ChevronDown, Globe, Activity, Wifi,
  TrendingUp, HardDrive, Radio, Server, AlertCircle, Users,
  Play, Square, RefreshCcw, BookOpen, Terminal, Copy, Check,
  Search, X, Eye, BarChart2, ExternalLink, CloudRain
} from "lucide-react";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import PeeringPlatformModal from "@/components/PeeringPlatformModal";
import Highcharts from 'highcharts';
import HighchartsReact from 'highcharts-react-official';
import highcharts3d from 'highcharts/highcharts-3d';

if (typeof Highcharts === 'object') {
  highcharts3d(Highcharts);
}
// ── Error Boundary ──────────────────────────────────────────────────────────
class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }
  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }
  componentDidCatch(error, info) {
    console.error('[PeeringEye] Render error:', error, info);
  }
  render() {
    if (this.state.hasError) {
      return (
        <div className="flex flex-col items-center justify-center min-h-[60vh] gap-4 text-center px-6">
          <div className="w-16 h-16 rounded-full bg-red-500/10 border border-red-500/30 flex items-center justify-center">
            <span className="text-3xl">⚠️</span>
          </div>
          <div>
            <p className="text-base font-bold text-red-400 mb-1">Terjadi Error pada Peering-Eye</p>
            <p className="text-xs text-muted-foreground max-w-sm">
              {this.state.error?.message || "Terjadi error tidak diketahui"}
            </p>
          </div>
          <button
            onClick={() => { this.setState({ hasError: false, error: null }); window.location.reload(); }}
            className="px-4 py-2 bg-primary/10 border border-primary/30 text-primary rounded-lg text-sm font-semibold hover:bg-primary/20 transition-colors"
          >
            🔄 Muat Ulang Halaman
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}



// â”€â”€ Format helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
function fmtBytes(b) {
  if (!b) return "0 B";
  if (b >= 1e9) return `${(b / 1e9).toFixed(2)} GB`;
  if (b >= 1e6) return `${(b / 1e6).toFixed(2)} MB`;
  if (b >= 1e3) return `${(b / 1e3).toFixed(1)} KB`;
  return `${b} B`;
}
function fmtNum(n) {
  if (!n) return "0";
  if (n >= 1e6) return `${(n / 1e6).toFixed(1)}M`;
  if (n >= 1e3) return `${(n / 1e3).toFixed(1)}K`;
  return String(n);
}

// â”€â”€ Range Options â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
const RANGES = [
  { value: "1h", label: "1 Jam" },
  { value: "6h", label: "6 Jam" },
  { value: "12h", label: "12 Jam" },
  { value: "24h", label: "24 Jam" },
  { value: "7d", label: "7 Hari" },
  { value: "30d", label: "30 Hari" },
];

// Highcharts natively handles 3D Pie Labels.

// â”€â”€ Stat Card â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
function StatCard({ icon: Icon, label, value, sub, color = "text-primary" }) {
  return (
    <div className="bg-card border border-border rounded-sm px-4 py-3">
      <div className="flex items-center gap-2 mb-1">
        <Icon className={`w-3.5 h-3.5 ${color}`} />
        <span className="text-[10px] text-muted-foreground uppercase tracking-wide">{label}</span>
      </div>
      <p className={`text-xl font-bold font-mono ${color}`}>{value}</p>
      {sub && <p className="text-[10px] text-muted-foreground mt-0.5">{sub}</p>}
    </div>
  );
}

// ────────────────────────────────────────────────────────────────────────────────
// BGP State Badge
// ────────────────────────────────────────────────────────────────────────────────
function BgpBadge({ state }) {
  const map = {
    ESTABLISHED: "text-green-400 border-green-400/30",
    ACTIVE:      "text-yellow-400 border-yellow-400/30",
    IDLE:        "text-red-400 border-red-400/30",
    CONNECT:     "text-blue-400 border-blue-400/30",
  };
  return (
    <Badge variant="outline" className={`text-[9px] rounded-sm px-1.5 ${map[state] || "text-muted-foreground border-border"}`}>
      {state || "UNKNOWN"}
    </Badge>
  );
}

// -- No Data Placeholder ---------------------------------------------------
function NoData({ message = "Belum ada data" }) {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-muted-foreground gap-2">
      <Radar className="w-10 h-10 opacity-20 animate-pulse" />
      <p className="text-sm">{message}</p>
    </div>
  );
}

// ===========================================================================
// BGP SETTINGS TAB
// ===========================================================================
function BgpSettingsTab({ bgpSettings, setBgpSettings, bgpSvcStatus, bgpSvcLoading, bgpSyncing, handleSvcCtrl, handleBgpSync, bgpStatus }) {
  const [form, setForm] = useState({ local_as: "", router_id: "" });
  const [saving, setSaving] = useState(false);
  const [allDevices, setAllDevices] = useState([]);
  const [loadingDevices, setLoadingDevices] = useState(false);
  const [diagnose, setDiagnose] = useState(null);
  const [diagnosing, setDiagnosing] = useState(false);
  const [savingDevice, setSavingDevice] = useState(null);
  const [pushingFilter, setPushingFilter] = useState(null);
  const [editDevice, setEditDevice] = useState({});

  useEffect(() => {
    if (bgpSettings) {
      setForm({ local_as: bgpSettings.local_as ?? "", router_id: bgpSettings.router_id ?? "" });
    }
  }, [bgpSettings]);

  useEffect(() => {
    setLoadingDevices(true);
    api.get("/devices?limit=200")
      .then(r => {
        const devs = Array.isArray(r.data) ? r.data : (r.data?.devices || r.data?.data || []);
        setAllDevices(devs);
        const initEdit = {};
        devs.forEach(d => {
          initEdit[d.id] = {
            bgp_peer_as: d.bgp_peer_as || "",
            bgp_enabled: !!d.bgp_enabled,
            bgp_peer_ip: d.bgp_peer_ip || "",
          };
        });
        setEditDevice(initEdit);
      })
      .catch(() => {})
      .finally(() => setLoadingDevices(false));
  }, []);

  const handleSave = async () => {
    if (!form.router_id || !form.local_as) { toast.error("Isi Router ID dan Local AS terlebih dahulu."); return; }
    setSaving(true);
    try {
      await api.post("/peering-eye/bgp/settings", { local_as: parseInt(form.local_as), router_id: form.router_id.trim() });
      setBgpSettings({ local_as: parseInt(form.local_as), router_id: form.router_id.trim() });
      toast.success("✅ Pengaturan BGP berhasil disimpan!");
    } catch (e) {
      toast.error("Gagal simpan: " + (e.response?.data?.detail || e.message));
    } finally { setSaving(false); }
  };

  const handleSaveDevice = async (deviceId) => {
    setSavingDevice(deviceId);
    const d = editDevice[deviceId] || {};
    try {
      const payload = {
        bgp_enabled: d.bgp_enabled,
        bgp_peer_as: d.bgp_peer_as ? parseInt(d.bgp_peer_as) : null,
        bgp_peer_ip: d.bgp_peer_ip ? d.bgp_peer_ip.trim() : null,
      };
      await api.put(`/devices/${deviceId}`, payload);
      setAllDevices(prev => prev.map(dev => dev.id === deviceId
        ? { ...dev, bgp_enabled: d.bgp_enabled, bgp_peer_as: d.bgp_peer_as, bgp_peer_ip: d.bgp_peer_ip }
        : dev));
      toast.success("✅ Perangkat BGP berhasil diperbarui.");
    } catch (e) {
      toast.error("Gagal update: " + (e.response?.data?.detail || e.message));
    } finally { setSavingDevice(null); }
  };

  const handlePushCommunityFilter = async (deviceIp, peerAs, deviceName) => {
    if (!deviceIp) return;
    if (!window.confirm(`Push BGP Community Filter (ROS v7) ke router ${deviceName} (${deviceIp})?`)) return;

    setPushingFilter(deviceIp);
    try {
      const res = await api.post("/peering-eye/bgp/peers/push-community-filter", { ip: deviceIp });
      toast.success(res.data?.message || "Route filter berhasil dikonfigurasi di MikroTik.");
    } catch (e) {
      toast.error("Gagal push filter: " + (e.response?.data?.detail || e.message));
    } finally {
      setPushingFilter(null);
    }
  };

  const handleDiagnose = async () => {
    setDiagnosing(true);
    try {
      const r = await api.get("/peering-eye/bgp/peers/diagnose");
      setDiagnose(r.data);
    } catch (e) {
      toast.error("Diagnosa gagal: " + (e.response?.data?.detail || e.message));
    } finally { setDiagnosing(false); }
  };

  const isActive  = bgpSvcStatus === "active";
  const enabledCount  = allDevices.filter(d => editDevice[d.id]?.bgp_enabled).length;
  const established   = bgpStatus?.established || 0;
  const totalPeers    = bgpStatus?.total || 0;

  const gobgpPeerMap = {};
  (bgpStatus?.peers || []).forEach(p => { gobgpPeerMap[p.neighbor_ip] = p.state; });

  const stateBadgeClass = (st) => {
    if (!st) return "bg-slate-500/15 text-slate-400 border-slate-500/30";
    const s = st.toUpperCase();
    if (s === "ESTABLISHED") return "bg-emerald-500/15 text-emerald-400 border-emerald-500/30";
    if (s === "ACTIVE")      return "bg-amber-500/15 text-amber-400 border-amber-500/30";
    if (s === "IDLE")        return "bg-red-500/15 text-red-400 border-red-500/30";
    if (s === "CONNECT")     return "bg-blue-500/15 text-blue-400 border-blue-500/30";
    return "bg-slate-500/15 text-slate-400 border-slate-500/30";
  };

  return (
    <div className="space-y-5 animate-in fade-in slide-in-from-bottom-2 duration-300 pb-16">

      {/* ── Hero Status Bar ───────────────────────────────────────────────── */}
      <div 
        className="relative overflow-hidden rounded-2xl border border-violet-500/30 p-5 shadow-lg shadow-violet-900/20"
        style={{ backgroundImage: 'linear-gradient(to bottom right, rgba(76, 29, 149, 0.4), rgba(88, 28, 135, 0.2), rgba(15, 23, 42, 0.6))', backgroundColor: '#0f172a' }}
      >
        {/* Background glow */}
        <div className="absolute top-0 right-0 w-64 h-64 bg-violet-500/10 rounded-full blur-3xl pointer-events-none" />

        <div className="relative flex flex-col sm:flex-row sm:items-center gap-4">
          {/* Icon + Title */}
          <div className="flex items-center gap-3 flex-1">
            <div className="p-2.5 rounded-xl bg-violet-500/20 border border-violet-500/30 shrink-0">
              <Radio className="w-5 h-5 text-violet-300" />
            </div>
            <div>
              <h2 className="text-base font-bold text-white tracking-tight">Konfigurasi BGP NOC Sentinel</h2>
              <p className="text-xs text-slate-400 mt-0.5">GoBGP daemon · Route steering · Peer management</p>
            </div>
          </div>

          {/* Status Pills */}
          <div className="flex items-center gap-2 flex-wrap">
            {/* Daemon status */}
            <div className={`flex items-center gap-2 px-3 py-1.5 rounded-full border text-xs font-semibold ${
              isActive
                ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-400"
                : "bg-red-500/10 border-red-500/30 text-red-400"
            }`}>
              <span className={`w-2 h-2 rounded-full ${isActive ? "bg-emerald-400 animate-pulse" : "bg-red-500"}`} />
              <span className="font-mono">{isActive ? "daemon: active" : "daemon: stopped"}</span>
            </div>

            {/* Peers status */}
            {totalPeers > 0 && (
              <div className="flex items-center gap-2 px-3 py-1.5 rounded-full border bg-violet-500/10 border-violet-500/30 text-violet-300 text-xs font-semibold">
                <Wifi className="w-3.5 h-3.5" />
                <span>{established}/{totalPeers} peers ESTABLISHED</span>
              </div>
            )}

            {/* Active devices */}
            <div className="flex items-center gap-2 px-3 py-1.5 rounded-full border bg-slate-800/50 border-slate-700 text-slate-300 text-xs font-semibold">
              <Server className="w-3.5 h-3.5" />
              <span>{enabledCount} perangkat BGP aktif</span>
            </div>
          </div>
        </div>

        {/* Config summary bar */}
        {bgpSettings?.router_id && (
          <div className="relative mt-4 pt-4 border-t border-violet-500/20 flex items-center gap-4 flex-wrap">
            <div className="flex items-center gap-2">
              <span className="text-[10px] font-semibold text-slate-400 uppercase tracking-widest">Local AS</span>
              <span className="font-mono text-sm font-bold text-violet-300">AS {bgpSettings.local_as}</span>
            </div>
            <div className="w-px h-4 bg-slate-700" />
            <div className="flex items-center gap-2">
              <span className="text-[10px] font-semibold text-slate-400 uppercase tracking-widest">Router ID</span>
              <span className="font-mono text-sm font-bold text-violet-300">{bgpSettings.router_id}</span>
            </div>
            <div className="w-px h-4 bg-slate-700" />
            <div className="flex items-center gap-1.5">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
              <span className="text-[10px] text-emerald-400 font-semibold">Konfigurasi aktif</span>
            </div>
          </div>
        )}
      </div>

      {/* ── Main Grid ────────────────────────────────────────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">

        {/* ── LEFT COLUMN ─────────────────────────────────────────────────── */}
        <div className="space-y-4">

          {/* GoBGP Server Config Card */}
          <div className="bg-card border border-border/60 rounded-xl overflow-hidden">
            {/* Card header */}
            <div className="flex items-center gap-2.5 px-5 py-3.5 border-b border-border/40 bg-secondary/20">
              <div className="p-1.5 rounded-lg bg-violet-500/15">
                <Server className="w-3.5 h-3.5 text-violet-400" />
              </div>
              <span className="text-sm font-bold">Server GoBGP</span>
            </div>

            <div className="p-5 space-y-4">
              <div>
                <label className="block text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-2">
                  Local AS (AS Number NOC)
                </label>
                <input
                  type="number" value={form.local_as}
                  onChange={e => setForm(f => ({ ...f, local_as: e.target.value }))}
                  placeholder="65000"
                  className="w-full px-3.5 py-2.5 bg-secondary/40 border border-border rounded-lg text-sm font-mono focus:outline-none focus:border-violet-500/70 focus:bg-secondary/60 transition-all placeholder:text-slate-600"
                />
                <p className="text-[10px] text-slate-500 mt-1.5">AS Number yang digunakan GoBGP server NOC Sentinel</p>
              </div>

              <div>
                <label className="block text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-2">
                  Router ID / IP Server NOC
                </label>
                <input
                  type="text" value={form.router_id}
                  onChange={e => setForm(f => ({ ...f, router_id: e.target.value }))}
                  placeholder="10.254.254.254"
                  className="w-full px-3.5 py-2.5 bg-secondary/40 border border-border rounded-lg text-sm font-mono focus:outline-none focus:border-violet-500/70 focus:bg-secondary/60 transition-all placeholder:text-slate-600"
                />
                <p className="text-[10px] text-amber-500/90 mt-1.5 flex items-start gap-1">
                  <span className="shrink-0 mt-0.5">⚠️</span>
                  IP ini di-set di MikroTik sebagai alamat BGP peer. Harus bisa diakses dari jaringan MikroTik.
                </p>
              </div>

              <button
                onClick={handleSave}
                disabled={saving}
                className="w-full flex items-center justify-center gap-2 px-4 py-2.5 bg-violet-600 hover:bg-violet-500 active:bg-violet-700 disabled:opacity-50 text-white rounded-lg text-sm font-semibold transition-all shadow-lg shadow-violet-500/20"
              >
                {saving
                  ? <><RefreshCw className="w-3.5 h-3.5 animate-spin" /> Menyimpan...</>
                  : <><Check className="w-3.5 h-3.5" /> Simpan Konfigurasi</>}
              </button>
            </div>
          </div>

          {/* Daemon Control Card */}
          <div className="bg-card border border-border/60 rounded-xl overflow-hidden">
            <div className="flex items-center justify-between px-5 py-3.5 border-b border-border/40 bg-secondary/20">
              <div className="flex items-center gap-2.5">
                <div className={`p-1.5 rounded-lg ${isActive ? "bg-emerald-500/15" : "bg-red-500/15"}`}>
                  <Activity className={`w-3.5 h-3.5 ${isActive ? "text-emerald-400" : "text-red-400"}`} />
                </div>
                <span className="text-sm font-bold">Kontrol GoBGP Daemon</span>
              </div>
              <div className={`flex items-center gap-1.5 text-[10px] font-semibold px-2 py-0.5 rounded-full ${
                isActive ? "bg-emerald-500/10 text-emerald-400" : "bg-red-500/10 text-red-400"
              }`}>
                <span className={`w-1.5 h-1.5 rounded-full ${isActive ? "bg-emerald-400 animate-pulse" : "bg-red-400"}`} />
                {bgpSvcStatus}
              </div>
            </div>

            <div className="p-5 space-y-3">
              {/* Control Buttons */}
              <div className="grid grid-cols-3 gap-2">
                {[
                  { action: "start", label: "Start", icon: Play, color: "emerald", desc: "Mulai daemon" },
                  { action: "stop",  label: "Stop",  icon: Square, color: "red",    desc: "Hentikan daemon" },
                  { action: "restart", label: "Restart", icon: RefreshCcw, color: "amber", desc: "Restart ulang" },
                ].map(({ action, label, icon: Icon, color, desc }) => (
                  <button
                    key={action}
                    onClick={() => handleSvcCtrl(action)}
                    disabled={bgpSvcLoading}
                    title={desc}
                    className={`flex flex-col items-center gap-2 py-3.5 rounded-xl border font-semibold text-[11px] transition-all disabled:opacity-40 disabled:cursor-not-allowed
                      ${color === "emerald" ? "bg-emerald-500/8 hover:bg-emerald-500/18 border-emerald-500/25 text-emerald-400 hover:border-emerald-500/40 hover:shadow-lg hover:shadow-emerald-500/10" : ""}
                      ${color === "red"     ? "bg-red-500/8 hover:bg-red-500/18 border-red-500/25 text-red-400 hover:border-red-500/40 hover:shadow-lg hover:shadow-red-500/10" : ""}
                      ${color === "amber"   ? "bg-amber-500/8 hover:bg-amber-500/18 border-amber-500/25 text-amber-400 hover:border-amber-500/40 hover:shadow-lg hover:shadow-amber-500/10" : ""}
                    `}
                  >
                    {bgpSvcLoading
                      ? <RefreshCw className="w-4 h-4 animate-spin opacity-50" />
                      : <Icon className="w-4 h-4" />
                    }
                    {label}
                  </button>
                ))}
              </div>

              {/* Sync Button */}
              <button
                onClick={handleBgpSync}
                disabled={bgpSyncing || bgpSvcStatus !== "active"}
                className="w-full flex items-center justify-center gap-2 py-2.5 bg-violet-500/10 hover:bg-violet-500/18 border border-violet-500/25 hover:border-violet-500/40 text-violet-400 rounded-xl text-[11px] font-semibold transition-all disabled:opacity-40 disabled:cursor-not-allowed"
              >
                <RefreshCw className={`w-3.5 h-3.5 ${bgpSyncing ? "animate-spin" : ""}`} />
                {bgpSyncing ? "Menyinkronkan peers..." : "Sync Peers ke GoBGP"}
              </button>
              <p className="text-[10px] text-slate-500 text-center">Mendaftarkan semua device BGP-enabled ke daemon</p>
            </div>
          </div>

          {/* Quick Stats */}
          {totalPeers > 0 && (
            <div className="grid grid-cols-2 gap-3">
              <div className="bg-card border border-emerald-500/20 rounded-xl p-4 text-center">
                <p className="text-2xl font-black text-emerald-400">{established}</p>
                <p className="text-[10px] text-slate-500 font-semibold uppercase tracking-wide mt-1">Established</p>
              </div>
              <div className="bg-card border border-slate-700/60 rounded-xl p-4 text-center">
                <p className="text-2xl font-black text-slate-300">{totalPeers - established}</p>
                <p className="text-[10px] text-slate-500 font-semibold uppercase tracking-wide mt-1">Tidak Aktif</p>
              </div>
            </div>
          )}
        </div>

        {/* ── RIGHT COLUMN ────────────────────────────────────────────────── */}
        <div className="lg:col-span-2 space-y-4">

          {/* Device BGP Peers Table */}
          <div className="bg-card border border-border/60 rounded-xl overflow-hidden">
            {/* Table header */}
            <div className="flex items-center justify-between px-5 py-3.5 border-b border-border/40 bg-secondary/20">
              <div className="flex items-center gap-2.5">
                <div className="p-1.5 rounded-lg bg-cyan-500/15">
                  <Wifi className="w-3.5 h-3.5 text-cyan-400" />
                </div>
                <div>
                  <span className="text-sm font-bold">Perangkat BGP Peers</span>
                  <span className="ml-2 text-[10px] px-2 py-0.5 rounded-full bg-cyan-500/10 border border-cyan-500/20 text-cyan-400 font-mono font-bold">
                    {enabledCount}/{allDevices.length} aktif
                  </span>
                </div>
              </div>
              <p className="text-[10px] text-slate-500 hidden sm:block">Toggle BGP &amp; isi AS Number per device</p>
            </div>

            {/* Column headers */}
            <div className="grid grid-cols-[40px_1fr_90px_130px_90px] gap-x-4 items-center px-4 py-3 bg-[#1e2230] border-b border-border/30">
              <span className="text-[10px] font-bold text-slate-500 uppercase tracking-widest">BGP</span>
              <span className="text-[10px] font-bold text-slate-500 uppercase tracking-widest">Perangkat</span>
              <span className="text-[10px] font-bold text-slate-500 uppercase tracking-widest text-center">Peer AS</span>
              <span className="text-[10px] font-bold text-slate-500 uppercase tracking-widest text-center">IP Override</span>
              <span className="text-[10px] font-bold text-slate-500 uppercase tracking-widest text-center">Aksi</span>
            </div>

            {loadingDevices ? (
              <div className="flex items-center justify-center py-16 gap-2.5 text-slate-500">
                <RefreshCw className="w-4 h-4 animate-spin" />
                <span className="text-xs">Memuat perangkat...</span>
              </div>
            ) : allDevices.length === 0 ? (
              <div className="text-center py-16 text-slate-500">
                <Server className="w-10 h-10 mx-auto mb-3 opacity-15" />
                <p className="text-sm font-semibold">Belum ada perangkat</p>
                <p className="text-xs mt-1">Tambahkan perangkat di halaman Devices terlebih dahulu.</p>
              </div>
            ) : (
              <div className="divide-y divide-border/10 pb-4">
                {allDevices.map(dev => {
                  const devEdit = editDevice[dev.id] || {};
                  const isEnabled = devEdit.bgp_enabled;
                  const devIp = dev.ip_address?.split(":")[0];
                  const overrideIp = (devEdit.bgp_peer_ip || "").trim();
                  const peerIp = overrideIp || devIp;
                  const gobgpState = gobgpPeerMap[peerIp] || gobgpPeerMap[devIp] || null;
                  const isEstablished = gobgpState === "ESTABLISHED";

                  return (
                    <div
                      key={dev.id}
                      className={`grid grid-cols-[40px_1fr_90px_130px_90px] gap-x-4 items-center px-4 py-3.5 transition-colors
                        ${isEnabled
                          ? isEstablished
                            ? "bg-emerald-500/5 hover:bg-emerald-500/10"
                            : "bg-violet-500/5 hover:bg-violet-500/10"
                          : "bg-transparent hover:bg-slate-800/30"
                        }`}
                    >
                      {/* Toggle */}
                      <div>
                        <button
                          onClick={() => setEditDevice(prev => ({
                            ...prev,
                            [dev.id]: { ...prev[dev.id], bgp_enabled: !devEdit.bgp_enabled }
                          }))}
                          className={`flex items-center rounded-full p-0.5 transition-colors duration-200 shrink-0 outline-none cursor-pointer
                            ${isEnabled ? "bg-[#8b5cf6]" : "bg-slate-600"}`}
                          style={{ height: "20px", width: "36px", minWidth: "36px" }}
                        >
                          <div className={`h-4 w-4 rounded-full bg-white shadow-sm transition-transform duration-200 ${isEnabled ? "translate-x-4" : "translate-x-0"}`} />
                        </button>
                      </div>

                      {/* Device info */}
                      <div className="min-w-0 pr-2">
                        <div className="flex items-center gap-2">
                          <p className={`text-[13px] font-bold truncate ${isEnabled ? "text-slate-200" : "text-slate-500"}`}>
                            {dev.name || dev.id}
                          </p>
                          {gobgpState && (
                            <span className={`text-[9px] px-1.5 py-0.5 rounded border font-bold tracking-wider ${stateBadgeClass(gobgpState)}`}>
                              {gobgpState}
                            </span>
                          )}
                        </div>
                        <p className="text-[11px] text-slate-500 font-mono mt-0.5">
                          {dev.ip_address}
                          {overrideIp && <span className="text-[#8b5cf6] font-semibold"> → {overrideIp}</span>}
                        </p>
                      </div>

                      {/* Peer AS input */}
                      <div>
                        <input
                          type="number"
                          value={devEdit.bgp_peer_as || ""}
                          onChange={e => setEditDevice(prev => ({
                            ...prev,
                            [dev.id]: { ...prev[dev.id], bgp_peer_as: e.target.value }
                          }))}
                          placeholder="65005"
                          disabled={!isEnabled}
                          className={`w-full px-2 py-1.5 rounded-lg text-[11px] font-mono text-center focus:outline-none transition-colors border
                            ${isEnabled 
                              ? "bg-black/30 border-slate-700 text-slate-300 focus:border-[#8b5cf6]" 
                              : "bg-transparent border-transparent text-slate-600 disabled:opacity-50"
                            }`}
                        />
                      </div>

                      {/* IP Override input */}
                      <div>
                        <input
                          type="text"
                          value={devEdit.bgp_peer_ip || ""}
                          onChange={e => setEditDevice(prev => ({
                            ...prev,
                            [dev.id]: { ...prev[dev.id], bgp_peer_ip: e.target.value }
                          }))}
                          placeholder="10.x.x.x"
                          disabled={!isEnabled}
                          className={`w-full px-2 py-1.5 rounded-lg text-[11px] font-mono text-center focus:outline-none transition-colors border
                            ${isEnabled 
                              ? "bg-black/30 border-slate-700 text-slate-300 focus:border-[#8b5cf6]" 
                              : "bg-transparent border-transparent text-slate-600 disabled:opacity-50"
                            }`}
                        />
                      </div>

                      {/* Actions */}
                      <div className="flex flex-col gap-1.5">
                        <button
                          onClick={() => handleSaveDevice(dev.id)}
                          disabled={savingDevice === dev.id}
                          className="w-full flex items-center justify-center gap-1.5 px-2 py-1.5 bg-[#8b5cf6]/10 hover:bg-[#8b5cf6]/20 border border-[#8b5cf6]/30 text-[#a78bfa] rounded-lg text-[10px] font-bold transition-all disabled:opacity-40"
                        >
                          {savingDevice === dev.id ? <RefreshCw className="w-3 h-3 animate-spin" /> : <><Check className="w-3 h-3" /> Simpan</>}
                        </button>
                        
                        {isEstablished && (
                          <button
                            onClick={() => handlePushCommunityFilter(dev.ip_address?.split(":")[0], devEdit.bgp_peer_as, dev.name)}
                            disabled={pushingFilter === dev.ip_address?.split(":")[0]}
                            className="w-full flex items-center justify-center gap-1 mt-0.5 px-2 py-1.5 bg-sky-500/12 hover:bg-sky-500/22 border border-sky-500/25 hover:border-sky-500/40 text-sky-400 rounded-lg text-[10px] font-bold transition-all disabled:opacity-40 shadow-sm shadow-sky-500/5"
                            title="Push Route Filter (Includes Community) ke MikroTik"
                          >
                            {pushingFilter === dev.ip_address?.split(":")[0] ? (
                              <RefreshCw className="w-2.5 h-2.5 animate-spin" />
                            ) : (
                              <CloudRain className="w-2.5 h-2.5" />
                            )}
                            Push Filter
                          </button>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}

            {/* Table footer */}
            <div className="px-4 py-3 border-t border-border/30 bg-secondary/10">
              <p className="text-[10px] text-slate-500">
                <span className="text-violet-400 font-semibold">IP Override</span>
                {" "}— Isi jika IP untuk koneksi BGP berbeda dengan IP management (contoh: pakai SSTP VPN atau NAT). Kosongkan jika tidak digunakan.
              </p>
            </div>
          </div>

          {/* Diagnostics Card */}
          <div className="bg-card border border-border/60 rounded-xl overflow-hidden">
            <div className="flex items-center justify-between px-5 py-3.5 border-b border-border/40 bg-secondary/20">
              <div className="flex items-center gap-2.5">
                <div className="p-1.5 rounded-lg bg-amber-500/15">
                  <Terminal className="w-3.5 h-3.5 text-amber-400" />
                </div>
                <div>
                  <span className="text-sm font-bold">Diagnostik Koneksi BGP</span>
                  <p className="text-[10px] text-slate-500 mt-0.5">Cek API & BGP connection ke semua perangkat (ROS 6 & ROS 7)</p>
                </div>
              </div>
              <button
                onClick={handleDiagnose}
                disabled={diagnosing}
                className="flex items-center gap-1.5 px-3 py-1.5 bg-amber-500/10 hover:bg-amber-500/20 border border-amber-500/25 hover:border-amber-500/40 text-amber-400 rounded-lg text-[11px] font-bold transition-all disabled:opacity-50 shadow-sm"
              >
                <Activity className={`w-3.5 h-3.5 ${diagnosing ? "animate-pulse" : ""}`} />
                {diagnosing ? "Mendiagnosa..." : "Jalankan Diagnosa"}
              </button>
            </div>

            <div className="p-5">
              {!diagnose && !diagnosing && (
                <div className="text-center py-10 text-slate-500">
                  <div className="w-12 h-12 rounded-2xl bg-amber-500/10 border border-amber-500/20 flex items-center justify-center mx-auto mb-3">
                    <Terminal className="w-6 h-6 text-amber-500/50" />
                  </div>
                  <p className="text-sm font-semibold text-slate-400">Siap mendiagnosa</p>
                  <p className="text-xs text-slate-600 mt-1">Klik "Jalankan Diagnosa" untuk memeriksa konektivitas ke semua perangkat</p>
                </div>
              )}

              {diagnosing && (
                <div className="flex flex-col items-center justify-center py-10 gap-3 text-amber-400">
                  <div className="relative w-10 h-10">
                    <RefreshCw className="w-10 h-10 animate-spin opacity-30 absolute" />
                    <Activity className="w-5 h-5 absolute top-2.5 left-2.5 animate-pulse" />
                  </div>
                  <span className="text-sm font-semibold">Menghubungi semua perangkat...</span>
                  <p className="text-xs text-slate-500">Memeriksa API & BGP connection</p>
                </div>
              )}

              {diagnose && !diagnosing && (
                <div className="space-y-2.5">
                  <div className="flex items-center gap-3 mb-4 p-3 bg-secondary/30 rounded-xl">
                    <div className="flex items-center gap-2 text-xs text-slate-400">
                      <Server className="w-3.5 h-3.5" />
                      <span><strong className="text-foreground">{diagnose.total_devices}</strong> perangkat diperiksa</span>
                    </div>
                    <div className="w-px h-4 bg-slate-700" />
                    <p className="text-[10px] text-slate-500 truncate">{diagnose.tip}</p>
                  </div>

                  {(diagnose.results || []).map((r, i) => (
                    <div
                      key={i}
                      className={`rounded-xl border overflow-hidden ${
                        r.reachable
                          ? "bg-emerald-500/4 border-emerald-500/20"
                          : "bg-red-500/4 border-red-500/20"
                      }`}
                    >
                      {/* Result header */}
                      <div className={`flex items-center gap-2.5 px-3 py-2.5 border-b flex-wrap ${
                        r.reachable ? "border-emerald-500/15 bg-emerald-500/5" : "border-red-500/15 bg-red-500/5"
                      }`}>
                        <span className={`w-2 h-2 rounded-full shrink-0 ${r.reachable ? "bg-emerald-400" : "bg-red-500"}`} />
                        <span className="text-xs font-bold">{r.name}</span>
                        <span className="text-[10px] font-mono text-slate-500">{r.ip}</span>

                        <div className="flex items-center gap-1.5 ml-auto flex-wrap">
                          <span className={`text-[9px] px-2 py-0.5 rounded-full border font-bold ${
                            r.ros_gen === "ROS 6"
                              ? "bg-blue-500/15 border-blue-500/30 text-blue-400"
                              : "bg-cyan-500/15 border-cyan-500/30 text-cyan-400"
                          }`}>
                            {r.ros_gen || r.api_mode}
                          </span>
                          {r.ros_version && (
                            <span className="text-[9px] text-slate-500 font-mono">{r.ros_version}</span>
                          )}
                          {r.bgp_enabled && (
                            <span className="text-[9px] px-2 py-0.5 rounded-full bg-violet-500/15 border border-violet-500/30 text-violet-400 font-bold">BGP ✓</span>
                          )}
                          {r.bgp_peer_ip && (
                            <span className="text-[9px] px-2 py-0.5 rounded-full bg-violet-500/10 border border-violet-500/20 text-violet-300 font-mono">
                              VPN: {r.bgp_peer_ip}
                            </span>
                          )}
                          {r.identity && (
                            <span className="text-[9px] text-slate-500 font-mono">{r.identity}</span>
                          )}
                        </div>
                      </div>

                      {/* Result body */}
                      <div className="px-3 py-2">
                        {r.error && (
                          <p className="text-[11px] text-red-400 font-mono bg-red-500/8 border border-red-500/15 px-3 py-2 rounded-lg mb-2 leading-relaxed">
                            {r.error}
                          </p>
                        )}

                        {r.bgp_connections?.length > 0 ? (
                          <div className="space-y-1">
                            <p className="text-[10px] text-slate-500 font-semibold mb-1.5">
                              {r.ros_gen === "ROS 6" ? "BGP Peers (ROS 6):" : "BGP Connections (ROS 7):"}
                            </p>
                            {r.bgp_connections.map((c, j) => {
                              const isRos6     = c._ros6 === true;
                              const remoteAddr = isRos6 ? (c["remote-address"] || "-") : (c.remote?.address || c["remote.address"] || "-");
                              const remoteAs   = isRos6 ? (c["remote-as"] || "?") : (c.remote?.as || c["remote.as"] || "?");
                              const localAs    = c.as || "?";
                              const connState  = c["connection-state"] || c.state || "";
                              const isOk = remoteAddr && remoteAddr !== "0.0.0.0" && remoteAs !== "0" && remoteAs !== "?";
                              return (
                                <div key={j} className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-[10px] font-mono ${
                                  isOk ? "bg-emerald-500/8 text-emerald-300" : "bg-amber-500/8 text-amber-300"
                                }`}>
                                  <span className="shrink-0">{isOk ? "✅" : "⚠️"}</span>
                                  <span className="font-bold text-foreground">{c.name || "(no name)"}</span>
                                  <span className="text-slate-400">AS{localAs} → {remoteAddr} AS{remoteAs}</span>
                                  {connState && (
                                    <span className={`ml-auto text-[9px] px-2 py-0.5 rounded-full border font-bold ${stateBadgeClass(connState)}`}>
                                      {connState.toUpperCase()}
                                    </span>
                                  )}
                                </div>
                              );
                            })}
                          </div>
                        ) : r.reachable && !r.error ? (
                          <p className="text-[11px] text-amber-400 flex items-center gap-1.5 py-1">
                            <span>⚠️</span>
                            Tidak ada BGP {r.ros_gen === "ROS 6" ? "peer" : "connection"} di RouterOS — klik Auto-Fix di panel BGP Peer Status
                          </p>
                        ) : null}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>

        </div>
      </div>
    </div>
  );
}

const POLL_INTERVAL = 30_000;

export default function PeeringEyePage(props) {
  return (
    <ErrorBoundary>
      <PeeringEyePageInner {...props} />
    </ErrorBoundary>
  );
}

function PeeringEyePageInner() {
  const [devices, setDevices]       = useState([]);
  const [selectedDev, setSelectedDev] = useState(null); // null = all
  const [range, setRange]           = useState("24h");
  const [summary, setSummary]       = useState(null);
  const [stats, setStats]           = useState(null);
  const [timeline, setTimeline]     = useState([]);
  const [topDomains, setTopDomains] = useState([]);
  const [topClients, setTopClients] = useState([]);
  const [bgpStatus, setBgpStatus]   = useState(null);
  const [loading, setLoading]       = useState(true);
  const [lastUpdate, setLastUpdate] = useState(null);
  const [domainPlatform, setDomainPlatform] = useState("all");
  const [bgpSvcStatus, setBgpSvcStatus] = useState("unknown");
  const [bgpSvcLoading, setBgpSvcLoading] = useState(false);
  const [platformDetail, setPlatformDetail] = useState(null); // { platform, data, loading }
  const [bgpSyncing, setBgpSyncing]       = useState(false);
  const [svcStatus, setSvcStatus] = useState(null);
  const [svcRestarting, setSvcRestarting] = useState(false);
  const [bgpSettings, setBgpSettings]   = useState(null); // { local_as, router_id }
  const bgpPollRef = useRef(null);

  const [showDevDropdown, setShowDevDropdown] = useState(false);
  const [showRangeDropdown, setShowRangeDropdown] = useState(false);
  const [showDomainDropdown, setShowDomainDropdown] = useState(false);
  const [showPlatformsModal, setShowPlatformsModal] = useState(false);
  const [activeTab, setActiveTab] = useState("traffic");

  // ── Client Activity Modal ──────────────────────────────────────────────────
  const [clientActivityIp, setClientActivityIp] = useState(null);
  const [showClientActivity, setShowClientActivity] = useState(false);
  const [clientSearchIp, setClientSearchIp] = useState("");

  const openClientActivity = (ip) => {
    setClientActivityIp(ip);
    setShowClientActivity(true);
  };

  const intervalRef = useRef(null);

  // â”€â”€ Fetch all data â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
  const fetchAll = useCallback(async (showLoader = false) => {
    if (showLoader) setLoading(true);
    const devId = selectedDev?.device_id || "";
    try {
      const [sumRes, statsRes, tlRes, domainsRes, clientsRes, bgpRes, svcRes] = await Promise.allSettled([
        api.get(`/peering-eye/summary?device_id=${devId}&range=${range}`),
        api.get(`/peering-eye/stats?device_id=${devId}&range=${range}`),
        api.get(`/peering-eye/timeline?device_id=${devId}&range=${range}`),
        api.get(`/peering-eye/top-domains?device_id=${devId}&range=${range}&limit=20&platform=${domainPlatform}`),
        api.get(`/peering-eye/top-clients?device_id=${devId}&range=${range}&limit=20&platform=${domainPlatform}`),
        api.get("/peering-eye/bgp/status"),
        api.get("/peering-eye/bgp/service/status"),
        api.get("/peering-eye/service-status"),
      ]);

      if (sumRes.status    === "fulfilled") setSummary(sumRes.value.data);
      if (statsRes.status  === "fulfilled") setStats(statsRes.value.data);
      if (tlRes.status     === "fulfilled") setTimeline(tlRes.value.data.data || []);
      if (domainsRes.status === "fulfilled") setTopDomains(domainsRes.value.data.domains || []);
      if (clientsRes.status === "fulfilled") setTopClients(clientsRes.value.data.clients || []);
      if (bgpRes.status    === "fulfilled") setBgpStatus(bgpRes.value.data);
      if (svcRes.status    === "fulfilled") setBgpSvcStatus(svcRes.value.data.status || "unknown");
      // fetch service-status separately & update
      try {
        const svcR = await api.get("/peering-eye/service-status");
        setSvcStatus(svcR.data);
      } catch (_) {}
      setLastUpdate(new Date());
    } catch (e) {
      // silent
    } finally {
      setLoading(false);
    }
  }, [selectedDev, range, domainPlatform]);

  const handleBlock = async (targetType, target) => {
    if (!selectedDev?.device_id) {
      alert("Silakan pilih perangkat/router spesifik (bukan 'Semua Router') terlebih dahulu sebelum melakukan aksi blokir.");
      return;
    }
    const msg = targetType === "domain" 
      ? `Anda yakin ingin memblokir akses ke domain ${target}?` 
      : `Anda yakin ingin memblokir/mengisolir klien ${target}?`;
    
    if (!window.confirm(msg)) return;
    
    try {
      const res = await api.post("/peering-eye/block", {
        device_id: selectedDev.device_id,
        target_type: targetType,
        target: target
      });
      alert(res.data?.message || "Berhasil diblokir!");
    } catch (e) {
      alert("Gagal memblokir: " + (e.response?.data?.detail || e.message));
    }
  };

  const handleSvcCtrl = async (action) => {
    setBgpSvcLoading(true);
    try {
      await api.post("/peering-eye/bgp/service/control", { action });
      toast.success(`Service BGP berhasil di-${action}`);
      // Setelah start/restart, otomatis sync peers & refresh status
      if (action !== "stop") {
        setTimeout(async () => {
          try {
            await api.post("/peering-eye/bgp/peers/sync");
            const r = await api.get("/peering-eye/bgp/peers/status");
            setBgpStatus(r.data);
            toast.success(`${r.data?.total || 0} peer BGP berhasil di-sync ke gobgpd`);
          } catch (_) {}
        }, 3500);
      }
      setTimeout(() => fetchAll(false), 2000);
    } catch (e) {
      toast.error(`Gagal ${action} service: ${e.response?.data?.detail || e.message}`);
    } finally {
      setBgpSvcLoading(false);
    }
  };

  // Sync peers BGP dari DB ke gobgpd secara manual
  const handleBgpSync = async () => {
    setBgpSyncing(true);
    try {
      const res = await api.post("/peering-eye/bgp/peers/sync");
      toast.success(res.data?.message || "Sync BGP peers berhasil");
      // Refresh status setelah sync
      const r = await api.get("/peering-eye/bgp/peers/status");
      setBgpStatus(r.data);
    } catch (e) {
      toast.error("Gagal sync peers: " + (e.response?.data?.detail || e.message));
    } finally {
      setBgpSyncing(false);
    }
  };

  const [fixingBgpFor, setFixingBgpFor] = useState(null);
  const handleAutoFixBgp = async (neighborIp) => {
    // Validasi: router_id harus sudah dikonfigurasi
    const routerId = bgpSettings?.router_id;
    if (!routerId || routerId === "127.0.0.1" || routerId === "0.0.0.0") {
      toast.error(
        "IP GoBGP server belum dikonfigurasi! " +
        "Masuk ke Pengaturan BGP dan isi Router ID dengan IP server NOC yang bisa diakses MikroTik.",
        { duration: 8000 }
      );
      return;
    }

    const confirmed = window.confirm(
      `Auto-Fix BGP untuk peer ${neighborIp}?\n\n` +
      `MikroTik akan dikonfigurasi untuk konek ke:\n` +
      `  Server IP : ${routerId}\n` +
      `  Server AS : ${bgpSettings?.local_as || 65000}\n\n` +
      `Pastikan IP ini bisa diakses dari MikroTik router.`
    );
    if (!confirmed) return;

    setFixingBgpFor(neighborIp);
    try {
      const res = await api.post("/peering-eye/bgp/peers/autofix", { 
        neighbor_ip: neighborIp,
        // server_ip tidak perlu dikirim — backend pakai router_id dari bgp_settings
      });
      const data = res.data;
      toast.success(data?.message || "Auto-fix BGP MikroTik berhasil!", { duration: 6000 });
      
      // Tampilkan detail langkah-langkah jika ada
      if (data?.detail?.length > 0) {
        data.detail.forEach(dev => {
          const lastStep = dev.steps?.[dev.steps.length - 1] || "";
          if (lastStep.includes("✅")) {
            toast.success(`${dev.device}: ${lastStep.replace("✅ ", "")}`, { duration: 5000 });
          }
        });
      }
      
      // Refresh BGP status
      setTimeout(async () => {
        try {
          const r = await api.get("/peering-eye/bgp/peers/status");
          setBgpStatus(r.data);
        } catch (_) {}
      }, 4000);
    } catch (e) {
      const errData = e.response?.data?.detail;
      if (errData && typeof errData === "object") {
        const msgs = errData.errors || [];
        const shortMsg = msgs[0] || errData.message || "Gagal auto-fix";
        toast.error(`Auto-fix gagal: ${shortMsg}`, { duration: 8000 });
        if (errData.detail?.length > 0) {
          errData.detail.forEach(dev => {
            const failStep = (dev.steps || []).find(s => s.includes("❌"));
            if (failStep) {
              toast.error(`${dev.device}: ${failStep.replace("❌ ", "")}`, { duration: 8000 });
            }
          });
        }
      } else {
        toast.error("Auto-fix gagal: " + (typeof errData === "string" ? errData : e.message), { duration: 8000 });
      }
    } finally {
      setFixingBgpFor(null);
    }
  };

  // ── Push Community Filter ke MikroTik ──────────────────────────────────────────
  const [pushingFilterFor, setPushingFilterFor] = useState(null);
  const handlePushCommunityFilter = async (neighborIp) => {
    const localAs = bgpSettings?.local_as || 65000;
    const lastOctet = neighborIp.split(".").pop();
    const community = `${localAs}:${lastOctet}`;

    const confirmed = window.confirm(
      `Push BGP Community Filter ke MikroTik peer ${neighborIp}?\n\n` +
      `Filter akan dikonfigurasi sehingga peer ini:\n` +
      `  ✅ Hanya menerima prefix dengan community: ${community}\n` +
      `  ❌ Menolak prefix dengan community lain\n\n` +
      `Syntax ROS v7: if (bgp-communities.any(${community})) { accept } else { reject }\n\n` +
      `Pastikan MikroTik dapat diakses via REST API.`
    );
    if (!confirmed) return;

    setPushingFilterFor(neighborIp);
    try {
      const res = await api.post("/peering-eye/bgp/peers/push-community-filter", {
        neighbor_ip: neighborIp,
      });
      const data = res.data;
      const peerResult = data?.results?.find(r => r.peer === neighborIp);
      if (peerResult?.success) {
        toast.success(
          `✅ Community Filter berhasil di-push ke ${peerResult.device || neighborIp}! ` +
          `Community: ${community} — chain: ${peerResult.filter_chain || "sentinel-bgp-in"}`,
          { duration: 8000 }
        );
        (peerResult.steps || []).forEach(step => {
          if (step.includes("✅")) toast.success(step, { duration: 4000 });
        });
      } else {
        const errMsg = peerResult?.error || data?.message || "Gagal push filter";
        toast.error(`Push filter gagal: ${errMsg}`, { duration: 8000 });
      }
    } catch (e) {
      const errData = e.response?.data?.detail;
      toast.error("Push filter gagal: " + (typeof errData === "string" ? errData : e.message), { duration: 8000 });
    } finally {
      setPushingFilterFor(null);
    }
  };

  // â”€â”€ Load devices â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
  // ── Load devices & BGP settings ─────────────────────────────────────────────────────────
  useEffect(() => {
    api.get("/peering-eye/devices")
      .then(r => setDevices(r.data || []))
      .catch(() => {});
    api.get("/peering-eye/bgp/settings")
      .then(r => setBgpSettings(r.data))
      .catch(() => {});
  }, []);

  // â”€â”€ Poll â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
  useEffect(() => {
    fetchAll(true);
    clearInterval(intervalRef.current);
    intervalRef.current = setInterval(() => fetchAll(false), POLL_INTERVAL);
    return () => clearInterval(intervalRef.current);
  }, [fetchAll]);

  // ── Poll BGP peer status tersendiri (15 detik) ───────────────────────────────
  useEffect(() => {
    clearInterval(bgpPollRef.current);
    bgpPollRef.current = setInterval(async () => {
      try {
        const [peerRes, svcRes] = await Promise.allSettled([
          api.get("/peering-eye/bgp/peers/status"),
          api.get("/peering-eye/bgp/service/status"),
        ]);
        if (peerRes.status === "fulfilled") setBgpStatus(peerRes.value.data);
        if (svcRes.status === "fulfilled") setBgpSvcStatus(svcRes.value.data?.status || "unknown");
      } catch (_) {}
    }, 15_000);
    return () => clearInterval(bgpPollRef.current);
  }, []);


  // â”€â”€ Build line chart series keys â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
  const platformsInTimeline = timeline.length > 0
    ? Object.keys(timeline[0]).filter(k => k !== "time" && k !== "Others").slice(0, 10)
    : [];

  // â”€â”€ Flatten timeline for recharts â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
  const chartData = timeline.map(row => {
    const flat = { time: row.time };
    platformsInTimeline.forEach(p => {
      flat[p] = (row[p]?.hits || 0);
    });
    return flat;
  });

  const rawPlatforms = stats?.platforms || [];
  // Gunakan hits jika semua bytes = 0 (mode DNS syslog only, tanpa NetFlow)
  const totalBytes = rawPlatforms.reduce((s, p) => s + (p.bytes || 0), 0);
  const useHits    = totalBytes === 0;
  const sortedRaw  = [...rawPlatforms].sort((a, b) =>
    useHits ? (b.hits - a.hits) : (b.bytes - a.bytes)
  );

  const NEON_COLORS = [
    "#00FFC4", "#7c3aed", "#f7a35c", "#ef4444", "#8085e9",
    "#f15c80", "#22d3ee", "#84cc16", "#f59e0b", "#ec4899",
  ];
  const platforms = sortedRaw.map((p, i) => ({
    ...p,
    color: p.color && p.color !== "#64748b" ? p.color : (i < 10 ? NEON_COLORS[i] : p.color)
  }));
  const bgpPeers  = bgpStatus?.peers || [];

  return (
    <div className="space-y-4 pb-16">
      {/* â”€â”€ Header â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <h1 className="text-xl sm:text-2xl font-bold tracking-tight flex items-center gap-2">
            <Radar className="w-6 h-6 text-cyan-400" />
            Sentinel Peering-Eye
            <span className="text-[9px] font-mono bg-cyan-500/10 border border-cyan-500/30 text-cyan-400 px-1.5 py-0.5 rounded-sm">
              BETA
            </span>
          </h1>
          <p className="text-xs text-muted-foreground">
            Analitik traffic platform &middot; Update setiap 30 detik
            {lastUpdate && (
              <span className="ml-2 opacity-60">
                &middot; terakhir {lastUpdate.toLocaleTimeString("id-ID")}
              </span>
            )}
          </p>
        </div>

        {/* Controls */}
        <div className="flex flex-wrap items-center gap-2">
          {/* Range Picker */}
          <div className="relative">
            <button
              onClick={() => { setShowRangeDropdown(v => !v); setShowDevDropdown(false); }}
              className="flex items-center gap-1.5 px-3 py-2 bg-card border border-border rounded-sm text-xs hover:bg-secondary/20 transition-colors"
            >
              {RANGES.find(r => r.value === range)?.label}
              <ChevronDown className="w-3 h-3 text-muted-foreground" />
            </button>
            {showRangeDropdown && (
              <div className="absolute right-0 top-full mt-1 z-50 bg-card border border-border rounded-sm shadow-xl min-w-[100px]">
                {RANGES.map(r => (
                  <button
                    key={r.value}
                    onClick={() => { setRange(r.value); setShowRangeDropdown(false); }}
                    className={`w-full text-left px-3 py-2 text-xs hover:bg-secondary/30 ${range === r.value ? "text-primary" : ""}`}
                  >
                    {r.label}
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* Device Picker */}
          <div className="relative">
            <button
              onClick={() => { setShowDevDropdown(v => !v); setShowRangeDropdown(false); }}
              className="flex items-center gap-2 px-3 py-2 bg-card border border-border rounded-sm text-xs hover:bg-secondary/20 transition-colors min-w-[160px] justify-between"
            >
              <div className="flex items-center gap-1.5 truncate">
                <Server className="w-3 h-3 text-muted-foreground flex-shrink-0" />
                <span className="truncate">{selectedDev ? selectedDev.device_name : "Semua Router"}</span>
              </div>
              <ChevronDown className="w-3 h-3 text-muted-foreground flex-shrink-0" />
            </button>
            {showDevDropdown && (
              <div className="absolute right-0 top-full mt-1 z-50 bg-card border border-border rounded-sm shadow-xl min-w-[220px] max-h-64 overflow-y-auto">
                <button
                  onClick={() => { setSelectedDev(null); setShowDevDropdown(false); }}
                  className={`w-full text-left px-3 py-2.5 text-xs hover:bg-secondary/30 flex items-center gap-2 ${!selectedDev ? "text-primary bg-primary/10" : ""}`}
                >
                  <Globe className="w-3 h-3" /> Semua Router
                </button>
                {devices.map(d => (
                  <button
                    key={d.device_id}
                    onClick={() => { setSelectedDev(d); setShowDevDropdown(false); }}
                    className={`w-full text-left px-3 py-2.5 text-xs hover:bg-secondary/30 flex items-center gap-2 justify-between ${selectedDev?.device_id === d.device_id ? "text-primary bg-primary/10" : ""}`}
                  >
                    <span className="truncate">{d.device_name}</span>
                    <span className="text-[9px] text-muted-foreground font-mono shrink-0">{fmtNum(d.total_hits)} hits</span>
                  </button>
                ))}
              </div>
            )}
          </div>

          <button
            onClick={() => fetchAll(true)}
            disabled={loading}
            className="p-2 bg-card border border-border rounded-sm hover:bg-secondary/20 transition-colors"
          >
            <RefreshCw className={`w-4 h-4 text-muted-foreground ${loading ? "animate-spin" : ""}`} />
          </button>
          
          <button
            onClick={() => setShowPlatformsModal(true)}
            className="flex items-center gap-1.5 px-3 py-2 bg-primary/10 border border-primary/30 text-primary rounded-sm text-xs font-semibold hover:bg-primary/20 transition-colors ml-2"
          >
            <Server className="w-3.5 h-3.5" /> Kelola Platform
          </button>
        </div>
      </div>

      {/* Tab Navigation */}
      <div className="flex flex-wrap border-b border-border/50 bg-card mb-4">
        <button onClick={() => setActiveTab("traffic")} className={`px-4 py-2.5 text-sm font-semibold transition-colors whitespace-nowrap ${activeTab === "traffic" ? "border-b-2 border-cyan-400 text-cyan-400" : "text-muted-foreground hover:bg-secondary/20 hover:text-foreground"}`}>Traffic Intelligence</button>
        <button onClick={() => setActiveTab("bgp-settings")} className={`px-4 py-2.5 text-sm font-semibold transition-colors flex items-center gap-1.5 whitespace-nowrap ${activeTab === "bgp-settings" ? "border-b-2 border-violet-400 text-violet-400" : "text-muted-foreground hover:bg-secondary/20 hover:text-foreground"}`}>
          <Radio className="w-3.5 h-3.5" /> BGP Settings
        </button>
        <button onClick={() => setActiveTab("guide")} className={`px-4 py-2.5 text-sm font-semibold transition-colors whitespace-nowrap ${activeTab === "guide" ? "border-b-2 border-emerald-400 text-emerald-400" : "text-muted-foreground hover:bg-secondary/20 hover:text-foreground"}`}>Cara Penggunaan</button>
      </div>

      {activeTab === "guide" && <PeeringGuideTab />}
      {activeTab === "bgp-settings" && (
        <BgpSettingsTab
          bgpSettings={bgpSettings}
          setBgpSettings={setBgpSettings}
          bgpSvcStatus={bgpSvcStatus}
          bgpSvcLoading={bgpSvcLoading}
          bgpSyncing={bgpSyncing}
          handleSvcCtrl={handleSvcCtrl}
          handleBgpSync={handleBgpSync}
          bgpStatus={bgpStatus}
        />
      )}

      {activeTab === "traffic" && (
        <div className="space-y-4 animate-in fade-in slide-in-from-bottom-2 duration-300">
    {/* ─── Service Status Banner ─────────────────────────────────────────── */}
    {!loading && (() => {
  const hasFresh = svcStatus?.has_fresh_data;
      const syslogOk = svcStatus?.syslog_enabled || svcStatus?.syslog_running;
      const totalRec = svcStatus?.total_records || 0;
      const noData   = !summary?.total_hits;
      const isGlobal = !selectedDev;

      // Banner error: Tampil jika service mati (hasFresh == false global) ATAU global 0 data
      if (svcStatus && (!hasFresh || (isGlobal && noData))) {
        return (
          <div className="flex items-start gap-3 p-4 bg-yellow-500/10 border border-yellow-500/20 rounded-sm">
            <AlertCircle className="w-4 h-4 text-yellow-400 mt-0.5 flex-shrink-0" />
            <div className="flex-1">
              <p className="text-xs font-semibold text-yellow-300">Belum ada data Peering-Eye</p>
              <p className="text-[11px] text-yellow-300/70 mt-0.5">
                Pastikan MikroTik sudah dikonfigurasi mengirim DNS Syslog (port {svcStatus?.syslog_port || 5514}) ke server ini.
              </p>
              <div className="flex flex-wrap gap-2 mt-2">
                <span className={`inline-flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-full border ${syslogOk ? "border-green-500/40 bg-green-500/10 text-green-400" : "border-red-500/40 bg-red-500/10 text-red-400"}`}>
                  <span className={`w-1.5 h-1.5 rounded-full ${syslogOk ? "bg-green-400" : "bg-red-400"}`} />
                  Syslog Listener {syslogOk ? "✔ Aktif" : "✘ Nonaktif"} :{svcStatus?.syslog_port || 5514}
                </span>
                {totalRec > 0 && (
                  <span className="inline-flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-full border border-blue-500/40 bg-blue-500/10 text-blue-400">
                    📊 {totalRec.toLocaleString()} record tersimpan (data lama)
                  </span>
                )}
              </div>
            </div>
            {syslogOk && (
              <button
                onClick={async () => {
                  setSvcRestarting(true);
                  try {
                    const r = await api.post("/peering-eye/service-restart");
                    toast.success(r.data?.message || "Collector berhasil direstart");
                    setTimeout(() => fetchAll(false), 3000);
                  } catch (e) {
                    toast.error("Gagal restart: " + (e.response?.data?.detail || e.message));
                  } finally { setSvcRestarting(false); }
                }}
                disabled={svcRestarting}
                className="flex items-center gap-1.5 px-2.5 py-1.5 bg-yellow-500/20 border border-yellow-500/40 text-yellow-300 rounded text-[11px] font-semibold hover:bg-yellow-500/30 transition-colors whitespace-nowrap shrink-0"
              >
                <RefreshCcw className={`w-3 h-3 ${svcRestarting ? "animate-spin" : ""}`} />
                {svcRestarting ? "Restarting..." : "Restart Collector"}
              </button>
            )}
          </div>
        );
      }
      if (!noData && svcStatus) {
        return (
          <div className="flex items-center gap-2 px-3 py-2 bg-green-500/5 border border-green-500/20 rounded-sm">
            <span className="w-2 h-2 rounded-full bg-green-400 animate-pulse" />
            <p className="text-[11px] text-green-300 font-medium">
              Collector aktif &mdash; {svcStatus.total_records?.toLocaleString()} record tersimpan
              {svcStatus.last_seen && <span className="text-green-300/60 ml-1">(terakhir: {new Date(svcStatus.last_seen).toLocaleTimeString("id-ID")})</span>}
            </p>
          </div>
        );
      }
      return null;
    })()}

      {/* ─── Stat Cards ────────────────────────────────────────────────────────── */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <StatCard icon={Activity}   label="Total DNS Hits"    value={fmtNum(summary?.total_hits || 0)}       color="text-cyan-400" />
        <StatCard icon={TrendingUp} label="Top Platform"      value={summary?.top_platform || "—"}           sub={summary?.top_platform_icon}  color="text-emerald-400" />
        <StatCard icon={Globe}      label="Unique Platform"   value={summary?.unique_platforms || 0}         color="text-purple-400" />
        <StatCard icon={HardDrive}  label="Est. Traffic"      value={summary?.total_bytes_fmt || "0 B"}      color="text-yellow-400" />
      </div>

      {/* ─── Charts Row ────────────────────────────────────────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-5 gap-4">
        {/* Donut Chart */}
        <div className="lg:col-span-2 bg-[#09090b] border border-[#27272a]/70 rounded-xl p-4 relative overflow-hidden shadow-2xl">
          <div className="absolute top-0 right-0 w-48 h-48 bg-indigo-500/10 rounded-full blur-3xl pointer-events-none" />
          <p className="text-xs font-bold mb-1 text-white z-10 relative">Distribusi Platform</p>
          <p className="text-[10px] text-muted-foreground mb-3 z-10 relative">
            {useHits ? "Berdasarkan DNS Hits" : "Berdasarkan Total Estimasi Traffic"}
          </p>
          {platforms.length === 0 ? (
            <NoData message="Belum ada data platform" />
          ) : (
            <div className="z-10 relative mt-2 w-full h-[260px]">
              <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none z-10" style={{ transform: 'translateY(-10px)' }}>
                 <p className="text-white text-[15px] font-[800] drop-shadow-md tracking-wide">TRAFFIC</p>
                 <p className="text-white text-[15px] font-[800] drop-shadow-md tracking-wide">SHARES</p>
              </div>
              <HighchartsReact
                highcharts={Highcharts}
                options={{
                  chart: {
                    type: 'pie',
                    backgroundColor: 'transparent',
                    options3d: { enabled: true, alpha: 45 },
                    height: 260,
                    margin: [0, 0, 0, 0]
                  },
                  title: { text: '' },
                  tooltip: {
                    backgroundColor: "rgba(9, 9, 11, 0.95)",
                    borderColor: "#27272a",
                    style: { color: '#fff', fontSize: '12px' },
                    pointFormatter: function() {
                      return useHits
                        ? `<b>${this.name}</b>: ${this.y.toLocaleString()} hits`
                        : `<b>${this.name}</b>: ${fmtBytes(this.y)}`;
                    }
                  },
                  plotOptions: {
                    pie: {
                      innerSize: '55%',
                      depth: 45,
                      dataLabels: {
                        enabled: true,
                        useHTML: true,
                        format: '<div style="color:{point.color}; text-align:center; font-family:\'Inter\',\'Segoe UI\',sans-serif; font-weight:700; font-size:11px; line-height: 1.2;">{point.name}<br/>{point.percentage:.1f}%</div>',
                        style: { textOutline: 'none' },
                        connectorWidth: 1.5,
                        connectorPadding: 5,
                        distance: 30
                      }
                    }
                  },
                  series: [{
                    name: useHits ? 'DNS Hits' : 'Traffic',
                    data: platforms.filter(p => p.platform !== "Others").slice(0, 10).map(p => ({
                       name: p.platform,
                       y: useHits ? (p.hits || 0) : (p.bytes || 0),
                       color: p.color
                    })).filter(p => p.y > 0)
                  }],
                  credits: { enabled: false }
                }}
              />
            </div>
          )}
        </div>

        {/* Area Chart Timeline */}
        <div className="lg:col-span-3 bg-[#09090b] border border-[#27272a]/70 rounded-xl p-4 relative shadow-2xl">
          <div className="absolute top-0 left-0 w-64 h-64 bg-cyan-500/5 rounded-full blur-3xl pointer-events-none" />
          <p className="text-xs font-bold mb-1 text-white z-10 relative">Timeline Traffic</p>
          <p className="text-[10px] text-muted-foreground mb-3 z-10 relative">DNS hits per platform &ndash; {RANGES.find(r => r.value === range)?.label} terakhir</p>
          {chartData.length === 0 ? (
            <NoData message="Belum ada data timeline" />
          ) : (
            <ResponsiveContainer width="100%" height={260} className="z-10 relative">
              <LineChart data={chartData} margin={{ left: -10, right: 10, top: 15, bottom: 0 }}>
                <defs>
                  <filter id="neonLine" x="-50%" y="-50%" width="200%" height="200%">
                    <feGaussianBlur stdDeviation="2" result="blur" />
                    <feMerge>
                      <feMergeNode in="blur" />
                      <feMergeNode in="SourceGraphic" />
                    </feMerge>
                  </filter>
                </defs>
                <CartesianGrid strokeDasharray="5 5" stroke="#27272a" vertical={true} />
                <XAxis dataKey="time" tick={{ fill: "#a1a1aa", fontSize: 9 }} tickLine={false} axisLine={false} />
                <YAxis tick={{ fill: "#a1a1aa", fontSize: 10, fontWeight: 500 }} tickLine={false} axisLine={false} width={65} tickFormatter={fmtBytes} />
                <ReTooltip
                  contentStyle={{ backgroundColor: "rgba(9, 9, 11, 0.95)", borderColor: "#27272a", borderRadius: "8px", fontSize: "12px", boxShadow: "0 0 20px rgba(0,0,0,0.8)", border: "1px solid rgba(255,255,255,0.1)" }}
                  formatter={(v, n) => [fmtBytes(v), n]}
                />
                <Legend iconSize={12} iconType="circle" wrapperStyle={{ fontSize: 11, paddingTop: 8, color: '#e4e4e7' }} />
                {platformsInTimeline.map((p, i) => {
                  const color = platforms.find(pl => pl.platform === p)?.color || "#64748b";
                  return (
                    <Line
                      key={p}
                      type="linear"
                      dataKey={p}
                      stroke={color}
                      strokeWidth={2.5}
                      dot={false}
                      filter="url(#neonLine)"
                      isAnimationActive={true}
                    />
                  );
                })}
              </LineChart>
            </ResponsiveContainer>
          )}
        </div>
      </div>

      {/* ─── Platform Detail Modal ────────────────────────────────────────────── */}
      {platformDetail && (
        <div className="fixed inset-0 z-50 flex items-center justify-center" style={{ backgroundColor: 'rgba(0,0,0,0.75)', backdropFilter: 'blur(4px)' }} onClick={() => setPlatformDetail(null)}>
          <div className="relative bg-card border border-border rounded-xl w-full max-w-lg mx-4 overflow-hidden shadow-2xl" style={{ maxHeight: '85vh' }} onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between px-5 py-4 border-b border-border" style={{ background: `linear-gradient(135deg, ${platformDetail.color}22, transparent)` }}>
              <div className="flex items-center gap-3">
                <span className="text-2xl">{platformDetail.icon}</span>
                <div>
                  <p className="text-sm font-bold">{platformDetail.platform}</p>
                  <p className="text-[10px] text-muted-foreground">{fmtNum(platformDetail.total_hits)} hits {platformDetail.total_bytes > 0 && `· ${platformDetail.bytes_fmt}`}</p>
                </div>
              </div>
              <button onClick={() => setPlatformDetail(null)} className="p-1.5 hover:bg-secondary/50 rounded-lg transition-colors text-muted-foreground hover:text-foreground"><X className="w-4 h-4" /></button>
            </div>
            <div className="overflow-y-auto" style={{ maxHeight: 'calc(85vh - 72px)' }}>
              {platformDetail.loading ? (
                <div className="flex items-center justify-center py-16 gap-2 text-muted-foreground"><RefreshCw className="w-4 h-4 animate-spin" /><span className="text-sm">Memuat data domain...</span></div>
              ) : (
                <div className="p-5 space-y-5">
                  <div>
                    <p className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground mb-3">Top Domain Dikunjungi</p>
                    {(platformDetail.domains || []).length === 0 ? (
                      <p className="text-xs text-muted-foreground text-center py-6">Belum ada data domain</p>
                    ) : (
                      <div className="space-y-1.5">
                        {(platformDetail.domains || []).map((d, i) => (
                          <div key={d.domain} className="flex items-center gap-3">
                            <span className="text-[10px] text-muted-foreground font-mono w-4 text-right shrink-0">{i+1}</span>
                            <div className="flex-1 min-w-0">
                              <div className="flex items-center justify-between gap-2 mb-0.5">
                                <p className="text-[11px] font-mono truncate text-foreground">{d.domain}</p>
                                <span className="text-[10px] font-mono text-cyan-400 shrink-0">{fmtNum(d.hits)}</span>
                              </div>
                              <div className="h-1 bg-secondary rounded-full overflow-hidden">
                                <div className="h-full rounded-full" style={{ width: `${d.pct}%`, backgroundColor: platformDetail.color }} />
                              </div>
                            </div>
                            <span className="text-[10px] text-muted-foreground w-8 text-right shrink-0">{d.pct}%</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                  {(platformDetail.top_clients || []).length > 0 && (
                    <div>
                      <p className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground mb-3">Top IP Klien</p>
                      <div className="space-y-1">
                        {(platformDetail.top_clients || []).map((c, i) => (
                          <div key={c.ip} className="flex items-center justify-between px-3 py-2 rounded-lg bg-secondary/20 hover:bg-secondary/40 transition-colors">
                            <div className="flex items-center gap-2">
                              <span className="text-[9px] text-muted-foreground font-mono w-4">{i+1}.</span>
                              <span className="text-[11px] font-mono">{c.ip}</span>
                            </div>
                            <span className="text-[10px] font-mono text-cyan-400">{fmtNum(c.hits)} hits</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* ─── Platform Table ────────────────────────────────────────────────────── */}
      <div className="bg-card border border-border rounded-sm p-4">
        <div className="flex items-center justify-between mb-1">
          <p className="text-xs font-semibold">Detail Platform Traffic</p>
          <p className="text-[10px] text-muted-foreground">Klik baris untuk lihat detail domain</p>
        </div>
        <p className="text-[10px] text-muted-foreground mb-3">Klasifikasi berdasarkan DNS syslog</p>
        {platforms.length === 0 ? (
          <NoData />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left">
              <thead>
                <tr className="border-b border-border">
                  {["Platform", "DNS Hits", "Est. Traffic", "% Hits", "% Traffic", "Detail"].map(h => (
                    <th key={h} className="px-3 py-2 text-[10px] text-muted-foreground uppercase tracking-wider font-medium whitespace-nowrap">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {platforms.map((p, i) => (
                  <tr
                    key={p.platform}
                    className="border-b border-border/20 hover:bg-secondary/20 transition-colors cursor-pointer group"
                    onClick={async () => {
                      setPlatformDetail({ platform: p.platform, icon: p.icon, color: p.color, total_hits: p.hits, total_bytes: p.bytes, bytes_fmt: p.bytes_fmt, domains: [], top_clients: [], loading: true });
                      try {
                        const params = new URLSearchParams({ platform: p.platform, range, ...(selectedDev ? { device_id: selectedDev.device_id } : {}) });
                        const res = await api.get(`/peering-eye/platform-domains?${params}`);
                        setPlatformDetail(prev => prev?.platform === p.platform ? { ...prev, ...res.data, loading: false } : prev);
                      } catch {
                        setPlatformDetail(prev => prev?.platform === p.platform ? { ...prev, loading: false } : prev);
                      }
                    }}
                  >
                    <td className="px-3 py-2.5">
                      <div className="flex items-center gap-2">
                        <div className="w-2.5 h-2.5 rounded-full flex-shrink-0" style={{ backgroundColor: p.color }} />
                        <span className="text-base leading-none">{p.icon}</span>
                        <span className="text-xs font-semibold">{p.platform}</span>
                        {i === 0 && (
                          <Badge variant="outline" className="text-[8px] rounded-sm h-4 px-1 text-yellow-400 border-yellow-400/30 ml-1">TOP</Badge>
                        )}
                      </div>
                    </td>
                    <td className="px-3 py-2.5 text-xs font-mono text-cyan-300">{fmtNum(p.hits)}</td>
                    <td className="px-3 py-2.5 text-xs font-mono text-emerald-300">{p.bytes_fmt}</td>
                    <td className="px-3 py-2.5">
                      <div className="flex items-center gap-2">
                        <div className="w-16 h-1.5 bg-secondary rounded-full overflow-hidden">
                          <div className="h-full rounded-full" style={{ width: `${p.pct_hits}%`, backgroundColor: p.color }} />
                        </div>
                        <span className="text-[11px] font-mono text-muted-foreground">{p.pct_hits}%</span>
                      </div>
                    </td>
                    <td className="px-3 py-2.5">
                      <div className="flex items-center gap-2">
                        <div className="w-16 h-1.5 bg-secondary rounded-full overflow-hidden">
                          <div className="h-full rounded-full" style={{ width: `${p.pct_bytes}%`, backgroundColor: p.color }} />
                        </div>
                        <span className="text-[11px] font-mono text-muted-foreground">{p.pct_bytes}%</span>
                      </div>
                    </td>
                    <td className="px-3 py-2.5">
                      <div className="flex items-center gap-1 text-muted-foreground group-hover:text-primary transition-colors">
                        <Eye className="w-3 h-3" />
                        <span className="text-[10px]">Lihat</span>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* ─── Bottom Row: BGP Status + Top Domains + Top Clients ────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* BGP Status Panel */}
        <div className="bg-card border border-border rounded-sm p-4 relative">
          <div className="flex items-center justify-between mb-3 border-b border-border/50 pb-3">
            <div>
              <div className="flex items-center gap-2">
                <p className="text-xs font-semibold flex items-center gap-1.5 align-middle">
                  <Radio className="w-3.5 h-3.5 text-purple-400" />
                  BGP Peer Status
                </p>
                <div className="flex gap-1 ml-2">
                  <button onClick={() => handleSvcCtrl("start")} disabled={bgpSvcLoading} className="p-1 hover:bg-green-500/20 text-green-400 rounded transition-colors" title="Start GoBGP"><Play className="w-3.5 h-3.5" /></button>
                  <button onClick={() => handleSvcCtrl("stop")} disabled={bgpSvcLoading} className="p-1 hover:bg-red-500/20 text-red-400 rounded transition-colors" title="Stop GoBGP"><Square className="w-3.5 h-3.5" /></button>
                  <button onClick={() => handleSvcCtrl("restart")} disabled={bgpSvcLoading} className="p-1 hover:bg-yellow-500/20 text-yellow-400 rounded transition-colors" title="Restart GoBGP"><RefreshCcw className="w-3.5 h-3.5" /></button>
                  <button
                    onClick={handleBgpSync}
                    disabled={bgpSyncing || bgpSvcStatus !== "active"}
                    className="p-1 hover:bg-purple-500/20 text-purple-400 rounded transition-colors disabled:opacity-40"
                    title="Sync Peers dari DB ke GoBGP"
                  >
                    <RefreshCw className={`w-3.5 h-3.5 ${bgpSyncing ? "animate-spin" : ""}`} />
                  </button>
                </div>
              </div>
              <p className="text-[10px] text-muted-foreground mt-0.5">
                Service: <span className={`font-mono ${bgpSvcStatus === "active" ? "text-green-400" : "text-red-400"}`}>{bgpSvcStatus}</span>
                {bgpSvcLoading && " (loading...)"}
              </p>
              <p className="text-[10px] text-muted-foreground mt-0.5">
                {bgpStatus?.established || 0}/{bgpStatus?.total || 0} peers ESTABLISHED
              </p>
            </div>
            {bgpStatus?.updated_at && (
              <span className="text-[9px] text-muted-foreground font-mono self-start flex gap-2 items-center">
                {new Date(bgpStatus.updated_at).toLocaleTimeString("id-ID")}
              </span>
            )}
          </div>

          {bgpPeers.length === 0 ? (
            <div className="text-center py-8 text-muted-foreground">
              <Radio className="w-6 h-6 mx-auto mb-2 opacity-20" />
              {bgpSvcStatus === "active" ? (
                <>
                  <p className="text-xs">GoBGP aktif — belum ada BGP peer</p>
                  <p className="text-[10px] mt-1 opacity-60">Aktifkan BGP pada device, lalu klik tombol Sync (🔄) di atas</p>
                  <button
                    onClick={handleBgpSync}
                    disabled={bgpSyncing}
                    className="mt-3 px-3 py-1.5 text-[10px] bg-purple-500/15 border border-purple-500/30 text-purple-400 rounded hover:bg-purple-500/25 transition-colors disabled:opacity-50"
                  >
                    {bgpSyncing ? "Syncing..." : "🔄 Sync Peers Sekarang"}
                  </button>
                </>
              ) : (
                <>
                  <p className="text-xs">BGP belum aktif</p>
                  <p className="text-[10px] mt-1 opacity-60">Klik tombol ▶ untuk menjalankan GoBGP daemon</p>
                </>
              )}
            </div>
          ) : (
            <div className="space-y-1.5">
              {bgpPeers.map((peer, i) => (
                <div key={i} className="flex items-center justify-between p-2 rounded-sm bg-secondary/20 hover:bg-secondary/30 transition-colors">
                  <div className="flex items-center gap-2 min-w-0">
                    <div className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${peer.state === "ESTABLISHED" ? "bg-green-500 animate-pulse" : "bg-red-500"}`} />
                    <div className="min-w-0">
                      <p className="text-xs font-mono font-semibold truncate">{peer.device_name || peer.neighbor_ip}</p>
                      <p className="text-[9px] text-muted-foreground font-mono">{peer.neighbor_ip} &middot; AS{peer.peer_as}</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-3 flex-shrink-0">
                    <div className="text-right">
                      <p className="text-[9px] text-muted-foreground">{peer.prefixes_rx || 0} pfx</p>
                      <p className="text-[9px] text-muted-foreground">{peer.uptime_fmt || "-"}</p>
                    </div>
                    
                    {/* Auto-Fix button: tampil untuk semua state yang tidak ESTABLISHED */}
                    {peer.state !== "ESTABLISHED" && (
                      <button
                        onClick={() => handleAutoFixBgp(peer.neighbor_ip)}
                        disabled={fixingBgpFor === peer.neighbor_ip}
                        className={`text-[9px] flex items-center gap-1 font-semibold px-2 py-0.5 rounded-sm border 
                          ${fixingBgpFor === peer.neighbor_ip 
                            ? "bg-amber-500/10 text-amber-500/50 border-amber-500/20" 
                            : "bg-amber-500/10 text-amber-400 border-amber-500/30 hover:bg-amber-500/20"
                          } transition-colors`}
                        title={`Auto-Fix BGP ke ${bgpSettings?.router_id || "(IP belum dikonfigurasi)"} AS${bgpSettings?.local_as || 65000}`}
                      >
                        {fixingBgpFor === peer.neighbor_ip ? (
                          <><RefreshCw className="w-2.5 h-2.5 animate-spin" /> Fixing...</>
                        ) : (
                          <>✨ Auto-Fix</>
                        )}
                      </button>
                    )}
                    
                    {/* Push Community Filter button: tampil untuk peer ESTABLISHED */}
                    {peer.state === "ESTABLISHED" && (
                      <button
                        onClick={() => handlePushCommunityFilter(peer.neighbor_ip)}
                        disabled={pushingFilterFor === peer.neighbor_ip}
                        className={`text-[9px] flex items-center gap-1 font-semibold px-2 py-0.5 rounded-sm border 
                          ${pushingFilterFor === peer.neighbor_ip
                            ? "bg-blue-500/10 text-blue-500/50 border-blue-500/20"
                            : "bg-blue-500/10 text-blue-400 border-blue-500/30 hover:bg-blue-500/20"
                          } transition-colors`}
                        title={`Push routing filter rule ke MikroTik: hanya terima community ${bgpSettings?.local_as || 65000}:${peer.neighbor_ip.split('.').pop()}`}
                      >
                        {pushingFilterFor === peer.neighbor_ip ? (
                          <><RefreshCw className="w-2.5 h-2.5 animate-spin" /> Pushing...</>
                        ) : (
                          <>🔒 Push Filter</>
                        )}
                      </button>
                    )}

                    <BgpBadge state={peer.state} />
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Top Domains Panel */}
        <div className="bg-card border border-border rounded-sm p-4">
          <div className="flex items-center justify-between mb-3">
            <div>
              <p className="text-xs font-semibold flex items-center gap-1.5">
                <Globe className="w-3.5 h-3.5 text-cyan-400" />
                Top 20 Domain
              </p>
              <p className="text-[10px] text-muted-foreground mt-0.5">Filter raw domain per platform</p>
            </div>
            
            <div className="relative">
              <button
                onClick={() => setShowDomainDropdown(!showDomainDropdown)}
                className="flex items-center gap-2 px-2 py-1 bg-secondary/30 hover:bg-secondary/50 rounded border border-border/50 text-[10px] font-medium transition-colors"
                title="Filter by Platform"
              >
                {domainPlatform === "all" ? "Semua Platform" : domainPlatform}
                <ChevronDown className="w-3 h-3 text-muted-foreground" />
              </button>
              
              {showDomainDropdown && (
                <>
                  <div className="fixed inset-0 z-40" onClick={() => setShowDomainDropdown(false)} />
                  <div className="absolute right-0 top-full mt-1 w-40 bg-card border border-border rounded-md shadow-xl z-50 overflow-hidden text-[10px] max-h-64 overflow-y-auto">
                    <button
                      onClick={() => { setDomainPlatform("all"); setShowDomainDropdown(false); fetchAll(true); }}
                      className={`w-full text-left px-3 py-2 hover:bg-secondary/40 transition-colors ${domainPlatform === "all" ? "text-primary font-semibold" : "text-muted-foreground"}`}
                    >
                      Semua Platform
                    </button>
                    {["Situs Dewasa", "Judi Online", "YouTube", "TikTok", "Facebook", "Instagram", "WhatsApp", "Telegram", "Netflix", "Google", "Shopee", "Tokopedia"].map(p => (
                      <button
                        key={p}
                        onClick={() => { setDomainPlatform(p); setShowDomainDropdown(false); fetchAll(true); }}
                        className={`w-full text-left px-3 py-2 hover:bg-secondary/40 transition-colors ${domainPlatform === p ? "text-primary font-semibold" : "text-muted-foreground"}`}
                      >
                        {p}
                      </button>
                    ))}
                  </div>
                </>
              )}
            </div>
          </div>

          {topDomains.length === 0 ? (
            <NoData message="Belum ada data domain" />
          ) : (
            <div className="space-y-1 max-h-[400px] overflow-y-auto pr-1">
              {topDomains.map((d, i) => (
                <div key={i} className="flex items-center justify-between gap-2 py-1.5 border-b border-border/20">
                  <div className="flex items-center gap-2 min-w-0">
                    <span className="text-[10px] text-muted-foreground font-mono w-5 text-right flex-shrink-0">{i + 1}</span>
                    <span className="text-base leading-none">{d.icon}</span>
                    <div className="min-w-0">
                      <p className="text-xs font-mono font-semibold truncate text-foreground">{d.domain}</p>
                      <p className="text-[9px]" style={{ color: d.color }}>{d.platform}</p>
                    </div>
                  </div>
                  <div className="flex-shrink-0 flex items-center gap-3">
                    <div className="text-right">
                      <p className="text-xs font-mono text-cyan-300">{fmtNum(d.hits)}</p>
                      <p className="text-[9px] text-muted-foreground">hits</p>
                    </div>
                    <button
                      onClick={() => handleBlock("domain", d.domain)}
                      className="p-1.5 bg-red-500/10 hover:bg-red-500/20 text-red-500 rounded transition-colors"
                      title="Blokir Domain"
                    >
                      <AlertCircle className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Top Clients Panel */}
        <div className="bg-card border border-border rounded-sm p-4">
          <div className="flex items-center justify-between mb-3">
            <div>
              <p className="text-xs font-semibold flex items-center gap-1.5">
                <Users className="w-3.5 h-3.5 text-emerald-400" />
                Top 20 Klien
              </p>
              <p className="text-[10px] text-muted-foreground mt-0.5">Klik 🔍 untuk lihat aktivitas lengkap</p>
            </div>
          </div>

          {/* Pencarian IP Manual */}
          <div className="flex items-center gap-2 mb-3">
            <div className="flex-1 flex items-center gap-2 bg-secondary/30 border border-border/50 rounded px-2 py-1.5">
              <Search className="w-3.5 h-3.5 text-muted-foreground flex-shrink-0" />
              <input
                type="text"
                placeholder="Cari IP pelanggan... (contoh: 192.168.1.100)"
                value={clientSearchIp}
                onChange={e => setClientSearchIp(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter' && clientSearchIp.trim()) openClientActivity(clientSearchIp.trim()); }}
                className="w-full bg-transparent text-xs text-foreground placeholder:text-muted-foreground/60 outline-none font-mono"
              />
              {clientSearchIp && (
                <button onClick={() => setClientSearchIp('')} className="text-muted-foreground hover:text-foreground">
                  <X className="w-3 h-3" />
                </button>
              )}
            </div>
            <button
              onClick={() => { if (clientSearchIp.trim()) openClientActivity(clientSearchIp.trim()); }}
              disabled={!clientSearchIp.trim()}
              className="flex items-center gap-1 px-2.5 py-1.5 bg-emerald-500/15 hover:bg-emerald-500/25 text-emerald-400 border border-emerald-500/30 rounded text-[11px] font-semibold transition-colors disabled:opacity-40 disabled:cursor-not-allowed whitespace-nowrap"
            >
              <Eye className="w-3.5 h-3.5" />
              Cek
            </button>
          </div>

          {topClients.length === 0 ? (
            <NoData message="Belum ada data klien" />
          ) : (
            <div className="space-y-1 max-h-[380px] overflow-y-auto pr-1">
              {topClients.map((c, i) => (
                <div key={i} className="flex items-center justify-between gap-2 py-1.5 border-b border-border/20 group hover:bg-secondary/10 transition-colors rounded px-1">
                  <div className="flex items-center gap-2 min-w-0">
                    <span className="text-[10px] text-muted-foreground font-mono w-5 text-right flex-shrink-0">{i + 1}</span>
                    <span className="text-base leading-none">{c.icon}</span>
                    <div className="min-w-0 flex-1">
                      <p className="text-xs font-mono font-semibold truncate text-foreground">
                        {c.name && c.name !== "Unknown" ? c.name : c.ip}
                      </p>
                      <div className="flex items-center gap-2">
                        <p className="text-[9px]" style={{ color: c.color }}>{c.platform}</p>
                        <p className="text-[9px] text-muted-foreground font-mono">{c.name && c.name !== "Unknown" ? c.ip : ""}{c.mac ? ` • ${c.mac}` : ""}</p>
                      </div>
                    </div>
                  </div>
                  <div className="flex-shrink-0 flex items-center gap-1.5">
                    <div className="text-right mr-1">
                      <p className="text-xs font-mono text-emerald-300">
                        {c.bytes > 0 ? fmtBytes(c.bytes) : `${fmtNum(c.hits)} hits`}
                      </p>
                      <p className="text-[9px] text-muted-foreground">
                        {c.bytes > 0 ? `${fmtNum(c.hits)} hits` : "DNS only"}
                      </p>
                    </div>
                    {/* Tombol Lihat Aktivitas */}
                    <button
                      onClick={() => openClientActivity(c.ip)}
                      className="p-1.5 bg-emerald-500/10 hover:bg-emerald-500/25 text-emerald-400 rounded transition-all opacity-60 group-hover:opacity-100"
                      title="Lihat Aktivitas Klien"
                    >
                      <Eye className="w-3.5 h-3.5" />
                    </button>
                    <button
                      onClick={() => handleBlock("client", c.name && c.name !== "Unknown" ? c.name : c.ip)}
                      className="p-1.5 bg-red-500/10 hover:bg-red-500/20 text-red-400 rounded transition-all opacity-60 group-hover:opacity-100"
                      title="Blokir/Isolir Klien"
                    >
                      <AlertCircle className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

      </div>
      {/* Intelligence & Content Map Panels */}
      <IspIntelligencePanel deviceId={selectedDev?.device_id} />
      <ContentMapPanel deviceId={selectedDev?.device_id} />

      {showPlatformsModal && (
        <PeeringPlatformModal
          onClose={() => setShowPlatformsModal(false)}
          onChange={() => fetchAll(true)}
        />
      )}

      {/* Client Activity Modal */}
      {showClientActivity && clientActivityIp && (
        <ClientActivityModal
          ip={clientActivityIp}
          deviceId={selectedDev?.device_id || ""}
          onClose={() => { setShowClientActivity(false); setClientActivityIp(null); }}
          onBlock={handleBlock}
        />
      )}
      </div>
      )}
    </div>
  );
}

// ─── ISP Intelligence Panel ──────────────────────────────────────────────────
function IspIntelligencePanel({ deviceId }) {
  const [mode, setMode] = useState(null);
  const [enrichment, setEnrichment] = useState(null);
  const [upstreamPath, setUpstreamPath] = useState(null);
  const [pathTarget, setPathTarget] = useState("1.1.1.1");
  const [loadingEnr, setLoadingEnr] = useState(false);
  const [pathLoading, setPathLoading] = useState(false);
  const [open, setOpen] = useState(true);
  const [expandedAsn, setExpandedAsn] = useState(null);

  useEffect(() => {
    api.get("/peering-eye/intelligence/mode")
      .then(r => setMode(r.data))
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (mode?.mode === "bgp") {
      setLoadingEnr(true);
      api.get("/peering-eye/intelligence/asn-enrichment")
        .then(r => setEnrichment(r.data))
        .catch(() => {})
        .finally(() => setLoadingEnr(false));
    }
  }, [mode]);

  const runTraceroute = async () => {
    if (!deviceId) {
      toast.warning("Pilih router spesifik terlebih dahulu");
      return;
    }
    setPathLoading(true);
    try {
      const r = await api.get("/peering-eye/intelligence/upstream-path", {
        params: { device_id: deviceId, target: pathTarget }
      });
      setUpstreamPath(r.data);
    } catch (e) {
      toast.error("Traceroute gagal: " + (e.response?.data?.detail || e.message));
    }
    setPathLoading(false);
  };

  const modeLabel = mode?.mode === "bgp" ? "BGP Mode" : mode?.mode === "broadband" ? "Broadband Mode" : "Mendeteksi...";
  const modeColor = mode?.mode === "bgp" ? "text-purple-400 border-purple-400/30" : "text-cyan-400 border-cyan-400/30";

  return (
    <div className="bg-card border border-border rounded-sm">
      <button
        onClick={() => setOpen(v => !v)}
        className="w-full flex items-center justify-between px-4 py-3 hover:bg-secondary/10 transition-colors"
      >
        <div className="flex items-center gap-2">
          <Globe className="w-4 h-4 text-purple-400" />
          <span className="text-sm font-semibold">ISP Peering Intelligence</span>
          {mode && (
            <span className={`text-[9px] border rounded-sm px-1.5 py-0.5 font-mono ${modeColor}`}>
              {modeLabel}
            </span>
          )}
        </div>
        <ChevronDown className={`w-4 h-4 text-muted-foreground transition-transform ${open ? "rotate-180" : ""}`} />
      </button>

      {open && (
        <div className="px-4 pb-4 space-y-4 border-t border-border/50">

          {/* Mode Info Banner */}
          {mode && (
            <div className={`mt-3 p-3 rounded-sm text-xs border ${
              mode.mode === "bgp"
                ? "bg-purple-500/5 border-purple-500/20 text-purple-300"
                : "bg-cyan-500/5 border-cyan-500/20 text-cyan-300"
            }`}>
              {mode.description}
              {mode.mode === "bgp" && (
                <span className="ml-2 font-mono">
                  ({mode.established}/{mode.bgp_peer_count} peers ESTABLISHED)
                </span>
              )}
            </div>
          )}

          {/* BGP MODE: ASN Enrichment Table */}
          {mode?.mode === "bgp" && (
            <div>
              <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">ASN Peer Enrichment</p>
              {loadingEnr ? (
                <p className="text-xs text-muted-foreground animate-pulse py-6 text-center">Mengambil data dari BGPView + PeeringDB...</p>
              ) : enrichment?.peers?.length > 0 ? (
                <div className="space-y-2">
                  {enrichment.peers.map((peer, i) => {
                    const e = peer.enrich || {};
                    const pdb = e.peeringdb || {};
                    const ixList = e.ix_list || [];
                    const isExpanded = expandedAsn === peer.remote_as;
                    return (
                      <div key={i} className="border border-border/40 rounded-sm overflow-hidden">
                        <button
                          onClick={() => setExpandedAsn(isExpanded ? null : peer.remote_as)}
                          className="w-full flex items-center justify-between px-3 py-2.5 bg-secondary/10 hover:bg-secondary/20 transition-colors text-left"
                        >
                          <div className="flex items-center gap-3">
                            <div className={`w-2 h-2 rounded-full flex-shrink-0 ${peer.state === "ESTABLISHED" ? "bg-green-500" : "bg-red-500"}`} />
                            <div>
                              <p className="text-xs font-semibold">{e.name || peer.name || `AS${peer.remote_as}`}</p>
                              <p className="text-[10px] text-muted-foreground">AS{peer.remote_as} · {e.country_code || "?"} · {peer.state}</p>
                            </div>
                          </div>
                          <div className="flex items-center gap-3 text-right">
                            <div>
                              <p className="text-[10px] font-mono text-purple-300">{e.ipv4_count || 0} IPv4 pfx</p>
                              <p className="text-[10px] text-muted-foreground">{e.ix_count || 0} IX</p>
                            </div>
                            <ChevronDown className={`w-3 h-3 text-muted-foreground transition-transform ${isExpanded ? "rotate-180" : ""}`} />
                          </div>
                        </button>

                        {isExpanded && (
                          <div className="px-3 py-3 space-y-3 bg-card">
                            {e.description && (
                              <p className="text-[11px] text-muted-foreground italic">{e.description}</p>
                            )}
                            {e.website && (
                              <a href={e.website} target="_blank" rel="noreferrer"
                                className="text-[10px] text-blue-400 hover:underline font-mono">
                                {e.website}
                              </a>
                            )}

                            {/* PeeringDB Net Info */}
                            {pdb.net?.name && (
                              <div className="grid grid-cols-3 gap-2 text-[10px]">
                                <div>
                                  <p className="text-muted-foreground">Tipe Jaringan</p>
                                  <p className="font-mono">{pdb.net.type || "—"}</p>
                                </div>
                                <div>
                                  <p className="text-muted-foreground">Peering Policy</p>
                                  <p className="font-mono">{pdb.net.policy || "—"}</p>
                                </div>
                                <div>
                                  <p className="text-muted-foreground">Prefix di PeeringDB</p>
                                  <p className="font-mono">{pdb.net.prefixes4 || 0} IPv4</p>
                                </div>
                              </div>
                            )}

                            {/* IX List */}
                            {ixList.length > 0 && (
                              <div>
                                <p className="text-[10px] text-muted-foreground uppercase tracking-wider mb-1.5">
                                  Internet Exchange ({ixList.length})
                                </p>
                                <div className="flex flex-wrap gap-1.5">
                                  {ixList.map((ix, j) => (
                                    <span key={j}
                                      className="text-[9px] font-mono bg-purple-500/10 border border-purple-500/20 text-purple-300 px-2 py-0.5 rounded-sm">
                                      {ix.name}
                                      {ix.speed_mbps > 0 && ` · ${ix.speed_mbps >= 1000 ? `${ix.speed_mbps / 1000}G` : `${ix.speed_mbps}M`}`}
                                    </span>
                                  ))}
                                </div>
                              </div>
                            )}

                            {ixList.length === 0 && pdb.net && (
                              <p className="text-[10px] text-muted-foreground">Tidak ditemukan di Internet Exchange manapun (private peering only)</p>
                            )}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              ) : (
                <p className="text-xs text-muted-foreground text-center py-6">Data enrichment tidak tersedia</p>
              )}
            </div>
          )}

          {/* BROADBAND MODE: Traceroute Path */}
          {(mode?.mode === "broadband" || mode?.mode === "bgp") && (
            <div>
              <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">
                Upstream Path Analysis
              </p>
              <div className="flex gap-2 mb-3">
                <input
                  type="text"
                  value={pathTarget}
                  onChange={e => setPathTarget(e.target.value)}
                  placeholder="Target IP (cth: 1.1.1.1)"
                  className="flex-1 h-8 px-3 text-xs rounded-sm border border-border bg-secondary/20 text-foreground font-mono"
                />
                <button
                  onClick={runTraceroute}
                  disabled={pathLoading || !deviceId}
                  className="h-8 px-4 text-xs rounded-sm bg-primary text-white font-semibold hover:bg-primary/80 transition-colors disabled:opacity-50 flex items-center gap-1.5"
                >
                  <Activity className="w-3.5 h-3.5" />
                  {pathLoading ? "Tracing..." : "Traceroute"}
                </button>
              </div>

              {!deviceId && (
                <p className="text-[11px] text-amber-400 bg-amber-500/10 border border-amber-500/20 rounded-sm px-3 py-2">
                  Pilih router spesifik dari menu di atas untuk menjalankan traceroute.
                </p>
              )}

              {upstreamPath && (
                <div className="space-y-3">
                  {/* Upstream summary */}
                  <div className="grid grid-cols-3 gap-3">
                    <div className="bg-secondary/20 rounded-sm p-2.5">
                      <p className="text-[10px] text-muted-foreground">Upstream ISP</p>
                      <p className="text-xs font-semibold truncate">{upstreamPath.upstream_isp || "—"}</p>
                    </div>
                    <div className="bg-secondary/20 rounded-sm p-2.5">
                      <p className="text-[10px] text-muted-foreground">Upstream ASN</p>
                      <p className="text-xs font-mono font-semibold">AS{upstreamPath.upstream_asn || "?"}</p>
                    </div>
                    <div className="bg-secondary/20 rounded-sm p-2.5">
                      <p className="text-[10px] text-muted-foreground">Total Hops</p>
                      <p className="text-xs font-mono font-semibold">{upstreamPath.total_hops}</p>
                    </div>
                  </div>

                  {/* ASN Path */}
                  {upstreamPath.path_asns?.length > 0 && (
                    <div>
                      <p className="text-[10px] text-muted-foreground mb-2">Path ASN (unique)</p>
                      <div className="flex flex-wrap items-center gap-1">
                        {upstreamPath.path_asns.map((a, i) => (
                          <span key={i} className="flex items-center gap-1">
                            <span className="text-[9px] font-mono bg-cyan-500/10 border border-cyan-500/20 text-cyan-300 px-2 py-0.5 rounded-sm">
                              AS{a.asn} {a.org ? `· ${a.org.substring(0, 30)}` : ""}
                            </span>
                            {i < upstreamPath.path_asns.length - 1 && (
                              <span className="text-muted-foreground text-xs">→</span>
                            )}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Hop table */}
                  <div className="overflow-x-auto">
                    <table className="w-full text-left min-w-[500px]">
                      <thead>
                        <tr className="border-b border-border">
                          {["Hop", "IP", "Latency", "AS", "Organisasi", "Negara"].map(h => (
                            <th key={h} className="px-2 py-1.5 text-[9px] text-muted-foreground uppercase tracking-wider">{h}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {upstreamPath.hops.map((hop, i) => (
                          <tr key={i} className={`border-b border-border/20 text-[10px] ${hop.new_asn ? "bg-cyan-500/5" : ""}`}>
                            <td className="px-2 py-1.5 font-mono text-muted-foreground">{hop.hop}</td>
                            <td className="px-2 py-1.5 font-mono">{hop.ip === "*" ? <span className="text-muted-foreground/50">*</span> : hop.ip}</td>
                            <td className="px-2 py-1.5 font-mono text-green-400">{hop.avg_ms ? `${hop.avg_ms} ms` : "—"}</td>
                            <td className="px-2 py-1.5">
                              {hop.asn ? (
                                <span className="text-[9px] font-mono bg-cyan-500/10 text-cyan-300 px-1.5 py-0.5 rounded-sm">
                                  AS{hop.asn}
                                </span>
                              ) : "—"}
                            </td>
                            <td className="px-2 py-1.5 truncate max-w-[160px]">{hop.org || "—"}</td>
                            <td className="px-2 py-1.5 text-muted-foreground">{hop.country || "—"}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ─── Content Provider Map Panel ───────────────────────────────────────────────
const STATUS_CONFIG = {
  good:     { label: "Baik",     color: "text-green-400",  bg: "bg-green-500/10",  border: "border-green-500/20" },
  fair:     { label: "Fair",     color: "text-yellow-400", bg: "bg-yellow-500/10", border: "border-yellow-500/20" },
  poor:     { label: "Lambat",   color: "text-orange-400", bg: "bg-orange-500/10", border: "border-orange-500/20" },
  degraded: { label: "Degraded", color: "text-amber-400",  bg: "bg-amber-500/10",  border: "border-amber-500/20" },
  offline:  { label: "Offline",  color: "text-red-400",    bg: "bg-red-500/10",    border: "border-red-500/20"   },
};

const PROVIDER_ICONS = {
  "Google": "🔵", "Cloudflare": "🟠", "Netflix": "🔴", "Akamai": "🔵",
  "Meta/Facebook": "🔵", "AWS": "🟡", "TikTok": "⚫", "Telegram": "🔵",
  "WhatsApp": "🟢", "Indihome/Telkom": "🔴", "Biznet": "🟢", "YouTube": "🔴",
};

function ContentMapPanel({ deviceId }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(true);
  const [lastFetch, setLastFetch] = useState(null);

  const fetchMap = async (force = false) => {
    if (!deviceId) {
      toast.warning("Pilih router spesifik terlebih dahulu");
      return;
    }
    setLoading(true);
    try {
      const r = await api.get("/peering-eye/intelligence/content-map", {
        params: { device_id: deviceId, force: force ? "true" : "false" }
      });
      setData(r.data);
      setLastFetch(new Date());
    } catch (e) {
      toast.error("Gagal ambil data: " + (e.response?.data?.detail || e.message));
    }
    setLoading(false);
  };

  return (
    <div className="bg-card border border-border rounded-sm">
      <button
        onClick={() => setOpen(v => !v)}
        className="w-full flex items-center justify-between px-4 py-3 hover:bg-secondary/10 transition-colors"
      >
        <div className="flex items-center gap-2">
          <Wifi className="w-4 h-4 text-cyan-400" />
          <span className="text-sm font-semibold">Content Provider Map</span>
          {data && (
            <span className="text-[9px] border border-green-500/30 text-green-400 rounded-sm px-1.5 py-0.5 font-mono">
              {data.good_count} / {data.providers?.length} GOOD
            </span>
          )}
        </div>
        <ChevronDown className={`w-4 h-4 text-muted-foreground transition-transform ${open ? "rotate-180" : ""}`} />
      </button>

      {open && (
        <div className="px-4 pb-4 border-t border-border/50">
          {/* Toolbar */}
          <div className="flex items-center justify-between py-3">
            <p className="text-[10px] text-muted-foreground">
              Latency dari router ke major content providers
              {data?.from_cache && <span className="ml-2 text-amber-400">(cached)</span>}
              {lastFetch && <span className="ml-2 opacity-60">· {lastFetch.toLocaleTimeString("id-ID")}</span>}
            </p>
            <button
              onClick={() => fetchMap(true)}
              disabled={loading || !deviceId}
              className="flex items-center gap-1.5 px-3 py-1.5 text-[10px] rounded-sm border border-border bg-secondary/20 hover:bg-secondary/40 transition-colors disabled:opacity-50"
            >
              <RefreshCw className={`w-3 h-3 ${loading ? "animate-spin" : ""}`} />
              {loading ? "Mengukur..." : "Ukur Sekarang"}
            </button>
          </div>

          {!deviceId && (
            <p className="text-[11px] text-amber-400 bg-amber-500/10 border border-amber-500/20 rounded-sm px-3 py-2 mb-3">
              Pilih router spesifik dari menu di atas untuk mengukur latency.
            </p>
          )}

          {/* Summary bar */}
          {data && (
            <div className="grid grid-cols-4 gap-2 mb-4">
              {[
                { label: "Baik (<50ms)", val: data.good_count, color: "text-green-400" },
                { label: "Fair (50-150ms)", val: data.fair_count, color: "text-yellow-400" },
                { label: "Degraded", val: data.degraded_count, color: "text-amber-400" },
                { label: "Offline", val: data.offline_count, color: "text-red-400" },
              ].map(s => (
                <div key={s.label} className="bg-secondary/20 rounded-sm p-2 text-center">
                  <p className={`text-lg font-bold font-mono ${s.color}`}>{s.val}</p>
                  <p className="text-[9px] text-muted-foreground">{s.label}</p>
                </div>
              ))}
            </div>
          )}

          {/* Provider Cards Grid */}
          {data?.providers ? (
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-2">
              {data.providers.map((p, i) => {
                const cfg = STATUS_CONFIG[p.status] || STATUS_CONFIG.offline;
                const icon = PROVIDER_ICONS[p.name] || "🌐";
                return (
                  <div key={i} className={`relative rounded-sm border p-3 ${cfg.bg} ${cfg.border} transition-all`}>
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-xl leading-none">{icon}</span>
                      <span className={`text-[8px] font-mono font-bold border rounded-sm px-1.5 py-0.5 ${cfg.color} ${cfg.border}`}>
                        {cfg.label}
                      </span>
                    </div>
                    <p className="text-xs font-semibold truncate">{p.name}</p>
                    <p className="text-[10px] text-muted-foreground font-mono mt-0.5">{p.ip}</p>
                    <div className="mt-2 pt-2 border-t border-border/30">
                      <p className={`text-base font-bold font-mono ${cfg.color}`}>
                        {p.latency_ms != null ? `${p.latency_ms} ms` : "—"}
                      </p>
                      {p.loss_pct > 0 && (
                        <p className="text-[9px] text-muted-foreground">Loss: {p.loss_pct}%</p>
                      )}
                      {p.asn_name && (
                        <p className="text-[8px] text-muted-foreground truncate mt-0.5" title={p.asn_name}>
                          {p.asn_name}
                        </p>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          ) : (
            <div className="flex flex-col items-center py-10 text-muted-foreground gap-2">
              <Radar className="w-8 h-8 opacity-20" />
              <p className="text-xs">Klik "Ukur Sekarang" untuk mulai pengukuran latency</p>
              <p className="text-[10px] opacity-60">Pengukuran berlangsung ~30 detik</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function AutoConfigBox() {
  const [serverIp, setServerIp] = useState(window.location.hostname || "192.168.1.100");
  const [copied, setCopied] = useState(false);

  const script = `/system logging add topics=dns action=syslog
/system logging action set [find name=syslog] target=remote remote=${serverIp} remote-port=5514 bsd-syslog=yes
/ip traffic-flow set enabled=yes interfaces=all
/ip traffic-flow target add dst-address=${serverIp} port=2055 version=9
`;

  const copyScript = () => {
    navigator.clipboard.writeText(script);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="bg-[#09090b] border border-cyan-500/30 rounded-lg p-4 mt-4 mb-2 shadow-lg">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-3">
        <div>
          <h4 className="text-sm font-semibold text-cyan-400 flex items-center gap-2">
            <Terminal className="w-4 h-4" /> Script Auto-Config (1-Click)
          </h4>
          <p className="text-[10px] text-muted-foreground mt-0.5">Copy & Paste script ini ke Terminal Winbox MikroTik Anda</p>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-[10px] text-muted-foreground font-semibold uppercase tracking-wider">IP Server NOC:</span>
          <input 
            type="text" 
            value={serverIp} 
            onChange={(e) => setServerIp(e.target.value)}
            className="bg-black border border-border/50 rounded px-2 py-1 text-xs text-white w-36 focus:outline-none focus:border-cyan-500/50 font-mono"
            placeholder="192.168.1.100"
          />
        </div>
      </div>
      
      <div className="relative group">
        <pre className="text-[11px] font-mono p-3 bg-black border border-border/30 rounded text-emerald-400 overflow-x-auto whitespace-pre-wrap leading-relaxed">
          {script}
        </pre>
        <button 
          onClick={copyScript}
          className="absolute top-2 right-2 p-1.5 bg-secondary/80 hover:bg-secondary rounded border border-border/50 transition-colors"
          title="Copy Script ke Clipboard"
        >
          {copied ? <Check className="w-4 h-4 text-green-400" /> : <Copy className="w-4 h-4 text-muted-foreground group-hover:text-foreground" />}
        </button>
      </div>
    </div>
  );
}

function AutoConfigBgpBox() {
  const [serverIp, setServerIp] = useState(window.location.hostname || "192.168.1.100");
  const [copied, setCopied] = useState(false);
  const [rosV, setRosV] = useState("7");

  const script = rosV === "7" 
    ? `/routing bgp connection add name="NOC-Sentinel" remote.address=${serverIp} local.role=ebgp local.default-as=65000 remote.as=65000`
    : `/routing bgp instance set default as=65000\n/routing bgp peer add name="NOC-Sentinel" remote-address=${serverIp} remote-as=65000`;

  const copyScript = () => {
    navigator.clipboard.writeText(script);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="bg-[#09090b] border border-amber-500/30 rounded-lg p-4 mt-4 mb-2 shadow-lg">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-3">
        <div>
          <h4 className="text-sm font-semibold text-amber-400 flex items-center gap-2">
            <Terminal className="w-4 h-4" /> Script Auto-Config BGP (1-Click)
          </h4>
          <p className="text-[10px] text-muted-foreground mt-0.5">Copy & Paste script ini ke Terminal Winbox MikroTik Anda</p>
        </div>
        <div className="flex items-center gap-2">
           <select 
              value={rosV} 
              onChange={e => setRosV(e.target.value)} 
              className="bg-black border border-border/50 rounded px-2 py-1 text-xs text-white focus:outline-none focus:border-amber-500/50"
            >
              <option value="7">RouterOS v7</option>
              <option value="6">RouterOS v6</option>
            </select>
          <input 
            type="text" 
            value={serverIp} 
            onChange={(e) => setServerIp(e.target.value)}
            className="bg-black border border-border/50 rounded px-2 py-1 text-xs text-white w-36 focus:outline-none focus:border-amber-500/50 font-mono"
            placeholder="IP Server NOC"
          />
        </div>
      </div>
      
      <div className="relative group">
        <pre className="text-[11px] font-mono p-3 bg-black border border-border/30 rounded text-emerald-400 overflow-x-auto whitespace-pre-wrap leading-relaxed">
          {script}
        </pre>
        <button 
          onClick={copyScript}
          className="absolute top-2 right-2 p-1.5 bg-secondary/80 hover:bg-secondary rounded border border-border/50 transition-colors"
          title="Copy Script ke Clipboard"
        >
          {copied ? <Check className="w-4 h-4 text-green-400" /> : <Copy className="w-4 h-4 text-muted-foreground group-hover:text-foreground" />}
        </button>
      </div>
    </div>
  );
}

/* ─── Peering-Eye Usage Guide ─────────────────────────────────────────────── */
function PeeringGuideTab() {
  const sections = [
    {
      title: "Apa itu Sentinel Peering-Eye?",
      color: "border-cyan-500/40 bg-cyan-500/5",
      headerColor: "text-cyan-400",
      items: [
        { label: "Fungsi Utama", text: "Sentinel Peering-Eye adalah modul analitik traffic berbasis DNS Syslog. Fitur ini memantau platform apa saja yang diakses oleh pelanggan ISP Anda secara real-time: YouTube, TikTok, Netflix, Situs Dewasa, Judi Online, dan 50+ kategori lainnya." },
        { label: "Data yang Dikumpulkan", text: "Sistem menerima DNS query log dari MikroTik (via UDP Syslog ke port 5514). Dari data ini, Sentinel mengidentifikasi platform berdasarkan nama domain yang diquery pelanggan." },
        { label: "Tampilan Utama", text: "Halaman Traffic Intelligence menampilkan: (1) Total DNS Hits, (2) Platform teratas, (3) Grafik distribusi traffic dalam pie chart 3D, (4) Timeline traffic per platform, (5) Tabel ranking domain, (6) Tabel IP klien terbanyak mengakses." },
      ]
    },
    {
      title: "Cara Mengaktifkan Pengiriman Data dari MikroTik",
      color: "border-blue-500/40 bg-blue-500/5",
      headerColor: "text-blue-400",
      isSetup: true,
      items: [
        { label: "Langkah 1 — Aktifkan DNS Syslog di MikroTik", text: "Masuk Winbox → System → Logging → tambah rule baru: Topics: \"dns\", Action: remote. Buat Action baru: Syslog, Remote Address = IP server NOC Sentinel, Port = 5514, BST = checked." },
        { label: "Langkah 2 — Verifikasi", text: "Kembali ke dashboard Peering-Eye, refresh halaman. Jika data masuk, counter \"Total DNS Hits\" akan mulai bertambah dalam 1-5 menit. Jika belum, cek firewall server mengizinkan port 5514 (UDP)." },
        { label: "Langkah 3 — Buka Port Firewall Server", text: "Di Ubuntu VPS: sudo ufw allow 5514/udp. Verifikasi status berjalan dari indikator di halaman dashboard." },
      ]
    },
    {
      title: "Memahami Dashboard Traffic Intelligence",
      color: "border-purple-500/40 bg-purple-500/5",
      headerColor: "text-purple-400",
      items: [
        { label: "Filter Router & Rentang Waktu", text: "Gunakan dropdown di pojok kanan atas untuk memfilter data per router spesifik atau tampilkan data agregat semua router. Ubah rentang waktu dari 1 jam hingga 30 hari." },
        { label: "Grafik Distribusi Platform", text: "Pie chart 3D menampilkan persentase traffic setiap platform berdasarkan estimasi bytes. Hover pada irisan untuk melihat detail nama platform dan jumlah traffic." },
        { label: "Timeline Traffic", text: "Line chart menampilkan tren traffic per platform dari waktu ke waktu. Berguna untuk mengidentifikasi jam sibuk dan pola penggunaan pelanggan." },
        { label: "Tabel Top 20 Domain", text: "Daftar domain spesifik yang paling banyak di-query pelanggan. Gunakan filter platform untuk menyaring domain per kategori (YouTube, TikTok, dll). Klik ikon blokir merah untuk memblokir domain dari MikroTik." },
        { label: "Tabel Top 20 Klien", text: "Daftar IP klien dengan traffic tertinggi. Tampil nama klien (dari DHCP Lease MikroTik), IP, MAC address, platform favorit, dan total traffic. Klik ikon blokir untuk mengisolir klien." },
      ]
    },
    {
      title: "Fitur BGP Peer Status",
      color: "border-amber-500/40 bg-amber-500/5",
      headerColor: "text-amber-400",
      isSetupBgp: true,
      items: [
        { label: "Apa itu BGP Peer Status?", text: "Panel ini menampilkan status sesi BGP (Border Gateway Protocol) antara router MikroTik Anda dengan upstream ISP atau IXP (Internet Exchange Point). Status ESTABLISHED berarti sesi BGP aktif dan route sedang dipertukarkan." },
        { label: "Kontrol Service BGP", text: "Tombol Play/Stop/Restart di samping judul panel digunakan untuk mengelola service BGP di server NOC (bukan di MikroTik). Fun mengelola proses sentinel_bgp.py yang mengumpulkan data BGP." },
        { label: "Kolom Panel BGP", text: "Setiap baris menampilkan: nama/IP peer, ASN (Autonomous System Number), jumlah prefix yang diterima (pfx), dan uptime sesi. Badge ESTABLISHED (hijau), ACTIVE (kuning), atau IDLE (merah) menunjukkan status sesi." },
        { label: "Konfigurasi BGP", text: "Pastikan sentinel_bgp.py sudah terkonfigurasi dengan router yang benar. Edit file konfigurasi sentinel_bgp.conf dengan IP router MikroTik yang memiliki BGP session aktif." },
      ]
    },
    {
      title: "Tips & Troubleshooting",
      color: "border-slate-500/40 bg-slate-500/5",
      headerColor: "text-slate-300",
      items: [
        { label: "Counter DNS Hits = 0?", text: "Pastikan: (1) DNS Syslog di MikroTik aktif dan mengirim ke IP & port yang benar, (2) Port 5514 UDP terbuka di firewall server, (3) Service sentinel_eye.py berjalan (sudo systemctl status nocsentinel)." },
        { label: "Platform tidak terdeteksi?", text: "Klik tombol \"Kelola Platform\" untuk melihat dan menambah rule klasifikasi domain. Anda bisa mendefinisikan domain apa yang masuk ke kategori platform apa." },
        { label: "Data terlambat?", text: "Sistem memproses data DNS syslog secara real-time, namun agregasi statistik dan timeline di-update setiap 30 detik. Klik tombol Refresh untuk memuat ulang data terkini." },
        { label: "Pemblokiran tidak berfungsi?", text: "Fitur blokir domain/klien memerlukan pilihan router spesifik (bukan 'Semua Router'). Pilih router tujuan dari dropdown di atas, lalu coba blokir lagi." },
      ]
    },
  ];

  return (
    <div className="space-y-5 pb-8 animate-in fade-in slide-in-from-bottom-2 duration-300">
      <div className="flex items-center gap-3 pb-3 border-b border-border">
        <BookOpen className="w-5 h-5 text-cyan-400" />
        <div>
          <h2 className="text-base font-bold">Panduan Lengkap Sentinel Peering-Eye</h2>
          <p className="text-xs text-muted-foreground mt-0.5">Analitik traffic platform &mdash; DNS Syslog Intelligence</p>
        </div>
      </div>

      {sections.map((sec, si) => (
        <div key={si} className={`rounded-xl border p-5 ${sec.color}`}>
          <h3 className={`font-bold text-sm mb-3 ${sec.headerColor}`}>{sec.title}</h3>
          
          {sec.isSetup && <AutoConfigBox />}
          {sec.isSetupBgp && <AutoConfigBgpBox />}
          
          <div className="space-y-3">
            {sec.items.map((item, i) => (
              <div key={i} className="flex gap-3">
                <span className={`flex-shrink-0 mt-0.5 w-5 h-5 rounded-full bg-white/10 flex items-center justify-center text-[10px] font-bold text-white`}>{i + 1}</span>
                <div>
                  <p className="text-xs font-semibold text-foreground">{item.label}</p>
                  <p className="text-xs text-muted-foreground mt-0.5 leading-relaxed">{item.text}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}


// ══════════════════════════════════════════════════════════════════════════════
// CLIENT ACTIVITY MODAL
// Modal pop-up untuk menampilkan aktivitas satu IP pelanggan secara detail
// ══════════════════════════════════════════════════════════════════════════════

const ACTIVITY_RANGES = [
  { value: "1h",  label: "1 Jam" },
  { value: "6h",  label: "6 Jam" },
  { value: "12h", label: "12 Jam" },
  { value: "24h", label: "24 Jam" },
  { value: "7d",  label: "7 Hari" },
];

function ClientActivityModal({ ip, deviceId, onClose, onBlock }) {
  const [range, setRange]     = useState("6h");
  const [data, setData]       = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError]     = useState(null);
  const [activeInnerTab, setActiveInnerTab] = useState("platforms");

  const fetchActivity = async (r) => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({ ip, range: r });
      if (deviceId) params.set("device_id", deviceId);
      const res = await api.get(`/peering-eye/client-activity?${params}`);
      setData(res.data);
    } catch (e) {
      setError(e.response?.data?.detail || "Gagal memuat data aktivitas.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchActivity(range);
  }, [ip, range, deviceId]);

  // Close on Escape
  useEffect(() => {
    const handler = (e) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onClose]);

  const uInfo = data?.user_info || {};
  const platforms = data?.platform_breakdown || [];
  const domains   = data?.top_domains || [];
  const maxHits   = platforms[0]?.hits || 1;

  return (
    <div
      className="fixed inset-0 z-[9999] flex items-center justify-center p-3 sm:p-6"
      style={{ background: "rgba(0,0,0,0.75)", backdropFilter: "blur(6px)" }}
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div
        className="relative w-full max-w-2xl max-h-[92vh] flex flex-col rounded-2xl border border-white/10 shadow-2xl overflow-hidden animate-in fade-in zoom-in-95 duration-200"
        style={{ background: "linear-gradient(160deg, #0d1117 0%, #0a0f1e 50%, #060b18 100%)" }}
      >
        {/* ── Header ─────────────────────────────────────────────────────────── */}
        <div className="flex items-start justify-between px-5 py-4 border-b border-white/[0.08]">
          <div className="flex items-start gap-3">
            {/* Avatar IP */}
            <div className="w-10 h-10 rounded-full bg-emerald-500/15 border border-emerald-500/30 flex items-center justify-center flex-shrink-0 mt-0.5">
              <Eye className="w-5 h-5 text-emerald-400" />
            </div>
            <div>
              <div className="flex items-center gap-2 flex-wrap">
                <p className="text-base font-bold text-white font-mono">{ip}</p>
                {uInfo.name && (
                  <span className="text-[10px] px-2 py-0.5 bg-emerald-500/15 border border-emerald-500/30 text-emerald-300 rounded-full font-semibold">
                    {uInfo.type} · {uInfo.name}
                  </span>
                )}
              </div>
              <div className="flex items-center gap-3 mt-1 flex-wrap">
                {uInfo.mac && (
                  <span className="text-[10px] text-slate-500 font-mono">MAC: {uInfo.mac}</span>
                )}
                {uInfo.uptime && (
                  <span className="text-[10px] text-slate-500">Uptime: {uInfo.uptime}</span>
                )}
                {uInfo.service && (
                  <span className="text-[10px] text-slate-500">Paket: {uInfo.service}</span>
                )}
                {!uInfo.name && (
                  <span className="text-[10px] text-slate-600">Pelanggan tidak terdeteksi di sesi aktif</span>
                )}
              </div>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 hover:bg-white/10 rounded-lg transition-colors text-slate-400 hover:text-white flex-shrink-0"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* ── Range Selector + Stats Bar ────────────────────────────────────── */}
        <div className="flex items-center justify-between px-5 py-3 bg-white/[0.02] border-b border-white/[0.06]">
          <div className="flex items-center gap-1.5">
            {ACTIVITY_RANGES.map(r => (
              <button
                key={r.value}
                onClick={() => setRange(r.value)}
                className={`px-2.5 py-1 rounded-md text-[11px] font-semibold transition-all ${ range === r.value ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/40" : "text-slate-500 hover:text-slate-300 hover:bg-white/5" }`}
              >
                {r.label}
              </button>
            ))}
          </div>
          {data?.found && (
            <div className="flex items-center gap-4">
              <div className="text-right">
                <p className="text-xs font-bold text-white">{fmtBytes(data.total_bytes || 0)}</p>
                <p className="text-[9px] text-slate-500">{fmtNum(data.total_hits)} DNS hits</p>
              </div>
              <button
                onClick={() => {
                  if (window.confirm(`Blokir/isolir klien ${uInfo.name || ip}?`)) {
                    onBlock("client", uInfo.name || ip);
                    onClose();
                  }
                }}
                className="flex items-center gap-1.5 px-2.5 py-1.5 bg-red-500/10 hover:bg-red-500/20 text-red-400 border border-red-500/30 rounded-lg text-[11px] font-semibold transition-colors"
              >
                <AlertCircle className="w-3.5 h-3.5" />
                Blokir
              </button>
            </div>
          )}
        </div>

        {/* ── Body ── */}
        <div className="flex-1 overflow-y-auto min-h-0">
          {loading ? (
            <div className="flex flex-col items-center justify-center py-20 gap-3">
              <div className="w-8 h-8 border-2 border-emerald-500/30 border-t-emerald-400 rounded-full animate-spin" />
              <p className="text-sm text-slate-500">Menganalisa aktivitas {ip}...</p>
            </div>
          ) : error ? (
            <div className="flex flex-col items-center justify-center py-20 gap-3">
              <AlertCircle className="w-8 h-8 text-red-400 opacity-60" />
              <p className="text-sm text-red-400">{error}</p>
              <button onClick={() => fetchActivity(range)} className="text-xs text-slate-400 hover:text-white">Coba lagi</button>
            </div>
          ) : !data?.found ? (
            <div className="flex flex-col items-center justify-center py-16 gap-3 px-6">
              <Radar className="w-10 h-10 text-slate-600 opacity-50" />
              <p className="text-sm text-slate-400 font-semibold text-center">
                Tidak ada aktivitas untuk IP ini dalam {ACTIVITY_RANGES.find(r=>r.value===range)?.label || range} terakhir.
              </p>
              {data?.has_historical && (
                <p className="text-xs text-emerald-400 text-center">
                  💡 IP ini pernah terdeteksi sebelumnya. Coba perlebar rentang waktu.
                </p>
              )}
              <p className="text-[11px] text-slate-600 text-center max-w-xs">
                Pastikan syslog MikroTik sudah aktif dan mengirim ke NOC Sentinel. Data akan muncul setelah ada traffic dari IP ini.
              </p>
            </div>
          ) : (
            <div className="p-5 space-y-5">
              {/* Inner Tab Navigation */}
              <div className="flex gap-1 bg-white/[0.04] p-1 rounded-lg border border-white/[0.06]">
                {[
                  { key: "platforms", label: "Platform", icon: BarChart2 },
                  { key: "domains",   label: `Domain (${domains.length})`, icon: Globe },
                ].map(tab => {
                  const Icon = tab.icon;
                  return (
                    <button
                      key={tab.key}
                      onClick={() => setActiveInnerTab(tab.key)}
                      className={`flex-1 flex items-center justify-center gap-1.5 py-1.5 rounded-md text-xs font-semibold transition-all ${ activeInnerTab === tab.key ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/30" : "text-slate-500 hover:text-slate-300" }`}
                    >
                      <Icon className="w-3.5 h-3.5" />
                      {tab.label}
                    </button>
                  );
                })}
              </div>

              {/* ── Platform Breakdown Tab ──────────────────────────────────── */}
              {activeInnerTab === "platforms" && (
                <div className="space-y-3">
                  {platforms.length === 0 ? (
                    <p className="text-center text-xs text-slate-500 py-8">Tidak ada data platform</p>
                  ) : platforms.map((p, i) => (
                    <div key={i} className="space-y-1.5">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <span className="text-base leading-none">{p.icon}</span>
                          <span className="text-xs font-semibold text-slate-200">{p.platform}</span>
                          {i === 0 && (
                            <span className="text-[9px] px-1.5 py-0.5 bg-amber-500/10 text-amber-400 border border-amber-500/30 rounded-full">TOP</span>
                          )}
                        </div>
                        <div className="flex items-center gap-4 text-right">
                          <div>
                            <p className="text-xs font-mono font-bold text-white">
                              {p.bytes > 0 ? p.bytes_fmt : `${fmtNum(p.hits)} hits`}
                            </p>
                            <p className="text-[9px] text-slate-500">
                              {p.bytes > 0 ? `${fmtNum(p.hits)} hits` : "DNS only"}
                            </p>
                          </div>
                          <div className="w-10 text-right">
                            <span className="text-[11px] font-bold" style={{ color: p.color }}>
                              {p.pct_hits}%
                            </span>
                          </div>
                        </div>
                      </div>
                      {/* Bar Chart */}
                      <div className="h-2 bg-white/[0.06] rounded-full overflow-hidden">
                        <div
                          className="h-full rounded-full transition-all duration-500"
                          style={{
                            width: `${(p.hits / maxHits) * 100}%`,
                            background: `linear-gradient(90deg, ${p.color}99, ${p.color})`,
                            boxShadow: `0 0 8px ${p.color}60`,
                          }}
                        />
                      </div>
                    </div>
                  ))}

                  {/* Summary footer */}
                  <div className="mt-4 pt-4 border-t border-white/[0.06] grid grid-cols-3 gap-3">
                    <div className="text-center bg-white/[0.03] rounded-lg p-3 border border-white/[0.06]">
                      <p className="text-lg font-bold text-emerald-400">{fmtBytes(data.total_bytes || 0)}</p>
                      <p className="text-[10px] text-slate-500 mt-0.5">Est. Traffic</p>
                    </div>
                    <div className="text-center bg-white/[0.03] rounded-lg p-3 border border-white/[0.06]">
                      <p className="text-lg font-bold text-cyan-400">{fmtNum(data.total_hits)}</p>
                      <p className="text-[10px] text-slate-500 mt-0.5">DNS Queries</p>
                    </div>
                    <div className="text-center bg-white/[0.03] rounded-lg p-3 border border-white/[0.06]">
                      <p className="text-lg font-bold text-purple-400">{platforms.length}</p>
                      <p className="text-[10px] text-slate-500 mt-0.5">Platform</p>
                    </div>
                  </div>

                  {/* Insight banner */}
                  {platforms.length > 0 && platforms[0].pct_hits >= 50 && (
                    <div className="flex items-start gap-2.5 p-3 bg-amber-500/5 border border-amber-500/20 rounded-lg">
                      <span className="text-base flex-shrink-0">💡</span>
                      <p className="text-[11px] text-amber-300/90 leading-relaxed">
                        Pelanggan ini dominan mengakses <strong>{platforms[0].icon} {platforms[0].platform}</strong> ({platforms[0].pct_hits}% dari total traffic). Jika mengeluh lambat, cek apakah ada masalah rute/latensi ke ASN platform tersebut.
                      </p>
                    </div>
                  )}
                </div>
              )}

              {/* ── Domains Tab ────────────────────────────────────────────── */}
              {activeInnerTab === "domains" && (
                <div>
                  {domains.length === 0 ? (
                    <div className="flex flex-col items-center py-12 gap-2">
                      <Globe className="w-8 h-8 text-slate-600 opacity-40" />
                      <p className="text-xs text-slate-500 text-center">
                        Tidak ada data domain tersedia.<br/>
                        <span className="text-[11px] opacity-70">Domain terhitung secara proporsional dari traffic platform.</span>
                      </p>
                    </div>
                  ) : (
                    <div className="space-y-0.5">
                      {domains.map((d, i) => (
                        <div
                          key={i}
                          className="flex items-center gap-3 py-2 px-2 hover:bg-white/[0.04] transition-colors rounded-lg group"
                        >
                          <span className="text-[10px] text-slate-600 font-mono w-5 text-right flex-shrink-0">{i+1}</span>
                          <span className="text-sm leading-none flex-shrink-0">{d.icon}</span>
                          <div className="flex-1 min-w-0">
                            <p className="text-xs font-mono text-slate-200 truncate group-hover:text-white transition-colors">
                              {d.domain}
                            </p>
                            <p className="text-[9px] mt-0.5" style={{ color: d.color }}>{d.platform}</p>
                          </div>
                          <div className="flex items-center gap-2 flex-shrink-0">
                            <span className="text-[10px] font-mono text-cyan-400 tabular-nums">{fmtNum(d.hits)}</span>
                            <span className="text-[9px] text-slate-600">hits</span>
                          </div>
                        </div>
                      ))}
                      <p className="text-[10px] text-slate-600 text-center pt-3 border-t border-white/[0.05]">
                        * Domain dihitung secara estimasi proporsional dari rasio traffic per platform.<br/>Akurasi meningkat seiring volume traffic.
                      </p>
                    </div>
                  )}
                </div>
              )}
            </div>
          )}
        </div>

        {/* ── Footer ─────────────────────────────────────────────────────────── */}
        <div className="px-5 py-3 border-t border-white/[0.06] bg-white/[0.02] flex items-center justify-between">
          <p className="text-[10px] text-slate-600 flex items-center gap-1.5">
            <Eye className="w-3 h-3" />
            Sentinel Peering Eye · {ACTIVITY_RANGES.find(r=>r.value===range)?.label} terakhir
            {data?.data_points ? ` · ${data.data_points} data point` : ""}
          </p>
          <button
            onClick={() => fetchActivity(range)}
            className="flex items-center gap-1.5 text-[11px] text-slate-400 hover:text-white transition-colors"
          >
            <RefreshCw className="w-3 h-3" />
            Refresh
          </button>
        </div>
      </div>
    </div>
  );
}
