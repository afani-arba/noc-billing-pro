import React, { useState, useEffect, useRef, useCallback } from 'react';
import axios from 'axios';
import { 
    Play, Square, RotateCw, Save, RefreshCw, Shield, Activity, Cpu, HardDrive, 
    AlertTriangle, Server, Search, CheckCircle, XCircle, Globe, List, Code, Settings
} from 'lucide-react';

const TOKEN_KEY = 'noc_token';

const getHeaders = () => ({
    Authorization: `Bearer ${localStorage.getItem(TOKEN_KEY)}`
});

export default function ZapretPage() {
    // ── State: Global ────────────────────────────────────────────────────────
    const [activeTab, setActiveTab] = useState('dashboard');
    const [status, setStatus] = useState(null);
    const [isLoading, setIsLoading] = useState(true);
    const [actionLoading, setActionLoading] = useState(false);
    const [errorMsg, setErrorMsg] = useState('');
    const pollRef = useRef(null);

    // ── State: Dashboard / Logs ──────────────────────────────────────────────
    const [logs, setLogs] = useState('');
    const logEndRef = useRef(null);

    // ── State: Advanced Config ───────────────────────────────────────────────
    const [config, setConfig] = useState('');
    const [editConfig, setEditConfig] = useState('');
    const [isEditing, setIsEditing] = useState(false);

    // ── State: Strategies ────────────────────────────────────────────────────
    const [strategies, setStrategies] = useState([]);
    const [selectedStrategy, setSelectedStrategy] = useState('universal');
    const [enableUdp, setEnableUdp] = useState(true);
    const [enableAutoHostlist, setEnableAutoHostlist] = useState(false);

    // ── State: Hostlist ──────────────────────────────────────────────────────
    const [hostlist, setHostlist] = useState([]);
    const [autoHostlist, setAutoHostlist] = useState([]);
    const [hostInput, setHostInput] = useState('');

    // ── State: Blockcheck ────────────────────────────────────────────────────
    const [blockcheckDomain, setBlockcheckDomain] = useState('');
    const [blockcheckResult, setBlockcheckResult] = useState(null);
    const [isChecking, setIsChecking] = useState(false);


    // ── Fetching Data ────────────────────────────────────────────────────────
    const fetchDashboardData = useCallback(async (silent = false) => {
        if (!silent) setIsLoading(true);
        setErrorMsg('');
        try {
            const headers = getHeaders();
            const [statusRes, logsRes] = await Promise.all([
                axios.get('/api/zapret/status', { headers }),
                axios.get('/api/zapret/logs', { headers }).catch(() => ({ data: { logs: '' } })),
            ]);
            setStatus(statusRes.data);
            setLogs(logsRes.data.logs || '');
        } catch (err) {
            if (err.response?.status === 401) {
                setErrorMsg('Sesi habis. Silakan login ulang.');
            } else {
                setErrorMsg(`Gagal memuat dashboard: ${err.response?.data?.detail || err.message}`);
            }
        } finally {
            setIsLoading(false);
        }
    }, []);

    const fetchConfigData = useCallback(async () => {
        setIsLoading(true);
        try {
            const res = await axios.get('/api/zapret/config', { headers: getHeaders() });
            setConfig(res.data.config || '');
        } catch (err) {
            setErrorMsg(`Gagal memuat config: ${err.response?.data?.detail || err.message}`);
        } finally {
            setIsLoading(false);
        }
    }, []);

    const fetchStrategiesData = useCallback(async () => {
        setIsLoading(true);
        try {
            const res = await axios.get('/api/zapret/strategies', { headers: getHeaders() });
            setStrategies(res.data.strategies || []);
        } catch (err) {
            setErrorMsg(`Gagal memuat strategies: ${err.response?.data?.detail || err.message}`);
        } finally {
            setIsLoading(false);
        }
    }, []);

    const fetchHostlistData = useCallback(async () => {
        setIsLoading(true);
        try {
            const headers = getHeaders();
            const [hlRes, autoRes] = await Promise.all([
                axios.get('/api/zapret/hostlist', { headers }),
                axios.get('/api/zapret/hostlist/auto', { headers }).catch(() => ({ data: { domains: [] } }))
            ]);
            setHostlist(hlRes.data.domains || []);
            setAutoHostlist(autoRes.data.domains || []);
        } catch (err) {
            setErrorMsg(`Gagal memuat hostlist: ${err.response?.data?.detail || err.message}`);
        } finally {
            setIsLoading(false);
        }
    }, []);

    // ── Effect: Tab Switching ────────────────────────────────────────────────
    useEffect(() => {
        if (activeTab === 'dashboard') fetchDashboardData();
        else if (activeTab === 'config') fetchConfigData();
        else if (activeTab === 'strategies') fetchStrategiesData();
        else if (activeTab === 'hostlist') fetchHostlistData();
        // blockcheck doesn't fetch on load
    }, [activeTab, fetchDashboardData, fetchConfigData, fetchStrategiesData, fetchHostlistData]);

    // ── Effect: Polling untuk Dashboard ──────────────────────────────────────
    useEffect(() => {
        if (activeTab === 'dashboard') {
            pollRef.current = setInterval(() => fetchDashboardData(true), 10000);
        } else {
            if (pollRef.current) clearInterval(pollRef.current);
        }
        return () => {
            if (pollRef.current) clearInterval(pollRef.current);
        };
    }, [activeTab, fetchDashboardData]);

    // ── Auto-scroll log ──────────────────────────────────────────────────────
    useEffect(() => {
        if (activeTab === 'dashboard') {
            logEndRef.current?.scrollIntoView({ behavior: 'smooth' });
        }
    }, [logs, activeTab]);


    // ── Actions: Core Service ────────────────────────────────────────────────
    const handleAction = async (action) => {
        setActionLoading(true);
        setErrorMsg('');
        try {
            const res = await axios.post(`/api/zapret/${action}`, {}, { headers: getHeaders() });
            if (res.data.status) setStatus(res.data.status);
            if (activeTab === 'dashboard') {
                const logsRes = await axios.get('/api/zapret/logs', { headers: getHeaders() }).catch(() => ({ data: { logs: '' } }));
                setLogs(logsRes.data.logs || '');
            }
        } catch (err) {
            setErrorMsg(`Gagal ${action} Zapret: ${err.response?.data?.detail || err.message}`);
        } finally {
            setActionLoading(false);
        }
    };


    // ── Actions: Config ──────────────────────────────────────────────────────
    const handleSaveConfig = async () => {
        if (!editConfig.trim()) {
            setErrorMsg('Konfigurasi tidak boleh kosong.');
            return;
        }
        setActionLoading(true);
        setErrorMsg('');
        try {
            const res = await axios.put('/api/zapret/config', { config: editConfig }, { headers: getHeaders() });
            setConfig(editConfig);
            setIsEditing(false);
            if (res.data.status) setStatus(res.data.status);
        } catch (err) {
            setErrorMsg(`Gagal menyimpan konfigurasi: ${err.response?.data?.detail || err.message}`);
        } finally {
            setActionLoading(false);
        }
    };

    // ── Actions: Strategies ──────────────────────────────────────────────────
    const handleApplyStrategy = async () => {
        setActionLoading(true);
        setErrorMsg('');
        try {
            const res = await axios.post('/api/zapret/strategies/apply', {
                strategy_key: selectedStrategy,
                enable_udp: enableUdp,
                enable_auto_hostlist: enableAutoHostlist
            }, { headers: getHeaders() });
            if (res.data.status) setStatus(res.data.status);
            alert(`Berhasil menerapkan strategi: ${res.data.strategy.name}`);
        } catch (err) {
            setErrorMsg(`Gagal menerapkan strategi: ${err.response?.data?.detail || err.message}`);
        } finally {
            setActionLoading(false);
        }
    };

    // ── Actions: Hostlist ────────────────────────────────────────────────────
    const handleSaveHostlist = async (newHostlist) => {
        setActionLoading(true);
        setErrorMsg('');
        try {
            const res = await axios.put('/api/zapret/hostlist', { domains: newHostlist }, { headers: getHeaders() });
            setHostlist(res.data.domains);
            setHostInput('');
        } catch (err) {
            setErrorMsg(`Gagal menyimpan hostlist: ${err.response?.data?.detail || err.message}`);
        } finally {
            setActionLoading(false);
        }
    };

    const handleAddHost = () => {
        if (!hostInput.trim()) return;
        const domains = hostInput.split(/[,;\n\s]+/).map(d => d.trim().toLowerCase()).filter(d => d);
        const combined = [...new Set([...hostlist, ...domains])];
        handleSaveHostlist(combined);
    };

    const handleRemoveHost = (domain) => {
        const filtered = hostlist.filter(d => d !== domain);
        handleSaveHostlist(filtered);
    };

    const handleClearAutoHostlist = async () => {
        if (!confirm('Yakin ingin menghapus semua domain yang terdeteksi secara otomatis?')) return;
        setActionLoading(true);
        try {
            await axios.delete('/api/zapret/hostlist/auto', { headers: getHeaders() });
            setAutoHostlist([]);
        } catch (err) {
            setErrorMsg(`Gagal menghapus auto hostlist: ${err.response?.data?.detail || err.message}`);
        } finally {
            setActionLoading(false);
        }
    };

    // ── Actions: Blockcheck ──────────────────────────────────────────────────
    const handleBlockcheck = async () => {
        if (!blockcheckDomain.trim()) return;
        setIsChecking(true);
        setErrorMsg('');
        setBlockcheckResult(null);
        try {
            const res = await axios.post('/api/zapret/blockcheck', { domain: blockcheckDomain, timeout: 5 }, { headers: getHeaders() });
            setBlockcheckResult(res.data);
        } catch (err) {
            setErrorMsg(`Blockcheck gagal: ${err.response?.data?.detail || err.message}`);
        } finally {
            setIsChecking(false);
        }
    };


    // ── Formatters ───────────────────────────────────────────────────────────
    const formatBytes = (bytes) => {
        if (!bytes) return '0 B';
        const k = 1024, sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return `${parseFloat((bytes / Math.pow(k, i)).toFixed(2))} ${sizes[i]}`;
    };

    const formatUptime = (seconds) => {
        if (!seconds) return '0s';
        const d = Math.floor(seconds / 86400), h = Math.floor((seconds % 86400) / 3600), m = Math.floor((seconds % 3600) / 60);
        const parts = [];
        if (d > 0) parts.push(`${d}d`);
        if (h > 0) parts.push(`${h}h`);
        parts.push(`${m}m`);
        return parts.join(' ');
    };

    const isRunning = status?.running === true;

    // ── Render ───────────────────────────────────────────────────────────────
    return (
        <div className="p-6 max-w-7xl mx-auto space-y-6">
            {/* Header & Global Actions */}
            <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
                <div>
                    <h1 className="text-2xl font-bold text-white flex items-center gap-2">
                        <Shield className="w-6 h-6 text-indigo-400" />
                        Zapret DPI Bypass
                    </h1>
                    <p className="text-slate-400 text-sm mt-1">
                        Bypass ISP Deep Packet Inspection tanpa VPN eksternal.
                    </p>
                </div>
                <div className="flex gap-2 flex-wrap">
                    <button onClick={() => handleAction('start')} disabled={actionLoading || isRunning}
                        className="px-4 py-2 bg-emerald-600/20 text-emerald-400 hover:bg-emerald-600/30 border border-emerald-600/30 rounded-lg flex items-center gap-2 transition disabled:opacity-40 disabled:cursor-not-allowed text-sm font-medium">
                        <Play className="w-4 h-4" /> Start
                    </button>
                    <button onClick={() => handleAction('stop')} disabled={actionLoading || !isRunning}
                        className="px-4 py-2 bg-rose-600/20 text-rose-400 hover:bg-rose-600/30 border border-rose-600/30 rounded-lg flex items-center gap-2 transition disabled:opacity-40 disabled:cursor-not-allowed text-sm font-medium">
                        <Square className="w-4 h-4" /> Stop
                    </button>
                    <button onClick={() => handleAction('restart')} disabled={actionLoading}
                        className="px-4 py-2 bg-indigo-600/20 text-indigo-400 hover:bg-indigo-600/30 border border-indigo-600/30 rounded-lg flex items-center gap-2 transition disabled:opacity-40 disabled:cursor-not-allowed text-sm font-medium">
                        <RotateCw className={`w-4 h-4 ${actionLoading ? 'animate-spin' : ''}`} /> Restart
                    </button>
                </div>
            </div>

            {/* Error Banner */}
            {errorMsg && (
                <div className="flex items-start gap-3 p-4 bg-rose-500/10 border border-rose-500/30 rounded-xl text-rose-300 text-sm">
                    <AlertTriangle className="w-5 h-5 flex-shrink-0 mt-0.5" />
                    <span>{errorMsg}</span>
                    <button onClick={() => setErrorMsg('')} className="ml-auto text-rose-400 hover:text-rose-200">✕</button>
                </div>
            )}

            {/* Navigation Tabs */}
            <div className="flex border-b border-slate-700/50 overflow-x-auto no-scrollbar">
                {[
                    { id: 'dashboard', icon: Activity, label: 'Dashboard & Logs' },
                    { id: 'strategies', icon: Server, label: 'ISP Strategies' },
                    { id: 'hostlist', icon: List, label: 'Hostlist Manager' },
                    { id: 'blockcheck', icon: Search, label: 'Blockcheck Tester' },
                    { id: 'config', icon: Code, label: 'Advanced Config' }
                ].map((t) => (
                    <button key={t.id} onClick={() => setActiveTab(t.id)}
                        className={`flex items-center gap-2 px-5 py-3 text-sm font-medium transition whitespace-nowrap border-b-2 ${
                            activeTab === t.id 
                                ? 'text-indigo-400 border-indigo-500 bg-indigo-500/5' 
                                : 'text-slate-400 border-transparent hover:text-slate-200 hover:bg-slate-800/50'
                        }`}
                    >
                        <t.icon className="w-4 h-4" /> {t.label}
                    </button>
                ))}
            </div>

            {/* Main Content Area */}
            <div className="min-h-[400px]">
                {isLoading && !status && activeTab !== 'blockcheck' ? (
                    <div className="flex items-center justify-center h-64 text-slate-400 gap-2">
                        <RefreshCw className="w-5 h-5 animate-spin" /> Memuat data...
                    </div>
                ) : (
                    <>
                        {/* TAB: DASHBOARD */}
                        {activeTab === 'dashboard' && (
                            <div className="space-y-6">
                                {/* Status Cards */}
                                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                                    <div className="bg-slate-800/50 backdrop-blur-sm border border-slate-700/50 rounded-xl p-5">
                                        <div className="flex items-center justify-between mb-3">
                                            <h3 className="text-slate-400 font-medium text-xs uppercase tracking-wide">Status</h3>
                                            <Activity className="w-4 h-4 text-slate-500" />
                                        </div>
                                        <div className="text-xl font-bold text-white flex items-center gap-2">
                                            {isRunning ? (
                                                <><span className="w-2.5 h-2.5 rounded-full bg-emerald-500 animate-pulse flex-shrink-0" />Running</>
                                            ) : (
                                                <><span className="w-2.5 h-2.5 rounded-full bg-rose-500 flex-shrink-0" />Stopped</>
                                            )}
                                        </div>
                                        <div className="text-xs text-slate-400 mt-1">Uptime: {formatUptime(status?.uptime_seconds)}</div>
                                    </div>
                                    <div className="bg-slate-800/50 backdrop-blur-sm border border-slate-700/50 rounded-xl p-5">
                                        <div className="flex items-center justify-between mb-3">
                                            <h3 className="text-slate-400 font-medium text-xs uppercase tracking-wide">Resource</h3>
                                            <Cpu className="w-4 h-4 text-slate-500" />
                                        </div>
                                        <div className="text-xl font-bold text-white">{status?.cpu_percent ?? 0}% CPU</div>
                                        <div className="text-xs text-slate-400 mt-1">{status?.ram_mb ?? 0} MB RAM • PID {status?.pid || '-'}</div>
                                    </div>
                                    <div className="bg-slate-800/50 backdrop-blur-sm border border-slate-700/50 rounded-xl p-5">
                                        <div className="flex items-center justify-between mb-3">
                                            <h3 className="text-slate-400 font-medium text-xs uppercase tracking-wide">Traffic Bypassed</h3>
                                            <HardDrive className="w-4 h-4 text-slate-500" />
                                        </div>
                                        <div className="text-xl font-bold text-white">{formatBytes(status?.bytes_processed)}</div>
                                        <div className="text-xs text-slate-400 mt-1">{(status?.packets_processed ?? 0).toLocaleString()} packets</div>
                                    </div>
                                    <div className="bg-slate-800/50 backdrop-blur-sm border border-slate-700/50 rounded-xl p-5">
                                        <div className="flex items-center justify-between mb-3">
                                            <h3 className="text-slate-400 font-medium text-xs uppercase tracking-wide">Features</h3>
                                            <Settings className="w-4 h-4 text-slate-500" />
                                        </div>
                                        <div className="flex flex-col gap-1.5 mt-1">
                                            <div className="flex justify-between items-center text-xs">
                                                <span className="text-slate-400">QUIC/UDP:</span>
                                                <span className={status?.quic_enabled ? 'text-emerald-400' : 'text-slate-500'}>
                                                    {status?.quic_enabled ? 'Active' : 'Disabled'}
                                                </span>
                                            </div>
                                            <div className="flex justify-between items-center text-xs">
                                                <span className="text-slate-400">Auto-Hostlist:</span>
                                                <span className={status?.auto_hostlist_enabled ? 'text-indigo-400' : 'text-slate-500'}>
                                                    {status?.auto_hostlist_enabled ? 'Active' : 'Disabled'}
                                                </span>
                                            </div>
                                            <div className="flex justify-between items-center text-xs">
                                                <span className="text-slate-400">Hostlist Count:</span>
                                                <span className="text-white">{status?.hostlist_count || 0} domains</span>
                                            </div>
                                        </div>
                                    </div>
                                </div>

                                {/* Mode & DPI Flags Display */}
                                <div className="bg-slate-800/50 backdrop-blur-sm border border-slate-700/50 rounded-xl p-5">
                                    <div className="flex items-center justify-between mb-3">
                                        <h3 className="text-slate-400 font-medium text-xs uppercase tracking-wide">Active Strategy: {status?.config_mode || 'unknown'}</h3>
                                    </div>
                                    {status?.nfqws_opt ? (
                                        <div className="flex flex-wrap gap-1.5">
                                            {status.nfqws_opt.split(/\s+--/).map((flag, i) => {
                                                const f = (i === 0 ? flag : '--' + flag).trim();
                                                if (!f) return null;
                                                const [key, val] = f.split('=');
                                                return (
                                                    <span key={i} title={f} className="inline-block px-2 py-1 bg-slate-900 text-slate-300 font-mono text-[11px] rounded border border-slate-700">
                                                        {val ? <><span className="text-slate-500">{key}=</span><span className="text-amber-300">{val}</span></> : <span className="text-slate-300">{key}</span>}
                                                    </span>
                                                );
                                            })}
                                        </div>
                                    ) : <div className="text-sm text-slate-500 italic">No strategy configured</div>}
                                </div>

                                {/* Live Logs */}
                                <div className="bg-slate-800/50 backdrop-blur-sm border border-slate-700/50 rounded-xl flex flex-col h-[400px]">
                                    <div className="p-3 border-b border-slate-700/50 flex justify-between items-center bg-slate-800/80 rounded-t-xl">
                                        <h2 className="text-sm font-semibold text-white flex items-center gap-2"><Activity className="w-4 h-4"/> Live Logs (journalctl)</h2>
                                    </div>
                                    <div className="flex-1 p-4 bg-slate-950 overflow-auto font-mono text-xs text-slate-400 leading-relaxed rounded-b-xl">
                                        {logs ? logs.split('\n').map((line, i) => {
                                            const isError = /error|fail|crit/i.test(line);
                                            const isWarn  = /warn|stop|deactiv/i.test(line);
                                            const isOk    = /started|starting|active/i.test(line);
                                            const cls = isError ? 'text-rose-400' : isWarn ? 'text-amber-400' : isOk ? 'text-emerald-400' : '';
                                            return <div key={i} className={`break-all hover:bg-slate-800/50 px-1 rounded ${cls}`}>{line}</div>;
                                        }) : <div className="text-slate-500 italic">No logs available.</div>}
                                        <div ref={logEndRef} />
                                    </div>
                                </div>
                            </div>
                        )}

                        {/* TAB: STRATEGIES */}
                        {activeTab === 'strategies' && (
                            <div className="space-y-6">
                                <div className="bg-indigo-500/10 border border-indigo-500/20 rounded-xl p-5">
                                    <h2 className="text-lg font-bold text-indigo-300 mb-2">Pilih Strategi Bypass ISP</h2>
                                    <p className="text-slate-400 text-sm mb-4">Setiap ISP menggunakan metode Deep Packet Inspection yang berbeda. Pilih strategi yang paling sesuai dengan ISP yang Anda gunakan.</p>
                                    
                                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 mb-6">
                                        {strategies.map(s => (
                                            <div 
                                                key={s.key} 
                                                onClick={() => setSelectedStrategy(s.key)}
                                                className={`p-4 rounded-xl border-2 cursor-pointer transition ${
                                                    selectedStrategy === s.key 
                                                        ? 'bg-slate-800 border-indigo-500 shadow-[0_0_15px_rgba(99,102,241,0.2)]' 
                                                        : 'bg-slate-800/50 border-slate-700/50 hover:border-slate-600'
                                                }`}
                                            >
                                                <div className="text-2xl mb-2">{s.icon}</div>
                                                <div className="font-semibold text-white mb-1">{s.name}</div>
                                                <div className="text-xs text-slate-400 line-clamp-3">{s.description}</div>
                                            </div>
                                        ))}
                                    </div>

                                    <div className="flex flex-col sm:flex-row gap-6 p-4 bg-slate-900/50 rounded-lg border border-slate-800">
                                        <label className="flex items-center gap-3 cursor-pointer">
                                            <input type="checkbox" checked={enableUdp} onChange={e => setEnableUdp(e.target.checked)} className="w-5 h-5 rounded border-slate-600 bg-slate-800 text-indigo-500 focus:ring-indigo-500 focus:ring-offset-slate-900" />
                                            <div>
                                                <div className="text-sm font-medium text-white">Enable QUIC / UDP Bypass</div>
                                                <div className="text-xs text-slate-500">Penting untuk YouTube dan situs dengan Cloudflare.</div>
                                            </div>
                                        </label>
                                        <label className="flex items-center gap-3 cursor-pointer">
                                            <input type="checkbox" checked={enableAutoHostlist} onChange={e => setEnableAutoHostlist(e.target.checked)} className="w-5 h-5 rounded border-slate-600 bg-slate-800 text-indigo-500 focus:ring-indigo-500 focus:ring-offset-slate-900" />
                                            <div>
                                                <div className="text-sm font-medium text-white">Enable Auto-Hostlist</div>
                                                <div className="text-xs text-slate-500">Hanya bypass situs yang terdeteksi diblokir (menghemat CPU).</div>
                                            </div>
                                        </label>
                                    </div>

                                    <div className="mt-6 flex justify-end">
                                        <button 
                                            onClick={handleApplyStrategy} 
                                            disabled={actionLoading}
                                            className="px-6 py-2.5 bg-indigo-600 text-white font-medium rounded-lg hover:bg-indigo-500 transition flex items-center gap-2 disabled:opacity-50"
                                        >
                                            <Save className="w-4 h-4" /> 
                                            {actionLoading ? 'Menerapkan...' : 'Terapkan Strategi & Restart'}
                                        </button>
                                    </div>
                                </div>
                            </div>
                        )}

                        {/* TAB: HOSTLIST */}
                        {activeTab === 'hostlist' && (
                            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                                {/* Manual Hostlist */}
                                <div className="bg-slate-800/50 border border-slate-700/50 rounded-xl overflow-hidden flex flex-col h-[500px]">
                                    <div className="p-4 bg-slate-800/80 border-b border-slate-700/50">
                                        <h3 className="font-semibold text-white">Manual Hostlist</h3>
                                        <p className="text-xs text-slate-400 mt-1">Daftar domain yang selalu di-bypass oleh Zapret.</p>
                                    </div>
                                    <div className="p-4 border-b border-slate-700/50 flex gap-2">
                                        <input 
                                            type="text" value={hostInput} onChange={e => setHostInput(e.target.value)}
                                            placeholder="contoh: reddit.com, vimeo.com"
                                            className="flex-1 bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-indigo-500"
                                            onKeyDown={e => e.key === 'Enter' && handleAddHost()}
                                        />
                                        <button onClick={handleAddHost} disabled={!hostInput.trim() || actionLoading}
                                            className="px-4 py-2 bg-indigo-600 text-white text-sm font-medium rounded-lg hover:bg-indigo-500 disabled:opacity-50">
                                            Tambah
                                        </button>
                                    </div>
                                    <div className="flex-1 overflow-auto p-2">
                                        {hostlist.length === 0 ? (
                                            <div className="text-center text-slate-500 mt-10 text-sm">Hostlist kosong. Semua trafik di-bypass jika filter mode=none.</div>
                                        ) : (
                                            <ul className="space-y-1">
                                                {hostlist.map((domain, i) => (
                                                    <li key={i} className="flex justify-between items-center px-3 py-2 hover:bg-slate-700/30 rounded-lg group">
                                                        <span className="text-sm text-slate-300 font-mono">{domain}</span>
                                                        <button onClick={() => handleRemoveHost(domain)} className="text-rose-400/0 group-hover:text-rose-400 transition">✕</button>
                                                    </li>
                                                ))}
                                            </ul>
                                        )}
                                    </div>
                                </div>

                                {/* Auto Hostlist */}
                                <div className="bg-slate-800/50 border border-slate-700/50 rounded-xl overflow-hidden flex flex-col h-[500px]">
                                    <div className="p-4 bg-slate-800/80 border-b border-slate-700/50 flex justify-between items-center">
                                        <div>
                                            <h3 className="font-semibold text-white">Auto Hostlist</h3>
                                            <p className="text-xs text-slate-400 mt-1">Domain yang otomatis terdeteksi diblokir oleh DPI.</p>
                                        </div>
                                        <button onClick={handleClearAutoHostlist} disabled={actionLoading || autoHostlist.length === 0}
                                            className="px-3 py-1.5 text-xs bg-rose-600/20 text-rose-400 hover:bg-rose-600/30 rounded border border-rose-600/30 transition disabled:opacity-50">
                                            Clear Data
                                        </button>
                                    </div>
                                    <div className="flex-1 overflow-auto p-2 bg-slate-900/30">
                                        {!status?.auto_hostlist_enabled ? (
                                            <div className="text-center text-amber-500/70 mt-10 text-sm px-6">
                                                <AlertTriangle className="w-8 h-8 mx-auto mb-2 opacity-50" />
                                                Fitur Auto-Hostlist saat ini nonaktif. Aktifkan melalui tab ISP Strategies.
                                            </div>
                                        ) : autoHostlist.length === 0 ? (
                                            <div className="text-center text-slate-500 mt-10 text-sm">Belum ada domain yang terdeteksi diblokir.</div>
                                        ) : (
                                            <ul className="space-y-1">
                                                {autoHostlist.map((domain, i) => (
                                                    <li key={i} className="px-3 py-2 text-sm text-amber-300 font-mono bg-slate-900/50 rounded">{domain}</li>
                                                ))}
                                            </ul>
                                        )}
                                    </div>
                                </div>
                            </div>
                        )}

                        {/* TAB: BLOCKCHECK */}
                        {activeTab === 'blockcheck' && (
                            <div className="max-w-3xl mx-auto space-y-6">
                                <div className="bg-slate-800/50 border border-slate-700/50 rounded-xl p-6">
                                    <h2 className="text-lg font-semibold text-white mb-1 flex items-center gap-2"><Search className="w-5 h-5 text-indigo-400"/> Uji Aksesibilitas Domain</h2>
                                    <p className="text-sm text-slate-400 mb-6">Test apakah sebuah website berhasil di-bypass oleh konfigurasi Zapret saat ini dari dalam server lokal.</p>
                                    
                                    <div className="flex gap-3">
                                        <input 
                                            type="text" value={blockcheckDomain} onChange={e => setBlockcheckDomain(e.target.value)}
                                            placeholder="reddit.com"
                                            className="flex-1 bg-slate-900 border border-slate-700 rounded-lg px-4 py-3 text-white focus:outline-none focus:border-indigo-500 font-mono"
                                            onKeyDown={e => e.key === 'Enter' && handleBlockcheck()}
                                        />
                                        <button onClick={handleBlockcheck} disabled={isChecking || !blockcheckDomain.trim()}
                                            className="px-6 py-3 bg-indigo-600 text-white font-medium rounded-lg hover:bg-indigo-500 disabled:opacity-50 flex items-center gap-2">
                                            {isChecking ? <RefreshCw className="w-5 h-5 animate-spin" /> : <Globe className="w-5 h-5" />}
                                            {isChecking ? 'Testing...' : 'Test Domain'}
                                        </button>
                                    </div>
                                </div>

                                {blockcheckResult && (
                                    <div className="bg-slate-800 border border-slate-700 rounded-xl overflow-hidden">
                                        <div className={`p-4 border-b ${
                                            blockcheckResult.verdict === 'bypass_success' ? 'bg-emerald-900/30 border-emerald-800/50' : 
                                            blockcheckResult.verdict === 'http_only' ? 'bg-amber-900/30 border-amber-800/50' : 
                                            'bg-rose-900/30 border-rose-800/50'
                                        }`}>
                                            <div className="font-semibold text-lg text-white flex items-center gap-2">
                                                {blockcheckResult.verdict === 'bypass_success' ? <CheckCircle className="text-emerald-400 w-6 h-6"/> : <XCircle className="text-rose-400 w-6 h-6"/>}
                                                {blockcheckResult.verdict_text}
                                            </div>
                                        </div>
                                        <div className="p-6 grid grid-cols-1 sm:grid-cols-3 gap-4">
                                            <div className="bg-slate-900 p-4 rounded-lg border border-slate-700/50">
                                                <div className="text-xs text-slate-500 mb-1">DNS Resolution</div>
                                                <div className="text-sm font-mono text-white">
                                                    {blockcheckResult.dns.resolved ? <span className="text-emerald-400">Resolved ({blockcheckResult.dns.addresses.length} IPs)</span> : <span className="text-rose-400">Failed</span>}
                                                </div>
                                            </div>
                                            <div className="bg-slate-900 p-4 rounded-lg border border-slate-700/50">
                                                <div className="text-xs text-slate-500 mb-1">HTTP (Port 80)</div>
                                                <div className="text-sm font-mono text-white">
                                                    {blockcheckResult.http.reachable ? <span className="text-emerald-400">Code: {blockcheckResult.http.http_code}</span> : <span className="text-rose-400">Timeout / Reset</span>}
                                                </div>
                                            </div>
                                            <div className="bg-slate-900 p-4 rounded-lg border border-slate-700/50">
                                                <div className="text-xs text-slate-500 mb-1">HTTPS (Port 443)</div>
                                                <div className="text-sm font-mono text-white">
                                                    {blockcheckResult.https.reachable ? <span className="text-emerald-400">Code: {blockcheckResult.https.http_code}</span> : <span className="text-rose-400">Timeout / Reset</span>}
                                                </div>
                                            </div>
                                        </div>
                                        {!blockcheckResult.zapret_active && (
                                            <div className="p-3 bg-amber-500/10 text-amber-400 text-sm text-center border-t border-amber-500/20">
                                                <AlertTriangle className="w-4 h-4 inline mr-1 -mt-0.5" /> Peringatan: Service Zapret sedang tidak aktif! Test ini mencerminkan network asli ISP.
                                            </div>
                                        )}
                                    </div>
                                )}
                            </div>
                        )}

                        {/* TAB: ADVANCED CONFIG */}
                        {activeTab === 'config' && (
                            <div className="bg-slate-800/50 backdrop-blur-sm border border-slate-700/50 rounded-xl flex flex-col h-[600px]">
                                <div className="p-4 border-b border-slate-700/50 flex justify-between items-center bg-slate-800/80 rounded-t-xl">
                                    <div>
                                        <h2 className="text-base font-semibold text-white">Raw Configuration (/opt/zapret/config)</h2>
                                        <p className="text-xs text-slate-400 mt-1">Hanya edit manual jika Anda mengerti konfigurasi NFQWS.</p>
                                    </div>
                                    {isEditing ? (
                                        <div className="flex gap-2">
                                            <button onClick={() => { setIsEditing(false); setEditConfig(''); setErrorMsg(''); }} className="px-3 py-1.5 text-sm bg-slate-700 text-white rounded-lg hover:bg-slate-600 transition">Cancel</button>
                                            <button onClick={handleSaveConfig} disabled={actionLoading} className="px-3 py-1.5 text-sm bg-indigo-600 text-white rounded-lg hover:bg-indigo-500 transition flex items-center gap-1.5 disabled:opacity-50">
                                                <Save className="w-4 h-4" /> Save & Restart
                                            </button>
                                        </div>
                                    ) : (
                                        <button onClick={() => { setEditConfig(config); setIsEditing(true); }} className="px-3 py-1.5 text-sm bg-slate-700 text-white rounded-lg hover:bg-slate-600 transition">
                                            Edit Raw Config
                                        </button>
                                    )}
                                </div>
                                <div className="flex-1 overflow-hidden">
                                    {isEditing ? (
                                        <textarea
                                            value={editConfig} onChange={(e) => setEditConfig(e.target.value)}
                                            className="w-full h-full bg-slate-950 text-emerald-400 font-mono text-sm p-4 focus:outline-none resize-none leading-relaxed"
                                            spellCheck={false}
                                        />
                                    ) : (
                                        <pre className="w-full h-full bg-slate-950 text-slate-300 font-mono text-sm p-4 overflow-auto leading-relaxed">
                                            {config || 'No configuration loaded.'}
                                        </pre>
                                    )}
                                </div>
                            </div>
                        )}
                    </>
                )}
            </div>
        </div>
    );
}
