import React, { useState, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import api from "@/lib/api";
import { toast } from "sonner";
import { 
  Radar, Activity, Plus, Trash2, Power, Globe,
  ServerCrash, Shield, AlertTriangle, ArrowRight, Play, Eye
} from "lucide-react";

export default function BgpSteeringPage() {
  const [activeTab, setActiveTab] = useState("app_traffic");

  return (
    <div className="space-y-6 max-w-[1600px] mx-auto pb-10">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-border pb-6">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-foreground flex items-center gap-3">
            <Radar className="w-7 h-7 text-indigo-500" />
            BGP Steering & App Traffic
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            Pantau penggunaan Bandwidth per-Aplikasi dan belokkan traffic (BGP Policy Routing).
          </p>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex flex-wrap gap-2 border-b border-border/50">
        <button
          onClick={() => setActiveTab("app_traffic")}
          className={`px-4 py-2.5 text-sm font-semibold transition-colors flex items-center gap-2 border-b-2 ${
            activeTab === "app_traffic" 
              ? "border-indigo-500 text-indigo-400" 
              : "border-transparent text-muted-foreground hover:bg-secondary/20 hover:text-foreground"
          }`}
        >
          <Activity className="w-4 h-4" /> Traffic App Monitor
        </button>
        <button
          onClick={() => setActiveTab("bgp_steering")}
          className={`px-4 py-2.5 text-sm font-semibold transition-colors flex items-center gap-2 border-b-2 ${
            activeTab === "bgp_steering"
              ? "border-emerald-500 text-emerald-400"
              : "border-transparent text-muted-foreground hover:bg-secondary/20 hover:text-foreground"
          }`}
        >
          <Globe className="w-4 h-4" /> BGP Steering Policies
        </button>
      </div>

      <div className="py-2">
        {activeTab === "app_traffic" && <AppTrafficMonitorTab />}
        {activeTab === "bgp_steering" && <BgpSteeringTab />}
      </div>
    </div>
  );
}

/* ─────────────────────────────────────────────────────────────────────────────
 * App Traffic Monitor Tab
 * ───────────────────────────────────────────────────────────────────────────── */
function AppTrafficMonitorTab() {
  const queryClient = useQueryClient();

  const { data: summary = [], isLoading } = useQuery({
    queryKey: ["app_traffic_summary"],
    queryFn: async () => {
      const res = await api.get("/peering-eye/app-traffic/summary");
      return res.data;
    },
    refetchInterval: 30000,
  });

  const formatBytes = (bytes) => {
    if (!bytes) return "0 B";
    const k = 1024;
    const sizes = ["B", "KB", "MB", "GB", "TB", "PB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + " " + sizes[i];
  };

  return (
    <div className="space-y-6">
      <div className="bg-card border border-border rounded-xl p-5 shadow-sm">
        <h3 className="text-lg font-semibold flex items-center gap-2 mb-4">
          <Activity className="w-5 h-5 text-indigo-500" />
          Bandwidth Usage per Application (24 Jam Terakhir)
        </h3>
        
        {isLoading ? (
          <div className="flex items-center justify-center py-10 text-muted-foreground">
            <RefreshCw className="w-6 h-6 animate-spin mr-2" /> Memuat data traffic...
          </div>
        ) : summary.length === 0 ? (
          <div className="text-center py-10">
            <ServerCrash className="w-12 h-12 text-muted-foreground/30 mx-auto mb-3" />
            <p className="text-muted-foreground">Belum ada pengumpulan data bandwidth aplikasi.</p>
            <p className="text-xs text-muted-foreground/60 mt-1">Pastikan BGP Policy untuk aplikasi sudah diaktifkan dan Queue terbuat di MikroTik.</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm whitespace-nowrap">
              <thead>
                <tr className="border-b border-border/50 text-muted-foreground">
                  <th className="pb-3 px-2 font-medium">Platform</th>
                  <th className="pb-3 px-2 font-medium text-right">Total Bandwidth</th>
                  <th className="pb-3 px-2 font-medium text-right">Download (Rx)</th>
                  <th className="pb-3 px-2 font-medium text-right">Upload (Tx)</th>
                  <th className="pb-3 px-2 font-medium text-right">Rasio (%)</th>
                </tr>
              </thead>
              <tbody>
                {summary.map((row, idx) => (
                  <tr key={idx} className="border-b border-border/20 last:border-0 hover:bg-secondary/10">
                    <td className="py-3 px-2 font-semibold text-foreground flex items-center gap-2">
                       <span className="w-2 h-2 rounded-full bg-indigo-500" />
                       {row.platform}
                    </td>
                    <td className="py-3 px-2 text-right font-mono text-indigo-400 font-bold">{formatBytes(row.total_bytes)}</td>
                    <td className="py-3 px-2 text-right font-mono text-emerald-400">{formatBytes(row.bytes_rx)}</td>
                    <td className="py-3 px-2 text-right font-mono text-amber-400">{formatBytes(row.bytes_tx)}</td>
                    <td className="py-3 px-2 text-right font-mono">
                      <div className="flex items-center justify-end gap-2">
                         <span className="w-12 text-right">{row.percent}%</span>
                         <div className="w-24 h-1.5 bg-secondary rounded-full overflow-hidden">
                           <div className="h-full bg-indigo-500 rounded-full" style={{ width: \`\${row.percent}%\` }} />
                         </div>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div className="bg-amber-500/10 border border-amber-500/20 rounded-xl p-4">
        <h4 className="text-sm font-semibold text-amber-500 flex items-center gap-2 mb-2">
          <AlertTriangle className="w-4 h-4" /> Cara Mengukur Traffic App
        </h4>
        <p className="text-xs text-amber-500/80 leading-relaxed">
          NOC Billing Pro mengukur ukuran byte aplikasi dengan menarik data <strong>Simple Queue</strong> dari MikroTik Anda setiap 5 menit. 
          Agar pengukuran berjalan, Anda WAJIB membuat Simple Queue di MikroTik bernama <code className="bg-amber-500/20 px-1 rounded">GLOBAL_APP_NamaPlatform</code> (Misalnya: <code>GLOBAL_APP_YouTube</code>).
        </p>
      </div>
    </div>
  );
}

/* ─────────────────────────────────────────────────────────────────────────────
 * BGP Steering Tab
 * ───────────────────────────────────────────────────────────────────────────── */
function BgpSteeringTab() {
  const queryClient = useQueryClient();
  const [showAdd, setShowAdd] = useState(false);

  const { data: policies = [], isLoading } = useQuery({
    queryKey: ["bgp_steering_policies"],
    queryFn: async () => {
      const res = await api.get("/peering-eye/bgp-steering");
      return res.data;
    },
  });

  const toggleMut = useMutation({
    mutationFn: (id) => api.post(\`/peering-eye/bgp-steering/\${id}/toggle\`),
    onSuccess: () => queryClient.invalidateQueries(["bgp_steering_policies"]),
    onError: (e) => toast.error(e.response?.data?.detail || "Gagal mengubah status policy.")
  });

  const deleteMut = useMutation({
    mutationFn: (id) => api.delete(\`/peering-eye/bgp-steering/\${id}\`),
    onSuccess: () => {
      toast.success("Policy BGP berhasil dihapus");
      queryClient.invalidateQueries(["bgp_steering_policies"]);
    },
    onError: (e) => toast.error(e.response?.data?.detail || "Gagal menghapus policy.")
  });

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
           <h3 className="text-lg font-semibold flex items-center gap-2 text-emerald-400">
              <Globe className="w-5 h-5" /> BGP Steering Configurations
           </h3>
           <p className="text-xs text-muted-foreground mt-1">Gunakan BGP Sentinel untuk membelokkan arah platform traffic ke Gateway ISP tertentu.</p>
        </div>
        <button
          onClick={() => setShowAdd(true)}
          className="bg-emerald-600 hover:bg-emerald-700 text-white px-4 py-2 rounded-lg text-sm font-semibold flex items-center gap-2 transition-colors shadow-lg shadow-emerald-500/20"
        >
          <Plus className="w-4 h-4" /> Buat BGP Policy
        </button>
      </div>

      {isLoading ? (
        <div className="text-center py-10"><RefreshCw className="w-6 h-6 animate-spin text-muted-foreground mx-auto" /></div>
      ) : policies.length === 0 ? (
        <div className="bg-card border border-border border-dashed rounded-xl p-10 text-center flex flex-col items-center justify-center">
          <Globe className="w-12 h-12 text-muted-foreground/20 mb-3" />
          <h4 className="text-lg font-semibold text-muted-foreground mb-1">Tidak Ada BGP Policy</h4>
          <p className="text-sm text-muted-foreground/60 max-w-md">Belum ada aturan BGP Steering yang aktif. Buat policy baru untuk mulai mengatur arah routing ke Peering/IX Anda.</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-5">
          {policies.map(p => (
            <div key={p.id} className="bg-card border border-border rounded-xl p-5 shadow-sm relative group hover:border-emerald-500/30 transition-colors">
              <div className="flex justify-between items-start mb-3">
                 <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-lg bg-secondary flex items-center justify-center text-xl shadow-inner">
                      {p.icon || "🌐"}
                    </div>
                    <div>
                       <h4 className="font-bold text-foreground">{p.platform_name}</h4>
                       <span className={\`text-[10px] font-bold px-2 py-0.5 rounded-full uppercase tracking-wider \${p.enabled ? "bg-emerald-500/10 text-emerald-400" : "bg-red-500/10 text-red-400"}\`}>
                         {p.enabled ? "Active" : "Disabled"}
                       </span>
                    </div>
                 </div>
                 <div className="flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                    <button 
                      onClick={() => toggleMut.mutate(p.id)}
                      className={\`p-1.5 rounded-md transition-colors \${p.enabled ? "text-amber-500 hover:bg-amber-500/10" : "text-emerald-500 hover:bg-emerald-500/10"}\`}
                      title={p.enabled ? "Disable Policy" : "Enable Policy"}
                    >
                      <Power className="w-4 h-4" />
                    </button>
                    <button 
                      onClick={() => { if(window.confirm("Hapus BGP Policy ini?")) deleteMut.mutate(p.id) }}
                      className="p-1.5 rounded-md text-red-400 hover:bg-red-500/10 transition-colors"
                      title="Hapus Policy"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                 </div>
              </div>

              <div className="space-y-3 mt-4">
                 <div className="bg-secondary/50 rounded-lg p-3 text-xs font-mono space-y-2">
                    <div className="flex justify-between items-center border-b border-border/50 pb-2">
                       <span className="text-muted-foreground flex items-center gap-1.5">Gateway Next-Hop <ArrowRight className="w-3 h-3" /></span>
                       <span className="font-bold text-emerald-400">{p.gateway_ip}</span>
                    </div>
                    <div className="flex justify-between items-center pt-1">
                       <span className="text-muted-foreground">Target / Community</span>
                       <span>{p.target_peer || "Global"}</span>
                    </div>
                 </div>

                 <div className="flex items-center justify-between text-xs px-1">
                    <span className="text-muted-foreground flex items-center gap-1">
                      <Radar className="w-3.5 h-3.5" /> Injected Routes:
                    </span>
                    <span className="font-bold bg-secondary px-2 py-0.5 rounded text-foreground">
                      {p.injected_prefix_count || 0} prefix
                    </span>
                 </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {showAdd && <AddBgpPolicyModal onClose={() => setShowAdd(false)} />}
    </div>
  );
}

import { RefreshCw } from "lucide-react";

/* ─────────────────────────────────────────────────────────────────────────────
 * Add BGP Policy Modal
 * ───────────────────────────────────────────────────────────────────────────── */
function AddBgpPolicyModal({ onClose }) {
  const queryClient = useQueryClient();
  const [formData, setFormData] = useState({
    platform_name: "", gateway_ip: "", target_peer: "", community: "", custom_prefixes: ""
  });
  const [loading, setLoading] = useState(false);

  const { data: catalog = [] } = useQuery({
    queryKey: ["bgp_steering_catalog"],
    queryFn: async () => {
      const res = await api.get("/peering-eye/bgp-steering/catalog");
      return res.data;
    }
  });

  // Use raw default if backend doesn't have it filled
  const fallbackCatalog = [
    { name: "YouTube", icon: "🟥" }, { name: "TikTok", icon: "🎵" }, 
    { name: "Facebook", icon: "🟦" }, { name: "Instagram", icon: "🟪" },
    { name: "Situs Dewasa", icon: "🔞" }, { name: "Judi Online", icon: "🎰" }
  ];

  const displayCatalog = catalog?.length > 0 ? catalog : fallbackCatalog;

  const submit = async (e) => {
    e.preventDefault();
    if (!formData.platform_name || !formData.gateway_ip) return toast.error("Platform & Gateway wajib diisi");
    
    setLoading(true);
    try {
      const payload = {
        ...formData,
        custom_prefixes: formData.custom_prefixes ? formData.custom_prefixes.split(",").map(s => s.trim()) : [],
        enabled: true
      };
      await api.post("/peering-eye/bgp-steering", payload);
      toast.success("BGP Policy berhasil dibuat! ASN Prefix sedang di-inject.");
      queryClient.invalidateQueries(["bgp_steering_policies"]);
      onClose();
    } catch (err) {
      toast.error(err.response?.data?.detail || err.message);
    }
    setLoading(false);
  };

  return (
    <div className="fixed inset-0 bg-black/70 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <div className="bg-card border border-border shadow-2xl rounded-2xl max-w-lg w-full p-6 animate-in fade-in zoom-in-95 duration-200">
        <div className="flex items-center justify-between mb-6">
          <h3 className="text-xl font-bold flex items-center gap-2">
             <Globe className="w-5 h-5 text-emerald-500" /> Tambah BGP Policy
          </h3>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground hover:bg-secondary p-1 rounded-md transition-colors"><Shield className="w-5 h-5" /></button>
        </div>

        <form onSubmit={submit} className="space-y-4">
          <div>
            <label className="block text-xs font-semibold text-muted-foreground mb-1.5">Pilih Platform Target</label>
            <select 
              required
              className="w-full bg-secondary/30 border border-border rounded-lg p-2.5 text-sm outline-none focus:ring-1 focus:ring-emerald-500"
              value={formData.platform_name}
              onChange={e => setFormData({...formData, platform_name: e.target.value})}
            >
              <option value="">-- Pilih Platform --</option>
              {displayCatalog.map((c, i) => (
                <option key={i} value={c.name}>{c.icon} {c.name}</option>
              ))}
              <option value="Custom">🔧 Custom /Lainnya</option>
            </select>
            {formData.platform_name === "Custom" && (
              <input 
                placeholder="Nama Platform Custom" 
                autoFocus
                onChange={e => setFormData({...formData, platform_name: e.target.value})}
                className="w-full bg-secondary/30 border border-border rounded-lg p-2.5 text-sm outline-none mt-2" 
              />
            )}
          </div>

          <div>
            <label className="block text-xs font-semibold text-muted-foreground mb-1.5">Gateway IP (Next-Hop)</label>
            <input 
              required type="text"
              placeholder="e.g. 192.168.3.1 (IP ISP Gateway yang ingin dituju)" 
              className="w-full bg-secondary/30 border border-border rounded-lg p-2.5 text-sm outline-none focus:ring-1 focus:ring-emerald-500 font-mono"
              value={formData.gateway_ip} onChange={e => setFormData({...formData, gateway_ip: e.target.value})}
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-semibold text-muted-foreground mb-1.5">Target Peer (Opsional)</label>
              <input 
                placeholder="e.g. 10.254.254.1" 
                className="w-full bg-secondary/30 border border-border rounded-lg p-2.5 text-xs outline-none focus:ring-1 focus:ring-emerald-500 font-mono"
                value={formData.target_peer} onChange={e => setFormData({...formData, target_peer: e.target.value})}
              />
              <p className="text-[10px] text-muted-foreground mt-1">Kosongkan untuk global broadcast.</p>
            </div>
            <div>
              <label className="block text-xs font-semibold text-muted-foreground mb-1.5">Manual Prefix (Opsional)</label>
              <input 
                placeholder="e.g. 8.8.8.8, 1.1.1.1/24" 
                className="w-full bg-secondary/30 border border-border rounded-lg p-2.5 text-xs outline-none focus:ring-1 focus:ring-emerald-500 font-mono"
                value={formData.custom_prefixes} onChange={e => setFormData({...formData, custom_prefixes: e.target.value})}
              />
              <p className="text-[10px] text-muted-foreground mt-1">Pisahkan dengan koma.</p>
            </div>
          </div>

          <div className="pt-4 mt-2 border-t border-border flex justify-end gap-3">
             <button type="button" onClick={onClose} className="px-4 py-2 bg-secondary hover:bg-secondary/80 text-foreground text-sm font-semibold rounded-lg transition-colors">Batal</button>
             <button type="submit" disabled={loading} className="px-6 py-2 bg-emerald-600 hover:bg-emerald-700 text-white text-sm font-semibold rounded-lg shadow-lg shadow-emerald-500/20 transition-colors flex items-center gap-2">
               {loading ? <span className="animate-spin text-lg">↻</span> : <Plus className="w-4 h-4" />} Simpan
             </button>
          </div>
        </form>
      </div>
    </div>
  );
}
