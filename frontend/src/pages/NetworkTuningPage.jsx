import React, { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { Shield, Activity, Link2, Zap, Wifi, HardDrive, RefreshCw, Play, Square, CheckCircle, XCircle, AlertTriangle, ChevronRight, Gamepad2 } from 'lucide-react';

const API = import.meta.env.VITE_API_URL || '';
const headers = () => ({ Authorization: `Bearer ${localStorage.getItem('token')}` });

/* ─── Helpers ─────────────────────────────────────────────────────────── */
const Badge = ({ ok, label }) => (
  <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium ${ok ? 'bg-emerald-500/20 text-emerald-400' : 'bg-rose-500/20 text-rose-400'}`}>
    {ok ? <CheckCircle className="w-3 h-3" /> : <XCircle className="w-3 h-3" />} {label}
  </span>
);

const SeverityDot = ({ s }) => {
  const c = s === 'critical' ? 'bg-rose-500' : s === 'warning' ? 'bg-amber-500' : 'bg-emerald-500';
  return <span className={`w-2 h-2 rounded-full ${c} inline-block`} />;
};

const Card = ({ children, className = '' }) => (
  <div className={`bg-slate-800/50 backdrop-blur-sm border border-slate-700/50 rounded-xl p-5 ${className}`}>{children}</div>
);

const Btn = ({ onClick, disabled, children, color = 'indigo', className = '' }) => {
  const colors = { indigo: 'bg-indigo-600/20 text-indigo-400 hover:bg-indigo-600/30', emerald: 'bg-emerald-600/20 text-emerald-400 hover:bg-emerald-600/30', rose: 'bg-rose-600/20 text-rose-400 hover:bg-rose-600/30', amber: 'bg-amber-600/20 text-amber-400 hover:bg-amber-600/30' };
  return <button onClick={onClick} disabled={disabled} className={`px-4 py-2 rounded-lg flex items-center gap-2 text-sm transition disabled:opacity-40 ${colors[color]} ${className}`}>{children}</button>;
};

/* ─── Device Selector ─────────────────────────────────────────────────── */
function DeviceSelector({ devices, value, onChange }) {
  return (
    <select value={value} onChange={e => onChange(e.target.value)} className="bg-slate-900 border border-slate-700 text-white text-sm rounded-lg px-3 py-2 focus:outline-none focus:ring-1 focus:ring-indigo-500">
      <option value="">Pilih Router...</option>
      {devices.map(d => <option key={d.id} value={d.id}>{d.name}</option>)}
    </select>
  );
}

/* ═══ TAB 1: SQM MANAGER ═══════════════════════════════════════════════ */
function SqmTab({ deviceId }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [applying, setApplying] = useState(false);
  const [queueType, setQueueType] = useState('fq-codel');

  const fetch_ = useCallback(async () => {
    if (!deviceId) return;
    setLoading(true);
    try { const r = await axios.get(`${API}/api/network-tuning/sqm/${deviceId}`, { headers: headers() }); setData(r.data); }
    catch { setData(null); } finally { setLoading(false); }
  }, [deviceId]);

  useEffect(() => { fetch_(); }, [fetch_]);

  const apply = async () => {
    setApplying(true);
    try {
      await axios.post(`${API}/api/network-tuning/sqm/apply`, { device_id: deviceId, queue_type: queueType }, { headers: headers() });
      await fetch_();
      alert('SQM berhasil diterapkan!');
    } catch (e) { alert(e.response?.data?.detail || 'Gagal'); } finally { setApplying(false); }
  };

  if (!deviceId) return <p className="text-slate-500 italic">Pilih router terlebih dahulu.</p>;
  if (loading) return <p className="text-slate-400">Loading...</p>;
  if (!data) return <p className="text-slate-500">Data tidak tersedia.</p>;

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-4 flex-wrap">
        <div className="text-sm text-slate-400">Total Queue: <span className="text-white font-bold">{data.total_queues}</span></div>
        <div className="text-sm text-slate-400">Sudah Optimal: <span className="text-emerald-400 font-bold">{data.optimized_count}</span></div>
        <div className="text-sm text-slate-400">Belum Optimal: <span className="text-rose-400 font-bold">{data.total_queues - data.optimized_count}</span></div>
      </div>
      <div className="max-h-64 overflow-auto">
        <table className="w-full text-sm">
          <thead><tr className="text-slate-500 border-b border-slate-700"><th className="text-left py-2 px-2">Queue</th><th className="text-left py-2 px-2">Target</th><th className="text-left py-2 px-2">Limit</th><th className="text-left py-2 px-2">Type</th><th className="py-2 px-2">Status</th></tr></thead>
          <tbody>{data.queues.map(q => (
            <tr key={q.id} className="border-b border-slate-800 hover:bg-slate-800/50">
              <td className="py-1.5 px-2 text-white">{q.name}</td>
              <td className="py-1.5 px-2 text-slate-400 font-mono text-xs">{q.target}</td>
              <td className="py-1.5 px-2 text-slate-400 font-mono text-xs">{q.max_limit}</td>
              <td className="py-1.5 px-2 font-mono text-xs">{q.queue_type}</td>
              <td className="py-1.5 px-2 text-center"><Badge ok={q.is_optimal} label={q.is_optimal ? 'Optimal' : 'Default'} /></td>
            </tr>
          ))}</tbody>
        </table>
      </div>
      <div className="flex items-center gap-3 pt-2 border-t border-slate-700">
        <label className="text-sm text-slate-400">Target Type:</label>
        <select value={queueType} onChange={e => setQueueType(e.target.value)} className="bg-slate-900 border border-slate-700 text-white text-sm rounded px-2 py-1">
          <option value="fq-codel">FQ-CoDel</option>
          <option value="cake">Cake (ROS 7.14+)</option>
        </select>
        <Btn onClick={apply} disabled={applying} color="emerald"><Play className="w-4 h-4" /> Apply ke Semua</Btn>
      </div>
    </div>
  );
}

/* ═══ TAB 2: CONNTRACK OPTIMIZER ═══════════════════════════════════════ */
function ConntrackTab({ deviceId }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [applying, setApplying] = useState(false);

  const fetch_ = useCallback(async () => {
    if (!deviceId) return;
    setLoading(true);
    try { const r = await axios.get(`${API}/api/network-tuning/conntrack/${deviceId}`, { headers: headers() }); setData(r.data); }
    catch { setData(null); } finally { setLoading(false); }
  }, [deviceId]);

  useEffect(() => { fetch_(); }, [fetch_]);

  const optimize = async () => {
    setApplying(true);
    try {
      await axios.post(`${API}/api/network-tuning/conntrack/optimize`, { device_id: deviceId }, { headers: headers() });
      await fetch_();
      alert('Conntrack berhasil dioptimasi!');
    } catch (e) { alert(e.response?.data?.detail || 'Gagal'); } finally { setApplying(false); }
  };

  if (!deviceId) return <p className="text-slate-500 italic">Pilih router terlebih dahulu.</p>;
  if (loading) return <p className="text-slate-400">Loading...</p>;
  if (!data) return <p className="text-slate-500">Data tidak tersedia.</p>;

  const pct = data.usage_percent || 0;
  const barColor = pct > 95 ? 'bg-rose-500' : pct > 80 ? 'bg-amber-500' : 'bg-emerald-500';

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-6">
        <div>
          <div className="text-3xl font-bold text-white">{data.total_connections.toLocaleString()}</div>
          <div className="text-xs text-slate-500">Active Connections</div>
        </div>
        <div className="flex-1">
          <div className="flex justify-between text-xs text-slate-400 mb-1"><span>{pct}% used</span><span>Max: {data.max_entries.toLocaleString()}</span></div>
          <div className="w-full bg-slate-700 rounded-full h-3"><div className={`${barColor} h-3 rounded-full transition-all`} style={{ width: `${Math.min(pct, 100)}%` }} /></div>
        </div>
        <SeverityDot s={data.severity} />
      </div>
      <div className="grid grid-cols-3 gap-3 text-sm">
        <div className="bg-slate-900/50 rounded-lg p-3"><div className="text-slate-500 text-xs">TCP Established</div><div className="text-white font-mono">{data.tcp_established_timeout}</div></div>
        <div className="bg-slate-900/50 rounded-lg p-3"><div className="text-slate-500 text-xs">TCP Close</div><div className="text-white font-mono">{data.tcp_close_timeout}</div></div>
        <div className="bg-slate-900/50 rounded-lg p-3"><div className="text-slate-500 text-xs">UDP Timeout</div><div className="text-white font-mono">{data.udp_timeout}</div></div>
      </div>
      <Btn onClick={optimize} disabled={applying} color="emerald"><Zap className="w-4 h-4" /> Optimize (65536 / 30m / 10s / 30s)</Btn>
    </div>
  );
}

/* ═══ TAB 3: MSS CLAMPING ═════════════════════════════════════════════ */
function MssTab({ deviceId, devices }) {
  const [statuses, setStatuses] = useState({});
  const [loading, setLoading] = useState(false);

  const fetchAll = useCallback(async () => {
    setLoading(true);
    const res = {};
    for (const d of devices) {
      try { const r = await axios.get(`${API}/api/network-tuning/mss/${d.id}`, { headers: headers() }); res[d.id] = r.data; }
      catch { res[d.id] = { applied: false }; }
    }
    setStatuses(res);
    setLoading(false);
  }, [devices]);

  useEffect(() => { if (devices.length) fetchAll(); }, [fetchAll]);

  const toggle = async (did, enable) => {
    try {
      await axios.post(`${API}/api/network-tuning/mss/apply`, { device_id: did, enable }, { headers: headers() });
      await fetchAll();
    } catch (e) { alert(e.response?.data?.detail || 'Gagal'); }
  };

  const enableAll = async () => { for (const d of devices) await toggle(d.id, true); };

  if (loading) return <p className="text-slate-400">Loading...</p>;

  return (
    <div className="space-y-4">
      <p className="text-sm text-slate-400">MSS Clamping mencegah fragmentasi paket pada koneksi PPPoE. Mengatasi masalah "website loading setengah".</p>
      <table className="w-full text-sm">
        <thead><tr className="text-slate-500 border-b border-slate-700"><th className="text-left py-2">Router</th><th className="py-2">Status</th><th className="py-2">Action</th></tr></thead>
        <tbody>{devices.map(d => {
          const s = statuses[d.id] || {};
          return (
            <tr key={d.id} className="border-b border-slate-800">
              <td className="py-2 text-white">{d.name}</td>
              <td className="py-2 text-center"><Badge ok={s.applied} label={s.applied ? 'Applied' : 'Not Set'} /></td>
              <td className="py-2 text-center">
                <Btn onClick={() => toggle(d.id, !s.applied)} color={s.applied ? 'rose' : 'emerald'} className="text-xs px-3 py-1">
                  {s.applied ? 'Disable' : 'Enable'}
                </Btn>
              </td>
            </tr>
          );
        })}</tbody>
      </table>
      <Btn onClick={enableAll} color="emerald"><Play className="w-4 h-4" /> Enable All</Btn>
    </div>
  );
}

/* ═══ TAB 4: RAW FIREWALL ═════════════════════════════════════════════ */
function RawFirewallTab({ deviceId }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [applying, setApplying] = useState(false);

  const fetch_ = useCallback(async () => {
    if (!deviceId) return;
    setLoading(true);
    try { const r = await axios.get(`${API}/api/network-tuning/raw-firewall/${deviceId}`, { headers: headers() }); setData(r.data); }
    catch { setData(null); } finally { setLoading(false); }
  }, [deviceId]);

  useEffect(() => { fetch_(); }, [fetch_]);

  const apply = async (enable) => {
    setApplying(true);
    try {
      await axios.post(`${API}/api/network-tuning/raw-firewall/apply`, { device_id: deviceId, enable_all: enable }, { headers: headers() });
      await fetch_();
      alert(enable ? 'Rules berhasil diterapkan!' : 'Rules berhasil dihapus!');
    } catch (e) { alert(e.response?.data?.detail || 'Gagal'); } finally { setApplying(false); }
  };

  if (!deviceId) return <p className="text-slate-500 italic">Pilih router terlebih dahulu.</p>;
  if (loading) return <p className="text-slate-400">Loading...</p>;
  if (!data) return <p className="text-slate-500">Data tidak tersedia.</p>;

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-6">
        <div><div className="text-2xl font-bold text-white">{data.cpu_load}%</div><div className="text-xs text-slate-500">CPU Load</div></div>
        <div><div className="text-2xl font-bold text-amber-400">{(data.total_packets_dropped || 0).toLocaleString()}</div><div className="text-xs text-slate-500">Total Dropped</div></div>
      </div>
      <table className="w-full text-sm">
        <thead><tr className="text-slate-500 border-b border-slate-700"><th className="text-left py-2">Rule</th><th className="py-2">Status</th><th className="text-right py-2">Packets Dropped</th></tr></thead>
        <tbody>{data.rules.map(r => (
          <tr key={r.id} className="border-b border-slate-800">
            <td className="py-2 text-white">{r.label}</td>
            <td className="py-2 text-center"><Badge ok={r.applied} label={r.applied ? 'ON' : 'OFF'} /></td>
            <td className="py-2 text-right font-mono text-slate-400">{r.packets_dropped.toLocaleString()}</td>
          </tr>
        ))}</tbody>
      </table>
      <div className="flex gap-2">
        <Btn onClick={() => apply(true)} disabled={applying} color="emerald"><Play className="w-4 h-4" /> Enable All</Btn>
        <Btn onClick={() => apply(false)} disabled={applying} color="rose"><Square className="w-4 h-4" /> Remove All</Btn>
      </div>
    </div>
  );
}

/* ═══ TAB 5: LATENCY MONITOR ═════════════════════════════════════════ */
function LatencyTab() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);

  const fetch_ = useCallback(async () => {
    setLoading(true);
    try { const r = await axios.get(`${API}/api/network-tuning/latency`, { headers: headers() }); setData(r.data); }
    catch { setData(null); } finally { setLoading(false); }
  }, []);

  useEffect(() => { fetch_(); const i = setInterval(fetch_, 15000); return () => clearInterval(i); }, [fetch_]);

  if (loading && !data) return <p className="text-slate-400">Loading...</p>;

  const devices = data?.devices || [];

  return (
    <div className="space-y-4">
      <p className="text-sm text-slate-400">Ping otomatis dari setiap router ke gateway ISP setiap 30 detik.</p>
      {devices.length === 0 ? <p className="text-slate-500 italic">Belum ada data. Tunggu polling berikutnya...</p> : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {devices.map((d, i) => (
            <Card key={i}>
              <div className="flex items-center justify-between mb-3">
                <div className="text-sm font-medium text-white">{d.device_name}</div>
                <SeverityDot s={d.severity} />
              </div>
              <div className="text-xs text-slate-500 font-mono mb-2">{d.gateway}</div>
              <div className="grid grid-cols-2 gap-2 text-sm">
                <div><span className="text-slate-500">Avg:</span> <span className="text-white font-bold">{d.avg_rtt}ms</span></div>
                <div><span className="text-slate-500">Max:</span> <span className="text-white">{d.max_rtt}ms</span></div>
                <div><span className="text-slate-500">Jitter:</span> <span className="text-white">{d.jitter}ms</span></div>
                <div><span className="text-slate-500">Loss:</span> <span className={d.packet_loss > 0 ? 'text-rose-400 font-bold' : 'text-white'}>{d.packet_loss}%</span></div>
              </div>
            </Card>
          ))}
        </div>
      )}
      <Btn onClick={fetch_} color="indigo"><RefreshCw className="w-4 h-4" /> Refresh</Btn>
    </div>
  );
}

/* ═══ TAB 6: INTERFACE HEALTH ════════════════════════════════════════ */
function InterfaceHealthTab({ deviceId }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);

  const fetch_ = useCallback(async () => {
    if (!deviceId) return;
    setLoading(true);
    try { const r = await axios.get(`${API}/api/network-tuning/interface-health/${deviceId}`, { headers: headers() }); setData(r.data); }
    catch { setData(null); } finally { setLoading(false); }
  }, [deviceId]);

  useEffect(() => { fetch_(); const i = setInterval(fetch_, 15000); return () => clearInterval(i); }, [fetch_]);

  if (!deviceId) return <p className="text-slate-500 italic">Pilih router terlebih dahulu.</p>;
  if (loading && !data) return <p className="text-slate-400">Loading...</p>;

  const ifaces = data?.interfaces || [];
  const sfps = data?.sfp || [];
  const alerts = data?.alerts || [];

  const statusIcon = (s) => s === 'up' ? '🟢' : s === 'disabled' ? '⚫' : '🔴';

  return (
    <div className="space-y-4">
      {alerts.length > 0 && (
        <div className="space-y-2">
          {alerts.map((a, i) => (
            <div key={i} className={`flex items-start gap-2 p-3 rounded-lg text-sm ${a.severity === 'critical' ? 'bg-rose-500/10 border border-rose-500/30 text-rose-300' : 'bg-amber-500/10 border border-amber-500/30 text-amber-300'}`}>
              <AlertTriangle className="w-4 h-4 mt-0.5 flex-shrink-0" />
              <span>{a.message}</span>
            </div>
          ))}
        </div>
      )}
      <table className="w-full text-sm">
        <thead><tr className="text-slate-500 border-b border-slate-700"><th className="text-left py-2">Interface</th><th className="py-2">Status</th><th className="text-right py-2">Errors/min</th><th className="text-right py-2">Drops/min</th><th className="text-right py-2">Total Errors</th></tr></thead>
        <tbody>{ifaces.map(f => (
          <tr key={f.name} className="border-b border-slate-800">
            <td className="py-1.5 text-white font-mono text-xs">{f.name}</td>
            <td className="py-1.5 text-center">{statusIcon(f.status)} <span className="text-xs text-slate-400">{f.status}</span></td>
            <td className={`py-1.5 text-right font-mono text-xs ${f.error_rate_per_min > 100 ? 'text-rose-400 font-bold' : f.error_rate_per_min > 0 ? 'text-amber-400' : 'text-slate-500'}`}>{f.error_rate_per_min}</td>
            <td className={`py-1.5 text-right font-mono text-xs ${f.drop_rate_per_min > 0 ? 'text-amber-400' : 'text-slate-500'}`}>{f.drop_rate_per_min}</td>
            <td className="py-1.5 text-right font-mono text-xs text-slate-500">{(f.rx_error_total + f.tx_error_total + f.rx_fcs_total).toLocaleString()}</td>
          </tr>
        ))}</tbody>
      </table>
      {sfps.length > 0 && (
        <div>
          <h3 className="text-sm font-semibold text-white mb-2">🌡️ SFP Modules</h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {sfps.map((s, i) => (
              <div key={i} className="bg-slate-900/50 rounded-lg p-3 text-sm">
                <div className="font-mono text-indigo-400 text-xs mb-1">{s.interface}</div>
                <div className="grid grid-cols-2 gap-1 text-xs">
                  <div><span className="text-slate-500">Temp:</span> <span className="text-white">{s.temperature}</span></div>
                  <div><span className="text-slate-500">Rate:</span> <span className="text-white">{s.rate}</span></div>
                  <div><span className="text-slate-500">TX:</span> <span className="text-white">{s.tx_power}</span></div>
                  <div><span className="text-slate-500">RX:</span> <span className="text-white">{s.rx_power}</span></div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

/* ═══ TAB 7: QOS PRIORITY ═════════════════════════════════════════════ */
function QosPriorityTab({ deviceId }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [applying, setApplying] = useState(false);

  const fetch_ = useCallback(async () => {
    if (!deviceId) return;
    setLoading(true);
    try { const r = await axios.get(`${API}/api/network-tuning/qos-priority/${deviceId}`, { headers: headers() }); setData(r.data); }
    catch { setData(null); } finally { setLoading(false); }
  }, [deviceId]);

  useEffect(() => { fetch_(); }, [fetch_]);

  const apply = async (enable) => {
    setApplying(true);
    try {
      const r = await axios.post(`${API}/api/network-tuning/qos-priority/apply`, { device_id: deviceId, enable }, { headers: headers() });
      await fetch_();
      alert(r.data.message || 'Berhasil');
    } catch (e) { alert(e.response?.data?.detail || 'Gagal'); } finally { setApplying(false); }
  };

  if (!deviceId) return <p className="text-slate-500 italic">Pilih router terlebih dahulu.</p>;
  if (loading) return <p className="text-slate-400">Loading...</p>;
  if (!data) return <p className="text-slate-500">Data tidak tersedia.</p>;

  return (
    <div className="space-y-4">
      <div className="flex items-start gap-4 p-4 rounded-xl bg-slate-800/50 border border-slate-700">
        <div className={`p-3 rounded-lg ${data.applied && !data.disabled ? 'bg-emerald-500/20 text-emerald-400' : 'bg-slate-700/50 text-slate-400'}`}>
          <Gamepad2 className="w-8 h-8" />
        </div>
        <div className="flex-1">
          <h3 className="text-lg font-bold text-white mb-1">QoS Priority (Gaming & Ping)</h3>
          <p className="text-sm text-slate-400 mb-3">Memisahkan paket Game (Mobile Legends, PUBG, FreeFire), DNS, dan Ping agar tidak lag saat ada user yang mendownload/streaming.</p>
          <div className="flex items-center gap-4 text-xs font-mono">
            <span className="flex items-center gap-1">Mangle Rules: <Badge ok={data.mangle_count >= 6} label={`${data.mangle_count} rules`} /></span>
            <span className="flex items-center gap-1">Simple Queue: <Badge ok={data.queue_applied} label={data.queue_applied ? 'Terpasang' : 'Belum'} /></span>
            <span className="flex items-center gap-1">Status: <Badge ok={data.applied && !data.disabled} label={data.applied && !data.disabled ? 'Active' : 'Disabled'} /></span>
          </div>
        </div>
      </div>
      <div className="p-4 bg-amber-500/10 border border-amber-500/30 text-amber-300 text-sm rounded-lg flex items-start gap-2">
        <AlertTriangle className="w-5 h-5 flex-shrink-0" />
        <div>
          <strong>PENTING:</strong> Setelah mengaktifkan, buka Winbox/WebFig, masuk ke <code>Queues</code> → <code>Simple Queues</code>, lalu pastikan queue <code>NOC-QoS-Games-DNS-Ping</code> dipindah (drag) ke urutan <strong>paling atas (#0)</strong> agar dieksekusi sebelum limit PPPoE user.
        </div>
      </div>
      <div className="flex gap-2">
        <Btn onClick={() => apply(true)} disabled={applying} color="emerald"><Play className="w-4 h-4" /> Enable QoS</Btn>
        <Btn onClick={() => apply(false)} disabled={applying} color="rose"><Square className="w-4 h-4" /> Remove QoS</Btn>
      </div>
    </div>
  );
}

/* ═══ MAIN PAGE ═══════════════════════════════════════════════════════ */
const TABS = [
  { id: 'sqm',       label: 'Smart Queue',    icon: Zap,        desc: 'FQ-CoDel / Cake' },
  { id: 'conntrack', label: 'Conntrack',       icon: Link2,      desc: 'Connection Tracking' },
  { id: 'mss',       label: 'MSS Clamp',      icon: Shield,     desc: 'TCP Fragmentation Fix' },
  { id: 'raw',       label: 'Raw Firewall',    icon: Shield,     desc: 'CPU Saver Rules' },
  { id: 'latency',   label: 'Latency',         icon: Activity,   desc: 'Ping Monitor' },
  { id: 'iface',     label: 'Interface',       icon: HardDrive,  desc: 'Port Health' },
  { id: 'qos',       label: 'QoS Game',        icon: Gamepad2,   desc: 'Game & Ping Priority' },
];

export default function NetworkTuningPage() {
  const [tab, setTab] = useState('sqm');
  const [devices, setDevices] = useState([]);
  const [deviceId, setDeviceId] = useState('');

  useEffect(() => {
    axios.get(`${API}/api/devices`, { headers: headers() })
      .then(r => { const devs = (r.data || []).map(d => ({ id: d.id, name: d.name })); setDevices(devs); if (devs.length) setDeviceId(devs[0].id); })
      .catch(() => {});
  }, []);

  const renderTab = () => {
    switch (tab) {
      case 'sqm':       return <SqmTab deviceId={deviceId} />;
      case 'conntrack': return <ConntrackTab deviceId={deviceId} />;
      case 'mss':       return <MssTab deviceId={deviceId} devices={devices} />;
      case 'raw':       return <RawFirewallTab deviceId={deviceId} />;
      case 'latency':   return <LatencyTab />;
      case 'iface':     return <InterfaceHealthTab deviceId={deviceId} />;
      case 'qos':       return <QosPriorityTab deviceId={deviceId} />;
      default:          return null;
    }
  };

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-2"><Wifi className="w-6 h-6 text-indigo-400" /> Network Tuning</h1>
          <p className="text-slate-400 text-sm mt-1">Optimasi MikroTik untuk jaringan stabil dan anti-lag.</p>
        </div>
        {tab !== 'latency' && <DeviceSelector devices={devices} value={deviceId} onChange={setDeviceId} />}
      </div>

      {/* Tab Navigation */}
      <div className="flex gap-1 overflow-x-auto pb-1 border-b border-slate-700/50">
        {TABS.map(t => (
          <button key={t.id} onClick={() => setTab(t.id)}
            className={`flex items-center gap-2 px-4 py-2.5 rounded-t-lg text-sm font-medium transition whitespace-nowrap ${tab === t.id ? 'bg-slate-800 text-indigo-400 border border-slate-700/50 border-b-transparent -mb-px' : 'text-slate-500 hover:text-slate-300 hover:bg-slate-800/50'}`}>
            <t.icon className="w-4 h-4" />
            <span className="hidden sm:inline">{t.label}</span>
            <span className="sm:hidden">{t.label.split(' ')[0]}</span>
          </button>
        ))}
      </div>

      {/* Tab Content */}
      <Card>{renderTab()}</Card>
    </div>
  );
}
