import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { useAuth } from '../context/AuthContext';
import { API_BASE_URL } from '../config';

const Technician = () => {
  const { user, logout } = useAuth();
  const [workOrders, setWorkOrders] = useState([]);
  const [poolOrders, setPoolOrders] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedWO, setSelectedWO] = useState(null);
  
  const [provisionData, setProvisionData] = useState({
    username: '', password: '', package_id: '', device_id: ''
  });
  const [packages, setPackages] = useState([]);
  const [devices, setDevices] = useState([]);
  
  // Refs for audio and previous state
  const prevPoolLength = React.useRef(0);
  const audioNewRef = React.useRef(new Audio('https://assets.mixkit.co/active_storage/sfx/2869/2869-preview.mp3')); // Ding sound
  const audioAlarmRef = React.useRef(new Audio('https://assets.mixkit.co/active_storage/sfx/995/995-preview.mp3')); // Alarm sound

  useEffect(() => {
    fetchWorkOrders();
    fetchOptions();
    
    // Auto refresh every 30 seconds
    const interval = setInterval(() => {
      fetchWorkOrders();
    }, 30000);
    return () => clearInterval(interval);
  }, []);

  const fetchWorkOrders = async () => {
    try {
      const res = await axios.get(`${API_BASE_URL}/technician/work-orders`);
      if (res.data.ok) {
        setWorkOrders(res.data.my_orders || res.data.data);
        const newPool = res.data.pool_orders || [];
        setPoolOrders(newPool);
        
        // Sound Notification Logic
        if (newPool.length > prevPoolLength.current) {
          audioNewRef.current.play().catch(e => console.log('Audio play blocked:', e));
        }
        prevPoolLength.current = newPool.length;
        
        // Check for tickets older than 1 hour (3600000 ms)
        const hasOverdue = newPool.some(wo => {
           const ageMs = Date.now() - new Date(wo.created_at).getTime();
           return ageMs > 3600000;
        });
        
        if (hasOverdue) {
           audioAlarmRef.current.play().catch(e => console.log('Audio play blocked:', e));
        }
      }
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const claimTask = async (wo_id) => {
    try {
      await axios.post(`${API_BASE_URL}/technician/work-orders/${wo_id}/claim`);
      alert("Tugas berhasil diambil!");
      fetchWorkOrders();
    } catch (err) {
      alert(err.response?.data?.detail || "Gagal mengambil tugas");
    }
  };

  const fetchOptions = async () => {
    try {
      const [pkgRes, devRes] = await Promise.all([
        axios.get(`${API_BASE_URL}/billing/packages`),
        axios.get(`${API_BASE_URL}/devices`)
      ]);
      setPackages(pkgRes.data);
      setDevices(devRes.data);
    } catch (err) {
      console.error(err);
    }
  };

  const updateStatus = async (wo_id, status) => {
    try {
      await axios.patch(`${API_BASE_URL}/technician/work-orders/${wo_id}`, { status });
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
      await axios.post(`${API_BASE_URL}/technician/provision`, {
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

  return (
    <div className="flex flex-col h-screen bg-gray-100">
      <div className="bg-blue-600 p-4 text-white flex justify-between items-center shadow-md">
        <div>
          <h1 className="font-bold text-lg">Portal Teknisi</h1>
          <p className="text-xs text-blue-200">{user?.username}</p>
        </div>
        <button onClick={logout} className="text-xs bg-blue-700 px-3 py-1.5 rounded-full hover:bg-blue-800">Logout</button>
      </div>
      
      <div className="flex-1 overflow-y-auto p-4">
        {loading ? <p className="text-center mt-10">Loading data...</p> : !selectedWO ? (
          <div className="flex flex-col gap-6">
            <div>
              <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wider mb-3">Tugas Saya (Aktif)</h2>
              {workOrders.length === 0 ? <p className="text-gray-500 text-center mt-2">Tidak ada tugas.</p> : (
                <div className="space-y-3">
                  {workOrders.map(wo => (
                    <div key={wo.id} className="bg-white border-l-4 border-blue-500 p-4 rounded-xl shadow-sm" onClick={() => setSelectedWO(wo)}>
                      <div className="flex justify-between items-center mb-2">
                        <span className="font-bold text-gray-800">{wo.customer_name || 'Pelanggan'}</span>
                        <span className={`px-2 py-0.5 text-[10px] font-bold rounded-full text-white ${wo.status === 'completed' ? 'bg-green-500' : wo.status === 'working' ? 'bg-orange-500' : 'bg-blue-500'}`}>
                          {wo.status.toUpperCase()}
                        </span>
                      </div>
                      <p className="text-xs text-gray-600 mb-1 line-clamp-1">{wo.customer_address}</p>
                      <p className="text-xs font-medium text-blue-600">{wo.task_type || (wo.type === 'pasang_baru' ? 'Pasang Baru' : 'Gangguan')}</p>
                    </div>
                  ))}
                </div>
              )}
            </div>

            <div>
              <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wider mb-3">Antrean Tiket Baru</h2>
              {poolOrders.length === 0 ? <p className="text-gray-500 text-center mt-2">Belum ada tugas baru.</p> : (
                <div className="space-y-3">
                  {poolOrders.map(wo => (
                    <div key={wo.id} className="bg-white border-l-4 border-gray-300 p-4 rounded-xl shadow-sm flex flex-col gap-2">
                      <div className="flex justify-between items-center">
                        <span className="font-bold text-gray-800">{wo.customer_name || 'Pelanggan'}</span>
                        <button onClick={() => claimTask(wo.id)} className="bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-bold py-1 px-3 rounded shadow">
                          Ambil Tugas
                        </button>
                      </div>
                      <p className="text-xs text-gray-600 line-clamp-2">{wo.notes}</p>
                      <div className="flex justify-between text-xs text-gray-500 mt-1 border-t pt-2">
                        <span>{wo.task_type || 'Gangguan'}</span>
                        <span>{new Date(wo.created_at).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})}</span>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        ) : (
          <div className="bg-white p-4 rounded-xl shadow-sm flex flex-col gap-4">
            <button onClick={() => setSelectedWO(null)} className="text-blue-600 text-sm font-semibold mb-2">← Kembali ke Daftar</button>
            <h2 className="text-lg font-bold border-b pb-2">Detail Tugas</h2>
            
            <div className="text-sm space-y-1">
              <p><strong>Nama:</strong> {selectedWO.customer_name}</p>
              <p><strong>Telepon:</strong> {selectedWO.customer_phone}</p>
              <p><strong>Alamat:</strong> {selectedWO.customer_address}</p>
              <p className="mt-2 text-gray-600 whitespace-pre-wrap">{selectedWO.notes || selectedWO.description}</p>
            </div>

            <div className="grid grid-cols-3 gap-2 mt-2">
              <button onClick={() => updateStatus(selectedWO.id, 'on_the_way')} className="bg-blue-100 text-blue-700 py-2 rounded-lg text-sm font-semibold border border-blue-200">Otw</button>
              <button onClick={() => updateStatus(selectedWO.id, 'working')} className="bg-orange-100 text-orange-700 py-2 rounded-lg text-sm font-semibold border border-orange-200">Kerja</button>
              <button onClick={() => updateStatus(selectedWO.id, 'completed')} className="bg-green-100 text-green-700 py-2 rounded-lg text-sm font-semibold border border-green-200">Selesai</button>
            </div>

            {selectedWO.type === 'pasang_baru' && selectedWO.status !== 'completed' && (
              <div className="mt-4 border-t pt-4">
                <h3 className="font-bold mb-3 text-purple-700">Aktivasi PPPoE (Provision)</h3>
                <form onSubmit={handleProvision} className="flex flex-col gap-3 text-sm">
                  <input required placeholder="PPPoE Username" className="border p-2.5 rounded-lg bg-gray-50 outline-none focus:ring-2 focus:ring-purple-500" value={provisionData.username} onChange={e => setProvisionData({...provisionData, username: e.target.value})} />
                  <input required placeholder="PPPoE Password" type="password" className="border p-2.5 rounded-lg bg-gray-50 outline-none focus:ring-2 focus:ring-purple-500" value={provisionData.password} onChange={e => setProvisionData({...provisionData, password: e.target.value})} />
                  
                  <select required className="border p-2.5 rounded-lg bg-gray-50 outline-none focus:ring-2 focus:ring-purple-500" value={provisionData.package_id} onChange={e => setProvisionData({...provisionData, package_id: e.target.value})}>
                    <option value="">Pilih Paket...</option>
                    {packages.map(p => <option key={p.id} value={p.id}>{p.name} (Rp{p.price})</option>)}
                  </select>

                  <select required className="border p-2.5 rounded-lg bg-gray-50 outline-none focus:ring-2 focus:ring-purple-500" value={provisionData.device_id} onChange={e => setProvisionData({...provisionData, device_id: e.target.value})}>
                    <option value="">Pilih Router MikroTik...</option>
                    {devices.map(d => <option key={d.id} value={d.id}>{d.name} ({d.ip_address})</option>)}
                  </select>

                  <button type="submit" className="bg-purple-600 text-white font-bold py-3 rounded-lg mt-2 shadow-md hover:bg-purple-700">Buat Akun & Aktifkan</button>
                </form>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};

export default Technician;
