import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import api from '@/lib/api';
import { FiShield, FiPlus, FiTrash2, FiUnlock, FiRefreshCw } from 'react-icons/fi';
import { toast } from 'sonner';

export default function DdosShieldPanel({ deviceId }) {
  const [showAdd, setShowAdd] = useState(false);
  const queryClient = useQueryClient();

  const { data: thresholds = [], isLoading: tLoading } = useQuery({
    queryKey: ['ddos_thresholds', deviceId],
    queryFn: async () => {
      const res = await api.get('/sdwan/ddos/thresholds');
      if (deviceId) return res.data.filter(p => p.device_id === deviceId);
      return res.data;
    },
    refetchInterval: 60000
  });

  const { data: blocked = [], isLoading: bLoading } = useQuery({
    queryKey: ['ddos_blocked', deviceId],
    queryFn: async () => {
      const res = await api.get('/sdwan/ddos/blocked');
      if (deviceId) return res.data.filter(p => p.device_id === deviceId);
      return res.data;
    },
    refetchInterval: 10000
  });

  const { data: events = [], isLoading: eLoading } = useQuery({
    queryKey: ['ddos_events', deviceId],
    queryFn: async () => {
      const res = await api.get('/sdwan/ddos/events');
      if (deviceId) return res.data.filter(p => p.device_id === deviceId);
      return res.data;
    },
    refetchInterval: 30000
  });

  const deleteMut = useMutation({
    mutationFn: (id) => api.delete(`/sdwan/ddos/thresholds/${id}`),
    onSuccess: () => {
      toast.success('Threshold dihapus');
      queryClient.invalidateQueries(['ddos_thresholds']);
    }
  });

  const unblockMut = useMutation({
    mutationFn: ({ device_id, ip }) => api.post('/sdwan/ddos/unblock', { device_id, ip }),
    onSuccess: (data) => {
      toast.success(data.data.message);
      queryClient.invalidateQueries(['ddos_blocked']);
      queryClient.invalidateQueries(['ddos_events']);
    },
    onError: (e) => toast.error(`Gagal Unblock: ${e.response?.data?.detail || e.message}`)
  });

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
         <div>
            <h3 className="text-xl font-bold flex items-center gap-2">
               <FiShield className="text-red-500" /> DDoS Shield & RTBH
            </h3>
            <p className="text-sm text-gray-500">Auto-block IP & BGP RTBH announcement berdasarkan threshold traffic.</p>
         </div>
         <button onClick={() => setShowAdd(true)} className="flex items-center gap-2 bg-red-600 hover:bg-red-700 text-white px-4 py-2 rounded-md text-sm font-semibold">
           <FiPlus /> Buat Threshold
         </button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
         <div className="space-y-4">
            <h4 className="font-semibold border-b pb-2">Konfigurasi Threshold</h4>
            {tLoading ? <p className="text-sm text-gray-500">Loading...</p> : thresholds.length === 0 ? <p className="text-sm text-gray-500">Belum ada konfigurasi DDoS.</p> : (
               <div className="space-y-3 overflow-x-auto pb-2 w-full">
                  {thresholds.map(t => (
                        <div key={t.id} className="p-4 rounded-lg border border-gray-200 dark:border-gray-800 bg-card">
                           <div className="flex justify-between items-start mb-2">
                              <div>
                                 <h5 className="font-bold flex items-center gap-2">
                                    {t.name}
                                    <span className="bg-red-500 text-white text-[10px] px-2 py-0.5 rounded-full">{t.threshold_mbps} Mbps</span>
                                 </h5>
                                 <p className="text-xs text-gray-500 font-mono mt-1">Block: {t.block_duration_minutes}m | Upstream RTBH: {t.use_upstream_rtbh ? 'Yes' : 'No'} {t.bgp_community}</p>
                              </div>
                              <button onClick={() => {if(window.confirm('Hapus threshold?')) deleteMut.mutate(t.id)}} className="p-1.5 hover:bg-gray-100 dark:hover:bg-gray-800 rounded text-red-500">
                                 <FiTrash2 />
                              </button>
                           </div>
                        </div>
                  ))}
               </div>
            )}

            <h4 className="font-semibold border-b pb-2 mt-6">IP Sedang Diblokir ({blocked.length})</h4>
            {bLoading ? <p className="text-sm text-gray-500">Loading...</p> : blocked.length === 0 ? <p className="text-sm text-gray-500">Tidak ada IP yang di-blokir RTBH.</p> : (
               <div className="space-y-2">
                  {blocked.map(b => (
                     <div key={b.ip} className="flex justify-between items-center bg-red-50 dark:bg-red-900/10 border border-red-200 dark:border-red-800 rounded p-3">
                        <div>
                           <div className="font-mono font-bold text-red-600">{b.ip} <span className="text-xs text-red-400 font-normal ml-2">({b.mbps_rate?.toFixed(1)} Mbps)</span></div>
                           <div className="text-[10px] text-gray-500 mt-1">Sisa Waktu: {Math.floor((b._remaining_sec||0)/60)} menit</div>
                        </div>
                        <button onClick={() => {if(window.confirm(`Unblock ${b.ip}?`)) unblockMut.mutate({device_id: b.device_id, ip: b.ip})}} className="text-xs flex items-center gap-1 bg-white dark:bg-gray-800 border px-2 py-1 rounded text-gray-600 hover:text-green-500 transition">
                           <FiUnlock /> Unblock
                        </button>
                     </div>
                  ))}
               </div>
            )}
         </div>

         <div className="space-y-4">
            <div className="flex items-center justify-between border-b pb-2">
               <h4 className="font-semibold">Event DDoS & Mitigasi</h4>
               <button onClick={() => queryClient.invalidateQueries(['ddos_events'])} className="text-gray-500 hover:text-red-500"><FiRefreshCw size={14} /></button>
            </div>
            
            {eLoading ? <p className="text-sm text-gray-500">Loading...</p> : events.length === 0 ? <p className="text-sm text-gray-500">Belum ada riwayat DDoS.</p> : (
               <div className="space-y-2 max-h-[500px] overflow-y-auto pr-2">
                  {events.map((e, idx) => (
                     <div key={idx} className={`p-3 rounded border text-xs flex gap-3 ${e.type === 'block' ? 'border-red-200 bg-red-50 dark:bg-red-900/10 dark:border-red-800' : 'border-gray-200 bg-gray-50 dark:bg-gray-800'}`}>
                        <div className="font-mono text-[10px] text-gray-500 shrink-0 w-12">
                           {new Date(e.timestamp).toLocaleTimeString('id-ID', {hour: '2-digit', minute:'2-digit'})}
                        </div>
                        <div>
                           <p className="font-bold">
                              {e.type === 'block' && <span className="text-red-600">⛔ BLOCKED (RTBH)</span>}
                              {e.type === 'unblock' && <span className="text-green-600">✔️ AUTO UNBLOCKED</span>}
                              {e.type === 'manual_unblock' && <span className="text-yellow-600">✔️ MANUAL UNBLOCK</span>}
                           </p>
                           <p className="mt-1 font-mono text-gray-600 dark:text-gray-400">
                              {e.ip} {e.mbps_rate && ` (${e.mbps_rate.toFixed(0)} Mbps)`}
                           </p>
                        </div>
                     </div>
                  ))}
               </div>
            )}
         </div>
      </div>
      {showAdd && <AddDdosModal deviceId={deviceId || ''} onClose={() => setShowAdd(false)} onSuccess={() => queryClient.invalidateQueries(['ddos_thresholds'])} />}
    </div>
  );
}

