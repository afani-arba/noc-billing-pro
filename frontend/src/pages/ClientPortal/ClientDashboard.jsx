import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { Card } from '../../components/ui/card';
import { registerPushNotifications } from '../../lib/pushNotifications';
import { Capacitor } from '@capacitor/core';
import { Preferences } from '@capacitor/preferences';
import { PushNotifications } from '@capacitor/push-notifications';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { ResponsiveContainer, AreaChart, Area, XAxis, YAxis, Tooltip, CartesianGrid } from 'recharts';
import { printInvoiceWithProfile } from '../../lib/printUtils';
import {
  LogOut, Wifi, WifiOff, Smartphone, CreditCard, Activity, AlertTriangle,
  ShieldCheck, X, Thermometer, Clock, Signal, Zap, Eye, EyeOff, RefreshCw, Network,
  RotateCcw, Bell, Timer, MessageCircle, FileUp, Pause, ArrowUpCircle, Printer, User, Box, Calendar, Ticket, BookOpen, CreditCard as PaymentIcon,
  Home, Monitor
} from 'lucide-react';

/* ─── Helpers ────────────────────────────────────────────────────────────── */
function formatUptime(seconds) {
  if (!seconds && seconds !== 0) return '—';
  const secs = parseInt(seconds, 10);
  if (isNaN(secs) || secs <= 0) return '—';
  const d = Math.floor(secs / 86400);
  const h = Math.floor((secs % 86400) / 3600);
  const m = Math.floor((secs % 3600) / 60);
  if (d > 0) return `${d}h ${h}m`;
  if (h > 0) return `${h}h ${m}m`;
  return `${m}m`;
}

/* ─── Sub Component: Live Traffic Graph ──────────────────────────────────── */
function LiveTrafficGraph({ token }) {
  const [traffic, setTraffic] = useState([]);
  const [error, setError] = useState(false);

  useEffect(() => {
    let interval;
    const fetchTraffic = async () => {
      try {
        const res = await axios.get('/api/client-portal/traffic', { headers: { Authorization: `Bearer ${token}` } });
        setTraffic(prev => {
          // Fix Issue 2: convert bps to Mbps
          const rxMbps = res.data.rx_bps ? parseFloat((res.data.rx_bps / 1000000).toFixed(2)) : 0;
          const txMbps = res.data.tx_bps ? parseFloat((res.data.tx_bps / 1000000).toFixed(2)) : 0;
          
          const newData = [...prev, { time: new Date().toLocaleTimeString('id-ID', { hour12: false }), rx: rxMbps, tx: txMbps }];
          if (newData.length > 20) newData.shift();
          return newData;
        });
        setError(false);
      } catch (err) {
        setError(true);
      }
    };
    fetchTraffic();
    interval = setInterval(fetchTraffic, 3000);
    return () => clearInterval(interval);
  }, [token]);

  if (error) return null;

  return (
    <div className="bg-white rounded-[24px] shadow-sm border border-slate-100 p-3 mt-4">
       <div className="h-28 w-full text-xs">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={traffic} margin={{ top: 0, right: 0, left: -20, bottom: 0 }}>
              <defs>
                <linearGradient id="colorRx" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#10b981" stopOpacity={0.4}/>
                  <stop offset="95%" stopColor="#10b981" stopOpacity={0}/>
                </linearGradient>
                <linearGradient id="colorTx" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.4}/>
                  <stop offset="95%" stopColor="#3b82f6" stopOpacity={0}/>
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" opacity={0.5} vertical={true} horizontal={false} />
              <XAxis dataKey="time" stroke="#94a3b8" opacity={0.8} tick={{fill: '#94a3b8', fontSize: 10}} minTickGap={20} axisLine={false} tickLine={false} />
              <YAxis stroke="#94a3b8" opacity={0.8} tick={{fill: '#94a3b8', fontSize: 10}} tickFormatter={(val) => `${val}M`} axisLine={false} tickLine={false} />
              <Tooltip contentStyle={{backgroundColor: '#fff', borderColor: '#e2e8f0', fontSize: '12px', borderRadius: '12px'}} itemStyle={{color: '#1e293b'}} labelStyle={{color: '#64748b'}} />
              <Area type="monotone" name="Upload" dataKey="rx" stroke="#10b981" strokeWidth={2} fillOpacity={1} fill="url(#colorRx)" isAnimationActive={false} />
              <Area type="monotone" name="Download" dataKey="tx" stroke="#3b82f6" strokeWidth={2} fillOpacity={1} fill="url(#colorTx)" isAnimationActive={false} />
            </AreaChart>
          </ResponsiveContainer>
       </div>
       <div className="flex justify-between text-[11px] text-slate-400 mt-2 px-2 font-medium">
          <span>Download: <strong className="text-blue-500">{(traffic[traffic.length - 1]?.tx || 0)} Mb/s</strong></span>
          <span>Upload: <strong className="text-emerald-500">{(traffic[traffic.length - 1]?.rx || 0)} Mb/s</strong></span>
       </div>
    </div>
  );
}

