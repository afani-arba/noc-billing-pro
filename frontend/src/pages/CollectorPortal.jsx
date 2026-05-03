import React, { useState, useEffect } from 'react';
import api from '@/lib/api';
import { useAuth } from '@/App';

const CollectorPortal = () => {
  const { user } = useAuth();
  const [invoices, setInvoices] = useState([]);
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [selectedInvoice, setSelectedInvoice] = useState(null);
  const [note, setNote] = useState('');

  useEffect(() => {
    fetchData();
  }, []);

  const fetchData = async () => {
    setLoading(true);
    try {
      const [invRes, sumRes] = await Promise.all([
        api.get("/collector/invoices"),
        api.get("/collector/summary")
      ]);
      if (invRes.data.ok) setInvoices(invRes.data.data);
      if (sumRes.data.ok) setSummary(sumRes.data.data);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const handlePay = async (payment_method) => {
    if (!window.confirm(`Tandai Lunas via ${payment_method.toUpperCase()}?`)) return;
    try {
      await api.post(`/collector/invoices/${selectedInvoice.id}/pay`, { payment_method, notes: note });
      alert("Pembayaran berhasil!");
      setSelectedInvoice(null);
      setNote('');
      fetchData(); // Refresh list & summary
    } catch (err) {
      alert("Gagal memproses pembayaran");
    }
  };

  const handleAddNote = async () => {
    if(!note) return alert("Isi catatan terlebih dahulu");
    try {
      await api.post(`/collector/invoices/${selectedInvoice.id}/note`, { notes: note });
      alert("Catatan disimpan");
      setNote('');
      fetchData();
    } catch (err) {
      alert("Gagal simpan catatan");
    }
  };

  if (!user || (user.role !== 'kolektor' && user.role !== 'administrator' && user.role !== 'super_admin')) {
    return <div className="p-8 text-center text-red-500">Akses Ditolak. Halaman ini khusus Petugas Penagihan.</div>;
  }

  return (
    <div className="p-4 max-w-4xl mx-auto">
      <h1 className="text-2xl font-bold mb-6">Portal Penagihan Lapangan</h1>
      
      {summary && (
        <div className="bg-gradient-to-r from-blue-600 to-indigo-700 text-white p-4 rounded shadow mb-6 flex justify-between items-center">
          <div>
            <p className="text-sm opacity-80">Setoran Hari Ini ({summary.date})</p>
            <p className="text-2xl font-bold">Rp {summary.grand_total.toLocaleString()}</p>
          </div>
          <div className="text-right text-sm">
            <p>{summary.count} Transaksi</p>
            <p>Cash: Rp {summary.total_cash.toLocaleString()}</p>
          </div>
        </div>
      )}

      {loading ? <p>Loading data...</p> : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {/* Daftar Tagihan */}
          <div className="bg-white p-4 rounded shadow">
            <h2 className="text-lg font-semibold mb-4">Daftar Tagihan (Belum Lunas)</h2>
            {invoices.length === 0 ? <p className="text-gray-500">Tidak ada tagihan tertunggak.</p> : (
              <div className="space-y-4 max-h-[60vh] overflow-y-auto pr-2">
                {invoices.map(inv => (
                  <div key={inv.id} className="border p-4 rounded hover:border-blue-500 cursor-pointer" onClick={() => setSelectedInvoice(inv)}>
                    <div className="flex justify-between items-center mb-1">
                      <span className="font-bold text-gray-800">{inv.customer_name || 'Tanpa Nama'}</span>
                      <span className="font-bold text-red-500">Rp {inv.total.toLocaleString()}</span>
                    </div>
                    <p className="text-xs text-gray-600 line-clamp-1">{inv.customer_address || '-'}</p>
                    <p className="text-xs text-gray-500 mt-1">Jatuh Tempo: {inv.due_date.substring(0,10)}</p>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Action / Detail */}
          {selectedInvoice ? (
            <div className="bg-white p-4 rounded shadow flex flex-col gap-4">
              <h2 className="text-lg font-semibold border-b pb-2">Aksi Tagihan</h2>
              
              <div>
                <p className="text-xl font-bold">{selectedInvoice.customer_name}</p>
                <p className="text-sm text-gray-600">{selectedInvoice.customer_address}</p>
                <p className="text-sm text-blue-600">{selectedInvoice.customer_phone}</p>
              </div>

              <div className="bg-red-50 border border-red-200 p-3 rounded text-center">
                <p className="text-sm text-red-600">Total Tagihan</p>
                <p className="text-3xl font-bold text-red-700">Rp {selectedInvoice.total.toLocaleString()}</p>
              </div>

              <textarea 
                className="w-full border rounded p-2 text-sm" 
                rows="2" 
                placeholder="Catatan penagihan (opsional)..."
                value={note}
                onChange={e => setNote(e.target.value)}
              />

              <div className="grid grid-cols-2 gap-2 mt-2">
                <button onClick={() => handlePay('cash')} className="bg-green-600 hover:bg-green-700 text-white py-3 rounded font-bold shadow">
                  💵 TERIMA CASH
                </button>
                <button onClick={() => handlePay('transfer')} className="bg-blue-600 hover:bg-blue-700 text-white py-3 rounded font-bold shadow">
                  💳 TRANSFER
                </button>
              </div>
              <button onClick={handleAddNote} className="w-full bg-gray-200 hover:bg-gray-300 text-gray-800 py-2 rounded mt-2">
                Hanya Simpan Catatan (Janji Bayar)
              </button>
            </div>
          ) : (
             <div className="bg-gray-50 p-4 rounded border border-dashed flex items-center justify-center text-gray-400">
               Pilih tagihan di sebelah kiri untuk melihat detail & memproses pembayaran.
             </div>
          )}
        </div>
      )}
    </div>
  );
};

export default CollectorPortal;
