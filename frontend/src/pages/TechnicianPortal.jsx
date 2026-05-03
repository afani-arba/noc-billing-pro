import React, { useState, useEffect } from 'react';
import api from '@/lib/api';
import { useAuth } from '@/App';

const TechnicianPortal = () => {
  const { user } = useAuth();
  const [workOrders, setWorkOrders] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedWO, setSelectedWO] = useState(null);
  
  // Provision Form State
  const [provisionData, setProvisionData] = useState({
    username: '', password: '', package_id: '', device_id: ''
  });
  const [packages, setPackages] = useState([]);
  const [devices, setDevices] = useState([]);

  useEffect(() => {
    fetchWorkOrders();
    fetchOptions();
  }, []);

  const fetchWorkOrders = async () => {
    try {
      const res = await api.get("/technician/work-orders");
      if (res.data.ok) setWorkOrders(res.data.data);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const fetchOptions = async () => {
    try {
      const [pkgRes, devRes] = await Promise.all([
        api.get("/billing/packages"),
        api.get("/devices")
      ]);
      setPackages(pkgRes.data);
      setDevices(devRes.data);
    } catch (err) {
      console.error(err);
    }
  };

  const updateStatus = async (wo_id, status) => {
    try {
      await api.patch(`/technician/work-orders/${wo_id}`, { status });
      fetchWorkOrders();
      if(selectedWO && selectedWO.id === wo_id) setSelectedWO({...selectedWO, status});
      alert(`Status diperbarui menjadi ${status}`);
    } catch (err) {
      alert("Gagal update status");
    }
  };

  const handleProvision = async (e) => {
    e.preventDefault();
    try {
      await api.post("/technician/provision", {
        ...provisionData,
        name: selectedWO?.customer_name || 'Pelanggan Baru',
        phone: selectedWO?.customer_phone || '',
        address: selectedWO?.customer_address || '',
        work_order_id: selectedWO?.id
      });
      alert("Provisioning Sukses! Pelanggan didaftarkan.");
      fetchWorkOrders();
      setSelectedWO(null);
    } catch (err) {
      alert(err.response?.data?.detail || "Gagal provisioning");
    }
  };

  if (!user || (user.role !== 'teknisi' && user.role !== 'administrator' && user.role !== 'super_admin')) {
    return <div className="p-8 text-center text-red-500">Akses Ditolak. Halaman ini khusus Teknisi.</div>;
  }

  return (
    <div className="p-4 max-w-4xl mx-auto">
      <h1 className="text-2xl font-bold mb-6">Portal Teknisi Lapangan</h1>
      
      {loading ? <p>Loading data...</p> : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {/* Daftar Tugas */}
          <div className="bg-white p-4 rounded shadow">
            <h2 className="text-lg font-semibold mb-4">Daftar Tugas (Work Orders)</h2>
            {workOrders.length === 0 ? <p className="text-gray-500">Tidak ada tugas saat ini.</p> : (
              <div className="space-y-4">
                {workOrders.map(wo => (
                  <div key={wo.id} className="border p-4 rounded hover:bg-gray-50 cursor-pointer" onClick={() => setSelectedWO(wo)}>
                    <div className="flex justify-between items-center mb-2">
                      <span className="font-bold text-blue-600">{wo.id}</span>
                      <span className={`px-2 py-1 text-xs rounded text-white ${wo.status === 'completed' ? 'bg-green-500' : wo.status === 'working' ? 'bg-orange-500' : 'bg-gray-500'}`}>
                        {wo.status.toUpperCase()}
                      </span>
                    </div>
                    <p className="text-sm font-semibold">{wo.customer_name}</p>
                    <p className="text-xs text-gray-600">{wo.customer_address}</p>
                    <p className="text-xs text-gray-500 mt-2">Tipe: {wo.type}</p>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Detail & Action */}
          {selectedWO && (
            <div className="bg-white p-4 rounded shadow flex flex-col gap-4">
              <h2 className="text-lg font-semibold">Detail Tugas</h2>
              <div className="text-sm bg-gray-50 p-3 rounded">
                <p><strong>Nama:</strong> {selectedWO.customer_name}</p>
                <p><strong>Telepon:</strong> {selectedWO.customer_phone}</p>
                <p><strong>Alamat:</strong> {selectedWO.customer_address}</p>
                <p><strong>Deskripsi:</strong> {selectedWO.description}</p>
              </div>

              <div className="flex gap-2">
                <button onClick={() => updateStatus(selectedWO.id, 'on_the_way')} className="flex-1 bg-blue-500 text-white py-2 rounded">Otw</button>
                <button onClick={() => updateStatus(selectedWO.id, 'working')} className="flex-1 bg-orange-500 text-white py-2 rounded">Kerjakan</button>
                <button onClick={() => updateStatus(selectedWO.id, 'completed')} className="flex-1 bg-green-500 text-white py-2 rounded">Selesai</button>
              </div>

              {selectedWO.type === 'pasang_baru' && selectedWO.status !== 'completed' && (
                <div className="mt-4 border-t pt-4">
                  <h3 className="font-bold mb-2">Aktivasi PPPoE (Provision)</h3>
                  <form onSubmit={handleProvision} className="flex flex-col gap-3 text-sm">
                    <input required placeholder="PPPoE Username" className="border p-2 rounded" value={provisionData.username} onChange={e => setProvisionData({...provisionData, username: e.target.value})} />
                    <input required placeholder="PPPoE Password" type="password" className="border p-2 rounded" value={provisionData.password} onChange={e => setProvisionData({...provisionData, password: e.target.value})} />
                    
                    <select required className="border p-2 rounded" value={provisionData.package_id} onChange={e => setProvisionData({...provisionData, package_id: e.target.value})}>
                      <option value="">Pilih Paket...</option>
                      {packages.map(p => <option key={p.id} value={p.id}>{p.name} (Rp{p.price})</option>)}
                    </select>

                    <select required className="border p-2 rounded" value={provisionData.device_id} onChange={e => setProvisionData({...provisionData, device_id: e.target.value})}>
                      <option value="">Pilih Router MikroTik...</option>
                      {devices.map(d => <option key={d.id} value={d.id}>{d.name} ({d.ip_address})</option>)}
                    </select>

                    <button type="submit" className="bg-purple-600 text-white font-bold py-2 rounded mt-2">Buat Pelanggan & Aktifkan</button>
                  </form>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default TechnicianPortal;