/* ─── Sub Component: Chat / Tiket Pengaduan (v2 — AI + riwayat + polling) ─── */
function TicketSupportChat({ token, open, setOpen, data }) {
  const [messages, setMessages] = React.useState([]);
  const [hasLoadedHistory, setHasLoadedHistory] = React.useState(false);
  const [input, setInput] = React.useState('');
  const [sending, setSending] = React.useState(false);
  const chatEndRef = React.useRef(null);
  const pollRef = React.useRef(null);

  useEffect(() => { chatEndRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [messages]);

  // Load riwayat chat saat dibuka
  useEffect(() => {
    if (!open || hasLoadedHistory) return;
    const loadHistory = async () => {
      try {
        const res = await axios.get('/api/client-portal/chat/history', { headers: { Authorization: `Bearer ${token}` } });
        const msgs = res.data.messages || [];
        if (msgs.length === 0) {
          setMessages([{ sender: 'AI', text: 'Halo! Ada yang bisa kami bantu? Anda juga bisa kirim foto jika ada masalah dengan perangkat.' }]);
        } else {
          const flat = [];
          for (const m of msgs) {
            if (m.sender === 'client') {
              flat.push({ sender: 'User', text: m.message, image: m.image_base64 || null, ts: m.timestamp });
              if (m.ai_reply) flat.push({ sender: 'AI', text: m.ai_reply, ts: m.timestamp, action: m.action_taken });
            } else if (m.sender === 'cs') {
              flat.push({ sender: 'CS', text: m.message, csName: m.cs_name, ts: m.timestamp });
            }
          }
          setMessages(flat);
        }
        setHasLoadedHistory(true);
      } catch {
        setMessages([{ sender: 'AI', text: 'Halo! Ada yang bisa kami bantu?' }]);
        setHasLoadedHistory(true);
      }
    };
    loadHistory();
  }, [open, token, hasLoadedHistory]);

  // Polling 5 detik untuk balasan CS baru
  useEffect(() => {
    if (!open) { clearInterval(pollRef.current); return; }
    pollRef.current = setInterval(async () => {
      try {
        const res = await axios.get('/api/client-portal/chat/history', { headers: { Authorization: `Bearer ${token}` } });
        const msgs = res.data.messages || [];
        const flat = [];
        for (const m of msgs) {
          if (m.sender === 'client') {
            flat.push({ sender: 'User', text: m.message, image: m.image_base64 || null, ts: m.timestamp });
            if (m.ai_reply) flat.push({ sender: 'AI', text: m.ai_reply, ts: m.timestamp, action: m.action_taken });
          } else if (m.sender === 'cs') {
            flat.push({ sender: 'CS', text: m.message, csName: m.cs_name, ts: m.timestamp });
          }
        }
        if (flat.length > 0) {
          setMessages(prev => {
            if (prev.length !== flat.length) return flat;
            const lastP = prev[prev.length - 1];
            const lastF = flat[flat.length - 1];
            if (lastP?.text !== lastF?.text || lastP?.sender !== lastF?.sender) return flat;
            return prev;
          });
        }
      } catch {}
    }, 5000);
    return () => clearInterval(pollRef.current);
  }, [open, token]);

  const handleSend = async (imageFile = null) => {
    if (!input.trim() && !imageFile) return;
    const msgText = input;
    setInput('');
    setSending(true);
    let b64 = null;
    if (imageFile) {
      const reader = new FileReader();
      b64 = await new Promise(r => { reader.onload = () => r(reader.result); reader.readAsDataURL(imageFile); });
    }
    setMessages(prev => [...prev, { sender: 'User', text: msgText, image: imageFile ? URL.createObjectURL(imageFile) : null }]);
    setMessages(prev => [...prev, { sender: 'AI', typing: true }]);
    try {
      const res = await axios.post('/api/client-portal/chat/send',
        { message: msgText, image_base64: b64 },
        { headers: { Authorization: `Bearer ${token}` } }
      );
      const reply = res.data.ai_reply || null;
      const action = res.data.action_taken || null;
      setMessages(prev => {
        const w = prev.filter(m => !m.typing);
        if (reply) return [...w, { sender: 'AI', text: reply, action }];
        return [...w, { sender: 'AI', text: 'Pesan diterima. Tim kami akan segera merespons.' }];
      });
    } catch {
      setMessages(prev => [...prev.filter(m => !m.typing), { sender: 'AI', text: 'Maaf, terjadi gangguan sementara.' }]);
    }
    setSending(false);
  };

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-[100] flex flex-col bg-slate-50 animate-in slide-in-from-bottom duration-300">
      <div className="flex justify-between items-center p-4 bg-[#1e3a8a] text-white">
        <div>
          <h3 className="font-semibold flex items-center gap-2"><MessageCircle className="w-5 h-5 text-blue-200"/> Support & Chat</h3>
          <p className="text-[11px] text-blue-200">Admin · Escalate ke Tim NOC jika perlu</p>
        </div>
        <button onClick={() => setOpen(false)} className="text-white/70 hover:text-white p-2 rounded-xl transition-colors"><X className="w-5 h-5"/></button>
      </div>
      <div className="flex-1 overflow-y-auto p-4 space-y-3 pb-24 bg-slate-100">
        {messages.map((m, i) => (
          <div key={i}>
            <div className={`flex ${m.sender === 'User' ? 'justify-end' : 'justify-start'}`}>
              {(m.sender === 'AI' || m.sender === 'CS') && (
                <div className={`w-7 h-7 rounded-full flex-shrink-0 flex items-center justify-center text-white text-xs font-bold mr-2 mt-1 ${m.sender === 'CS' ? 'bg-emerald-500' : 'bg-[#1e3a8a]'}`}>
                  {m.sender === 'CS' ? (m.csName?.[0] || 'C') : (data?.platform_settings?.ai_name?.[0] || 'A').toUpperCase()}
                </div>
              )}
              <div className="max-w-[80%]">
                {m.sender === 'CS' && <p className="text-[10px] text-emerald-600 font-semibold mb-0.5 ml-1">{m.csName || 'CS NOC'}</p>}
                {m.sender === 'AI' && <p className="text-[10px] text-blue-800 font-semibold mb-0.5 ml-1">{data?.platform_settings?.ai_name || 'AI'}</p>}
                <div className={`rounded-2xl p-3 text-sm shadow-sm ${
                  m.sender === 'User' ? 'bg-[#1e3a8a] text-white rounded-tr-none' :
                  m.sender === 'CS' ? 'bg-emerald-50 text-slate-700 rounded-tl-none border border-emerald-200' :
                  'bg-white text-slate-700 rounded-tl-none border border-slate-200'
                }`}>
                  {m.image && <img src={m.image} className="w-full rounded-lg mb-2 object-cover max-h-40" alt="foto" />}
                  {m.typing ? (
                    <div className="flex gap-1 items-center py-1">
                      <span className="w-2 h-2 bg-slate-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                      <span className="w-2 h-2 bg-slate-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                      <span className="w-2 h-2 bg-slate-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
                    </div>
                  ) : (
                    <p className="whitespace-pre-wrap">{m.text}</p>
                  )}
                </div>
                {m.action === 'modem_reprovisioned' && <p className="text-[10px] text-blue-600 mt-1 ml-1">🔄 Konfigurasi modem dikirim ulang otomatis</p>}
                {m.action === 'cable_issue' && <p className="text-[10px] text-red-600 mt-1 ml-1">📡 Tim NOC sudah dihubungi via Telegram</p>}
              </div>
            </div>
          </div>
        ))}
        <div ref={chatEndRef} />
      </div>
      <div className="p-4 bg-white border-t border-slate-200 flex items-center gap-2 pb-6 fixed bottom-0 w-full shadow-lg">
        <label className="cursor-pointer text-slate-400 hover:text-blue-600 p-2 transition-colors flex-shrink-0">
          <FileUp className="w-6 h-6"/>
          <input type="file" accept="image/*" className="hidden" onChange={e => { if(e.target.files[0]) handleSend(e.target.files[0]); }} />
        </label>
        <Input value={input} onChange={e => setInput(e.target.value)} onKeyDown={e => { if(e.key === 'Enter') handleSend(); }}
          placeholder="Ketik pesan atau kirim foto..." disabled={sending}
          className="bg-slate-100 border-transparent text-slate-800 h-11 rounded-full flex-1 focus-visible:ring-indigo-500 shadow-none"/>
        <Button onClick={() => handleSend()} disabled={sending || !input.trim()} className="bg-[#1e3a8a] hover:bg-blue-800 text-white h-11 w-11 p-0 rounded-full flex-shrink-0 shadow-md">
          <svg className="w-5 h-5 transform rotate-90 ml-1" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8"></path></svg>
        </Button>
      </div>
    </div>
  );
}


