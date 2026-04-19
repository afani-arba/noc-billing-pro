import { useState, useEffect, useCallback, useRef } from "react";
import api from "@/lib/api";
import { useAuth } from "@/App";
import { useAllowedDevices } from "@/hooks/useAllowedDevices";
import { Plus, Trash2, Edit, Save, RefreshCw, Send, CheckCircle2, Ticket, XCircle, Settings2, Package, Globe, Clock, MessageCircle, Activity, ShoppingCart, Loader2, Link2, Download, Zap, Wifi, WifiOff, ArrowRightLeft, Radio, AlertTriangle, AlertCircle, MessageSquare, Key, Image, ShieldCheck, CreditCard, Printer, BarChart2, List, TrendingUp, CheckCircle, Ban } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription } from "@/components/ui/dialog";
import { PackagesTab } from "@/components/BillingPackages";
import { toast } from "sonner";

// â”€â”€â”€ Helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
const fmt = (n) => `Rp ${parseInt(n || 0).toLocaleString("id-ID")}`;

const VoucherStatusBadge = ({ status }) => {
  const map = {
    new:     { label: "Baru",       icon: Clock,         cls: "bg-blue-500/10 text-blue-400 border-blue-500/20" },
    active:  { label: "Aktif",      icon: CheckCircle2,  cls: "bg-green-500/10 text-green-400 border-green-500/20" },
    expired: { label: "Kadaluarsa", icon: XCircle,       cls: "bg-red-500/10 text-red-400 border-red-500/20" },
    disabled:{ label: "Nonaktif",   icon: Ban,           cls: "bg-orange-500/10 text-orange-400 border-orange-500/20" },
  };
  const cfg = map[status] || { label: status, icon: Activity, cls: "bg-muted text-muted-foreground border-border" };
  const Icon = cfg.icon;
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold border ${cfg.cls}`}>
      <Icon className="w-3 h-3" />{cfg.label}
    </span>
  );
};

const SummaryCard = ({ icon: Icon, label, value, color }) => (
  <div className="bg-card border border-border rounded-lg p-4 flex items-center gap-4">
    <div className={`w-10 h-10 rounded-lg flex items-center justify-center flex-shrink-0 ${color}`}>
      <Icon className="w-5 h-5" />
    </div>
    <div className="min-w-0">
      <p className="text-xs text-muted-foreground truncate">{label}</p>
      <p className="text-xl font-bold leading-tight">{value}</p>
    </div>
  </div>
);

const RpIcon = ({ className = "w-5 h-5" }) => (
  <div className={`${className} flex items-center justify-center font-bold text-[9px] border-[1.5px] border-current rounded-[3px] leading-none select-none pt-[1px] px-[1px]`} style={{ fontFamily: 'Inter, sans-serif' }}>
    Rp
  </div>
);

const TabBtn = ({ active, onClick, icon: Icon, label }) => (
  <button
    onClick={onClick}
    className={`flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 transition-colors whitespace-nowrap ${
      active
        ? "border-primary text-primary"
        : "border-transparent text-muted-foreground hover:text-foreground hover:border-border"
    }`}
  >
    <Icon className="w-4 h-4" />{label}
  </button>
);

// â”€â”€â”€ RADIUS Status Badge â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
const RadiusBadge = ({ enabled, loading }) => {
  if (loading) return (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold border bg-muted text-muted-foreground border-border">
      <Loader2 className="w-3 h-3 animate-spin" /> Memeriksaâ€¦
    </span>
  );
  return enabled
    ? <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold border bg-green-500/10 text-green-400 border-green-500/20"><CheckCircle2 className="w-3 h-3" /> RADIUS Aktif</span>
    : <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold border bg-red-500/10 text-red-400 border-red-500/20"><XCircle className="w-3 h-3" /> RADIUS Tidak Aktif</span>;
};

// â”€â”€â”€ Main Page â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
export default function HotspotBillingPage() {
  const { user } = useAuth();
  const isViewer = user?.role === "viewer" || user?.role === "helpdesk";

  const [activeTab, setActiveTab] = useState("vouchers");

  // State (devices & loadingDevices sekarang dari useAllowedDevices hook di bawah)
  const [devRadiusMap, setDevRadiusMap] = useState({}); // { device_id: { radius_enabled, loading } }
  const [selectedDevice, setSelectedDevice] = useState("");
  const [profiles, setProfiles]         = useState([]);
  const [profilesLoading, setProfilesLoading] = useState(false);
  const [radiusStatus, setRadiusStatus] = useState(null);
  const [radiusLoading, setRadiusLoading] = useState(false);
  const [vouchers, setVouchers]         = useState([]);
  const [vLoading, setVLoading]         = useState(false);
  const [vSearch, setVSearch]           = useState("");
  const [sales, setSales]               = useState([]);
  const [salesLoading, setSalesLoading] = useState(false);
  const [generating, setGenerating]     = useState(false);
  const [generatedVouchers, setGeneratedVouchers] = useState([]);
  const [form, setForm] = useState({
    count: 10, prefix: "VC", length: 6,
    profile: "default", server: "all",
    price: "5000", uptime_limit: "1h", validity: "1d",
  });
  const [settings, setSettings]         = useState({});
  const [settingsLoading, setSettingsLoading] = useState(false);
  const [savingSettings, setSavingSettings]   = useState(false);
  const [packages, setPackages]         = useState([]);
  const [packagesLoading, setPackagesLoading] = useState(false);
  const [waOrders, setWaOrders]         = useState([]);
  const [waOrdersLoading, setWaOrdersLoading] = useState(false);
  const [waOrdersFilter, setWaOrdersFilter] = useState(""); // "" | "unpaid" | "paid"
  const [waSearch, setWaSearch]             = useState("");  // search query for pembelian online
  
  const [editVoucher, setEditVoucher] = useState(null);
  const [transferVoucher, setTransferVoucher] = useState(null);
  const [transferTarget, setTransferTarget] = useState("");
  
  // Real-time counter
  const lastFetchTime = useRef(Date.now());
  const [now, setNow] = useState(Date.now());

  // Handlers
  const handleEditSubmit = async () => {
    if (!editVoucher) return;
    try {
      await api.put(`/hotspot-vouchers/${editVoucher.id}`, {
        password: editVoucher.password,
        profile: editVoucher.profile,
        validity: editVoucher.validity
      });
      toast.success("Voucher diperbarui");
      setEditVoucher(null);
      fetchVouchers();
    } catch { toast.error("Gagal mengupdate voucher"); }
  };

  const handleTransferSubmit = async () => {
    if (!transferVoucher || !transferTarget) return;
    try {
      await api.post(`/hotspot-vouchers/${transferVoucher.id}/transfer`, {
        new_device_id: transferTarget
      });
      toast.success("Voucher berhasil dipindah");
      setTransferVoucher(null);
      setTransferTarget("");
      fetchVouchers();
    } catch { toast.error("Gagal memindah voucher"); }
  };

  const handleToggleStatus = (v) => {
    const toastId = toast.loading("Memproses perubahan status...");
    api.put(`/hotspot-vouchers/${v.id}/toggle-status`)
      .then(res => {
        toast.success(res.data?.status === "disabled" ? "Voucher dinonaktifkan" : "Voucher diaktifkan", { id: toastId });
        fetchVouchers(true);
      })
      .catch(err => {
        toast.error(err?.response?.data?.detail || "Gagal mengubah status voucher", { id: toastId });
        console.error("Toggle voucher error:", err);
      });
  };

  const loadPackages = useCallback(() => {
    setPackagesLoading(true);
    api.get("/billing/packages")
      .then(r => setPackages(r.data))
      .catch(() => {})
      .finally(() => setPackagesLoading(false));
  }, []);

  const loadSettings = async () => {
    setSettingsLoading(true);
    try {
      const r = await api.get("/hotspot-settings");
      setSettings(r.data || {});
    } catch {}
    finally { setSettingsLoading(false); }
  };

  const fetchVouchers = useCallback(async (silent = false) => {
    if (!silent) setVLoading(true);
    try {
      const params = {};
      if (vSearch) params.search = vSearch;
      
      const r = await api.get("/hotspot-vouchers", { params });
      const newData = r.data || [];
      const nowTs = Date.now();
      
      setVouchers(prev => {
        // Optimistic Merge: If server data is stale (lower or equal uptime than local calculation)
        // we "sticky" our local calculation into the new data to prevent the timer "jumping back".
        return newData.map(v => {
          const old = prev.find(o => o.id === v.id);
          if (old && v.status === "active" && old.status === "active") {
             const localProgress = Math.floor((nowTs - lastFetchTime.current) / 1000);
             const currentLocalUptime = (old.used_uptime_secs || 0) + localProgress;
             
             // If server value is lagging behind our local clock, keep the local one
             if ((v.used_uptime_secs || 0) < currentLocalUptime) {
               return { ...v, used_uptime_secs: currentLocalUptime };
             }
          }
          return v;
        });
      });
      
      lastFetchTime.current = nowTs;
    } catch { toast.error("Gagal memuat data voucher"); }
    finally { setVLoading(false); }
  }, [vSearch]);

  const fetchSales = useCallback(async (silent = false) => {
    if (!silent) setSalesLoading(true);
    try {
      const r = await api.get("/hotspot-sales");
      setSales(r.data || []);
    } catch { toast.error("Gagal memuat laporan penjualan"); }
    finally { setSalesLoading(false); }
  }, []);

  const fetchWaOrders = useCallback(async (silent = false) => {
    if (!silent) setWaOrdersLoading(true);
    try {
      const r = await api.get("/billing/voucher-orders", { params: { status: waOrdersFilter, search: waSearch, limit: 50 } });
      setWaOrders(r.data?.data || []);
    } catch { toast.error("Gagal memuat pesanan online"); }
    finally { setWaOrdersLoading(false); }
  }, [waOrdersFilter, waSearch]);

  const [waPayModal, setWaPayModal] = useState(null); // { id, name }
  const [waPayMethod, setWaPayMethod] = useState("cash");

  const markWaOrderPaid = async (id, method = "cash") => {
    try {
      await api.patch(`/billing/voucher-orders/${id}/pay`, { payment_method: method });
      toast.success("Pesanan ditandai lunas!");
      setWaPayModal(null);
      fetchWaOrders();
    } catch (e) { toast.error(e.response?.data?.detail || "Gagal"); }
  };

  const deleteWaOrder = async (id) => {
    if (!confirm("Hapus pesanan ini?")) return;
    try {
      await api.delete(`/billing/voucher-orders/${id}`);
      toast.success("Pesanan dihapus");
      fetchWaOrders();
    } catch (e) { toast.error(e.response?.data?.detail || "Gagal"); }
  };

  const fetchRadiusStatus = async (devId) => {
    if (!devId) return;
    setRadiusLoading(true);
    try {
      const r = await api.get("/hotspot-radius-status", { params: { device_id: devId } });
      setRadiusStatus(r.data);
    } catch { setRadiusStatus(null); }
    finally { setRadiusLoading(false); }
  };


  const { devices, isLocked, defaultDeviceId, loading: loadingDevices } = useAllowedDevices();

  // Auto-select: pilih pertama jika terkunci, atau semua device jika admin
  useEffect(() => {
    if (devices.length > 0) {
      const firstId = defaultDeviceId || devices[0]?.id;
      setSelectedDevice(firstId || "");
    }
  }, [devices, defaultDeviceId]);

  // Paralel cek status RADIUS semua device
  useEffect(() => {
    if (devices.length === 0) return;
    const initMap = Object.fromEntries(devices.map(d => [d.id, { radius_enabled: null, loading: true }]));
    setDevRadiusMap(initMap);
    Promise.all(devices.map(async d => {
      try {
        const res = await api.get("/hotspot-radius-status", { params: { device_id: d.id } });
        setDevRadiusMap(prev => ({ ...prev, [d.id]: { radius_enabled: res.data?.radius_enabled, loading: false } }));
      } catch {
        setDevRadiusMap(prev => ({ ...prev, [d.id]: { radius_enabled: false, loading: false, error: true } }));
      }
    }));
    loadSettings();
    loadPackages();
  }, [devices, loadPackages]);

  useEffect(() => {
    if (!selectedDevice) { setRadiusStatus(null); return; }
    // FULL RADIUS MODE: Tidak perlu fetch profil dari MikroTik.
    // Profil/paket diambil murni dari database NOC Billing (/api/billing/packages).
    fetchRadiusStatus(selectedDevice);
  }, [selectedDevice]);

  useEffect(() => {
    if (activeTab === "vouchers") fetchVouchers();
    if (activeTab === "sales")    fetchSales();
    if (activeTab === "wa_orders") fetchWaOrders();
  }, [activeTab, fetchVouchers, fetchSales, fetchWaOrders]);

  // FIX: Satu interval yang menggabungkan ticker 1s (UI) dan refresh 10s (data)
  // Sebelumnya ada 2 interval terpisah — mubazir dan bisa bentrok
  useEffect(() => {
    let tick = 0;
    const timer = setInterval(() => {
      tick++;
      setNow(Date.now()); // Update UI clock setiap 1s

      // Refresh data setiap 10 tick (10 detik), tapi skip jika sedang modal
      if (tick % 10 === 0 && !editVoucher && !generating && !transferVoucher) {
        if (activeTab === "vouchers")   fetchVouchers(true);
        if (activeTab === "sales")      fetchSales(true);
        if (activeTab === "wa_orders")  fetchWaOrders(true);
      }
    }, 1000);

    return () => clearInterval(timer);
  }, [activeTab, fetchVouchers, fetchSales, fetchWaOrders, editVoucher, generating, transferVoucher]);

  const getLiveUptime = (v) => {
    let secs = v.used_uptime_secs || 0;
    if (v.status === "active") {
      const diff = Math.floor((now - lastFetchTime.current) / 1000);
      secs += Math.max(0, diff);
    }
    return fmtTimeS(secs);
  };

  const getLiveSisaUptime = (v) => {
    if (v.status === "expired") return "Habis";
    if (!v.limit_uptime_secs || v.limit_uptime_secs >= 999999999) return "Unlimited";
    
    // For new/inactive, show full limit
    if (v.status === "new" || !v.session_start_time) return fmtTimeS(v.limit_uptime_secs);

    let used_secs = v.used_uptime_secs || 0;
    if (v.status === "active") {
      const diff = Math.floor((now - lastFetchTime.current) / 1000);
      used_secs += Math.max(0, diff);
    }
    const rem = Math.max(0, v.limit_uptime_secs - used_secs);
    return rem === 0 ? "Habis" : fmtTimeS(rem);
  };

  const getLiveSisaValiditas = (v) => {
    if (v.status === "expired") return "Habis";
    if (v.status === "new" || !v.session_start_time) return v.validity || "Belum Aktif";
    
    if (v.rem_validity_secs === undefined || v.rem_validity_secs === null || v.rem_validity_secs >= 999999999) return "Unlimited";
    
    let rem = v.rem_validity_secs;
    // Validitas berbasis kalender — terus mundur saat active MAUPUN offline
    // Hanya berhenti jika voucher berstatus 'new' (belum pernah dipakai sama sekali)
    if (v.status === "active" || v.status === "offline") {
      const diff = Math.floor((now - lastFetchTime.current) / 1000);
      rem -= diff;
    }
    const finalRem = Math.max(0, rem);
    return finalRem === 0 ? "Habis" : fmtTimeS(finalRem);
  };

  function fmtTimeS(s) {
    if (s <= 0) return "0s";
    const d = Math.floor(s / 86400); s %= 86400;
    const h = Math.floor(s / 3600); s %= 3600;
    const m = Math.floor(s / 60); const sec = Math.floor(s % 60);
    const res = [];
    if (d) res.push(`${d}d`);
    if (h) res.push(`${h}h`);
    if (m) res.push(`${m}m`);
    if (sec || res.length === 0) res.push(`${sec}s`);
    return res.join("");
  }

  const handleGenerate = async () => {
    if (!selectedDevice) return toast.error("Pilih router MikroTik terlebih dahulu!");
    if (form.count < 1 || form.count > 100) return toast.error("Jumlah voucher harus 1-100");
    setGenerating(true);
    try {
      const batch = [];
      const preview = [];
      const randStr = (len) => {
        const chars = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";
        return Array.from({ length: len }, () => chars[Math.floor(Math.random() * chars.length)]).join("");
      };
      for (let i = 0; i < form.count; i++) {
        const code = randStr(form.length);
        const username = `${form.prefix}${code}`;
        const password = username;
        batch.push({ name: username, password, profile: form.profile, server: form.server,
          price: form.price, uptime_limit: form.uptime_limit, validity: form.validity,
          comment: `Voucher ${new Date().toISOString().split("T")[0]}` });
        preview.push({ username, password, profile: form.profile, price: form.price, 
          uptime_limit: form.uptime_limit, validity: form.validity });
      }
      await api.post(`/hotspot-users/batch?device_id=${selectedDevice}`, { users: batch });
      toast.success(`${form.count} voucher berhasil dibuat dan disimpan ke database!`);
      setGeneratedVouchers(preview);
    } catch (e) {
      toast.error(e.response?.data?.detail || "Gagal membuat voucher");
    } finally {
      setGenerating(false);
    }
  };

  const handleSaveSettings = async () => {
    setSavingSettings(true);
    try {
      await api.post("/hotspot-settings", settings);
      toast.success("Pengaturan Hotspot disimpan!");
    } catch (e) {
      toast.error(e.response?.data?.detail || "Gagal menyimpan");
    } finally {
      setSavingSettings(false);
    }
  };


  const nowObj = new Date();
  const todayStr = nowObj.toLocaleDateString("en-CA"); // YYYY-MM-DD local
  const monthStr = todayStr.substring(0, 7);           // YYYY-MM local

  // Filter ONLY for current month (Monthly Reset)
  const monthlySales = sales.filter(x => {
    if (!x.created_at) return false;
    // Convert UTC string from DB to local date string (YYYY-MM-DD)
    const localDt = new Date(x.created_at).toLocaleDateString("en-CA");
    return localDt.startsWith(monthStr);
  });

  const totalRevenueLocal = monthlySales.reduce((s, x) => s + (parseFloat(x.price) || 0), 0);
  const totalCountLocal   = monthlySales.length;

  // Filter precisely for local today
  const todayStats = monthlySales.filter(x => {
    const localDt = new Date(x.created_at).toLocaleDateString("en-CA");
    return localDt === todayStr;
  });
  const todayRevenue = todayStats.reduce((s, x) => s + (parseFloat(x.price) || 0), 0);
  const vOnline  = vouchers.filter(v => v.status === "active").length;
  const vOffline = vouchers.filter(v => v.session_start_time && v.status !== "active" && v.status !== "expired").length;
  const vExpired = vouchers.filter(v => v.status === "expired").length;

  const fmtDt = (s) => s ? new Date(s).toLocaleString("id-ID", { dateStyle: "short", timeStyle: "short" }) : "—";

  const parseUptime = (str) => {
    if (!str) return 0;
    let total = 0;
    // Regex global untuk menangkap semua angka + unit (w/d/h/m/s)
    const regex = /(\d+)\s*([wdhms])/g;
    let m;
    while ((m = regex.exec(str.toLowerCase())) !== null) {
      const val = parseInt(m[1]);
      const unit = m[2];
      const multiplier = {
        w: 604800,
        d: 86400,
        h: 3600,
        m: 60,
        s: 1
      }[unit] || 0;
      total += val * multiplier;
    }
    return total;
  };

  const formatUptime = (seconds) => {
    if (seconds <= 0) return "0s";
    let w = Math.floor(seconds / 604800); seconds %= 604800;
    let d = Math.floor(seconds / 86400); seconds %= 86400;
    let h = Math.floor(seconds / 3600); seconds %= 3600;
    let m = Math.floor(seconds / 60); seconds %= 60;
    let s = seconds;
    let res = "";
    if (w) res += w + "w";
    if (d) res += d + "d";
    if (h) res += h + "h";
    if (m) res += m + "m";
    if (s) res += s + "s";
    return res;
  };
  const tabs = [
    { id: "wa_orders", label: "Pembelian Online", icon: ShoppingCart },
    { id: "vouchers", label: "Voucher History", icon: RpIcon },
    { id: "sales", label: "Laporan penjualan", icon: TrendingUp },
    { id: "packages", label: "Paket Layanan", icon: Package },
    { id: "generator", label: "Generator", icon: Zap },
  ];

  return (
    <div className="space-y-6 pb-20">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight flex items-center gap-2">
            <Wifi className="w-7 h-7 text-primary" /> Hotspot Billing
          </h1>
          <p className="text-sm text-muted-foreground">Manage your vouchers, sales, and hotspot packages</p>
        </div>
        <div className="flex items-center gap-3">
          {loadingDevices ? (
            <div className="flex items-center gap-2 h-9 px-3 rounded-md border border-border bg-card text-xs text-muted-foreground">
              <Loader2 className="w-3.5 h-3.5 animate-spin" /> Memeriksa router...
            </div>
          ) : isLocked ? (
            // Tampilkan nama router saja (tidak bisa diganti) jika terkunci
            <div className="flex items-center gap-2 h-9 px-3 rounded-md border border-border bg-card/80 text-xs text-foreground min-w-[180px]">
              <span className="truncate">{devices.find(d => d.id === selectedDevice)?.name || "Router"}</span>
              <span className="ml-auto text-[9px] text-muted-foreground px-1 py-0.5 border border-border rounded bg-secondary">Terkunci</span>
            </div>
          ) : (
            <Select value={selectedDevice} onValueChange={setSelectedDevice}>
              <SelectTrigger className="w-[240px] h-9 bg-card">
                <SelectValue placeholder="Pilih Router..." />
              </SelectTrigger>
              <SelectContent>
                {devices.map(d => {
                  const rs = devRadiusMap[d.id];
                  return (
                    <SelectItem key={d.id} value={d.id}>
                      <div className="flex items-center gap-2">
                        <span>{d.name}</span>
                        {rs?.loading ? (
                          <span className="text-[9px] text-muted-foreground">...</span>
                        ) : rs?.radius_enabled ? (
                          <span className="text-[9px] px-1 py-0.5 rounded bg-green-500/10 text-green-400 border border-green-500/20 font-semibold flex items-center gap-1">RADIUS <CheckCircle2 className="w-3 h-3" /></span>
                        ) : (
                          <span className="text-[9px] px-1 py-0.5 rounded bg-red-500/10 text-red-400 border border-red-500/20 font-semibold flex items-center gap-1">RADIUS <XCircle className="w-3 h-3" /></span>
                        )}
                      </div>
                    </SelectItem>
                  );
                })}
              </SelectContent>
            </Select>
          )}
          <RadiusBadge enabled={radiusStatus?.radius_enabled} loading={radiusLoading} />
        </div>
      </div>

      {/* MODALS */}
      <Dialog open={!!editVoucher} onOpenChange={(o) => !o && setEditVoucher(null)}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Edit Voucher {editVoucher?.username}</DialogTitle>
            <DialogDescription>Pengaturan ini akan tersinkronisasi ke MikroTik jika online</DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <div>
              <Label>Password</Label>
              <Input value={editVoucher?.password || ""} onChange={e => setEditVoucher({...editVoucher, password: e.target.value})} />
            </div>
            <div>
              <Label>Paket Layanan</Label>
              <Select value={editVoucher?.profile || "default"} onValueChange={v => setEditVoucher({...editVoucher, profile: v})}>
                <SelectTrigger className="h-9"><SelectValue placeholder="Pilih paket" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="default">default</SelectItem>
                  {packages.filter(p => p.service_type === "hotspot").map(p => (
                    <SelectItem key={p.id} value={p.name}>{p.name}</SelectItem>
                  ))}
                  {editVoucher?.profile && editVoucher.profile !== "default" && !packages.find(p => p.name === editVoucher.profile) && (
                    <SelectItem value={editVoucher.profile}>{editVoucher.profile}</SelectItem>
                  )}
                </SelectContent>
              </Select>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditVoucher(null)}>Batal</Button>
            <Button onClick={handleEditSubmit}>Simpan</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={!!transferVoucher} onOpenChange={(o) => !o && setTransferVoucher(null)}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Transfer Voucher</DialogTitle>
            <DialogDescription>
              Pindahkan voucher <b>{transferVoucher?.username}</b> dari <b>{transferVoucher?.router_name || "Router saat ini"}</b> ke router lain. Ini akan menghapus user di router asal.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div>
              <Label>Router Tujuan</Label>
              <Select value={transferTarget} onValueChange={setTransferTarget}>
                <SelectTrigger>
                  <SelectValue placeholder="Pilih mikrotik tujuan" />
                </SelectTrigger>
                <SelectContent>
                  {devices.map(d => (
                    <SelectItem key={d.id} value={d.id}>{d.name}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setTransferVoucher(null)}>Batal</Button>
            <Button onClick={handleTransferSubmit} disabled={!transferTarget}>Mulai Transfer</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Modal Konfirmasi Pembayaran WA Order */}
      <Dialog open={!!waPayModal} onOpenChange={(o) => !o && setWaPayModal(null)}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>Tandai Lunas Manual</DialogTitle>
            <DialogDescription>
              Pesanan <b>{waPayModal?.name || waPayModal?.invoice}</b> — konfirmasi metode pembayaran sebelum melanjutkan.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3 py-2">
            <Label className="text-xs text-muted-foreground">Metode Pembayaran</Label>
            <Select value={waPayMethod} onValueChange={setWaPayMethod}>
              <SelectTrigger className="h-9">
                <SelectValue placeholder="Pilih metode" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="cash">ðŸ’µ Cash / Tunai</SelectItem>
                <SelectItem value="transfer">ðŸ¦ Transfer Bank</SelectItem>
                <SelectItem value="qris">ðŸ“± QRIS</SelectItem>
                <SelectItem value="transfer_moota">ðŸ¤– Transfer (Auto-Moota)</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setWaPayModal(null)}>Batal</Button>
            <Button onClick={() => markWaOrderPaid(waPayModal.id, waPayMethod)}
              className="bg-green-600 hover:bg-green-700 text-white">
              <CheckCircle2 className="w-4 h-4 mr-1.5" /> Konfirmasi Lunas
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Tabs */}
      <div className="flex border-b border-border overflow-x-auto no-scrollbar">
        {tabs.map(t => (
          <TabBtn key={t.id} active={activeTab === t.id} onClick={() => setActiveTab(t.id)} icon={t.icon} label={t.label} />
        ))}
      </div>

      {/* Tab Content */}
      <div className="min-h-[400px]">

        {activeTab === "wa_orders" && (
          <div className="space-y-4">
            <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 flex-wrap">
              <div>
                <h2 className="text-base font-semibold flex items-center gap-2">
                  <ShoppingCart className="w-4 h-4 text-green-400" /> Pembelian Online
                </h2>
              </div>
              {/* Search */}
              <div className="flex items-center gap-2 flex-wrap">
                <div className="relative">
                  <Input
                    placeholder="Cari nama, no HP, invoice..."
                    value={waSearch}
                    onChange={e => setWaSearch(e.target.value)}
                    onKeyDown={e => e.key === "Enter" && fetchWaOrders()}
                    className="h-8 text-xs rounded-sm w-52 pr-7"
                  />
                  {waSearch && (
                    <button onClick={() => { setWaSearch(""); setTimeout(fetchWaOrders, 50); }}
                      className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground">
                      <XCircle className="w-3 h-3" />
                    </button>
                  )}
                </div>
                {["", "unpaid", "paid"].map(f => (
                  <button key={f} onClick={() => setWaOrdersFilter(f)}
                    className={`text-[10px] font-semibold px-2.5 py-1 rounded-sm border transition-all ${
                      waOrdersFilter === f
                        ? f === "paid" ? "border-green-500/40 text-green-400 bg-green-500/10"
                          : f === "unpaid" ? "border-amber-500/40 text-amber-400 bg-amber-500/10"
                          : "border-border text-foreground bg-muted"
                        : "border-border/30 text-muted-foreground/50"
                    }`}>
                    {f === "" ? "Semua" : f === "unpaid" ? "Belum Bayar" : "Sudah Bayar"}
                  </button>
                ))}
                <button onClick={fetchWaOrders}
                  className="text-[10px] px-2 py-1 rounded-sm border border-border text-muted-foreground hover:text-foreground">
                  <RefreshCw className={`w-3 h-3 inline ${waOrdersLoading ? 'animate-spin' : ''}`} />
                </button>
              </div>
            </div>

            <div className="bg-card border border-border rounded-lg overflow-hidden">
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="bg-muted/40 text-xs uppercase tracking-widest text-muted-foreground">
                    <tr>
                      <th className="px-4 py-3 text-left">No. Invoice</th>
                      <th className="px-4 py-3 text-left">Pelanggan</th>
                      <th className="px-4 py-3 text-left">Paket</th>
                      <th className="px-4 py-3 text-right">Total</th>
                      <th className="px-4 py-3 text-center">Status</th>
                      <th className="px-4 py-3 text-left">Dibuat</th>
                      <th className="px-4 py-3 text-center">Aksi</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border">
                    {waOrdersLoading ? (
                      <tr><td colSpan={7} className="py-12 text-center text-muted-foreground">
                        <Loader2 className="w-6 h-6 animate-spin mx-auto mb-2" />Memuat pesanan...
                      </td></tr>
                    ) : (() => {
                        const q = waSearch.toLowerCase().trim();
                        // Filter by status on the frontend just to be sure, although backend handles it too
                        const filtered = waOrders.filter(o => {
                          if (waOrdersFilter && o.status !== waOrdersFilter) return false;
                          return true;
                        });
                        if (filtered.length === 0) return (
                          <tr><td colSpan={7} className="py-12 text-center text-muted-foreground">
                            <ShoppingCart className="w-8 h-8 mx-auto mb-2 opacity-20" />
                            <p className="text-sm">{q ? `Tidak ada hasil untuk "${waSearch}"` : "Belum ada pembelian online"}</p>
                          </td></tr>
                        );
                        return filtered.map(o => (
                      <tr key={o.id} className="hover:bg-muted/30 transition-colors">
                        <td className="px-4 py-3 font-mono text-xs text-muted-foreground">{o.invoice_number}</td>
                        <td className="px-4 py-3">
                          <p className="font-semibold text-sm">{o.customer_name || '—'}</p>
                          <p className="text-[10px] text-muted-foreground font-mono">{o.customer_phone || '—'}</p>
                        </td>
                        <td className="px-4 py-3 text-xs text-muted-foreground">{o.package_name || '—'}</td>
                        <td className="px-4 py-3 text-right font-mono font-bold text-primary">{fmt(o.total)}</td>
                        <td className="px-4 py-3 text-center">
                          <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold border ${
                            o.status === 'paid' ? 'bg-green-500/10 text-green-400 border-green-500/20'
                            : o.status === 'overdue' ? 'bg-red-500/10 text-red-400 border-red-500/20'
                            : 'bg-amber-500/10 text-amber-400 border-amber-500/20'
                          }`}>
                            {o.status === 'paid'
                              ? <><CheckCircle2 className="w-3 h-3" /> Lunas</>
                              : o.status === 'overdue'
                                ? <><AlertCircle className="w-3 h-3" /> Kedaluwarsa</>
                                : <><Clock className="w-3 h-3" /> Pending</>}
                          </span>
                        </td>
                        <td className="px-4 py-3 text-xs text-muted-foreground">{o.created_at ? new Date(o.created_at).toLocaleString('id-ID', {dateStyle:'short',timeStyle:'short'}) : '—'}</td>
                        <td className="px-4 py-3">
                          <div className="flex gap-1 justify-center">
                            {o.status !== 'paid' && (
                              <button
                                onClick={() => { setWaPayMethod("cash"); setWaPayModal({ id: o.id, name: o.customer_name, invoice: o.invoice_number }); }}
                                className="text-[10px] px-2 py-1 rounded border border-green-500/30 text-green-400 hover:bg-green-500/10 flex items-center gap-1"
                                title="Tandai Lunas Manual">
                                <CheckCircle2 className="w-3 h-3" /> Lunas
                              </button>
                            )}
                            <button onClick={() => deleteWaOrder(o.id)}
                              className="text-[10px] px-2 py-1 rounded border border-red-500/30 text-red-400 hover:bg-red-500/10"
                              title="Hapus Pesanan">
                              <Trash2 className="w-3 h-3" />
                            </button>
                          </div>
                        </td>
                      </tr>
                    ));
                    })()}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}

        {activeTab === "vouchers" && (
          <div className="space-y-4">
            <div className="bg-primary/5 border border-primary/20 rounded-lg p-3 flex justify-center mb-4">
              <span className="text-sm font-semibold flex items-center gap-2">
                <Wifi className="w-5 h-5 text-primary" /> Live Aktif: <span className="text-xl text-primary">{vOnline}</span>
              </span>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
              <SummaryCard icon={RpIcon} label="Total Voucher" value={vouchers.length} color="bg-blue-500/20 text-blue-400" />
              <SummaryCard icon={WifiOff} label="OFFLINE" value={vOffline} color="bg-purple-500/20 text-purple-400" />
              <SummaryCard icon={CheckCircle2} label="Aktif" value={vOnline} color="bg-green-500/20 text-green-400" />
              <SummaryCard icon={XCircle} label="Kadaluarsa" value={vExpired} color="bg-red-500/20 text-red-400" />
            </div>

            <div className="flex flex-col sm:flex-row gap-3 items-start sm:items-center justify-between">
              <div className="relative">
                <Input placeholder="Cari username voucher..."
                  value={vSearch} onChange={e => setVSearch(e.target.value)}
                  onKeyDown={e => e.key === "Enter" && fetchVouchers()}
                  className="h-9 text-sm rounded-sm max-w-xs pr-8" />
                {vSearch && (
                  <button onClick={() => { setVSearch(""); }} className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground">
                    <XCircle className="w-3.5 h-3.5" />
                  </button>
                )}
              </div>
              <Button variant="outline" size="sm" className="gap-2 rounded-sm" onClick={() => fetchVouchers()} disabled={vLoading}>
                <RefreshCw className={`w-4 h-4 ${vLoading ? "animate-spin" : ""}`} /> Refresh
              </Button>
            </div>

            <div className="bg-card border border-border rounded-lg overflow-hidden">
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="bg-muted/40 text-xs uppercase tracking-widest text-muted-foreground">
                    <tr>
                      <th className="px-4 py-3 text-left">Router</th>
                      <th className="px-4 py-3 text-left">Username</th>
                      <th className="px-4 py-3 text-left">Paket / Profile</th>
                      <th className="px-4 py-3 text-left">Batas Waktu</th>
                      <th className="px-4 py-3 text-left">Waktu Pakai</th>
                      <th className="px-4 py-3 text-left">Sisa Waktu</th>
                      <th className="px-4 py-3 text-right">Harga</th>
                      <th className="px-4 py-3 text-center">Status</th>
                      <th className="px-4 py-3 text-left">Login Pertama</th>
                      <th className="px-4 py-3 text-left">Dibuat</th>
                      <th className="px-4 py-3 text-center">Aksi</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border">
                    {vLoading ? (
                      <tr><td colSpan={11} className="py-12 text-center text-muted-foreground">
                        <Loader2 className="w-6 h-6 animate-spin mx-auto mb-2" />Memuatâ€¦
                      </td></tr>
                    ) : vouchers.length === 0 ? (
                      <tr><td colSpan={11} className="py-12 text-center text-muted-foreground">
                        <RpIcon className="w-8 h-8 mx-auto mb-2 opacity-20" />
                        <p className="text-sm">Belum ada voucher</p>
                      </td></tr>
                    ) : vouchers.map(v => (
                      <tr key={v.id} className="hover:bg-muted/30 transition-colors">
                        <td className="px-4 py-3 font-semibold text-xs text-muted-foreground">{v.router_name || "—"}</td>
                        <td className="px-4 py-3 font-mono font-semibold text-primary">{v.username} <div className="text-[10px] text-muted-foreground">Pass: {v.password}</div></td>
                        <td className="px-4 py-3 text-xs">{v.profile || "—"}</td>
                        <td className="px-4 py-3 text-xs">
                          {v.uptime_limit ? <div className="text-primary font-semibold">Limit: {v.uptime_limit}</div> : null}
                          <div className="text-[10px] text-muted-foreground">Aktif: {v.validity || "—"}</div>
                        </td>
                        <td className="px-4 py-3 text-xs">
                           <span className="font-mono bg-muted/50 px-1 py-0.5 rounded">{getLiveUptime(v)}</span>
                           {v.comment && <div className="text-[10px] text-muted-foreground mt-1 line-clamp-1" title={v.comment}>{v.comment}</div>}
                        </td>
                        <td className="px-4 py-3 text-xs min-w-[120px]">
                          <div className="space-y-1">
                            <div className="flex items-center justify-between gap-2">
                              <span className="text-[10px] text-muted-foreground uppercase font-medium">Uptime:</span>
                              <span className={`font-mono font-semibold px-1 py-0.5 rounded text-[10px] ${
                                getLiveSisaUptime(v) === "Habis" ? "text-red-400 bg-red-400/10 border border-red-400/20" : "text-primary"
                              }`}>{getLiveSisaUptime(v)}</span>
                            </div>
                             <div className="flex items-center justify-between gap-2">
                               <span className="text-[10px] text-muted-foreground uppercase font-medium">Aktif:</span>
                               <span className={`font-mono font-semibold px-1 py-0.5 rounded text-[10px] ${
                                 getLiveSisaValiditas(v) === "Habis" ? "text-red-400 bg-red-400/10 border border-red-400/20" : "text-muted-foreground"
                               }`}>{getLiveSisaValiditas(v)}</span>
                             </div>
                          </div>
                        </td>


                        <td className="px-4 py-3 text-right font-medium">{fmt(v.price)}</td>
                        <td className="px-4 py-3 text-center"><VoucherStatusBadge status={v.status} /></td>
                        {/* Kolom Login Pertama — menggunakan session_start_time dari backend */}
                        <td className="px-4 py-3 text-xs min-w-[120px]">
                          {v.session_start_time ? (
                            <div className="space-y-0.5">
                              <div className="font-semibold text-green-400">
                                {new Date(v.session_start_time).toLocaleDateString("id-ID", { day: "2-digit", month: "short", year: "numeric" })}
                              </div>
                              <div className="text-[10px] text-muted-foreground font-mono">
                                {new Date(v.session_start_time).toLocaleTimeString("id-ID", { hour: "2-digit", minute: "2-digit", second: "2-digit" })}
                              </div>
                            </div>
                          ) : (
                            <span className="text-muted-foreground/40 text-[10px] italic">Belum login</span>
                          )}
                        </td>
                        <td className="px-4 py-3 text-xs text-muted-foreground">{fmtDt(v.created_at)}</td>
                        <td className="px-4 py-3">
                          <div className="flex gap-1 justify-center">
                            {/* Tombol toggle hanya untuk voucher yang bukan expired */}
                            {v.status === "disabled" ? (
                              <button onClick={() => handleToggleStatus(v)} className="text-[10px] px-2 py-1 rounded border border-green-500/30 text-green-400 hover:bg-green-500/10" title="Aktifkan Kembali">
                                <CheckCircle className="w-3 h-3" />
                              </button>
                            ) : v.status !== "expired" ? (
                              <button onClick={() => handleToggleStatus(v)} className="text-[10px] px-2 py-1 rounded border border-orange-500/30 text-orange-400 hover:bg-orange-500/10" title="Nonaktifkan Sementara">
                                <Ban className="w-3 h-3" />
                              </button>
                            ) : null}
                            <button onClick={() => setTransferVoucher(v)} className="text-[10px] px-2 py-1 rounded border border-blue-500/30 text-blue-400 hover:bg-blue-500/10" title="Transfer Mikrotik">
                              <ArrowRightLeft className="w-3 h-3" />
                            </button>
                            <button onClick={() => setEditVoucher({...v})} className="text-[10px] px-2 py-1 rounded border border-border text-foreground hover:bg-muted" title="Edit">
                              <Edit className="w-3 h-3" />
                            </button>
                            <button onClick={() => {
                               if(confirm(`Hapus voucher ${v.username}?`)) {
                                 api.delete(`/hotspot-vouchers/${v.id}`).then(()=>fetchVouchers());
                               }
                            }} className="text-[10px] px-2 py-1 rounded border border-red-500/30 text-red-400 hover:bg-red-500/10" title="Hapus">
                              <Trash2 className="w-3 h-3" />
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}

        {activeTab === "sales" && (
          <div className="space-y-4">
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
              <SummaryCard icon={ShoppingCart} label="Total Transaksi" value={totalCountLocal} color="bg-blue-500/20 text-blue-400" />
              <SummaryCard icon={TrendingUp} label="Transaksi Hari Ini" value={todayStats.length} color="bg-purple-500/20 text-purple-400" />
              <SummaryCard icon={Activity} label="Pendapatan Hari Ini" value={fmt(todayRevenue)} color="bg-orange-500/20 text-orange-400" />
              <SummaryCard icon={RpIcon} label="Total Pendapatan" value={fmt(totalRevenueLocal)} color="bg-green-500/20 text-green-400" />
            </div>

            <div className="flex justify-end">
              <Button variant="outline" size="sm" className="gap-2 rounded-sm" onClick={fetchSales} disabled={salesLoading}>
                <RefreshCw className={`w-4 h-4 ${salesLoading ? "animate-spin" : ""}`} /> Refresh
              </Button>
            </div>

            <div className="bg-card border border-border rounded-lg overflow-hidden">
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="bg-muted/40 text-xs uppercase tracking-widest text-muted-foreground">
                    <tr>
                      <th className="px-4 py-3 text-left">Username Voucher</th>
                      <th className="px-4 py-3 text-right">Nominal</th>
                      <th className="px-4 py-3 text-left">Router</th>
                      <th className="px-4 py-3 text-left">Waktu Transaksi</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border">
                    {salesLoading ? (
                      <tr><td colSpan={4} className="py-12 text-center text-muted-foreground">
                        <Loader2 className="w-6 h-6 animate-spin mx-auto mb-2" />Memuat laporanâ€¦
                      </td></tr>
                    ) : sales.length === 0 ? (
                      <tr><td colSpan={4} className="py-12 text-center text-muted-foreground">
                        <BarChart2 className="w-8 h-8 mx-auto mb-2 opacity-20" />
                        <p className="text-sm">Belum ada data penjualan</p>
                      </td></tr>
                    ) : sales.map((s, i) => (
                      <tr key={s.id || i} className="hover:bg-muted/30 transition-colors">
                        <td className="px-4 py-3 font-mono font-semibold text-primary">{s.username}</td>
                        <td className="px-4 py-3 text-right font-semibold text-green-400">{fmt(s.price)}</td>
                        <td className="px-4 py-3 text-xs text-muted-foreground">{s.device_name || "—"}</td>
                        <td className="px-4 py-3 text-xs text-muted-foreground">{fmtDt(s.created_at)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}

        {activeTab === "packages" && (
          <div className="bg-card border border-border rounded-lg p-5">
            <h2 className="text-lg font-semibold mb-1">Paket Layanan Hotspot</h2>
            <p className="text-xs text-muted-foreground mb-4">Paket yang anda buat di sini akan otomatis muncul di Halaman Login Hotspot.</p>
            <PackagesTab packages={packages} onRefresh={loadPackages} deviceId={selectedDevice} defaultServiceType="hotspot" />
          </div>
        )}

        {activeTab === "generator" && (
          <div className="grid grid-cols-1 lg:grid-cols-4 gap-4">
            <div className="bg-card border border-border rounded-lg p-5 lg:col-span-1 flex flex-col gap-4 h-fit">
              <div>
                <h2 className="text-sm font-semibold flex items-center gap-2 mb-0.5"><RpIcon className="w-4 h-4 text-primary" /> Generator Setup</h2>
                <p className="text-xs text-muted-foreground">Atur parameter batch voucher fisik</p>
              </div>

              <div className="space-y-1.5">
                <Label className="text-xs text-muted-foreground">Jumlah Voucher (1â€“100)</Label>
                <Input type="number" min={1} max={100} value={form.count}
                  onChange={e => setForm({ ...form, count: parseInt(e.target.value) || 0 })}
                  className="h-9 text-sm rounded-sm" />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1.5">
                  <Label className="text-xs text-muted-foreground">Prefix</Label>
                  <Input value={form.prefix} onChange={e => setForm({ ...form, prefix: e.target.value.toUpperCase() })} className="h-9 text-sm rounded-sm" />
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs text-muted-foreground">Length</Label>
                  <Input type="number" min={4} max={12} value={form.length}
                    onChange={e => setForm({ ...form, length: parseInt(e.target.value) || 4 })} className="h-9 text-sm rounded-sm" />
                </div>
              </div>

              <div className="space-y-1.5">
                <Label className="text-xs text-muted-foreground flex items-center gap-2">
                  Paket Layanan
                  <span className="text-[9px] px-1.5 py-0.5 rounded bg-green-500/10 text-green-400 border border-green-500/20 font-semibold">RADIUS DB</span>
                </Label>
                <Select value={form.profile} onValueChange={v => {
                  const pkg = packages.find(p => p.service_type === "hotspot" && p.name === v);
                  if (pkg) {
                    setForm({ 
                      ...form, 
                      profile: v, 
                      price: String(pkg.price || ""), 
                      uptime_limit: pkg.uptime_limit || "", 
                      validity: pkg.validity || "" 
                    });
                  } else {
                    setForm({ ...form, profile: v });
                  }
                }}>
                  <SelectTrigger className="rounded-sm bg-background h-9 text-sm"><SelectValue placeholder="Pilih Paket Hotspot..." /></SelectTrigger>
                  <SelectContent>
                    {packages.filter(p => p.service_type === "hotspot").length === 0 ? (
                      <SelectItem value="__empty__" disabled>Belum ada paket — tambah di tab "Paket Layanan"</SelectItem>
                    ) : (
                      packages.filter(p => p.service_type === "hotspot").map(p => (
                        <SelectItem key={p.id} value={p.name}>
                          {p.name} — Rp{parseInt(p.price || 0).toLocaleString("id-ID")}
                        </SelectItem>
                      ))
                    )}
                  </SelectContent>
                </Select>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1.5">
                  <Label className="text-xs text-muted-foreground">Waktu Pakai</Label>
                  <Input value={form.uptime_limit} onChange={e => setForm({ ...form, uptime_limit: e.target.value })} className="h-9 text-sm rounded-sm" placeholder="1h 30m / 45m" />
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs text-muted-foreground">Masa Berlaku</Label>
                  <Input value={form.validity} onChange={e => setForm({ ...form, validity: e.target.value })} className="h-9 text-sm rounded-sm" placeholder="1d / 24h" />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1.5">
                  <Label className="text-xs text-muted-foreground">Harga (Rp)</Label>
                  <Input value={form.price} onChange={e => setForm({ ...form, price: e.target.value })} className="h-9 text-sm rounded-sm" />
                </div>
              </div>

              <Button onClick={handleGenerate} disabled={generating || isViewer || !selectedDevice} className="w-full mt-2 rounded-sm gap-2">
                {generating ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />}
                Generate {form.count} Voucher
              </Button>
            </div>

            <div className="bg-card border border-border rounded-lg lg:col-span-3 flex flex-col min-h-[500px]">
              <div className="p-4 border-b border-border flex justify-between items-center bg-muted/20 rounded-t-lg">
                <h2 className="text-sm font-semibold">Papan Cetak Voucher</h2>
                <Button onClick={() => { if (!generatedVouchers.length) return toast.info("Belum ada voucher"); window.print(); }}
                  variant="outline" size="sm" className="gap-2 rounded-sm" disabled={!generatedVouchers.length}>
                  <Printer className="w-4 h-4" /> Cetak
                </Button>
              </div>
              <div className="p-4 flex-1 bg-neutral-100 dark:bg-neutral-900 overflow-auto rounded-b-lg">
                {generatedVouchers.length === 0 ? (
                  <div className="h-full flex flex-col items-center justify-center text-muted-foreground min-h-[400px]">
                    <RpIcon className="w-12 h-12 mb-3 opacity-20" />
                    <p className="text-sm">Generate voucher di panel kiri untuk cetak fisik</p>
                  </div>
                ) : (
                  <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-3" id="print-area">
                    {generatedVouchers.map((v, i) => (
                      <div key={i} className="bg-white dark:bg-black text-black dark:text-white border-2 border-black dark:border-white rounded p-3 shadow-sm flex flex-col print:break-inside-avoid print:border-black print:text-black">
                        <div className="text-center font-bold text-sm tracking-widest border-b-2 border-dashed border-black dark:border-white pb-1 mb-2">HOTSPOT</div>
                        <div className="flex-1 flex flex-col items-center justify-center mb-2">
                          <span className="text-[10px] uppercase tracking-wider mb-0.5 opacity-80">Kode / Username</span>
                          <span className="text-lg font-mono font-bold leading-tight tracking-tight">{v.username}</span>
                          <span className="text-[10px] uppercase tracking-wider mt-1.5 opacity-80">Password</span>
                          <span className="text-sm font-mono font-bold leading-tight">{v.password}</span>
                        </div>
                        <div className="flex justify-between items-end border-t border-black dark:border-white pt-1.5 mt-auto text-[9px]">
                          <div className="flex flex-col">
                            <span className="font-semibold uppercase truncate">Uptime: {v.uptime_limit}</span>
                            <span className="font-semibold uppercase truncate">Valid: {v.validity}</span>
                          </div>
                          <div className="font-bold whitespace-nowrap">{fmt(v.price)}</div>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

      </div>

      <style dangerouslySetInnerHTML={{ __html: `
        @media print {
          body * { visibility: hidden; }
          #print-area, #print-area * { visibility: visible; }
          #print-area { position: absolute; left: 0; top: 0; width: 100%; display: grid !important; grid-template-columns: repeat(4, 1fr) !important; gap: 10px !important; padding: 10px; background: white !important; }
        }
      `}} />
    </div>
  );
}
