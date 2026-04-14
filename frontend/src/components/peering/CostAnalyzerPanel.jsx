import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import api from '@/lib/api';
import { FiDollarSign, FiSave } from 'react-icons/fi';
import { toast } from 'sonner';

export default function CostAnalyzerPanel({ fetchAll }) {
  const queryClient = useQueryClient();
  const [transitPrice, setTransitPrice] = useState(0.05);

  const { data: config = {}, isLoading: cLoading } = useQuery({
    queryKey: ['cost_config'],
    queryFn: async () => {
      const res = await api.get('/sdwan/cost-config');
      setTransitPrice(res.data.transit_price_per_gb || 0.05);
      return res.data;
    },
    refetchOnWindowFocus: false
  });

  const saveMut = useMutation({
    mutationFn: () => api.post('/sdwan/cost-config', { transit_price_per_gb: transitPrice, currency: 'USD' }),
    onSuccess: () => {
      toast.success('Harga transit tersimpan');
      queryClient.invalidateQueries(['cost_config']);
      if (fetchAll) fetchAll(true);
    }
  });

  // Karena ini untuk simulasi MVP, kita akan menampilkan chart placeholder
  // dan perhitungan dummy/simulasi atau text dari summary jika API tersedia.
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
         <div>
            <h3 className="text-xl font-bold flex items-center gap-2">
               <FiDollarSign className="text-emerald-500" /> Cost Analyzer
            </h3>
            <p className="text-sm text-gray-500">Estimasi biaya traffic transit vs IX (gratis).</p>
         </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
         <div className="bg-card border border-border rounded-lg p-6 flex flex-col items-center justify-center text-center">
            <h4 className="font-semibold text-gray-400 mb-2">Simulasi Biaya Transit Bulan Ini</h4>
            <div className="text-4xl font-black text-emerald-500 font-mono tracking-tighter">
               ${((Math.random() * 500) + 100).toFixed(2)}
            </div>
            <p className="text-sm text-gray-500 mt-2">Berdasarkan {transitPrice} $/GB <br/>(Simulasi data preview)</p>
         </div>

         <div className="bg-card border border-gray-200 dark:border-gray-800 rounded-lg p-6">
            <h4 className="font-semibold mb-4 border-b pb-2">Konfigurasi Harga</h4>
            <div className="space-y-4">
               <div>
                  <label className="block text-sm font-semibold mb-1">Harga Transit per GB ($)</label>
                  <input 
                     type="number" 
                     step="0.01" 
                     className="w-full border rounded p-2 text-sm bg-transparent font-mono focus:ring-2 focus:ring-emerald-500 outline-none" 
                     value={transitPrice} 
                     onChange={e => setTransitPrice(Number(e.target.value))} 
                  />
               </div>
               <button 
                  onClick={() => saveMut.mutate()} 
                  disabled={saveMut.isLoading}
                  className="flex items-center gap-2 bg-emerald-600 hover:bg-emerald-700 text-white px-4 py-2 rounded-md justify-center w-full transition"
               >
                  <FiSave /> {saveMut.isLoading ? 'Menyimpan...' : 'Simpan Konfigurasi'}
               </button>
            </div>
         </div>
      </div>
    </div>
  );
}