/* ─── Sub Component: Layanan Modals ──────────────────────────────────────── */
function PauseModal({ open, onClose, onConfirm, pausing, msg }) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-slate-900/40 backdrop-blur-sm">
      <div className="bg-white border border-slate-100 rounded-3xl w-full max-w-sm overflow-hidden shadow-2xl p-6 space-y-4 animate-in zoom-in-95 duration-200">
         <h3 className="font-bold text-slate-800 flex items-center gap-2 text-lg"><Calendar className="w-5 h-5 text-orange-500"/> Extend Time (Cuti)</h3>
         <p className="text-slate-500 text-sm">
            Mengajukan cuti berarti <strong>invoice baru tidak akan diterbitkan bulan depan</strong> dan layanan akan <strong>dihentikan sementara</strong>. Anda bisa mengaktifkan kembali sewaktu-waktu.
         </p>
         {msg.text && (
            <div className={`p-3 rounded-xl text-sm font-medium ${msg.type === 'error' ? 'bg-red-50 text-red-600' : 'bg-emerald-50 text-emerald-600'}`}>
               {msg.text}
            </div>
         )}
         <div className="flex gap-3 pt-2">
            <Button onClick={onClose} variant="outline" className="flex-1 rounded-xl h-12 text-slate-600 font-semibold border-slate-200">Batal</Button>
            <Button onClick={onConfirm} disabled={pausing} className="flex-1 rounded-xl bg-orange-500 hover:bg-orange-600 h-12 text-white font-bold shadow-md shadow-orange-200">
               {pausing ? 'Tunggu...' : 'Ajukan'}
            </Button>
         </div>
      </div>
    </div>
  );
}

function UpgradeModal({ open, onClose, packages, selectedPkg, setSelectedPkg, onConfirm, upgrading, msg }) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-slate-900/40 backdrop-blur-sm">
      <div className="bg-white border border-slate-100 rounded-3xl w-full max-w-sm overflow-hidden shadow-2xl p-6 space-y-4 flex flex-col max-h-[80vh] animate-in zoom-in-95 duration-200">
         <div className="flex justify-between items-center">
            <h3 className="font-bold text-slate-800 flex items-center gap-2 text-lg"><Box className="w-5 h-5 text-blue-500"/> Change Package</h3>
            <button onClick={onClose} className="text-slate-400 hover:text-slate-600"><X className="w-5 h-5"/></button>
         </div>
         <p className="text-slate-500 text-sm">Pilih paket baru. Perubahan ini akan dijadwalkan otomatis pada tagihan bulan berikutnya.</p>
         
         <div className="flex-1 overflow-y-auto space-y-3 pr-1 py-1">
            {packages.map(p => (
               <div key={p.id} onClick={() => setSelectedPkg(p.id)} className={`p-4 rounded-2xl border-2 cursor-pointer transition-all ${selectedPkg === p.id ? 'bg-blue-50 border-blue-500 shadow-sm' : 'bg-white border-slate-100 hover:border-blue-200'}`}>
                  <p className="text-slate-800 font-bold">{p.name}</p>
                  <p className="text-blue-600 font-semibold text-sm">Rp {Number(p.price).toLocaleString('id-ID')} / bln</p>
                  {(p.speed_up || p.speed_down) && <p className="text-slate-500 text-xs mt-1 font-medium">{p.speed_down} Mbps - {p.fup_enabled ? p.fup_limit_gb + ' GB' : 'Unlimited'}</p>}
               </div>
            ))}
         </div>

         {msg.text && (
            <div className={`p-3 rounded-xl text-sm font-medium ${msg.type === 'error' ? 'bg-red-50 text-red-600' : 'bg-emerald-50 text-emerald-600'}`}>
               {msg.text}
            </div>
         )}
         <Button onClick={onConfirm} disabled={upgrading || !selectedPkg} className="w-full h-12 rounded-xl bg-blue-600 hover:bg-blue-700 text-white font-bold text-base shadow-md shadow-blue-200 shrink-0 mt-2">
            {upgrading ? 'Menyimpan...' : 'Ganti Paket'}
         </Button>
      </div>
    </div>
  );
}

