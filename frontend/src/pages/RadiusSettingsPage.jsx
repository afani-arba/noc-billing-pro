import { useState, useEffect } from "react";
import api from "@/lib/api";
import { Radio, Loader2, CheckCircle2, XCircle, ShieldCheck, RefreshCw, Zap, Trash2, List, Save, Settings2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { toast } from "sonner";
import { useAuth } from "@/App";

// ─── RADIUS Status Badge ───────────────────────────────────────────────────────
const RadiusBadge = ({ enabled, loading }) => {
  if (loading) return (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold border bg-muted text-muted-foreground border-border">
      <Loader2 className="w-3 h-3 animate-spin" /> Memeriksa…
    </span>
  );
  return enabled
    ? <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold border bg-green-500/10 text-green-400 border-green-500/20"><CheckCircle2 className="w-3 h-3" /> RADIUS Aktif</span>
    : <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold border bg-red-500/10 text-red-400 border-red-500/20"><XCircle className="w-3 h-3" /> RADIUS Tidak Aktif</span>;
};

export default function RadiusSettingsPage() {
  const { user } = useAuth();
  const isViewer = user?.role === "viewer" || user?.role === "helpdesk";

  // Devices & Monitoring State
  const [devices, setDevices] = useState([]);
  const [loadingDevices, setLoadingDevices] = useState(true);
  const [devRadiusMap, setDevRadiusMap] = useState({});
  const [selectedDevice, setSelectedDevice] = useState("");

  // RADIUS Setup State
  const [radiusStatus, setRadiusStatus] = useState(null);
  const [radiusLoading, setRadiusLoading] = useState(false);
  const [pushSettings, setPushSettings] = useState({
    radius_ip: "", secret: "", server_profile: "",
  });
  const [hsProfiles, setHsProfiles] = useState([]);
  const [pushingRadius, setPushingRadius] = useState(false);
  const [pushLog, setPushLog] = useState([]);

  // Walled Garden State
  const [wgEntries, setWgEntries] = useState([]);
  const [wgDefaults, setWgDefaults] = useState([]);
  const [wgLoading, setWgLoading] = useState(false);
  const [wgPushing, setWgPushing] = useState(false);
  const [wgLog, setWgLog] = useState([]);
  const [wgCustom, setWgCustom] = useState("");

  const fetchRadiusStatus = async (devId) => {
    if (!devId) return;
    setRadiusLoading(true);
    try {
      const r = await api.get("/hotspot-radius-status", { params: { device_id: devId } });
      setRadiusStatus(r.data);
    } catch { setRadiusStatus(null); }
    finally { setRadiusLoading(false); }
  };

  const fetchWalledGarden = async (devId) => {
    if (!devId) return;
    setWgLoading(true);
    try {
      const r = await api.get("/hotspot-walled-garden", { params: { device_id: devId } });
      setWgEntries(r.data || []);
    } catch { setWgEntries([]); }
    finally { setWgLoading(false); }
  };

  useEffect(() => {
    setLoadingDevices(true);
    api.get("/devices").then(async r => {
      const allDevs = r.data || [];
      setDevices(allDevs);
      if (allDevs.length > 0) setSelectedDevice(allDevs[0].id);

      const initMap = Object.fromEntries(allDevs.map(d => [d.id, { radius_enabled: null, loading: true }]));
      setDevRadiusMap(initMap);

      await Promise.all(allDevs.map(async d => {
        try {
          const res = await api.get("/hotspot-radius-status", { params: { device_id: d.id } });
          setDevRadiusMap(prev => ({ ...prev, [d.id]: { radius_enabled: res.data?.radius_enabled, loading: false } }));
        } catch {
          setDevRadiusMap(prev => ({ ...prev, [d.id]: { radius_enabled: false, loading: false, error: true } }));
        }
      }));
    }).catch(() => {}).finally(() => setLoadingDevices(false));

    api.get("/hotspot-walled-garden-defaults").then(r => setWgDefaults(r.data || [])).catch(() => {});
  }, []);

  useEffect(() => {
    if (!selectedDevice) { setRadiusStatus(null); setHsProfiles([]); return; }
    fetchRadiusStatus(selectedDevice);
    fetchWalledGarden(selectedDevice);
    
    // Fetch hotspot server profiles
    api.get("/hotspot-server-profiles", { params: { device_id: selectedDevice } })
      .then(r => {
        const profs = r.data || [];
        setHsProfiles(profs);
        if (profs.length > 0 && !pushSettings.server_profile) {
          setPushSettings(prev => ({ ...prev, server_profile: profs[0].name }));
        }
      })
      .catch(() => setHsProfiles([]));
  }, [selectedDevice]);

  const handlePushRadius = async () => {
    if (!selectedDevice) return toast.error("Pilih router terlebih dahulu");
    if (!pushSettings.radius_ip || !pushSettings.secret)
      return toast.error("IP RADIUS dan Secret wajib diisi");
    if (!pushSettings.server_profile)
      return toast.error("Pilih hotspot server profile terlebih dahulu");
      
    setPushingRadius(true);
    setPushLog([]);
    try {
      const r = await api.post("/hotspot-push-radius", {
        device_id: selectedDevice,
        radius_ip: pushSettings.radius_ip,
        secret: pushSettings.secret,
        server_profile: pushSettings.server_profile,
      });
      setPushLog(r.data.steps || []);
      if (r.data.success) {
        toast.success("Konfigurasi RADIUS berhasil di-push ke MikroTik!");
        setPushLog(prev => [...prev, "⏳ Menunggu MikroTik menerapkan konfigurasi..."]);
        await new Promise(res => setTimeout(res, 1200));
        
        setDevRadiusMap(prev => ({ ...prev, [selectedDevice]: { ...prev[selectedDevice], loading: true } }));
        await fetchRadiusStatus(selectedDevice);
        
        try {
          const statusRes = await api.get("/hotspot-radius-status", { params: { device_id: selectedDevice } });
          setDevRadiusMap(prev => ({
            ...prev,
            [selectedDevice]: { radius_enabled: statusRes.data?.radius_enabled, loading: false }
          }));

          setPushLog(prev => prev.map(msg => 
            msg.startsWith("⏳ Menunggu") ? "✅ MikroTik telah menerapkan konfigurasi" : msg
          ));

          if (statusRes.data?.radius_enabled) {
            setPushLog(prev => [...prev, "✅ Verifikasi: RADIUS aktif dan terkonfirmasi dari MikroTik!"]);
          } else {
            setPushLog(prev => [...prev, "⚠️ Verifikasi: MikroTik belum menunjukkan RADIUS aktif. Coba refresh manual."]);
          }
        } catch {
          setDevRadiusMap(prev => ({ ...prev, [selectedDevice]: { ...prev[selectedDevice], loading: false } }));
        }
      } else {
        toast.error("Push RADIUS gagal. Lihat log di bawah.");
      }
    } catch (e) {
      toast.error(e.response?.data?.detail || "Gagal push RADIUS");
    } finally {
      setPushingRadius(false);
    }
  };

  const handlePushWalledGarden = async () => {
    if (!selectedDevice) return toast.error("Pilih router terlebih dahulu");
    setWgPushing(true);
    setWgLog([]);
    const customArr = wgCustom.split("\n").map(h => h.trim()).filter(Boolean);
    try {
      const r = await api.post("/hotspot-push-walled-garden", {
        device_id: selectedDevice,
        entries: null,
        custom_hosts: customArr,
        server: "all",
      });
      setWgLog(r.data.steps || []);
      toast.success(`Selesai! ${r.data.added} domain ditambahkan, ${r.data.skipped} sudah ada.`);
      fetchWalledGarden(selectedDevice);
    } catch (e) {
      toast.error(e.response?.data?.detail || "Gagal push Walled Garden");
    } finally { setWgPushing(false); }
  };

  const handleDeleteWg = async (mtId) => {
    if (!selectedDevice || !mtId) return;
    try {
      await api.delete(`/hotspot-walled-garden/${mtId}`, { params: { device_id: selectedDevice } });
      toast.success("Entry Walled Garden dihapus");
      setWgEntries(prev => prev.filter(e => e[".id"] !== mtId));
    } catch { toast.error("Gagal hapus entry Walled Garden"); }
  };

  return (
    <div className="space-y-6 pb-20">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight flex items-center gap-2">
            <Radio className="w-7 h-7 text-primary" /> RADIUS Server
          </h1>
          <p className="text-sm text-muted-foreground">Setup and monitor Hotspot RADIUS connectivity across routers</p>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 xl:grid-cols-4 gap-4 mb-6">
        {loadingDevices ? (
          <div className="col-span-full h-32 flex items-center justify-center border border-border rounded-lg bg-card text-muted-foreground">
            <Loader2 className="w-6 h-6 animate-spin mr-2" /> Memuat daftar router...
          </div>
        ) : devices.length === 0 ? (
          <div className="col-span-full h-32 flex flex-col items-center justify-center border border-border rounded-lg bg-card text-muted-foreground">
            <p>Belum ada router ditambahkan.</p>
          </div>
        ) : devices.map(dev => {
          const statusMap = devRadiusMap[dev.id] || { loading: true };
          const isActive = dev.id === selectedDevice;
          return (
            <div 
              key={dev.id} 
              onClick={() => setSelectedDevice(dev.id)}
              className={`p-4 rounded-xl border transition-all cursor-pointer flex flex-col gap-2 relative ${
                isActive ? 'border-primary bg-primary/5 ring-1 ring-primary/20' : 'border-border bg-card hover:bg-muted/50'
              }`}
            >
              <div className="flex justify-between items-start">
                <span className="font-semibold text-sm truncate pr-4">{dev.name}</span>
                <RadiusBadge enabled={statusMap.radius_enabled} loading={statusMap.loading} />
              </div>
              <p className="text-[11px] text-muted-foreground font-mono">{dev.host}</p>
            </div>
          )
        })}
      </div>

      {selectedDevice && (
        <div className="space-y-6 animate-in fade-in slide-in-from-bottom-2">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            
            {/* RADIUS Setup */}
            <div className="bg-card border border-border rounded-lg p-5 space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <h2 className="text-sm font-semibold flex items-center gap-2">
                    <Settings2 className="w-4 h-4 text-primary" /> RADIUS Configuration
                  </h2>
                  <p className="text-xs text-muted-foreground mt-0.5">Push konfigurasi RADIUS NOC Sentinel ke MikroTik</p>
                </div>
              </div>

              {radiusStatus && (
                <div className={`rounded-md p-3 text-xs space-y-1 border ${radiusStatus.radius_enabled ? "bg-green-500/5 border-green-500/20" : "bg-amber-500/5 border-amber-500/20"}`}>
                  <p className="font-semibold text-[13px]">{radiusStatus.radius_enabled ? "✅ RADIUS aktif" : "⚠️ RADIUS belum aktif di hotspot profile"}</p>
                  {radiusStatus.radius_enabled && <p className="text-muted-foreground">Hotspot Profile: <span className="text-primary font-mono">{radiusStatus.active_profile || "?"}</span></p>}
                </div>
              )}

              <div className="space-y-3">
                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-1.5">
                    <Label className="text-xs">IP Server Radius</Label>
                    <Input className="h-8 text-xs" placeholder="Contoh: 103.x.x.x" value={pushSettings.radius_ip} onChange={e => setPushSettings({...pushSettings, radius_ip: e.target.value})} />
                  </div>
                  <div className="space-y-1.5">
                    <Label className="text-xs">Radius Secret</Label>
                    <Input className="h-8 text-xs" type="password" placeholder="***" value={pushSettings.secret} onChange={e => setPushSettings({...pushSettings, secret: e.target.value})} />
                  </div>
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs">Target Server Profile Hotspot</Label>
                  <Select value={pushSettings.server_profile} onValueChange={v => setPushSettings({...pushSettings, server_profile: v})}>
                    <SelectTrigger className="h-8 text-xs bg-card"><SelectValue placeholder="Pilih yang aktif..." /></SelectTrigger>
                    <SelectContent>
                      {hsProfiles.length === 0 && <SelectItem value="-">Tidak ada hotspot ditemukan</SelectItem>}
                      {hsProfiles.map((hp) => (
                        <SelectItem key={hp.name || hp['.id']} value={hp.name}>{hp.name}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <p className="text-[10px] text-muted-foreground">NOC Sentinel akan membuat hotspot profile otomatis khusus RADIUS</p>
                </div>

                {pushLog.length > 0 && (
                  <div className="bg-muted/40 p-2 border border-border rounded max-h-32 overflow-auto text-[10px] font-mono space-y-1">
                    {pushLog.map((log, i) => <div key={i}>{log}</div>)}
                  </div>
                )}
                
                <Button className="w-full h-9 mt-4" onClick={handlePushRadius} disabled={pushingRadius || isViewer || hsProfiles.length === 0}>
                  {pushingRadius ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Save className="w-4 h-4 mr-2" />}
                  {pushingRadius ? "Menerapkan ke MikroTik..." : "Push Radius"}
                </Button>
              </div>
            </div>

            {/* Guide Card */}
            <div className="bg-card border border-border rounded-lg p-5">
              <h2 className="text-sm font-semibold flex items-center gap-2 mb-3"><List className="w-4 h-4 text-primary" /> Informasi Walled Garden & RADIUS</h2>
              <div className="text-xs text-muted-foreground space-y-3 leading-relaxed">
                <p>NOC Sentinel Billing dan Voucher Online berintegrasi dengan router Anda menggunakan protokol RADIUS.</p>
                <p><strong>Walled Garden</strong> penting untuk akses pelanggan yang belum login. Dengan melakukan bypass pada Walled Garden, pelanggan dapat:</p>
                <ul className="list-disc pl-4 space-y-1">
                  <li>Mengakses gateway pembayaran Moota</li>
                  <li>Scan QRIS secara mandiri (Midtrans/Tripay)</li>
                  <li>Membuka link pendaftaran yang disediakan NOC Sentinel</li>
                </ul>
                <p>Oleh karena itu, selalu pastikan <code>dst-host</code> mutlak penting telah di push ke MikroTik perangkat Access Point Hotspot Anda.</p>
              </div>
            </div>

            {/* Walled Garden */}
            <div className="lg:col-span-2 bg-card border border-border rounded-lg overflow-hidden">
              <div className="p-4 border-b border-border bg-muted/20 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
                <div>
                  <h2 className="text-sm font-semibold flex items-center gap-2"><ShieldCheck className="w-4 h-4 text-primary" /> Walled Garden</h2>
                  <p className="text-xs text-muted-foreground mt-0.5">Bypass akses sebelum login</p>
                </div>
                <div className="flex gap-2">
                  <Button variant="outline" size="sm" onClick={() => fetchWalledGarden(selectedDevice)} disabled={wgLoading || !selectedDevice}>
                    <RefreshCw className={`w-3.5 h-3.5 ${wgLoading ? "animate-spin" : ""}`} /> Refresh
                  </Button>
                  <Button variant="outline" size="sm" onClick={() => setWgEntries([])} disabled={wgLoading || !selectedDevice || wgEntries.length === 0} title="Lihat Rekomendasi">
                    <List className="w-3.5 h-3.5" /> Reset View
                  </Button>
                  <Button size="sm" onClick={handlePushWalledGarden} disabled={wgPushing || isViewer || !selectedDevice}>
                    {wgPushing ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Zap className="w-3.5 h-3.5" />}
                    Push ke MikroTik
                  </Button>
                </div>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-3 divide-y md:divide-y-0 md:divide-x divide-border">
                <div className="md:col-span-2 max-h-64 overflow-auto">
                  <table className="w-full text-xs">
                    <thead className="bg-muted/30 sticky top-0">
                      <tr>
                        <th className="px-4 py-2 text-left text-muted-foreground">Host / Domain</th>
                        <th className="px-4 py-2 w-8"></th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border">
                      {(wgEntries.length > 0 ? wgEntries : wgDefaults).map((e, i) => (
                        <tr key={e[".id"] || i} className="hover:bg-muted/20">
                          <td className="px-4 py-2 font-mono text-primary flex items-center justify-between">
                            <span>{e["dst-host"] || e["host"] || "-"}</span>
                            {wgEntries.length === 0 && (
                              <span className="text-[9px] bg-yellow-500/10 text-yellow-500 px-1.5 py-0.5 rounded border border-yellow-500/20 italic font-sans uppercase tracking-tighter">Rekomendasi</span>
                            )}
                          </td>
                          <td className="px-4 py-2 text-right">
                            {wgEntries.length > 0 ? (
                              <button onClick={() => handleDeleteWg(e[".id"])} className="text-red-400 hover:text-red-300">
                                <Trash2 className="w-3.5 h-3.5" />
                              </button>
                            ) : (
                              <div className="w-3.5 h-3.5 opacity-20"><Zap className="w-full h-full" /></div>
                            )}
                          </td>
                        </tr>
                      ))}
                      {wgEntries.length === 0 && wgDefaults.length === 0 && (
                        <tr><td colSpan="2" className="px-4 py-8 text-center text-muted-foreground italic">Belum ada data...</td></tr>
                      )}
                    </tbody>
                  </table>
                </div>
                <div className="p-4 space-y-3 bg-muted/5">
                  <div className="space-y-1.5">
                    <Label className="text-xs text-muted-foreground">Custom Domain Tambahan</Label>
                    <Textarea value={wgCustom} onChange={e => setWgCustom(e.target.value)} rows={4} placeholder="Satu domain per baris" className="text-xs font-mono resize-none bg-background" />
                  </div>
                  {wgLog.length > 0 && (
                    <div className="bg-background/80 p-2 text-[10px] font-mono border border-border rounded max-h-24 overflow-auto">
                      {wgLog.map((l, i) => <div key={i}>{l}</div>)}
                    </div>
                  )}
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
