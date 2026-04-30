import React, { useState, useEffect, useRef } from 'react';
import axios from 'axios';
import { Play, Square, RotateCw, Save, RefreshCw, Shield, Activity, Cpu, HardDrive } from 'lucide-react';

const API_URL = import.meta.env.VITE_API_URL || '';

export default function ZapretPage() {
    const [status, setStatus] = useState(null);
    const [config, setConfig] = useState('');
    const [logs, setLogs] = useState('');
    const [isLoading, setIsLoading] = useState(true);
    const [isEditing, setIsEditing] = useState(false);
    const [actionLoading, setActionLoading] = useState(false);
    const logEndRef = useRef(null);

    const fetchData = async () => {
        try {
            const token = localStorage.getItem('token');
            const headers = { Authorization: `Bearer ${token}` };
            
            const [statusRes, configRes, logsRes] = await Promise.all([
                axios.get(`${API_URL}/api/zapret/status`, { headers }),
                axios.get(`${API_URL}/api/zapret/config`, { headers }).catch(() => ({ data: { config: '' } })),
                axios.get(`${API_URL}/api/zapret/logs`, { headers })
            ]);
            
            setStatus(statusRes.data);
            if (!isEditing) {
                setConfig(configRes.data.config);
            }
            setLogs(logsRes.data.logs);
        } catch (error) {
            console.error('Error fetching Zapret data:', error);
        } finally {
            setIsLoading(false);
        }
    };

    useEffect(() => {
        fetchData();
        const interval = setInterval(fetchData, 10000); // refresh every 10s
        return () => clearInterval(interval);
    }, [isEditing]);

    useEffect(() => {
        if (logEndRef.current) {
            logEndRef.current.scrollIntoView({ behavior: 'smooth' });
        }
    }, [logs]);

    const handleAction = async (action) => {
        setActionLoading(true);
        try {
            const token = localStorage.getItem('token');
            await axios.post(`${API_URL}/api/zapret/${action}`, {}, {
                headers: { Authorization: `Bearer ${token}` }
            });
            await fetchData();
            alert(`Zapret ${action} successful`);
        } catch (error) {
            alert(`Failed to ${action} Zapret: ${error.response?.data?.detail || error.message}`);
        } finally {
            setActionLoading(false);
        }
    };

    const handleSaveConfig = async () => {
        setActionLoading(true);
        try {
            const token = localStorage.getItem('token');
            await axios.put(`${API_URL}/api/zapret/config`, { config }, {
                headers: { Authorization: `Bearer ${token}` }
            });
            setIsEditing(false);
            await fetchData();
            alert('Configuration saved successfully. Zapret has been restarted.');
        } catch (error) {
            alert(`Failed to save config: ${error.response?.data?.detail || error.message}`);
        } finally {
            setActionLoading(false);
        }
    };

    const formatBytes = (bytes) => {
        if (bytes === 0) return '0 B';
        const k = 1024;
        const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    };

    const formatUptime = (seconds) => {
        if (!seconds) return '0s';
        const d = Math.floor(seconds / (3600 * 24));
        const h = Math.floor(seconds % (3600 * 24) / 3600);
        const m = Math.floor(seconds % 3600 / 60);
        return `${d > 0 ? d + 'd ' : ''}${h}h ${m}m`;
    };

    if (isLoading && !status) return <div className="p-6 text-slate-300">Loading Zapret status...</div>;

    return (
        <div className="p-6 max-w-7xl mx-auto space-y-6">
            <div className="flex justify-between items-center">
                <div>
                    <h1 className="text-2xl font-bold text-white flex items-center gap-2">
                        <Shield className="w-6 h-6 text-indigo-400" />
                        Zapret DPI Bypass
                    </h1>
                    <p className="text-slate-400 text-sm mt-1">Manage Deep Packet Inspection bypass settings and monitor performance.</p>
                </div>
                <div className="flex gap-2">
                    <button 
                        onClick={() => handleAction('start')} 
                        disabled={actionLoading || status?.running}
                        className="px-4 py-2 bg-emerald-600/20 text-emerald-400 hover:bg-emerald-600/30 rounded-lg flex items-center gap-2 transition disabled:opacity-50"
                    >
                        <Play className="w-4 h-4" /> Start
                    </button>
                    <button 
                        onClick={() => handleAction('stop')} 
                        disabled={actionLoading || !status?.running}
                        className="px-4 py-2 bg-rose-600/20 text-rose-400 hover:bg-rose-600/30 rounded-lg flex items-center gap-2 transition disabled:opacity-50"
                    >
                        <Square className="w-4 h-4" /> Stop
                    </button>
                    <button 
                        onClick={() => handleAction('restart')} 
                        disabled={actionLoading}
                        className="px-4 py-2 bg-indigo-600/20 text-indigo-400 hover:bg-indigo-600/30 rounded-lg flex items-center gap-2 transition disabled:opacity-50"
                    >
                        <RotateCw className="w-4 h-4" /> Restart
                    </button>
                </div>
            </div>

            {/* Status Cards */}
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                <div className="bg-slate-800/50 backdrop-blur-sm border border-slate-700/50 rounded-xl p-5">
                    <div className="flex items-center justify-between mb-4">
                        <h3 className="text-slate-400 font-medium text-sm">Service Status</h3>
                        <Activity className="w-5 h-5 text-slate-500" />
                    </div>
                    <div className="flex items-end justify-between">
                        <div>
                            <div className="text-2xl font-bold text-white flex items-center gap-2">
                                {status?.running ? (
                                    <><span className="w-2.5 h-2.5 rounded-full bg-emerald-500 animate-pulse"></span> Running</>
                                ) : (
                                    <><span className="w-2.5 h-2.5 rounded-full bg-rose-500"></span> Stopped</>
                                )}
                            </div>
                            <div className="text-sm text-slate-400 mt-1">Uptime: {formatUptime(status?.uptime_seconds)}</div>
                        </div>
                    </div>
                </div>

                <div className="bg-slate-800/50 backdrop-blur-sm border border-slate-700/50 rounded-xl p-5">
                    <div className="flex items-center justify-between mb-4">
                        <h3 className="text-slate-400 font-medium text-sm">Resource Usage</h3>
                        <Cpu className="w-5 h-5 text-slate-500" />
                    </div>
                    <div className="flex items-end justify-between">
                        <div>
                            <div className="text-2xl font-bold text-white">{status?.cpu_percent || 0}% CPU</div>
                            <div className="text-sm text-slate-400 mt-1">{status?.ram_mb || 0} MB RAM • PID {status?.pid || '-'}</div>
                        </div>
                    </div>
                </div>

                <div className="bg-slate-800/50 backdrop-blur-sm border border-slate-700/50 rounded-xl p-5">
                    <div className="flex items-center justify-between mb-4">
                        <h3 className="text-slate-400 font-medium text-sm">Traffic Bypassed</h3>
                        <HardDrive className="w-5 h-5 text-slate-500" />
                    </div>
                    <div className="flex items-end justify-between">
                        <div>
                            <div className="text-2xl font-bold text-white">{formatBytes(status?.bytes_processed || 0)}</div>
                            <div className="text-sm text-slate-400 mt-1">{(status?.packets_processed || 0).toLocaleString()} packets</div>
                        </div>
                    </div>
                </div>

                <div className="bg-slate-800/50 backdrop-blur-sm border border-slate-700/50 rounded-xl p-5">
                    <div className="flex items-center justify-between mb-4">
                        <h3 className="text-slate-400 font-medium text-sm">Mode & Strategy</h3>
                        <Shield className="w-5 h-5 text-slate-500" />
                    </div>
                    <div className="flex items-end justify-between">
                        <div>
                            <div className="text-lg font-bold text-white truncate" title={status?.config_mode}>{status?.config_mode || 'Unknown'}</div>
                            <div className="text-sm text-slate-400 mt-1 truncate" title={status?.nfqws_opt}>{status?.nfqws_opt || 'No strategy'}</div>
                        </div>
                    </div>
                </div>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                {/* Configuration */}
                <div className="bg-slate-800/50 backdrop-blur-sm border border-slate-700/50 rounded-xl flex flex-col h-[500px]">
                    <div className="p-4 border-b border-slate-700/50 flex justify-between items-center bg-slate-800/80 rounded-t-xl">
                        <h2 className="text-lg font-semibold text-white">Configuration (/opt/zapret/config)</h2>
                        {isEditing ? (
                            <div className="flex gap-2">
                                <button onClick={() => setIsEditing(false)} className="px-3 py-1.5 text-sm bg-slate-700 text-white rounded hover:bg-slate-600 transition">Cancel</button>
                                <button onClick={handleSaveConfig} disabled={actionLoading} className="px-3 py-1.5 text-sm bg-indigo-600 text-white rounded hover:bg-indigo-500 transition flex items-center gap-1">
                                    <Save className="w-4 h-4" /> Save & Restart
                                </button>
                            </div>
                        ) : (
                            <button onClick={() => setIsEditing(true)} className="px-3 py-1.5 text-sm bg-slate-700 text-white rounded hover:bg-slate-600 transition">Edit Config</button>
                        )}
                    </div>
                    <div className="flex-1 p-0 overflow-hidden relative">
                        {isEditing ? (
                            <textarea
                                value={config}
                                onChange={(e) => setConfig(e.target.value)}
                                className="w-full h-full bg-slate-950 text-emerald-400 font-mono text-sm p-4 focus:outline-none resize-none"
                                spellCheck="false"
                            />
                        ) : (
                            <pre className="w-full h-full bg-slate-950 text-slate-300 font-mono text-sm p-4 overflow-auto">
                                {config || 'No configuration loaded. Is Zapret installed?'}
                            </pre>
                        )}
                    </div>
                </div>

                {/* Live Logs */}
                <div className="bg-slate-800/50 backdrop-blur-sm border border-slate-700/50 rounded-xl flex flex-col h-[500px]">
                    <div className="p-4 border-b border-slate-700/50 flex justify-between items-center bg-slate-800/80 rounded-t-xl">
                        <h2 className="text-lg font-semibold text-white">Live Logs (journalctl)</h2>
                        <button onClick={fetchData} className="text-slate-400 hover:text-white transition">
                            <RefreshCw className={`w-4 h-4 ${actionLoading ? 'animate-spin' : ''}`} />
                        </button>
                    </div>
                    <div className="flex-1 p-4 bg-slate-950 overflow-auto font-mono text-xs text-slate-400 leading-relaxed">
                        {logs ? (
                            logs.split('\n').map((line, i) => (
                                <div key={i} className="break-all hover:bg-slate-800/50 px-1 rounded">
                                    {line}
                                </div>
                            ))
                        ) : (
                            <div className="text-slate-500 italic">No logs available.</div>
                        )}
                        <div ref={logEndRef} />
                    </div>
                </div>
            </div>
        </div>
    );
}
