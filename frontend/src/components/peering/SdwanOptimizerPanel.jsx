import React, { useState, useEffect, useRef } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import api from '@/lib/api';
import { FiActivity, FiPlus, FiTrash2, FiPlay, FiRefreshCw, FiXCircle, FiEye, FiChevronDown, FiSearch } from 'react-icons/fi';
import { toast } from 'sonner';

export default function SdwanOptimizerPanel({ deviceId }) {
  const [showAdd, setShowAdd] = useState(false);
  const queryClient = useQueryClient();

  // Poller untuk device_id yang dipilih
  const { data: policies = [], isLoading: pLoading } = useQuery({
    queryKey: ['sdwan_policies', deviceId],
    queryFn: async () => {
      const res = await api.get('/sdwan/policies');
      if (deviceId) {
         return res.data.filter(p => p.device_id === deviceId);
      }
      return res.data;
    },
    refetchInterval: 30000
  });

  const { data: overrides = [], isLoading: oLoading } = useQuery({
    queryKey: ['sdwan_overrides', deviceId],
    queryFn: async () => {
      const res = await api.get('/sdwan/active-overrides');
      if (deviceId) {
         return res.data.filter(p => p.device_id === deviceId);
      }
      return res.data;
    },
    refetchInterval: 10000
  });

  const { data: events = [], isLoading: eLoading } = useQuery({
    queryKey: ['sdwan_events', deviceId],
    queryFn: async () => {
      const url = deviceId ? `/sdwan/events?device_id=${deviceId}` : '/sdwan/events';
      const res = await api.get(url);
      return res.data;
    },
    refetchInterval: 30000
  });

  const deleteMut = useMutation({
    mutationFn: (id) => api.delete(`/sdwan/policies/${id}`),
    onSuccess: () => {
      toast.success('Kebijakan dihapus');
      queryClient.invalidateQueries(['sdwan_policies']);
    }
  });

  const revertMut = useMutation({
    mutationFn: (id) => api.post(`/sdwan/active-overrides/${id}/revert`),
    onSuccess: () => {
      toast.success('Routing dikembalikan ke primary');
      queryClient.invalidateQueries(['sdwan_overrides']);
      queryClient.invalidateQueries(['sdwan_events']);
    },
    onError: (e) => toast.error(`Gagal: ${e.response?.data?.detail || e.message}`)
  });

  const testMut = useMutation({
    mutationFn: (id) => api.post(`/sdwan/policies/${id}/test`),
    onSuccess: (data) => {
      if (data.data.would_failover) {
         toast.error(`TEST RTT: ${data.data.avg_rtt_ms}ms, Loss: ${data.data.packet_loss_pct}%. Akan failover!`, {duration: 5000});
      } else {
         toast.success(`TEST RTT: ${data.data.avg_rtt_ms}ms, Loss: ${data.data.packet_loss_pct}%. LINK AMAN.`, {duration: 5000});
      }
    },
    onError: (e) => toast.error(`Gagal Test: ${e.response?.data?.detail || e.message}`)
  });

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
         <div>
            <h3 className="text-xl font-bold flex items-center gap-2">
               <FiActivity className="text-blue-500" /> SD-WAN Optimizer
            </h3>
            <p className="text-sm text-gray-500">Failover automatis untuk route spesifik / target prefix.</p>
         </div>
         <button onClick={() => setShowAdd(true)} className="flex items-center gap-2 bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-md text-sm font-semibold">
           <FiPlus /> Buat Kebijakan
         </button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
         {/* Kiri: Daftar Kebijakan & Override Aktif */}
         <div className="space-y-4">
            <h4 className="font-semibold border-b pb-2">Kebijakan Aktif</h4>
            {pLoading ? <p className="text-sm text-gray-500">Loading...</p> : policies.length === 0 ? <p className="text-sm text-gray-500">Belum ada kebijakan SD-WAN.</p> : (
               <div className="space-y-3 overflow-x-auto pb-2 w-full">
                  {policies.map(p => {
                     const override = overrides.find(o => o.policy_id === p.id);
                     return (
                        <div key={p.id} className={`p-4 rounded-lg border ${override ? 'border-red-500 bg-red-500/5' : 'border-gray-200 dark:border-gray-800 bg-card'}`}>
                           <div className="flex justify-between items-start mb-2">
                              <div>
                                 <h5 className="font-bold flex items-center gap-2">
                                    {p.name}
                                    {override ? (
                                       <span className="bg-red-500 text-white text-[10px] px-2 py-0.5 rounded-full animate-pulse">FAILOVER</span>
                                    ) : (
                                       <span className="bg-green-500 text-white text-[10px] px-2 py-0.5 rounded-full">PRIMARY</span>
                                    )}
                                 </h5>
                                 <p className="text-xs text-gray-500 font-mono mt-1">Target: {p.target_prefix}</p>
                              </div>
                              <div className="flex gap-2">
                                 {override && (
                                    <button onClick={() => {if(window.confirm('Paksa rollback routing ke primary?')) revertMut.mutate(p.id)}} className="p-1.5 text-xs bg-yellow-500/10 text-yellow-600 rounded">
                                       Rollback
                                    </button>
                                 )}
                                 <button onClick={() => testMut.mutate(p.id)} className="p-1.5 hover:bg-gray-100 dark:hover:bg-gray-800 rounded text-blue-500" title="Test Latensi">
                                    <FiPlay />
                                 </button>
                                 <button onClick={() => {if(window.confirm('Hapus kebijakan?')) deleteMut.mutate(p.id)}} className="p-1.5 hover:bg-gray-100 dark:hover:bg-gray-800 rounded text-red-500">
                                    <FiTrash2 />
                                 </button>
                              </div>
                           </div>
                           <div className="grid grid-cols-2 gap-2 text-[11px] text-gray-500 mt-3 pt-3 border-t dark:border-gray-800">
                              <div>Thr: {p.latency_threshold_ms}ms / {p.packet_loss_threshold_pct}% Loss</div>
                              <div>Backup: {p.backup_interface || p.routing_mark}</div>
                              {override && (
                                 <div className="col-span-2 text-red-500 mt-1">
                                    Triggered at: {new Date(override.started_at).toLocaleTimeString('id-ID')} (RTT: {override.trigger_rtt}ms)
                                 </div>
                              )}
                           </div>
                        </div>
                     )
                  })}
               </div>
            )}
         </div>

         {/* Kanan: Event History */}
         <div className="space-y-4">
            <div className="flex items-center justify-between border-b pb-2">
               <h4 className="font-semibold">Event Failover Terbaru</h4>
               <button onClick={() => queryClient.invalidateQueries(['sdwan_events'])} className="text-gray-500 hover:text-blue-500"><FiRefreshCw size={14} /></button>
            </div>
            
            {eLoading ? <p className="text-sm text-gray-500">Loading...</p> : events.length === 0 ? <p className="text-sm text-gray-500">Belum ada history failover.</p> : (
               <div className="space-y-2 max-h-[500px] overflow-y-auto pr-2">
                  {events.map((e, idx) => (
                     <div key={idx} className={`p-3 rounded border text-xs flex gap-3 ${e.type === 'failover' ? 'border-red-200 bg-red-50 dark:bg-red-900/10 dark:border-red-800' : e.type === 'recover' ? 'border-green-200 bg-green-50 dark:bg-green-900/10 dark:border-green-800' : 'border-gray-200 bg-gray-50 dark:bg-gray-800'}`}>
                        <div className="font-mono text-[10px] text-gray-500 shrink-0 w-12">
                           {new Date(e.timestamp).toLocaleTimeString('id-ID', {hour: '2-digit', minute:'2-digit'})}
                        </div>
                        <div>
                           <p className="font-bold">
                              {e.type === 'failover' && <span className="text-red-600">↘ FAILOVER Triggered</span>}
                              {e.type === 'recover' && <span className="text-green-600">↗ RECOVER (Back to Primary)</span>}
                              {e.type === 'manual_revert' && <span className="text-yellow-600">&#8634; MANUAL ROLLBACK</span>}
                              {e.type === 'route_inject' && <span className="text-blue-600">&#43; STATIC ROUTE INJECTED</span>}
                           </p>
                           <p className="mt-1 text-gray-600 dark:text-gray-400">
                              {e.policy_name || e.target_prefix} 
                              {e.rtt_ms && ` (RTT: ${e.rtt_ms.toFixed(0)}ms)`}
                           </p>
                        </div>
                     </div>
                  ))}
               </div>
            )}
         </div>
      </div>

      {showAdd && <AddSdwanModal deviceId={deviceId || ''} onClose={() => setShowAdd(false)} onSuccess={() => queryClient.invalidateQueries(['sdwan_policies'])} />}
    </div>
  );
}

/* ─── Prefix Picker Dropdown Component ────────────────────────────────────── */
function PrefixPicker({ value, onChange }) {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState('');
  const [expandedGroup, setExpandedGroup] = useState(null);
  const dropRef = useRef(null);

  // Fetch prefix suggestions dari Peering Eye
  const { data: suggestions, isLoading } = useQuery({
    queryKey: ['peering_prefix_suggestions'],
    queryFn: async () => {
      const res = await api.get('/peering-eye/sdwan-prefix-suggestions');
      return res.data;
    },
    staleTime: 5 * 60 * 1000,  // Cache 5 menit
  });

  // Close on outside click
  useEffect(() => {
    const handler = (e) => {
      if (dropRef.current && !dropRef.current.contains(e.target)) setOpen(false);
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  const groups = suggestions?.groups || [];

  // Filter items berdasarkan search
  const filteredGroups = groups.map(g => ({
    ...g,
    items: g.items.filter(item =>
      !search ||
      item.label.toLowerCase().includes(search.toLowerCase()) ||
      item.value.toLowerCase().includes(search.toLowerCase()) ||
      item.description?.toLowerCase().includes(search.toLowerCase())
    )
  })).filter(g => g.items.length > 0);

  const handleSelect = (item) => {
    if (item.value) {
      onChange(item.value);
      setOpen(false);
      setSearch('');
    }
  };

  return (
    <div className="relative" ref={dropRef}>
      <div className="flex gap-2">
        {/* Input field manual */}
        <input
          required
          className="flex-1 border border-white/10 rounded-md p-2 text-sm bg-background text-foreground font-mono focus:outline-none focus:ring-1 focus:ring-blue-500 transition-shadow"
          value={value}
          onChange={e => onChange(e.target.value)}
          placeholder="e.g. 157.240.0.0/16 atau 8.8.8.8"
        />
        {/* Tombol buka Peering Eye picker */}
        <button
          type="button"
          onClick={() => setOpen(v => !v)}
          title="Pilih prefix dari Sentinel Peering Eye"
          className={`flex items-center gap-1.5 px-3 py-2 rounded-md border text-xs font-semibold transition-all ${
            open
              ? 'bg-blue-600 border-blue-500 text-white'
              : 'border-white/10 bg-white/5 text-blue-400 hover:bg-blue-500/15 hover:border-blue-500/40'
          }`}
        >
          <FiEye className="w-3.5 h-3.5" />
          <span className="hidden sm:inline">Peering Eye</span>
          <FiChevronDown className={`w-3 h-3 transition-transform ${open ? 'rotate-180' : ''}`} />
        </button>
      </div>

      {/* Dropdown panel */}
      {open && (
        <div
          className="absolute left-0 right-0 top-full mt-1.5 z-50 rounded-xl border border-white/10 shadow-2xl overflow-hidden"
          style={{ background: 'linear-gradient(135deg, rgba(15,23,42,0.98) 0%, rgba(2,8,23,0.98) 100%)' }}
        >
          {/* Header */}
          <div className="flex items-center gap-2 px-3 py-2.5 border-b border-white/10">
            <FiEye className="w-4 h-4 text-blue-400 flex-shrink-0" />
            <p className="text-xs font-bold text-blue-300">Sentinel Peering Eye — Prefix Suggestions</p>
          </div>

          {/* Search */}
          <div className="px-3 py-2 border-b border-white/[0.06]">
            <div className="flex items-center gap-2 bg-white/5 rounded-lg px-2.5 py-1.5">
              <FiSearch className="w-3.5 h-3.5 text-slate-500 flex-shrink-0" />
              <input
                autoFocus
                type="text"
                value={search}
                onChange={e => setSearch(e.target.value)}
                placeholder="Cari platform atau prefix..."
                className="flex-1 bg-transparent text-xs text-slate-200 placeholder-slate-500 outline-none"
              />
              {search && (
                <button onClick={() => setSearch('')} className="text-slate-500 hover:text-slate-300">
                  <FiXCircle className="w-3.5 h-3.5" />
                </button>
              )}
            </div>
          </div>

          {/* Content */}
          <div className="max-h-72 overflow-y-auto">
            {isLoading ? (
              <div className="flex items-center justify-center py-8">
                <div className="w-5 h-5 border-2 border-blue-500/30 border-t-blue-400 rounded-full animate-spin" />
                <span className="ml-2 text-xs text-slate-500">Memuat data Peering Eye...</span>
              </div>
            ) : filteredGroups.length === 0 ? (
              <div className="text-center py-8 text-slate-500 text-xs">
                {search ? `Tidak ada prefix yang cocok dengan "${search}"` : 'Tidak ada data Peering Eye tersedia'}
              </div>
            ) : (
              filteredGroups.map((group, gi) => (
                <div key={gi}>
                  {/* Group header */}
                  <button
                    type="button"
                    onClick={() => setExpandedGroup(expandedGroup === gi ? null : gi)}
                    className="w-full flex items-center justify-between px-3 py-2 text-left hover:bg-white/5 transition-colors border-b border-white/[0.04]"
                  >
                    <div className="flex items-center gap-2">
                      <span className="text-base leading-none">{group.icon}</span>
                      <span className="text-[11px] font-semibold" style={{ color: group.color }}>{group.group}</span>
                      <span className="text-[10px] text-slate-500 bg-white/5 rounded-full px-1.5 py-0.5">
                        {group.items.length}
                      </span>
                    </div>
                    <FiChevronDown
                      className={`w-3.5 h-3.5 text-slate-500 transition-transform ${expandedGroup === gi || search ? 'rotate-180' : ''}`}
                    />
                  </button>

                  {/* Group items */}
                  {(expandedGroup === gi || search) && (
                    <div>
                      {group.items.map((item, ii) => (
                        <button
                          key={ii}
                          type="button"
                          onClick={() => handleSelect(item)}
                          className="w-full text-left px-4 py-2.5 hover:bg-blue-500/10 transition-colors flex items-start gap-3 group"
                        >
                          <div className="flex-1 min-w-0">
                            <p className="text-xs font-mono text-slate-200 group-hover:text-blue-300 transition-colors truncate">
                              {item.value}
                            </p>
                            <p className="text-[10px] text-slate-500 truncate mt-0.5">{item.label}</p>
                            {item.description && (
                              <p className="text-[9px] text-slate-600 mt-0.5">{item.description}</p>
                            )}
                          </div>
                          <span
                            className="text-[9px] px-1.5 py-0.5 rounded border flex-shrink-0 mt-0.5 opacity-60 group-hover:opacity-100 transition-opacity"
                            style={{
                              background: group.color + '15',
                              borderColor: group.color + '40',
                              color: group.color,
                            }}
                          >
                            {item.type === 'bgp_peer' ? 'BGP' :
                             item.type === 'known_prefix' ? 'Known' : '24h'}
                          </span>
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              ))
            )}
          </div>

          {/* Footer hint */}
          <div className="px-3 py-2 border-t border-white/[0.06] flex items-center gap-2">
            <FiEye className="w-3 h-3 text-slate-600" />
            <p className="text-[10px] text-slate-600">
              Termasuk BGP peers aktif, platform terdeteksi, dan known IP range per platform
            </p>
          </div>
        </div>
      )}
    </div>
  );
}


/* ─── Add SD-WAN Policy Modal ─────────────────────────────────────────────── */
function AddSdwanModal({ deviceId, onClose, onSuccess }) {
   const [formData, setFormData] = useState({
      name: '', device_id: deviceId, target_prefix: '', backup_interface: '', routing_mark: '', latency_threshold_ms: 150, packet_loss_threshold_pct: 30
   });
   const [loading, setLoading] = useState(false);
   const [devices, setDevices] = useState([]);

   useEffect(() => {
      api.get('/devices').then(r => {
         setDevices(r.data || []);
         if (!deviceId && r.data.length === 1) {
            setFormData(prev => ({ ...prev, device_id: r.data[0].id }));
         }
      }).catch(() => {});
   }, [deviceId]);

   const submit = async (e) => {
      e.preventDefault();
      setLoading(true);
      try {
         await api.post('/sdwan/policies', formData);
         toast.success('Kebijakan tersimpan!');
         onSuccess();
         onClose();
      } catch (err) {
         toast.error(err.response?.data?.detail || err.message);
      }
      setLoading(false);
   };

   return (
      <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
         <div className="bg-card border border-white/10 shadow-2xl rounded-xl max-w-md w-full p-6 animate-in fade-in zoom-in-95 duration-200">
            <div className="flex items-center justify-between mb-5">
               <h3 className="text-lg font-bold text-foreground">Buat Kebijakan SD-WAN</h3>
               <button type="button" onClick={onClose} className="text-muted-foreground hover:text-foreground">
                  <FiXCircle className="w-5 h-5" />
               </button>
            </div>
            <form onSubmit={submit} className="space-y-4">
               <div>
                  <label className="block text-xs font-semibold text-muted-foreground mb-1.5">Nama Kebijakan</label>
                  <input required className="w-full border border-white/10 rounded-md p-2 text-sm bg-background text-foreground focus:outline-none focus:ring-1 focus:ring-blue-500 transition-shadow" value={formData.name} onChange={e=>setFormData({...formData, name: e.target.value})} placeholder="e.g. Meta Failover to ISP2" />
               </div>
               <div>
                  <label className="block text-xs font-semibold text-muted-foreground mb-1.5">Pilih Device / Router</label>
                  <select
                     required
                     className="w-full border border-white/10 rounded-md p-2 text-sm bg-background text-foreground focus:outline-none focus:ring-1 focus:ring-blue-500 transition-shadow"
                     value={formData.device_id}
                     onChange={e => setFormData({...formData, device_id: e.target.value})}
                  >
                     <option value="">-- Pilih device --</option>
                     {devices.map(d => (
                        <option key={d.id} value={d.id}>
                           {d.name || d.identity || d.ip_address} ({d.status === 'online' ? '🟢' : '🔴'} {d.ip_address})
                        </option>
                     ))}
                  </select>
               </div>

               {/* Target Prefix dengan Peering Eye Picker */}
               <div>
                  <div className="flex items-center justify-between mb-1.5">
                     <label className="block text-xs font-semibold text-muted-foreground">Target Prefix</label>
                     <span className="flex items-center gap-1 text-[10px] text-blue-400/70">
                        <FiEye className="w-3 h-3" />
                        Klik "Peering Eye" untuk saran prefix
                     </span>
                  </div>
                  <PrefixPicker
                     value={formData.target_prefix}
                     onChange={(val) => setFormData({...formData, target_prefix: val})}
                  />
                  <p className="text-[10px] text-muted-foreground mt-1">
                     Masukkan IP/CIDR manual atau pilih dari data Sentinel Peering Eye.
                  </p>
               </div>

               <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div>
                     <label className="block text-xs font-semibold text-muted-foreground mb-1.5">Latency Threshold (ms)</label>
                     <input type="number" required className="w-full border border-white/10 rounded-md p-2 text-sm bg-background text-foreground focus:outline-none focus:ring-1 focus:ring-blue-500 transition-shadow" value={formData.latency_threshold_ms} onChange={e=>setFormData({...formData, latency_threshold_ms: Number(e.target.value)})} />
                  </div>
                  <div>
                     <label className="block text-xs font-semibold text-muted-foreground mb-1.5">Loss Threshold (%)</label>
                     <input type="number" required className="w-full border border-white/10 rounded-md p-2 text-sm bg-background text-foreground focus:outline-none focus:ring-1 focus:ring-blue-500 transition-shadow" value={formData.packet_loss_threshold_pct} onChange={e=>setFormData({...formData, packet_loss_threshold_pct: Number(e.target.value)})} />
                  </div>
               </div>
               <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div>
                     <label className="block text-xs font-semibold text-muted-foreground mb-1.5">Backup Interface (Optional)</label>
                     <input className="w-full border border-white/10 rounded-md p-2 text-sm bg-background text-foreground focus:outline-none focus:ring-1 focus:ring-blue-500 transition-shadow" value={formData.backup_interface} onChange={e=>setFormData({...formData, backup_interface: e.target.value})} placeholder="ether2" />
                  </div>
                  <div>
                     <label className="block text-xs font-semibold text-muted-foreground mb-1.5">Routing Mark</label>
                     <input className="w-full border border-white/10 rounded-md p-2 text-sm bg-background text-foreground focus:outline-none focus:ring-1 focus:ring-blue-500 transition-shadow" value={formData.routing_mark} onChange={e=>setFormData({...formData, routing_mark: e.target.value})} placeholder="Auto-generated" />
                  </div>
               </div>
               <div className="flex justify-end gap-3 mt-8 pt-4 border-t border-white/10">
                  <button type="button" onClick={onClose} className="px-4 py-2 hover:bg-white/5 rounded-md text-sm text-foreground transition-colors">Batal</button>
                  <button type="submit" disabled={loading} className="px-5 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-md text-sm font-semibold transition-colors shadow-lg shadow-blue-500/20">{loading ? 'Menyimpan...' : 'Simpan Kebijakan'}</button>
               </div>
            </form>
         </div>
      </div>
   )
}