function AddDdosModal({ deviceId, onClose, onSuccess }) {
   const [formData, setFormData] = useState({
      name: '', device_id: deviceId, threshold_mbps: 1000, block_duration_minutes: 60, use_upstream_rtbh: false, bgp_community: ''
   });
   const [loading, setLoading] = useState(false);

   const submit = async (e) => {
      e.preventDefault();
      setLoading(true);
      try {
         await api.post('/sdwan/ddos/thresholds', formData);
         toast.success('DDoS Threshold tersimpan!');
         onSuccess();
         onClose();
      } catch (err) {
         toast.error(err.response?.data?.detail || err.message);
      }
      setLoading(false);
   };

   return (
      <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
         <div className="bg-card border border-border rounded-2xl max-w-md w-full p-6 shadow-2xl">
            <h3 className="text-lg font-bold mb-5 flex items-center gap-2 text-foreground">
               <FiShield className="text-red-500 w-5 h-5" /> Buat Threshold DDoS
            </h3>
            <form onSubmit={submit} className="space-y-4">
               <div>
                  <label className="block text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-1.5">Nama Aturan</label>
                  <input required className="w-full border border-border rounded-lg p-2.5 text-sm bg-secondary text-foreground focus:outline-none focus:ring-1 focus:ring-red-500 transition-all" value={formData.name} onChange={e=>setFormData({...formData, name: e.target.value})} placeholder="e.g. Layer 4 Protection" />
               </div>
               <div>
                  <label className="block text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-1.5">Device ID</label>
                  <input required className="w-full border border-border rounded-lg p-2.5 text-sm bg-secondary text-foreground focus:outline-none focus:ring-1 focus:ring-red-500 transition-all" value={formData.device_id} onChange={e=>setFormData({...formData, device_id: e.target.value})} placeholder="e.g. RTR-CORE-01" />
               </div>
               <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div>
                     <label className="block text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-1.5">Threshold (Mbps)</label>
                     <input type="number" required className="w-full border border-border rounded-lg p-2.5 text-sm bg-secondary text-foreground focus:outline-none focus:ring-1 focus:ring-red-500 transition-all" value={formData.threshold_mbps} onChange={e=>setFormData({...formData, threshold_mbps: Number(e.target.value)})} />
                  </div>
                  <div>
                     <label className="block text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-1.5">Waktu Block (Mins)</label>
                     <input type="number" required className="w-full border border-border rounded-lg p-2.5 text-sm bg-secondary text-foreground focus:outline-none focus:ring-1 focus:ring-red-500 transition-all" value={formData.block_duration_minutes} onChange={e=>setFormData({...formData, block_duration_minutes: Number(e.target.value)})} />
                  </div>
               </div>
               <div className="mt-4 border-t border-border pt-5">
                  <label className="flex items-center gap-3 mb-2 cursor-pointer bg-secondary/30 hover:bg-secondary/50 p-3 rounded-lg border border-border transition-colors">
                     <input type="checkbox" className="w-4 h-4 rounded text-red-500 bg-secondary border-border" checked={formData.use_upstream_rtbh} onChange={e=>setFormData({...formData, use_upstream_rtbh: e.target.checked})} />
                     <div>
                       <span className="text-sm font-semibold text-foreground block">Enable Upstream BGP RTBH?</span>
                       <span className="text-[10px] text-muted-foreground">Injeksi route BGP dengan community string ke upstream ISP</span>
                     </div>
                  </label>
                  {formData.use_upstream_rtbh && (
                     <div className="mt-3">
                        <label className="block text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-1.5">BGP Community Tag</label>
                        <input required className="w-full border border-border rounded-lg p-2.5 text-sm font-mono bg-secondary text-foreground focus:outline-none focus:ring-1 focus:ring-red-500 transition-all" value={formData.bgp_community} onChange={e=>setFormData({...formData, bgp_community: e.target.value})} placeholder="e.g. 65001:666" />
                     </div>
                  )}
               </div>
               <div className="flex justify-end gap-3 mt-6 border-t border-border pt-5">
                  <button type="button" onClick={onClose} className="px-4 py-2 hover:bg-secondary rounded-lg text-sm text-foreground border border-border transition">Batal</button>
                  <button type="submit" disabled={loading} className="px-5 py-2 bg-red-600 hover:bg-red-700 text-white rounded-lg text-sm font-semibold shadow-lg shadow-red-500/20 disabled:opacity-50 transition">{loading ? 'Menyimpan...' : 'Simpan'}</button>
               </div>
            </form>
         </div>
      </div>
   )
}
