import { useState, useEffect, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import api from "@/lib/api";
import { useTheme } from "@/context/ThemeContext";
import { Plus, Trash2, Server, Wifi, WifiOff, Pencil, Zap, Monitor, Radio, AlertTriangle, Shield, Lock, Network, Tag, Globe, MapPin, Info, Cpu, User } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { toast } from "sonner";

export default function DevicesPage() {
  const { theme } = useTheme();
  const isCyber = theme === "cyber";
  const navigate = useNavigate();
  const [devices, setDevices] = useState([]);
  const [loading, setLoading] = useState(true);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [testing, setTesting] = useState("");
  const [form, setForm] = useState({
    name: "", ip_address: "", winbox_address: "",
    api_mode: "api", api_username: "admin", api_password: "",
    api_port: "", use_https: false, api_ssl: true, api_plaintext_login: true,
    description: "", device_type: "MikroTik"
  });

  const fetchDevices = useCallback(async () => {
    try {
      const r = await api.get("/devices");
      setDevices(r.data);
    } catch (e) { toast.error("Failed to fetch devices"); }
    setLoading(false);
  }, []);

  useEffect(() => { fetchDevices(); }, [fetchDevices]);

  const openAdd = () => {
    setEditing(null);
    setForm({ name: "", ip_address: "", winbox_address: "", api_mode: "api", api_username: "admin", api_password: "", api_port: "", use_https: false, api_ssl: true, api_plaintext_login: true, description: "", device_type: "MikroTik" });
    setDialogOpen(true);
  };

  const openEdit = (d) => {
    setEditing(d);
    setForm({
      name: d.name, ip_address: d.ip_address || "",
      winbox_address: d.winbox_address || "",
      api_mode: d.api_mode || "rest", api_username: d.api_username || "admin", api_password: "",
      api_port: d.api_port || "",
      use_https: d.use_https || false,
      api_ssl: d.api_ssl !== undefined ? d.api_ssl : true,
      api_plaintext_login: d.api_plaintext_login !== undefined ? d.api_plaintext_login : true,
      description: d.description || "",
      device_type: d.device_type || "MikroTik",
    });
    setDialogOpen(true);
  };

  const handleSave = async () => {
    try {
      const apiPort = form.api_port ? parseInt(form.api_port) : null;
      const data = { ...form, api_port: apiPort, use_https: form.use_https };
      // winbox_address: kirim null jika kosong (bukan string kosong)
      if (!data.winbox_address || !data.winbox_address.trim()) data.winbox_address = null;
      else data.winbox_address = data.winbox_address.trim();
      if (editing) {
        if (!data.api_password) delete data.api_password;
        await api.put(`/devices/${editing.id}`, data);
        toast.success("Device updated");
      } else {
        await api.post("/devices", data);
        toast.success("Device added & polling started");
      }
      setDialogOpen(false);
      fetchDevices();
    } catch (e) { toast.error(e.response?.data?.detail || "Failed"); }
  };

  const handleDelete = async (id, name) => {
    if (!window.confirm(`Delete device "${name}"?`)) return;
    try {
      await api.delete(`/devices/${id}`);
      toast.success("Device deleted");
      fetchDevices();
    } catch (e) { toast.error(e.response?.data?.detail || "Failed"); }
  };

  const handleTestApi = async (id) => {
    setTesting(id + "_api");
    try {
      const r = await api.post(`/devices/${id}/test-api`);
      if (r.data.success) {
        toast.success(`API OK — Identity: ${r.data.identity}`);
      } else {
        toast.error(`API Failed: ${r.data.error || "connection error"}`);
      }
    } catch (e) { toast.error("API test failed"); }
    setTesting("");
  };


  const handlePoll = async (id) => {
    setTesting(id + "_poll");
    try {
      const r = await api.post(`/devices/${id}/poll`);
      toast.success(r.data.reachable ? "Poll OK — device online" : "Poll completed — device offline");
      fetchDevices();
    } catch (e) { toast.error("Poll failed"); }
    setTesting("");
  };

  return (
    <div className="space-y-4 pb-16" data-testid="devices-page">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <h1 className={`text-xl sm:text-2xl md:text-3xl font-bold tracking-tight ${ isCyber ? "gradient-text font-mono" : "" }`}>
            {isCyber ? "> Devices" : "Devices"}
          </h1>
          <p className={`text-xs sm:text-sm ${ isCyber ? "font-mono text-[hsl(185,100%,35%)]" : "text-muted-foreground" }`}>Manage MikroTik devices — polling via REST API</p>
        </div>
        <div className="flex gap-2">
          <Button onClick={openAdd} size="sm" className="rounded-sm gap-2" data-testid="add-device-btn"><Plus className="w-4 h-4" /> <span className="hidden sm:inline">Add Device</span></Button>
        </div>
      </div>



      {loading ? (
        <div className="text-center text-muted-foreground py-12 text-sm">Loading devices...</div>
      ) : devices.length === 0 ? (
        <div className="bg-card border border-border rounded-sm p-8 sm:p-12 text-center"><Server className="w-10 h-10 sm:w-12 sm:h-12 mx-auto mb-3 text-muted-foreground/30" /><p className="text-sm text-muted-foreground">No devices configured</p></div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3 sm:gap-4">
          {devices.map(d => (
            <div key={d.id} className={`p-3 sm:p-5 transition-all ${ isCyber ? "glass-card hover:border-[rgba(0,230,118,0.3)]" : "bg-card border border-border rounded-sm hover:border-border/80" }`} data-testid={`device-card-${d.name}`}>
              <div className="flex items-start justify-between mb-3 sm:mb-4">
                <div className="flex items-center gap-2 sm:gap-3">
                  <div className={`w-8 h-8 sm:w-10 sm:h-10 rounded-sm flex items-center justify-center ${d.status === "online" ? "bg-green-500/10" : "bg-red-500/10"}`}>
                    {d.status === "online" ? <Wifi className="w-4 h-4 sm:w-5 sm:h-5 text-green-500" /> : <WifiOff className="w-4 h-4 sm:w-5 sm:h-5 text-red-500" />}
                  </div>
                  <div><h3 className="text-xs sm:text-sm font-semibold">{d.name}</h3><p className="text-[10px] sm:text-xs text-muted-foreground font-mono">{d.ip_address}</p></div>
                </div>
                <Badge className={`rounded-sm text-[10px] sm:text-xs border ${d.status === "online" ? "bg-green-500/10 text-green-500 border-green-500/20" : "bg-red-500/10 text-red-500 border-red-500/20"}`}>{d.status || "?"}</Badge>
              </div>
              <div className="space-y-1.5 sm:space-y-2 text-[10px] sm:text-xs">
                <div className="flex justify-between"><span className="text-muted-foreground">API Mode</span><Badge variant="outline" className="rounded-sm text-[10px]">{d.api_mode === "api" ? "ROS6" : "ROS7"}</Badge></div>
                {d.ros_version && <div className="flex justify-between"><span className="text-muted-foreground">RouterOS</span><span className="font-mono">v{d.ros_version}</span></div>}
                {d.uptime && <div className="flex justify-between"><span className="text-muted-foreground">Uptime</span><span className="font-mono text-[10px]">{d.uptime}</span></div>}
                {typeof d.cpu_load === "number" && d.status === "online" && (
                  <div className="flex justify-between items-center"><span className="text-muted-foreground">CPU</span><div className="flex items-center gap-2"><div className="w-12 sm:w-16 h-1.5 bg-secondary rounded-full overflow-hidden"><div className="h-full rounded-full" style={{ width: `${d.cpu_load}%`, backgroundColor: d.cpu_load > 80 ? "#ef4444" : d.cpu_load > 50 ? "#f59e0b" : "#10b981" }} /></div><span className="font-mono w-6 sm:w-8 text-right">{d.cpu_load}%</span></div></div>
                )}
              </div>
              <div className="mt-3 sm:mt-4 pt-2 sm:pt-3 border-t border-border/50 flex flex-wrap gap-1">
                <Button variant="outline" size="sm" className="text-[10px] sm:text-xs gap-1 h-6 sm:h-7 rounded-sm px-2" onClick={() => handleTestApi(d.id)} disabled={testing === d.id + "_api"} data-testid={`test-api-${d.name}`}>
                  <Zap className="w-3 h-3" />{testing === d.id + "_api" ? "..." : "Test API"}
                </Button>


                <Button variant="ghost" size="sm" className="text-[10px] sm:text-xs gap-1 h-6 sm:h-7 rounded-sm px-2" onClick={() => openEdit(d)} data-testid={`edit-device-${d.name}`}><Pencil className="w-3 h-3" /></Button>
                <Button variant="ghost" size="sm" className="text-[10px] sm:text-xs gap-1 h-6 sm:h-7 rounded-sm px-2 text-destructive" onClick={() => handleDelete(d.id, d.name)} data-testid={`delete-device-${d.name}`}><Trash2 className="w-3 h-3" /></Button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* ════ PROFESSIONAL 2-COLUMN DEVICE FORM DIALOG ════ */}
      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent
          className="rounded-xl bg-[#0f172a] border border-slate-700/60 shadow-2xl w-full max-w-4xl p-0 overflow-hidden"
          data-testid="device-dialog"
        >
          {/* ── Header Bar ── */}
          <div className="flex items-center gap-3 px-6 py-4 border-b border-slate-700/60 bg-slate-800/50">
            <div className="w-8 h-8 rounded-lg bg-blue-500/10 border border-blue-500/20 flex items-center justify-center flex-shrink-0">
              <Server className="w-4 h-4 text-blue-400" />
            </div>
            <div className="min-w-0">
              <h2 className="text-base font-bold text-slate-100">{editing ? "Edit Device" : "Tambah Perangkat Baru"}</h2>
              <p className="text-[11px] text-slate-500">Konfigurasi koneksi MikroTik via REST API (ROS 7+) atau API Protocol (ROS 6+)</p>
            </div>
          </div>

          {/* ── Body: 2-Column Cockpit Layout ── */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-0 divide-y md:divide-y-0 md:divide-x divide-slate-700/60">

            {/* ═══ KOLOM KIRI: Identitas Jaringan ═══ */}
            <div className="p-6 space-y-5 flex flex-col">
              <div className="flex items-center gap-2.5 pb-2 border-b border-white/5">
                <Network className="w-3.5 h-3.5 text-cyan-400" />
                <span className="text-[11px] font-bold text-slate-300 uppercase tracking-widest">Identitas Jaringan</span>
              </div>

              <div className="space-y-4 flex-1">
                {/* Nama Device */}
                <div className="space-y-1.5 font-sans">
                  <Label className="h-5 flex items-center gap-2 text-[11px] font-medium text-slate-400">
                    <Tag className="w-3 h-3 text-slate-500" /> Nama Perangkat *
                  </Label>
                  <Input
                    value={form.name}
                    onChange={e => setForm({ ...form, name: e.target.value })}
                    className="h-10 rounded-lg bg-slate-800/40 border-slate-700/50 text-sm text-slate-100 placeholder:text-slate-600 focus:border-blue-500/50 focus:bg-slate-800/80 transition-all shadow-inner"
                    placeholder="Contoh: Router-Core-Pusat"
                    data-testid="device-form-name"
                  />
                </div>

                {/* IP Address & Winbox dalam 1 baris */}
                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-1.5">
                    <Label className="h-5 flex items-center gap-2 text-[11px] font-medium text-slate-400">
                      <Globe className="w-3 h-3 text-slate-500" /> IP Address API *
                    </Label>
                    <Input
                      value={form.ip_address}
                      onChange={e => setForm({ ...form, ip_address: e.target.value })}
                      className="h-10 rounded-lg bg-slate-800/40 border-slate-700/50 font-mono text-xs text-slate-100 placeholder:text-slate-600 focus:border-blue-500/50 focus:bg-slate-800/80 transition-all shadow-inner"
                      placeholder="192.168.1.1"
                      data-testid="device-form-ip"
                    />
                  </div>
                  <div className="space-y-1.5">
                    <Label className="h-5 flex items-center gap-2 text-[11px] font-medium text-slate-400">
                      <Monitor className="w-3 h-3 text-slate-500" /> Winbox Remote 
                    </Label>
                    <Input
                      value={form.winbox_address}
                      onChange={e => setForm({ ...form, winbox_address: e.target.value })}
                      className="h-10 rounded-lg bg-slate-800/40 border-slate-700/50 font-mono text-xs text-slate-100 placeholder:text-slate-600 focus:border-blue-500/50 focus:bg-slate-800/80 transition-all shadow-inner"
                      placeholder="IP/DDNS (opsional)"
                      data-testid="device-form-winbox-address"
                    />
                  </div>
                </div>

                {/* Deskripsi */}
                <div className="space-y-1.5">
                  <Label className="h-5 flex items-center gap-2 text-[11px] font-medium text-slate-400">
                    <MapPin className="w-3 h-3 text-slate-500" /> Deskripsi / Lokasi
                  </Label>
                  <Input
                    value={form.description}
                    onChange={e => setForm({ ...form, description: e.target.value })}
                    className="h-10 rounded-lg bg-slate-800/40 border-slate-700/50 text-sm text-slate-100 placeholder:text-slate-600 focus:border-blue-500/50 focus:bg-slate-800/80 transition-all shadow-inner"
                    placeholder="Gedung A - Lantai 2, Kantor Cabang"
                    data-testid="device-form-description"
                  />
                </div>
              </div>

              {/* Tips Section — repositioned to stay at bottom and balanced */}
              <div className="mt-4 p-3 rounded-lg bg-blue-500/5 border border-blue-500/10 flex items-start gap-2 items-center">
                <Info className="w-3.5 h-3.5 text-blue-400 flex-shrink-0" />
                <p className="text-[10px] text-slate-500 italic leading-snug">
                  Gunakan IP Static untuk kestabilan monitoring. Pastikan port API (8728/8729/80/443) terbuka di firewall router.
                </p>
              </div>
            </div>

            {/* ═══ KOLOM KANAN: Keamanan & API ═══ */}
            <div className="p-6 space-y-5">
              <div className="flex items-center gap-2.5 pb-2 border-b border-white/5">
                <Shield className="w-3.5 h-3.5 text-amber-400" />
                <span className="text-[11px] font-bold text-slate-300 uppercase tracking-widest">Keamanan & Akses API</span>
              </div>

              {/* API Mode */}
              <div className="space-y-1.5">
                <Label className="h-5 flex items-center gap-2 text-[11px] font-medium text-slate-400">
                  <Cpu className="w-3 h-3 text-slate-500" /> Mode API (Versi RouterOS)
                </Label>
                <Select value={form.api_mode} onValueChange={v => setForm({ ...form, api_mode: v })}>
                  <SelectTrigger className="h-10 rounded-lg bg-slate-800/50 border-slate-700/60 text-sm text-slate-100 focus:border-amber-500/50 focus:bg-slate-800/90 transition-all shadow-inner" data-testid="device-form-api-mode">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent className="bg-slate-800 border-slate-700">
                    <SelectItem value="api">⚡ API Protocol (Port 8728) — ROS 6 & 7</SelectItem>
                    <SelectItem value="rest">🌐 REST API (RouterOS 7.1+ saja)</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              {/* Username & Password */}
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1.5">
                  <Label className="h-5 flex items-center gap-2 text-[11px] font-medium text-slate-400">
                    <User className="w-3 h-3 text-slate-500" /> Username API
                  </Label>
                  <Input
                    value={form.api_username}
                    onChange={e => setForm({ ...form, api_username: e.target.value })}
                    className="h-10 rounded-lg bg-slate-800/50 border-slate-700/60 text-sm text-slate-100 focus:border-amber-500/50 focus:bg-slate-800/90 transition-all shadow-inner"
                    data-testid="device-form-api-username"
                  />
                </div>
                <div className="space-y-1.5">
                  <Label className="h-5 flex items-center gap-2 text-[11px] font-medium text-slate-400">
                    <Lock className="w-3 h-3 text-slate-500" /> Password API
                  </Label>
                  <Input
                    type="password"
                    value={form.api_password}
                    onChange={e => setForm({ ...form, api_password: e.target.value })}
                    className="h-10 rounded-lg bg-slate-800/50 border-slate-700/60 text-sm text-slate-100 focus:border-amber-500/50 focus:bg-slate-800/90 transition-all shadow-inner"
                    placeholder={editing ? "(tidak berubah)" : ""}
                    data-testid="device-form-api-password"
                  />
                </div>
              </div>

              {/* Port & Protocol Config — conditional per API mode */}
              {form.api_mode === "api" ? (
                <div className="p-3 rounded-lg bg-slate-800/40 border border-slate-700/40 space-y-2.5">
                  <span className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">Konfigurasi Port ROS6</span>
                  <div className="grid grid-cols-2 gap-2.5">
                    <div className="space-y-1">
                      <Label className="text-[11px] font-medium text-slate-400">Enkripsi SSL</Label>
                      <Select value={form.api_ssl ? "true" : "false"} onValueChange={v => setForm({ ...form, api_ssl: v === "true" })}>
                        <SelectTrigger className="h-9 rounded-lg bg-slate-800 border-slate-700/60 text-xs text-slate-100" data-testid="device-form-api-ssl">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent className="bg-slate-800 border-slate-700">
                          <SelectItem value="false">🔓 Plain (Port 8728)</SelectItem>
                          <SelectItem value="true">🔒 SSL (Port 8729)</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                    <div className="space-y-1">
                      <Label className="text-[11px] font-medium text-slate-400">Port Custom</Label>
                      <Input
                        type="number"
                        value={form.api_port}
                        onChange={e => setForm({ ...form, api_port: e.target.value })}
                        className="h-9 rounded-lg bg-slate-800 border-slate-700/60 font-mono text-xs text-slate-100 focus:border-amber-500/50"
                        placeholder={form.api_ssl ? "8729 (Default)" : "8728 (Default)"}
                        data-testid="device-form-api-port"
                      />
                    </div>
                  </div>
                  <p className="text-[10px] text-slate-600">Kosongkan port untuk menggunakan default ({form.api_ssl ? "8729" : "8728"}). Isi hanya jika port diubah di IP › Services MikroTik.</p>
                </div>
              ) : (
                <div className="p-3 rounded-lg bg-slate-800/40 border border-slate-700/40 space-y-2.5">
                  <span className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">Konfigurasi REST API ROS7</span>
                  <div className="grid grid-cols-2 gap-2.5">
                    <div className="space-y-1">
                      <Label className="text-[11px] font-medium text-slate-400">Protokol</Label>
                      <Select value={form.use_https ? "https" : "http"} onValueChange={v => setForm({ ...form, use_https: v === "https" })}>
                        <SelectTrigger className="h-9 rounded-lg bg-slate-800 border-slate-700/60 text-xs text-slate-100" data-testid="device-form-protocol">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent className="bg-slate-800 border-slate-700">
                          <SelectItem value="http">HTTP (www)</SelectItem>
                          <SelectItem value="https">HTTPS (www-ssl)</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                    <div className="space-y-1">
                      <Label className="text-[11px] font-medium text-slate-400">Port WWW</Label>
                      <Input
                        type="number"
                        value={form.api_port}
                        onChange={e => setForm({ ...form, api_port: e.target.value })}
                        className="h-9 rounded-lg bg-slate-800 border-slate-700/60 font-mono text-xs text-slate-100 focus:border-amber-500/50"
                        placeholder={form.use_https ? "443 (Default)" : "80 (Default)"}
                        data-testid="device-form-api-port"
                      />
                    </div>
                  </div>
                  <p className="text-[10px] text-slate-600">Kosongkan port untuk default ({form.use_https ? "443" : "80"}). Isi jika port {form.use_https ? "www-ssl" : "www"} di IP › Services sudah diubah.</p>
                </div>
              )}

              {/* Tips Info Box */}
              <div className="p-3 rounded-lg bg-blue-500/5 border border-blue-500/15 flex gap-2.5">
                <AlertTriangle className="w-4 h-4 text-blue-400/70 flex-shrink-0 mt-0.5" />
                <div className="text-[10px] text-slate-500 leading-relaxed">
                  <strong className="text-slate-400">Quick Setup MikroTik:</strong><br />
                  Pastikan user <code className="bg-slate-700/60 px-1 rounded text-slate-300">{form.api_username || "admin"}</code> memiliki policy <code className="bg-slate-700/60 px-1 rounded text-slate-300">api</code>
                  {form.api_mode === "rest" && <> dan <code className="bg-slate-700/60 px-1 rounded text-slate-300">rest-api</code></>} di IP › Services MikroTik Anda.
                </div>
              </div>
            </div>
          </div>

          {/* ── Footer ── */}
          <div className="flex items-center justify-between px-6 py-3 border-t border-slate-700/60 bg-slate-800/30">
            <div className="text-[10px] text-slate-600">
              {editing ? `ID: ${editing.id?.slice(0, 8)}...` : "Semua field bertanda * wajib diisi"}
            </div>
            <div className="flex gap-2">
              <Button
                variant="outline"
                onClick={() => setDialogOpen(false)}
                className="h-8 px-4 rounded-lg text-xs border-slate-700 text-slate-400 hover:bg-slate-800"
                data-testid="device-form-cancel"
              >
                Batal
              </Button>
              <Button
                onClick={handleSave}
                className="h-8 px-5 rounded-lg text-xs bg-blue-600 hover:bg-blue-700 text-white font-semibold"
                data-testid="device-form-save"
              >
                {editing ? "✏️ Perbarui Device" : "➕ Tambah Device"}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
