import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { useAuth } from '../context/AuthContext';
import { API_BASE_URL } from '../config';

const Collector = () => {
  const { user, logout } = useAuth();
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
        axios.get(`${API_BASE_URL}/collector/invoices`),
        axios.get(`${API_BASE_URL}/collector/summary`)
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
      await axios.post(`${API_BASE_URL}/collector/invoices/${selectedInvoice.id}/pay`, { payment_method, notes: note });
      alert("Pembayaran berhasil!");
      setSelectedInvoice(null);
      setNote('');
      fetchData();
    } catch (err) {
      alert("Gagal memproses pembayaran");
    }
  };

  const handleAddNote = async () => {
    if(!note) return alert("Isi catatan terlebih dahulu");
    try {
      await axios.post(`${API_BASE_URL}/collector/invoices/${selectedInvoice.id}/note`, { notes: note });
      alert("Catatan disimpan");
      setNote('');
      fetchData();
    } catch (err) {
      alert("Gagal simpan catatan");
    }
  };

  return (
    <div className="flex flex-col h-screen bg-gray-100">
      <div className="bg-indigo-700 p-4 text-white flex justify-between items-center shadow-md">
        <div>
          <h1 className="font-bold text-lg">Portal Kolektor</h1>
          <p className="text-xs text-indigo-200">{user?.username}</p>
        </div>
        <button onClick={logout} className="text-xs bg-indigo-800 px-3 py-1.5 rounded-full hover:bg-indigo-900">Logout</button>
      </div>

      {summary && !selectedInvoice && (
        <div className="bg-indigo-600 text-white px-4 py-5 shadow-inner">
          <p className="text-xs text-indigo-200 mb-1">Setoran Hari Ini</p>
          <p className="text-3xl font-bold">Rp {summary.grand_total.toLocaleString()}</p>
          <div className="flex gap-4 mt-2 text-xs text-indigo-100">
            <p>{summary.count} Transaksi</p>
            <p>Cash: Rp {summary.total_cash.toLocaleString()}</p>
          </div>
        </div>
      )}
      
      <div className="flex-1 overflow-y-auto p-4">
        {loading ? <p className="text-center mt-10">Loading data...</p> : !selectedInvoice ? (
          <div>
            <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wider mb-3 mt-2">Daftar Tagihan Tertunggak</h2>
            {invoices.length === 0 ? <p className="text-gray-500 text-center mt-10">Tidak ada tagihan tertunggak.</p> : (
              <div className="space-y-3">
                {invoices.map(inv => (
                  <div key={inv.id} className="bg-white border p-4 rounded-xl shadow-sm flex flex-col gap-1" onClick={() => setSelectedInvoice(inv)}>
                    <div className="flex justify-between items-start">
                      <span className="font-bold text-gray-800 leading-tight">{inv.customer_name || 'Tanpa Nama'}</span>
                      <span className="font-bold text-red-600 shrink-0">Rp {inv.total.toLocaleString()}</span>
                    </div>
                    <p className="text-xs text-gray-500 line-clamp-2 mt-1">{inv.customer_address || '-'}</p>
                    <p className="text-[10px] text-gray-400 mt-1">Jatuh Tempo: {inv.due_date.substring(0,10)}</p>
                  </div>
                ))}
              </div>
            )}
          </div>
        ) : (
          <div className="bg-white p-4 rounded-xl shadow-sm flex flex-col gap-4">
            <button onClick={() => setSelectedInvoice(null)} className="text-indigo-600 text-sm font-semibold mb-2">← Kembali ke Daftar</button>
            <h2 className="text-lg font-bold border-b pb-2">Aksi Tagihan</h2>
            
            <div>
              <p className="text-xl font-bold">{selectedInvoice.customer_name}</p>
              <p className="text-sm text-gray-600">{selectedInvoice.customer_address}</p>
              <p className="text-sm text-blue-600 font-medium mt-1">{selectedInvoice.customer_phone}</p>
            </div>

            <div className="bg-red-50 border border-red-200 p-4 rounded-xl text-center my-2">
              <p className="text-xs text-red-600 uppercase font-bold mb-1">Total Tagihan</p>
              <p className="text-3xl font-bold text-red-700">Rp {selectedInvoice.total.toLocaleString()}</p>
            </div>

            <textarea 
              className="w-full border rounded-lg p-3 text-sm bg-gray-50 outline-none focus:ring-2 focus:ring-indigo-500" 
              rows="3" 
              placeholder="Catatan penagihan lapangan (opsional)..."
              value={note}
              onChange={e => setNote(e.target.value)}
            />

            <div className="grid grid-cols-2 gap-3 mt-2">
              <button onClick={() => handlePay('cash')} className="bg-green-600 hover:bg-green-700 text-white py-3 rounded-xl font-bold shadow-md">
                💵 TERIMA CASH
              </button>
              <button onClick={() => handlePay('transfer')} className="bg-blue-600 hover:bg-blue-700 text-white py-3 rounded-xl font-bold shadow-md">
                💳 TRANSFER
              </button>
            </div>
            <button onClick={handleAddNote} className="w-full bg-gray-100 hover:bg-gray-200 text-gray-700 font-semibold py-3 rounded-xl mt-1 border">
              Hanya Simpan Catatan (Janji Bayar)
            </button>
          </div>
        )}
      </div>
    </div>
  );
};

export default Collector;