/* ─── Main Component ─────────────────────────────────────────────────────── */
export default function ClientDashboard() {
  const [data, setData] = useState(null);
  const [wifiData, setWifiData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [wifiLoading, setWifiLoading] = useState(false);
  const [savingWifi, setSavingWifi] = useState(false);
  const [ssid, setSsid] = useState('');
  const [password, setPassword] = useState('');
  const [showPass, setShowPass] = useState(false);
  const [wifiMsg, setWifiMsg] = useState({ text: '', type: '' });
  const [paymentModalOpen, setPaymentModalOpen] = useState(false);
  const [selectedInvoice, setSelectedInvoice] = useState(null);
  const [rebooting, setRebooting] = useState(false);
  const [rebootMsg, setRebootMsg] = useState({ text: '', type: '' });
  const [rebootConfirm, setRebootConfirm] = useState(false);
  const [inAppNotif, setInAppNotif] = useState(null);

  const [pauseModalOpen, setPauseModalOpen] = useState(false);
  const [upgradeModalOpen, setUpgradeModalOpen] = useState(false);
  const [chatOpen, setChatOpen] = useState(false);
  const [notifOpen, setNotifOpen] = useState(false);
  const [wifiSettingOpen, setWifiSettingOpen] = useState(false);

  const [availablePackages, setAvailablePackages] = useState([]);
  const [pausing, setPausing] = useState(false);
  const [pauseMsg, setPauseMsg] = useState({ text: '', type: '' });
  const [upgrading, setUpgrading] = useState(false);
  const [upgradeMsg, setUpgradeMsg] = useState({ text: '', type: '' });
  const [selectedPkgId, setSelectedPkgId] = useState('');

  const navigate = useNavigate();
  const [token, setToken] = useState(null);
  const [tokenLoaded, setTokenLoaded] = useState(false);
  const baseUrl = '/api';

  useEffect(() => {
    const loadToken = async () => {
      let t = null;
      try {
        const { value } = await Preferences.get({ key: 'clientToken' });
        t = value;
      } catch (e) {}

      if (!t) {
        t = localStorage.getItem('clientToken');
      }
      setToken(t);
      setTokenLoaded(true);
    };
    loadToken();
  }, []);

  useEffect(() => {
    if (!tokenLoaded) return;
    if (!token) { navigate('/portal/login'); return; }

    const fetchDashboard = async () => {
      try {
        const res = await axios.get(`${baseUrl}/client-portal/dashboard`, {
          headers: { Authorization: `Bearer ${token}` }
        });
        setData(res.data);
      } catch (err) {
        if (err.response?.status === 401) {
          await Preferences.remove({ key: 'clientToken' });
          localStorage.removeItem('clientToken');
          navigate('/portal/login');
        } else {
          setError(err.message || "Gagal memuat data portal.");
        }
      } finally {
        setLoading(false);
      }
    };

    fetchDashboard();
    
    registerPushNotifications(token);

    let notifListenerHandle = null;
    let notifActionHandle = null;
    if (Capacitor.isNativePlatform()) {
      try {
        notifListenerHandle = PushNotifications.addListener('pushNotificationReceived', (notification) => {
          setInAppNotif({
            title: notification.title || 'NOC Sentinel',
            body: notification.body || '',
          });
          setTimeout(() => setInAppNotif(null), 6000);
        });
        notifActionHandle = PushNotifications.addListener('pushNotificationActionPerformed', () => {
          axios.get(`/api/client-portal/dashboard`, { headers: { Authorization: `Bearer ${token}` } })
            .then(r => setData(r.data))
            .catch(() => {});
        });
      } catch (pushErr) {
        console.warn('[Dashboard] Gagal mendaftarkan push listener:', pushErr);
      }
    }

    const refreshInterval = setInterval(async () => {
      try {
        const r1 = await axios.get(`/api/client-portal/dashboard`, { headers: { Authorization: `Bearer ${token}` } });
        setData(r1.data);
        const r2 = await axios.get(`/api/client-portal/wifi`, { headers: { Authorization: `Bearer ${token}` } });
        if (r2.data.ok) {
          setWifiData(r2.data);
          setSsid(prev => prev || r2.data.ssid || '');
        }
      } catch { /* silent fail */ }
    }, 60000);
    return () => {
      clearInterval(refreshInterval);
      if (notifListenerHandle?.remove) notifListenerHandle.remove();
      if (notifActionHandle?.remove) notifActionHandle.remove();
    };
    
  }, [token, tokenLoaded, baseUrl, navigate]);

  useEffect(() => {
    if (data && !wifiData && !wifiLoading) loadWifi();
  }, [data]); // eslint-disable-line

  const loadWifi = async () => {
    setWifiLoading(true);
    setWifiMsg({ text: '', type: '' });
    try {
      const res = await axios.get(`${baseUrl}/client-portal/wifi`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      if (res.data.ok) {
        setWifiData(res.data);
        setSsid(res.data.ssid || '');
        setPassword(res.data.password || '');
      } else {
        setWifiMsg({ text: res.data.error, type: 'error' });
      }
    } catch {
      setWifiMsg({ text: 'Gagal mengambil data Router.', type: 'error' });
    } finally { setWifiLoading(false); }
  };

  const saveWifi = async () => {
    setSavingWifi(true);
    setWifiMsg({ text: '', type: '' });
    try {
      if (password && password.length < 8) throw new Error('Password WiFi minimal 8 karakter');
      const res = await axios.post(`${baseUrl}/client-portal/wifi`, {
        device_id: wifiData.device_id, ssid, password
      }, { headers: { Authorization: `Bearer ${token}` } });
      setWifiMsg({ text: res.data.message || 'Sukses', type: 'success' });
    } catch (err) {
      setWifiMsg({ text: err.response?.data?.detail || err.message || 'Gagal menyimpan', type: 'error' });
    } finally { setSavingWifi(false); }
  };

  const handleReboot = async () => {
    setRebooting(true);
    setRebootMsg({ text: '', type: '' });
    try {
      const res = await axios.post(`${baseUrl}/client-portal/reboot`, {}, {
        headers: { Authorization: `Bearer ${token}` }
      });
      setRebootMsg({ text: res.data.message || 'Perintah dikirim', type: res.data.ok ? 'success' : 'error' });
      setTimeout(() => { setRebootConfirm(false); setRebootMsg({text:'', type:''}); }, 3000);
    } catch (err) {
      setRebootMsg({ text: err.response?.data?.detail || 'Gagal mengirim perintah restart', type: 'error' });
    } finally { setRebooting(false); }
  };

  useEffect(() => {
     if (upgradeModalOpen && availablePackages.length === 0) {
        axios.get(`${baseUrl}/client-portal/packages`, { headers: { Authorization: `Bearer ${token}` } })
            .then(res => setAvailablePackages(res.data.packages || []))
            .catch(() => {});
     }
  }, [upgradeModalOpen, availablePackages.length, baseUrl, token]);

  const handlePause = async () => {
    setPausing(true);
    setPauseMsg({ text: '', type: '' });
    try {
      const res = await axios.post(`${baseUrl}/client-portal/pause`, {}, { headers: { Authorization: `Bearer ${token}` } });
      setPauseMsg({ text: res.data.message || 'Sukses diajukan', type: 'success' });
      setTimeout(() => navigate(0), 2000);
    } catch (err) {
      setPauseMsg({ text: err.response?.data?.detail?.error || err.response?.data?.error || 'Gagal mengajukan cuti', type: 'error' });
    } finally { setPausing(false); }
  };

  const handleUpgrade = async () => {
    if (!selectedPkgId) return;
    setUpgrading(true);
    setUpgradeMsg({ text: '', type: '' });
    try {
      const res = await axios.post(`${baseUrl}/client-portal/change-package`, { package_id: selectedPkgId }, { headers: { Authorization: `Bearer ${token}` } });
      setUpgradeMsg({ text: res.data.message || 'Paket dijadwalkan berubah', type: 'success' });
      setTimeout(() => navigate(0), 2000);
    } catch (err) {
      setUpgradeMsg({ text: err.response?.data?.detail?.error || err.response?.data?.error || 'Gagal jadwal pindah paket', type: 'error' });
    } finally { setUpgrading(false); }
  };

  const handleLogout = async () => {
    await Preferences.remove({ key: 'clientToken' });
    localStorage.removeItem('clientToken');
    navigate('/portal/login');
  };

  const scrollToBilling = () => {
    document.getElementById('billingSection')?.scrollIntoView({ behavior: 'smooth' });
  };

  if (!tokenLoaded || loading) {
    return (
      <div className="min-h-screen bg-slate-50 flex justify-center items-center">
        <div className="flex flex-col items-center gap-4">
          <div className="w-10 h-10 border-4 border-blue-500 border-t-transparent rounded-full animate-spin" />
        </div>
      </div>
    );
  }

  if (error && !data) {
    return (
      <div className="min-h-screen bg-slate-50 flex flex-col justify-center items-center gap-4 p-6">
        <AlertTriangle className="w-14 h-14 text-red-500" />
        <p className="text-slate-800 font-bold text-xl text-center">Connection Error</p>
        <p className="text-slate-500 text-sm text-center font-medium">{error}</p>
        <button
          onClick={() => { setError(''); setLoading(true); navigate(0); }}
          className="mt-4 px-8 py-3 bg-[#1e3a8a] text-white rounded-full font-bold shadow-lg shadow-blue-900/20 active:scale-95 transition-transform"
        >
          Try Again
        </button>
      </div>
    );
  }

  if (!data) return null;

  const isIsolated = data.customer?.status === 'isolated';
  const hasUnpaid = data.unpaid_invoices && data.unpaid_invoices.length > 0;
  const isOnline = wifiData?.status === 'online';

  const notifications = [];
  if (hasUnpaid) {
    data.unpaid_invoices.forEach((inv, idx) => notifications.push({ id: `unpaid-${idx}`, title: 'Tagihan Belum Lunas', message: `Tagihan Anda dengan nomor ${inv.invoice_number} sejumlah Rp ${inv.total?.toLocaleString('id-ID')} belum lunas. Segera lakukan pembayaran.`, date: inv.due_date, type: 'alert' }));
  }
  if (data.upcoming_invoice && !hasUnpaid) {
    notifications.push({ id: 'upcoming', title: 'Tagihan Mendatang', message: `Tagihan bulan ini sejumlah Rp ${data.upcoming_invoice.amount?.toLocaleString('id-ID')} akan jatuh tempo pada ${new Date(data.upcoming_invoice.due_date).toLocaleDateString('id-ID')}.`, date: data.upcoming_invoice.due_date, type: 'info' });
  }
  if (isIsolated) {
    notifications.push({ id: 'isolir', title: 'Layanan Terisolir', message: 'Koneksi internet Anda sedang ditangguhkan. Silakan bayar tagihan untuk mengaktifkan.', date: new Date().toISOString(), type: 'alert' });
  }
  if (notifications.length === 0) {
    notifications.push({ id: 'sys-0', title: 'Sistem', message: 'Tidak ada pemberitahuan baru bulan ini. Jaringan internet Anda aman.', date: new Date().toISOString(), type: 'normal' });
  }

  return (
    <div className="min-h-[100dvh] bg-[#f0f4f8] text-slate-800 flex flex-col font-sans pb-[80px]">
      
      {/* ── Top Header Banner (Blue) ── */}
      <div className="bg-[#2b518c] rounded-b-[32px] pt-6 pb-6 px-4 shadow-md relative shrink-0">
         <div className="flex justify-between items-start mb-1 max-w-lg mx-auto">
            <div className="flex items-center gap-3">
               <div className="w-14 h-14 rounded-full bg-white/20 border-2 border-white/50 flex items-center justify-center shadow-inner overflow-hidden flex-shrink-0">
                  <User className="w-8 h-8 text-white" />
               </div>
               <div>
                  <h1 className="font-bold text-white text-xl tracking-tight">{data.customer?.name}</h1>
                  <p className="text-blue-100 text-sm font-medium mt-1">Client Code: {data.customer?.client_id || data.customer?.id?.slice(0,8)}</p>
                  <p className="text-blue-100 text-xs mt-1">Status : <span className={isIsolated ? "text-[#fca5a5] font-bold" : "text-white font-bold"}>{isIsolated ? 'Terisolir' : 'Terhubung'}</span></p>
               </div>
            </div>
            <div className="flex flex-col items-end gap-3 mt-1 mr-1">
               <div className="flex gap-5 items-center">
                 <button onClick={() => setNotifOpen(true)} className="text-white hover:opacity-80 transition-opacity relative">
                    <Bell className="w-6 h-6"/>
                    {(hasUnpaid || data.upcoming_invoice?.days_until_due <= 3) && <span className="absolute top-0 right-0 w-2.5 h-2.5 bg-red-500 border-2 border-[#2b518c] rounded-full"></span>}
                 </button>
                 <button onClick={handleLogout} className="text-white hover:opacity-80 transition-opacity">
                    <LogOut className="w-6 h-6 transform rotate-180" />
                 </button>
               </div>
            </div>
         </div>
      </div>

      {/* Main Content Area */}
      <div className="flex-1 px-4 -mt-4 z-10 w-full max-w-lg mx-auto space-y-3 pb-[80px] overflow-y-auto">
         
         {/* ── Main Action Icons ── */}
         <div className="grid grid-cols-4 gap-2 text-center mx-1">
            <div onClick={() => setWifiSettingOpen(true)} className="cursor-pointer group flex flex-col items-center">
               <div className="bg-[#fb7185] w-[60px] h-[60px] rounded-[18px] flex items-center justify-center mb-1.5 shadow-sm group-hover:-translate-y-1 transition-transform">
                  <Wifi className="text-white w-7 h-7" />
               </div>
               <span className="text-[11px] font-semibold text-slate-600 leading-tight">Ubah<br/>Sandi WiFi</span>
            </div>
            <div onClick={() => setRebootConfirm(true)} className="cursor-pointer group flex flex-col items-center">
               <div className="bg-[#3b82f6] w-[60px] h-[60px] rounded-[18px] flex items-center justify-center mb-1.5 shadow-sm group-hover:-translate-y-1 transition-transform">
                  <RotateCcw className="text-white w-7 h-7" />
               </div>
               <span className="text-[11px] font-semibold text-slate-600 leading-tight">Restart<br/>Modem</span>
            </div>
            <div onClick={scrollToBilling} className="cursor-pointer group flex flex-col items-center">
               <div className="bg-[#34d399] w-[60px] h-[60px] rounded-[18px] flex items-center justify-center mb-1.5 shadow-sm group-hover:-translate-y-1 transition-transform">
                  <PaymentIcon className="text-white w-7 h-7"/>
               </div>
               <span className="text-[11px] font-semibold text-slate-600 leading-tight">Riwayat<br/>Tagihan</span>
            </div>
            <div onClick={() => setChatOpen(true)} className="cursor-pointer group flex flex-col items-center">
               <div className="bg-[#fbbf24] w-[60px] h-[60px] rounded-[18px] flex items-center justify-center mb-1.5 shadow-sm group-hover:-translate-y-1 transition-transform">
                  <MessageCircle className="text-white w-7 h-7" />
               </div>
               <span className="text-[11px] font-semibold text-slate-600 leading-tight">Bantuan<br/>& Tiket</span>
            </div>
         </div>

         {/* ── Bill Info Card ── */}
         <div className="bg-white rounded-[24px] p-3 py-4 shadow-sm mx-1">
            <div className="grid grid-cols-2 gap-y-3 gap-x-2">
               <div className="flex bg-slate-50/50 p-2 rounded-xl">
                  <div className="w-10 h-10 flex-shrink-0 bg-blue-100/50 rounded-xl flex items-center justify-center mr-3"><BookOpen className="w-5 h-5 text-slate-600"/></div>
                  <div className="overflow-hidden">
                     <p className="text-[11px] text-slate-500 font-semibold mb-0.5">Tagihan Bulanan</p>
                     <p className="font-bold text-slate-800 text-sm truncate">Rp {(data.package?.price || 0).toLocaleString('id-ID')}</p>
                  </div>
               </div>
               <div className="flex bg-slate-50/50 p-2 rounded-xl">
                  <div className="w-10 h-10 flex-shrink-0 bg-blue-100/50 rounded-xl flex items-center justify-center mr-3"><Activity className="w-5 h-5 text-slate-600"/></div>
                  <div className="overflow-hidden">
                     <p className="text-[11px] text-slate-500 font-semibold mb-0.5 whitespace-nowrap">Dibayar di Muka</p>
                     <p className="font-bold text-slate-800 text-sm truncate">(0.0)</p>
                  </div>
               </div>
               <div className="flex bg-slate-50/50 p-2 rounded-xl">
                  <div className="w-10 h-10 flex-shrink-0 bg-blue-100/50 rounded-xl flex items-center justify-center mr-3"><Monitor className="w-5 h-5 text-slate-600"/></div>
                  <div className="overflow-hidden">
                     <p className="text-[11px] text-slate-500 font-semibold mb-0.5">Paket</p>
                     <p className="font-bold text-slate-800 text-sm truncate">{data.package?.name?.toUpperCase() || 'STANDARD'}</p>
                  </div>
               </div>
               <div className="flex bg-slate-50/50 p-2 rounded-xl">
                  <div className="w-10 h-10 flex-shrink-0 bg-blue-100/50 rounded-xl flex items-center justify-center mr-3"><Timer className="w-5 h-5 text-slate-600"/></div>
                  <div className="overflow-hidden">
                     <p className="text-[11px] text-slate-500 font-semibold mb-0.5">Jatuh Tempo</p>
                     <p className="font-bold text-slate-800 text-sm truncate">
                        {data.upcoming_invoice 
                           ? new Date(data.upcoming_invoice.due_date).toLocaleDateString('id-ID', { day: '2-digit', month: 'short', year: 'numeric' }) 
                           : (data.unpaid_invoices?.length > 0 && data.unpaid_invoices[0].due_date
                               ? new Date(data.unpaid_invoices[0].due_date).toLocaleDateString('id-ID', { day: '2-digit', month: 'short', year: 'numeric' })
                               : `Tgl ${data.customer?.due_day || 10} Tiap Bulan`)}
                     </p>
                  </div>
               </div>
            </div>
         </div>



         {/* ── Graph Section ── */}
         <div className="bg-white rounded-[24px] p-4 shadow-sm mx-1">
            <div className="grid grid-cols-4 gap-2 text-center items-center py-2">
               <div>
                  <div className="flex justify-center items-center gap-1.5 mb-1.5">
                     <Smartphone className="w-4 h-4 text-purple-500"/>
                     <span className="text-[10px] text-slate-500 font-bold uppercase tracking-wider">Pengguna</span>
                  </div>
                  <p className="font-black text-slate-800 text-sm">{(wifiData?.connected_devices) ? wifiData.connected_devices : '0'}</p>
               </div>
               <div className="border-l border-r border-slate-100">
                  <div className="flex justify-center items-center gap-1.5 mb-1.5">
                     <Signal className="w-4 h-4 text-emerald-500"/>
                     <span className="text-[10px] text-slate-500 font-bold uppercase tracking-wider">Redaman</span>
                  </div>
                  <p className="font-black text-slate-800 text-sm">{(wifiData?.rx_power) ? wifiData.rx_power : '0'} <span className="text-[10px] text-slate-500 font-semibold">dBm</span></p>
               </div>
               <div className="border-r border-slate-100">
                  <div className="flex justify-center items-center gap-1.5 mb-1.5">
                     <Thermometer className="w-4 h-4 text-rose-500"/>
                     <span className="text-[10px] text-slate-500 font-bold uppercase tracking-wider">Suhu</span>
                  </div>
                  <p className="font-black text-slate-800 text-sm">{(wifiData?.ont_temp) ? parseFloat(wifiData.ont_temp).toFixed(0) : '0'} <span className="text-[10px] text-slate-500 font-semibold">°C</span></p>
               </div>
               <div>
                  <div className="flex justify-center items-center gap-1.5 mb-1.5">
                     <Clock className="w-4 h-4 text-blue-500"/>
                     <span className="text-[10px] text-slate-500 font-bold uppercase tracking-wider">Aktif</span>
                  </div>
                  <p className="font-black text-slate-800 text-[10px] leading-tight uppercase font-mono tracking-tighter">{formatUptime(wifiData?.uptime)}</p>
               </div>
            </div>
            
            <LiveTrafficGraph token={token} />
         </div>

         {/* ── Unpaid Invoices List (Billing Section) ── */}
         <div id="billingSection" className="pt-1 mx-1">
            {hasUnpaid && data.unpaid_invoices.map((inv, idx) => (
              <div key={idx} className="bg-white border border-red-200 p-4 rounded-[20px] shadow-sm mb-3">
                <div className="flex justify-between items-start mb-3">
                  <div>
                     <span className="text-xs bg-red-100 text-red-600 px-2.5 py-1 rounded-md font-bold tracking-wide uppercase">
                        {inv.days_overdue > 0 ? `Telat ${inv.days_overdue} Hari` : 'Belum Lunas'}
                     </span>
                     <p className="text-sm text-slate-500 mt-2 font-mono font-medium">{inv.invoice_number}</p>
                  </div>
                  <p className="text-xl font-bold text-slate-800">Rp {inv.total?.toLocaleString('id-ID')}</p>
                </div>
                <div className="flex gap-3">
                   <Button size="sm" variant="outline" className="flex-1 bg-white border-slate-200 text-slate-700 font-bold h-11 rounded-xl shadow-sm hover:bg-slate-50" 
                      onClick={() => printInvoiceWithProfile(inv, data.package?.name, data.customer?.name, data.customer?.username, data.customer?.phone, data.customer?.address)}>
                      Cetak / Lihat
                   </Button>
                   <Button onClick={() => { setSelectedInvoice(inv); setPaymentModalOpen(true); }} className="flex-1 bg-[#2b518c] hover:bg-[#1e3a8a] text-white font-bold h-11 rounded-xl shadow-md">
                      Bayar Sekarang
                   </Button>
                </div>
              </div>
            ))}
            
            {!hasUnpaid && data.upcoming_invoice && (
               <div className="bg-white border border-slate-100 p-5 rounded-[24px] shadow-sm mb-4">
                  <span className="text-xs text-blue-600 font-bold uppercase tracking-wider bg-blue-50 px-2.5 py-1 rounded-md">Tagihan Mendatang</span>
                  <div className="flex justify-between items-end mt-4 mb-5">
                     <p className="text-xl font-bold text-slate-800">Rp {data.upcoming_invoice.amount?.toLocaleString('id-ID')}</p>
                     <p className="text-xs text-slate-500 font-medium whitespace-nowrap">Jatuh Tempo: {new Date(data.upcoming_invoice.due_date).toLocaleDateString('id-ID')}</p>
                  </div>
                  <Button onClick={() => { setSelectedInvoice(data.upcoming_invoice); setPaymentModalOpen(true); }} className="w-full bg-slate-50 hover:bg-slate-100 text-[#2b518c] border border-blue-200 font-bold h-12 rounded-xl shadow-sm">
                     Bayar Lebih Awal
                  </Button>
               </div>
            )}
         </div>

      </div>

      {/* ── Fixed Bottom Navbar ── */}
      <div className="fixed bottom-0 left-0 w-full bg-white border-t border-slate-200 px-6 py-2 pb-3 flex justify-evenly items-center z-40 md:justify-center md:gap-24 shadow-[0_-4px_10px_rgba(0,0,0,0.02)]">
         <div className="flex flex-col items-center gap-1 w-20 cursor-pointer text-[#2b518c] active:scale-95 transition-transform shrink-0">
            <Home className="w-[26px] h-[26px]" />
            <span className="text-[10px] font-bold">Beranda</span>
         </div>
         <div onClick={scrollToBilling} className="flex flex-col items-center gap-1 w-20 cursor-pointer text-slate-400 hover:text-slate-600 active:scale-95 transition-all shrink-0">
            <PaymentIcon className="w-[26px] h-[26px]" />
            <span className="text-[10px] font-bold mt-0.5 text-center leading-tight">Riwayat<br/>Tagihan</span>
         </div>
      </div>

      {/* ── Internal Overlays & Modals ── */}
      <TicketSupportChat token={token} open={chatOpen} setOpen={setChatOpen} data={data} />
      
      {/* Notifications Modal */}
      {notifOpen && (
        <div className="fixed inset-0 z-[100] flex flex-col bg-slate-50 animate-in slide-in-from-right duration-300">
           <div className="flex justify-between items-center p-5 bg-white border-b border-slate-100 shadow-sm z-10 shrink-0">
              <h3 className="font-bold text-slate-800 text-lg flex items-center gap-2.5">
                 Riwayat Notifikasi
                 {notifications.filter(n => n.type === 'alert').length > 0 && <span className="bg-red-500 text-white text-[10px] px-2 py-0.5 rounded-full">{notifications.filter(n => n.type === 'alert').length} Baru</span>}
              </h3>
              <button onClick={() => setNotifOpen(false)} className="text-slate-400 hover:text-slate-600 p-2 rounded-xl bg-slate-50"><X className="w-5 h-5"/></button>
           </div>
           <div className="flex-1 p-4 space-y-3 overflow-y-auto w-full max-w-lg mx-auto">
              {notifications.map((notif, i) => (
                 <div key={notif.id || i} className="bg-white p-4 rounded-2xl shadow-sm border border-slate-100 flex gap-4 items-start active:bg-slate-50 transition-colors">
                    <div className={`w-10 h-10 rounded-full flex items-center justify-center shrink-0 ${notif.type === 'alert' ? 'bg-red-50 text-red-500' : notif.type === 'info' ? 'bg-blue-50 text-[#2b518c]' : 'bg-slate-100 text-slate-400'}`}>
                       <Bell className="w-5 h-5"/>
                    </div>
                    <div>
                       <div className="flex justify-between items-start mb-1">
                          <h4 className="font-bold text-slate-800 text-sm">{notif.title}</h4>
                          <span className="text-[10px] text-slate-400 font-medium whitespace-nowrap ml-2">{new Date(notif.date).toLocaleDateString('id-ID')}</span>
                       </div>
                       <p className="text-xs text-slate-500 leading-relaxed font-medium">{notif.message}</p>
                    </div>
                 </div>
              ))}
           </div>
        </div>
      )}

      {/* Reboot Confirm Modal */}
      {rebootConfirm && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-slate-900/40 backdrop-blur-sm">
          <div className="bg-white rounded-3xl w-full max-w-sm overflow-hidden shadow-2xl p-6">
            <div className="flex items-center gap-4 mb-4">
               <div className="w-12 h-12 rounded-2xl bg-blue-50 text-blue-500 flex justify-center items-center">
                  <RotateCcw className="w-6 h-6" />
               </div>
               <div>
                  <h3 className="font-bold text-slate-800 text-lg">Restart Modem</h3>
                  <p className="text-slate-500 text-xs mt-1">Sistem akan padam 1-2 menit.</p>
               </div>
            </div>
            {rebootMsg.text ? (
               <div className={`p-4 rounded-xl text-sm font-bold text-center ${rebootMsg.type === 'error' ? 'bg-red-50 text-red-600' : 'bg-emerald-50 text-emerald-600'}`}>{rebootMsg.text}</div>
            ) : (
               <div className="flex gap-3 mt-6">
                 <Button onClick={() => setRebootConfirm(false)} variant="outline" className="flex-1 h-12 rounded-xl text-slate-600 border-slate-200">Batal</Button>
                 <Button onClick={handleReboot} disabled={rebooting} className="flex-1 h-12 rounded-xl bg-blue-600 hover:bg-blue-700 text-white shadow-md shadow-blue-200">{rebooting ? 'Tunggu...' : 'Ya, Restart'}</Button>
               </div>
            )}
          </div>
        </div>
      )}

      {/* WiFi Settings Modal */}
      {wifiSettingOpen && (
        <div className="fixed inset-0 z-[100] flex flex-col bg-slate-50 animate-in slide-in-from-bottom duration-300">
           <div className="flex justify-between items-center p-5 bg-white border-b border-slate-100 shadow-sm z-10">
              <h3 className="font-bold flex items-center gap-2 text-slate-800"><Wifi className="w-5 h-5 text-rose-500"/> WiFi Settings</h3>
              <button onClick={() => setWifiSettingOpen(false)} className="text-slate-400 hover:text-slate-600 p-2 rounded-xl bg-slate-50"><X className="w-5 h-5"/></button>
           </div>
           <div className="flex-1 p-6 space-y-6 overflow-y-auto">
              {wifiLoading ? (
                 <div className="flex flex-col items-center justify-center p-10 h-[50vh]"><div className="w-10 h-10 border-4 border-blue-500 border-t-transparent rounded-full animate-spin"></div><p className="text-sm text-slate-400 mt-4 font-medium">Connecting to Router...</p></div>
              ) : (
                 <div className="bg-white rounded-3xl p-6 shadow-sm border border-slate-100">
                    <h4 className="font-bold text-slate-800 mb-6 text-lg">SSID & Password</h4>
                    {wifiMsg.text && (
                      <div className={`p-3 rounded-xl text-sm font-medium mb-6 ${wifiMsg.type === 'error' ? 'bg-red-50 text-red-600' : 'bg-emerald-50 text-emerald-600'}`}>
                        {wifiMsg.text}
                      </div>
                    )}
                    <div className="space-y-5">
                       <div>
                         <label className="text-xs font-bold text-slate-500 ml-1 uppercase tracking-wider mb-2 block">WiFi Name (SSID)</label>
                         <Input value={ssid} onChange={e => setSsid(e.target.value)} className="h-12 bg-slate-50 border-slate-200 rounded-xl mt-1 text-slate-800 font-bold focus-visible:ring-blue-500"/>
                       </div>
                       <div>
                         <label className="text-xs font-bold text-slate-500 ml-1 uppercase tracking-wider mb-2 block">WiFi Password</label>
                         <div className="relative mt-1">
                           <Input type={showPass ? 'text' : 'password'} value={password} onChange={e => setPassword(e.target.value)} className="h-12 bg-slate-50 border-slate-200 rounded-xl text-slate-800 font-bold font-mono tracking-wider pr-12 focus-visible:ring-blue-500"/>
                           <button onClick={() => setShowPass(!showPass)} className="absolute right-4 top-1/2 -translate-y-1/2 text-slate-400">
                              {showPass ? <EyeOff className="w-5 h-5"/> : <Eye className="w-5 h-5"/>}
                           </button>
                         </div>
                       </div>
                       <Button onClick={saveWifi} disabled={savingWifi} className="w-full h-12 bg-[#fb7185] hover:bg-rose-600 text-white rounded-xl shadow-md shadow-rose-200 font-bold text-base mt-4 transition-colors">
                         {savingWifi ? 'Saving to Router...' : 'Apply Changes'}
                       </Button>
                    </div>
                 </div>
              )}
           </div>
        </div>
      )}

      {/* Payment Modal */}
      {paymentModalOpen && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-slate-900/40 backdrop-blur-sm">
          <div className="bg-white rounded-3xl w-full max-w-sm overflow-hidden shadow-2xl p-6 relative">
            <button onClick={() => setPaymentModalOpen(false)} className="absolute top-4 right-4 text-slate-400 bg-slate-100 hover:bg-slate-200 transition-colors rounded-full p-1.5"><X className="w-5 h-5"/></button>
            <h3 className="font-bold text-slate-800 text-center text-lg mb-2 pt-2">Detail Pembayaran</h3>
            <div className="text-center my-6">
              <p className="text-sm text-slate-500 font-medium">Total Pembayaran</p>
              <p className="text-3xl font-black text-[#2b518c] mt-1">Rp {selectedInvoice?.total?.toLocaleString('id-ID') || selectedInvoice?.amount?.toLocaleString('id-ID')}</p>
            </div>
            <div className="bg-blue-50 border border-blue-100 rounded-2xl p-4 text-center mb-6">
              <p className="text-xs text-blue-600 uppercase font-bold tracking-wider mb-2">{data?.platform_settings?.bank_name || 'Transfer Bank'}</p>
              <p className="text-2xl font-mono text-slate-800 font-bold tracking-widest">{data?.platform_settings?.bank_account || '—'}</p>
              <p className="text-sm text-slate-600 font-medium mt-1 uppercase">{data?.platform_settings?.bank_account_name || '—'}</p>
            </div>
            <Button onClick={() => setPaymentModalOpen(false)} className="w-full bg-[#34d399] hover:bg-emerald-500 text-white rounded-xl h-12 font-bold shadow-md shadow-emerald-200 text-base">
               Selesai
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
// Add simple css animations inline or keep using tailwind defaults
