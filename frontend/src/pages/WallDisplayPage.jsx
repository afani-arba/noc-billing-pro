import React, { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import api from '@/lib/api';
import { AreaChart, Area, ResponsiveContainer, Tooltip as RechartsTooltip } from 'recharts';
import { ShieldAlert, WifiOff, Monitor, Server, RotateCcw, MonitorPlay, X, Terminal, ArrowDown, ArrowUp, Activity, Zap, CheckCircle, AlertTriangle, ChevronDown, ChevronUp } from 'lucide-react';

export default function WallDisplayPage() {
  const navigate = useNavigate();
  const [data, setData] = useState({ routers: [], security_alerts: [], global_stats: {} });
  const [time, setTime] = useState(new Date().toLocaleTimeString('id-ID', { hour: '2-digit', minute: '2-digit', second: '2-digit' }));
  const [selectedRouter, setSelectedRouter] = useState(null);
  const [acting, setActing] = useState(false);
  const [winboxInfo, setWinboxInfo] = useState(null);
  const [telemetryResult, setTelemetryResult] = useState(null);
  const [telemetryLoading, setTelemetryLoading] = useState(false);
  const [snmpResult, setSnmpResult] = useState(null);
  const [snmpLoading, setSnmpLoading] = useState(false);
  const [alertsOpen, setAlertsOpen] = useState(false);
  
  const historyRef = useRef({});

  useEffect(() => {
    const fetchData = async () => {
      try {
        const res = await api.get('/dashboard/wall-data');
        let liveRouters = res.data.routers || [];
        
        liveRouters.sort((a, b) => {
          if (a.status === 'offline' && b.status !== 'offline') return -1;
          if (b.status === 'offline' && a.status !== 'offline') return 1;
          const alertA = (a.cpu > 80 || a.ram > 80) ? 1 : 0;
          const alertB = (b.cpu > 80 || b.ram > 80) ? 1 : 0;
          if (alertA !== alertB) return alertB - alertA;
          const trafA = (a.dl_total || 0) + (a.ul_total || 0);
          const trafB = (b.dl_total || 0) + (b.ul_total || 0);
          return trafB - trafA;
        });

        const newHistory = { ...historyRef.current };
        const nowLabel = new Date().toLocaleTimeString('id-ID', {hour: '2-digit', minute: '2-digit', second: '2-digit'});
        
        liveRouters.forEach(rt => {
           if (!newHistory[rt.id]) newHistory[rt.id] = [];
           const dlMb = typeof rt.dl_total === 'number' && rt.dl_total > 0 ? rt.dl_total / 1_000_000 : 0;
           const ulMb = typeof rt.ul_total === 'number' && rt.ul_total > 0 ? rt.ul_total / 1_000_000 : 0;
           
           newHistory[rt.id].push({
             name: nowLabel,
             dl: parseFloat(dlMb.toFixed(3)),
             ul: parseFloat(ulMb.toFixed(3)),
           });
           
           if (newHistory[rt.id].length > 60) {
              newHistory[rt.id].shift();
           }
        });

        historyRef.current = newHistory;
        setData({
           routers: liveRouters,
           security_alerts: res.data.security_alerts || [],
           global_stats: res.data.global_stats || {}
        });
      } catch (err) {
        console.error("WallDisplay Error:", err);
      }
    };

    fetchData();
    const interval = setInterval(() => {
      fetchData();
      setTime(new Date().toLocaleTimeString('id-ID', { hour: '2-digit', minute: '2-digit', second: '2-digit' }));
    }, 2000);

    return () => clearInterval(interval);
  }, []);


  const formatGbps = (bps) => {
    if (!bps) return '0.00 G';
    const gbps = bps / 1_000_000_000;
    if (gbps < 1) return (bps / 1_000_000).toFixed(1) + ' M';
    return gbps.toFixed(2) + ' G';
  };
  
  const formatMbps = (bps) => {
    if (!bps) return '0';
    const mbps = bps / 1_000_000;
    if (mbps < 0.1) return (bps / 1000).toFixed(0) + 'K';
    return mbps.toFixed(1) + ' M';
  };

  const getCpuGradient = (cpu) => {
    if (!cpu || cpu <= 50) return 'linear-gradient(90deg, #1e40af 0%, #3b82f6 100%)';
    const midPoint = (50 / cpu) * 100;
    return `linear-gradient(90deg, #1e40af 0%, #3b82f6 ${midPoint}%, #ef4444 100%)`;
  };

  const handleWinbox = async (type) => {
    try {
      setActing(true);
      const res = await api.get(`/devices/${selectedRouter.id}/winbox-url`);
      const url = type === 'mobile' ? res.data.mobile_url : res.data.url;
      setWinboxInfo({ ...res.data, activeType: type });
      
      const a = document.createElement("a");
      a.href = url;
      a.target = "_top";
      document.body.appendChild(a);
      a.click();
      setTimeout(() => {
         if (document.body.contains(a)) document.body.removeChild(a);
      }, 500);
    } catch (e) {
      alert("Gagal memuat URL Winbox: " + (e.response?.data?.detail || e.message));
    } finally {
      setActing(false);
    }
  };

  const handleSetupTelemetry = async () => {
    if (!selectedRouter) return;
    setTelemetryLoading(true);
    setTelemetryResult(null);
    try {
      const res = await api.post(`/devices/${selectedRouter.id}/setup-telemetry`);
      setTelemetryResult(res.data);
      setData(prev => ({
        ...prev,
        routers: prev.routers.map(r =>
          r.id === selectedRouter.id ? { ...r, snmp_active: true, netflow_active: false } : r
        )
      }));
    } catch (e) {
      setTelemetryResult({
        ok_count: 0,
        fail_count: 1,
        message: '❌ Gagal: ' + (e.response?.data?.detail || e.message),
        results: [{ step: 'Koneksi', ok: false, detail: e.response?.data?.detail || e.message }]
      });
    } finally {
      setTelemetryLoading(false);
    }
  };

  const handleTestSnmp = async () => {
    if (!selectedRouter) return;
    setSnmpLoading(true);
    setSnmpResult(null);
    try {
      const res = await api.get(`/devices/${selectedRouter.id}/test-snmp`);
      setSnmpResult(res.data);
    } catch (e) {
      setSnmpResult({
        success: false,
        error: e.response?.data?.detail || e.message || 'Koneksi gagal'
      });
    } finally {
      setSnmpLoading(false);
    }
  };

  const handleReboot = async () => {
    if (!selectedRouter) return;
    const ok = window.confirm(
      `⚠️ Yakin ingin me-REBOOT router "${selectedRouter.name || selectedRouter.identity}"?\n\nRouter akan offline selama ±30 detik.`
    );
    if (!ok) return;
    setActing(true);
    try {
      await api.post(`/devices/${selectedRouter.id}/reboot`);
      alert(`✅ Perintah reboot berhasil dikirim ke ${selectedRouter.name || selectedRouter.identity}.`);
      setSelectedRouter(null);
    } catch (e) {
      alert('❌ Gagal reboot: ' + (e.response?.data?.detail || e.message));
    } finally {
      setActing(false);
    }
  };

  const gs = data.global_stats;
  const warningCount = data.security_alerts.length;

  return (
    <div className="min-h-screen border-t-[3px] border-blue-500 bg-[#0f172a] text-slate-300 font-sans flex flex-col overflow-hidden selection:bg-blue-900/50" style={{ background: 'radial-gradient(circle at 50% 0%, #172554 0%, #0f172a 50%)' }}>
      
      {/* ── HEADER NAVBAR ── */}
      <div className="flex-none border-b border-white/[0.04] bg-[#0f172a]/60 z-20 shadow-xl shadow-black/20">

        {/* SINGLE HEADER: Branding kiri, semua stats + jam kanan — flex-wrap agar turun ke bawah */}
        <div className="flex items-center justify-between gap-3 px-4 py-3">

          {/* Left: Branding */}
          <div className="flex items-center gap-3 cursor-pointer group flex-none" onClick={() => navigate('/')}>
            <div className="w-9 h-9 rounded-xl bg-slate-800 border border-white/10 flex items-center justify-center text-slate-300 group-hover:text-blue-400 transition-all shadow-inner flex-none">
              <Monitor className="w-4 h-4" strokeWidth={1.5} />
            </div>
            <div>
              <h1 className="text-[15px] font-bold tracking-tight text-white leading-none drop-shadow-lg">
                NOC Billing <span className="text-blue-500 font-semibold">Pro</span>
              </h1>
              <p className="text-[9px] text-blue-400 font-bold tracking-[0.1em] uppercase mt-0.5">Wall Display</p>
            </div>
          </div>

          {/* Right: Clock */}
          <div className="text-[15px] font-mono font-medium text-slate-200 drop-shadow-md tabular-nums flex-none">
            {time}
          </div>
        </div>

        {/* STATS ROW — flex-wrap: turun ke bawah jika tidak muat, TIDAK scroll ke samping */}
        <div className="flex flex-wrap items-center gap-x-2 gap-y-2 px-4 pb-3">

          {/* Online */}
          <div className="flex items-center gap-2 px-3 py-2 bg-emerald-950/20 border border-emerald-500/30 rounded-lg">
            <div className="w-2.5 h-2.5 rounded-full bg-emerald-500 shadow-[0_0_10px_rgba(16,185,129,0.8)] flex-none"></div>
            <span className="text-emerald-400 font-bold text-xs uppercase tracking-widest leading-none whitespace-nowrap">{gs.online_routers || 0} Online</span>
          </div>

          {/* Offline */}
          <div className="flex items-center gap-2 px-3 py-2 bg-red-950/20 border border-red-500/30 rounded-lg">
            <WifiOff className="w-4 h-4 text-red-400 flex-none" />
            <span className="text-red-400 font-bold text-xs uppercase tracking-widest leading-none whitespace-nowrap">{gs.offline_routers || 0} Offline</span>
          </div>

          {/* Warning */}
          <div className="flex items-center gap-2 px-3 py-2 bg-amber-950/20 border border-amber-500/30 rounded-lg">
            <ShieldAlert className="w-4 h-4 text-amber-500 flex-none" />
            <span className="text-amber-500 font-bold text-xs uppercase tracking-widest leading-none whitespace-nowrap">{warningCount} Alert</span>
            {/* Alerts toggle on mobile */}
            {warningCount > 0 && (
              <button onClick={() => setAlertsOpen(prev => !prev)} className="lg:hidden ml-0.5">
                {alertsOpen ? <ChevronUp className="w-3 h-3 text-amber-400" /> : <ChevronDown className="w-3 h-3 text-amber-400" />}
              </button>
            )}
          </div>

          {/* Separator */}
          <div className="w-px h-4 bg-white/10 flex-none"></div>

          {/* Bandwidth DL/UL */}
          <div className="flex items-center gap-3 px-4 py-2 rounded-lg bg-black/20 border border-white/5">
            <div className="flex items-center gap-1.5 text-blue-400">
              <ArrowDown className="w-4 h-4 flex-none" strokeWidth={2.5} />
              <span className="font-bold text-xs tracking-wide whitespace-nowrap">{formatGbps(gs.total_dl_mbps)}</span>
            </div>
            <span className="text-slate-600 text-sm">/</span>
            <div className="flex items-center gap-1.5 text-teal-400">
              <ArrowUp className="w-4 h-4 flex-none" strokeWidth={2.5} />
              <span className="font-bold text-xs tracking-wide whitespace-nowrap">{formatGbps(gs.total_ul_mbps)}</span>
            </div>
          </div>

          {/* Separator */}
          <div className="w-px h-4 bg-white/10 flex-none"></div>

          {/* PPPoE / Hotspot */}
          <div className="flex items-center gap-3 px-4 py-2 rounded-lg bg-black/20 border border-white/5">
            <div className="flex items-center gap-2">
              <span className="font-bold text-xs text-slate-200 whitespace-nowrap">{gs.total_pppoe?.toLocaleString() || 0}</span>
              <span className="text-[10px] text-blue-400 uppercase tracking-widest font-bold">PPPoE</span>
            </div>
            <span className="text-slate-700 text-sm">·</span>
            <div className="flex items-center gap-2">
              <span className="font-bold text-xs text-slate-200 whitespace-nowrap">{gs.total_hotspot?.toLocaleString() || 0}</span>
              <span className="text-[10px] text-amber-500 uppercase tracking-widest font-bold">Hotspot</span>
            </div>
          </div>

        </div>

        {/* Mobile: Collapsible Alerts Panel */}
        {alertsOpen && (
          <div className="lg:hidden border-t border-white/[0.04] bg-[#0f172a]/80 max-h-60 overflow-y-auto px-4 py-3 space-y-2.5">
            {data.security_alerts.map((al, idx) => {
              const isCrit = al.type === 'CRITICAL' || al.type === 'error';
              return (
                <div key={idx} className={`p-3 rounded-xl border border-l-4 ${isCrit ? 'bg-red-950/20 border-r-white/5 border-t-white/5 border-b-white/5 border-l-red-500' : 'bg-[#1e293b]/30 border-r-white/5 border-t-white/5 border-b-white/5 border-l-amber-500'}`}>
                  <div className="flex items-start gap-2.5">
                    <div className={`mt-0.5 p-1 rounded-lg flex-none ${isCrit ? 'bg-red-500/10 text-red-500' : 'bg-amber-500/10 text-amber-500'}`}>
                      {isCrit ? <WifiOff className="w-3.5 h-3.5" /> : <ShieldAlert className="w-3.5 h-3.5" />}
                    </div>
                    <div className="min-w-0">
                      <h4 className={`text-[10px] font-bold uppercase tracking-widest truncate mb-1 ${isCrit ? 'text-red-400' : 'text-amber-400'}`}>{al.title || 'WARNING'}</h4>
                      <p className="text-[11px] text-slate-300 leading-relaxed">{al.message}</p>
                      <div className="text-[9px] font-mono text-slate-500 mt-1">{al.time}</div>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* ── MAIN LAYOUT ── */}
      <div className="flex-1 flex flex-col lg:flex-row overflow-y-auto lg:overflow-hidden p-3 sm:p-4 lg:p-6 gap-3 lg:gap-6">
        
        {/* LEFT: ROUTER GRID */}
        <div className="flex-1 lg:overflow-y-auto custom-scrollbar-minimal lg:pr-2 pb-6">
          {data.routers.length === 0 ? (
             <div className="flex flex-col items-center justify-center h-full min-h-[200px] text-slate-500 font-medium">
                <div className="w-12 h-12 border-4 border-slate-700 border-t-blue-500 rounded-full animate-spin mb-4" />
                Membangkitkan Radar...
             </div>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4 gap-3 sm:gap-4 xl:gap-5 auto-rows-max">
              {data.routers.map(rt => {
                const isOffline = rt.status === "offline";
                const sparkData = [...(historyRef.current[rt.id] || [])];

                // Offline Card
                if (isOffline) {
                  return (
                    <div key={rt.id} onClick={() => setSelectedRouter(rt)}
                         className="flex flex-col rounded-2xl bg-red-950/10 border border-red-900/30 p-4 cursor-pointer hover:bg-red-950/20 transition-all min-h-[200px] sm:min-h-[240px]">
                       <div className="flex items-center justify-between opacity-50 mb-2">
                         <div className="min-w-0 pr-2">
                           <span className="text-slate-500 font-bold uppercase tracking-widest text-[9px] block mb-0.5">ROUTER</span>
                           <span className="text-red-300 font-bold text-base sm:text-lg truncate block">{rt.name}</span>
                         </div>
                       </div>
                       <div className="flex-1 flex flex-col items-center justify-center">
                         <WifiOff className="w-10 h-10 sm:w-12 sm:h-12 text-red-500/50 mb-3" strokeWidth={1} />
                         <span className="text-[10px] font-bold text-red-500/50 tracking-[0.2em] uppercase">Offline Target</span>
                         <span className="text-[10px] font-mono text-slate-600 mt-2">{rt.ip}</span>
                       </div>
                    </div>
                  );
                }

                return (
                  <div key={rt.id} 
                       onClick={() => { setSelectedRouter(rt); setTelemetryResult(null); }}
                       className="flex flex-col rounded-2xl bg-[#1e293b]/60 border border-[#334155]/60 hover:bg-[#1e293b]/90 hover:border-slate-500/50 shadow-2xl transition-all duration-300 p-3.5 sm:p-4 cursor-pointer group">
                    
                    {/* Header Top Nav */}
                    <div className="flex justify-between items-center mb-3 pb-3 border-b border-transparent group-hover:border-white/5 transition-colors">
                      <div className="flex items-center gap-2 min-w-0 pr-2">
                         <h2 className="text-[9px] sm:text-[10px] font-bold text-slate-400 tracking-wider uppercase shrink-0">ROUTER:</h2>
                         <span className="text-slate-100 text-sm sm:text-[15px] font-bold truncate">{rt.name}</span>
                         <div className="w-2 h-2 shrink-0 rounded-full bg-emerald-500 shadow-[0_0_10px_rgba(16,185,129,0.8)] ml-0.5"></div>
                         {(rt.snmp_active || rt.netflow_active) && (
                           <span className="px-1.5 py-0.5 shrink-0 rounded-full bg-violet-500/20 border border-violet-500/40 text-[7px] sm:text-[8px] font-bold tracking-widest text-violet-400 uppercase flex items-center gap-1 ml-0.5">
                             <Zap className="w-2 h-2" /> SNMP
                           </span>
                         )}
                      </div>
                      <div className="text-[9px] uppercase tracking-widest font-mono text-slate-500 shrink-0">{rt.ip}</div>
                    </div>

                    {/* Body Split */}
                    <div className="flex gap-2.5 sm:gap-3 mb-3">
                       
                       {/* LEFT SIDE: CPU & RAM Box */}
                       <div className="flex-1 flex flex-col gap-2 min-w-0">
                          {/* CPU */}
                          <div className="bg-[#0f172a] rounded-xl p-2.5 sm:p-3 border border-white/[0.02] shadow-inner shadow-black/40">
                             <div className="text-[9px] sm:text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-2">CPU ({rt.cpu}%)</div>
                             <div className="h-2 w-full bg-[#1e293b] rounded-full overflow-hidden shadow-inner">
                                 <div className="h-full rounded-full transition-all duration-700 shadow-[inset_0_2px_4px_rgba(255,255,255,0.1)]" style={{width: `${Math.min(rt.cpu, 100)}%`, background: getCpuGradient(rt.cpu)}}></div>
                             </div>
                          </div>
                          {/* RAM */}
                          <div className="bg-[#0f172a] rounded-xl p-2.5 sm:p-3 border border-white/[0.02] shadow-inner shadow-black/40">
                             <div className="text-[9px] sm:text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-2">RAM ({rt.ram}%)</div>
                             <div className="h-2 w-full bg-[#1e293b] rounded-full overflow-hidden shadow-inner">
                                 <div className={`h-full rounded-full transition-all duration-700 shadow-[inset_0_2px_4px_rgba(255,255,255,0.1)] ${rt.ram > 80 ? 'bg-amber-400' : 'bg-blue-400 shadow-[0_0_10px_rgba(96,165,250,0.5)]'}`} style={{width: `${Math.min(rt.ram, 100)}%`}}></div>
                             </div>
                          </div>
                       </div>

                       {/* RIGHT SIDE: PING, DL, UL Box */}
                       <div className="w-[96px] sm:w-[108px] flex-none flex flex-col gap-1.5">
                           {/* PING */}
                           <div className="flex-1 bg-[#0f172a] rounded-[10px] border border-white/[0.02] shadow-inner px-2 flex items-center justify-between min-h-[34px]">
                              <div className="flex items-center gap-1"><Activity className="w-3 h-3 text-amber-500 flex-none"/><span className="text-[9px] text-slate-400 font-medium tracking-wide uppercase">PING</span></div>
                              <span className="text-[10px] font-mono font-medium text-slate-200">{rt.ping != null ? (rt.ping === 0 ? '<1' : rt.ping) + 'ms' : '---'}</span>
                           </div>
                           {/* DL */}
                           <div className="flex-1 bg-[#0f172a] rounded-[10px] border border-white/[0.02] shadow-inner px-2 flex items-center justify-between min-h-[34px]">
                              <div className="flex items-center gap-1"><ArrowDown className="w-3 h-3 text-[#38bdf8] flex-none"/><span className="text-[9px] text-slate-400 font-medium tracking-wide">DL</span></div>
                              <span className="text-[10px] font-mono font-medium text-white shrink-0">{formatMbps(rt.dl_total)}</span>
                           </div>
                           {/* UL */}
                           <div className="flex-1 bg-[#0f172a] rounded-[10px] border border-white/[0.02] shadow-inner px-2 flex items-center justify-between min-h-[34px]">
                              <div className="flex items-center gap-1"><ArrowUp className="w-3 h-3 text-[#f87171] flex-none"/><span className="text-[9px] text-slate-400 font-medium tracking-wide">UL</span></div>
                              <span className="text-[10px] font-mono font-medium text-white shrink-0">{formatMbps(rt.ul_total)}</span>
                           </div>
                       </div>
                    </div>

                    {/* BOTTOM: CHART BLOCK */}
                    <div className="w-full bg-[#0f172a] rounded-xl border border-white/[0.02] p-3 pb-2 flex flex-col h-[120px] sm:h-[140px] relative shadow-inner shadow-black/40">
                        {/* Legends */}
                        <div className="flex items-center gap-3 mb-2 truncate shrink-0">
                           <div className="flex items-center gap-1.5 shrink-0">
                               <div className="w-1.5 h-1.5 rounded-full bg-[#38bdf8] shadow-[0_0_8px_rgba(56,189,248,0.8)]"></div>
                               <span className="text-[9px] font-medium text-slate-400 tracking-wide">DL</span>
                           </div>
                           <div className="flex items-center gap-1.5 shrink-0">
                               <div className="w-1.5 h-1.5 rounded-full bg-[#f472b6] shadow-[0_0_8px_rgba(244,114,182,0.8)]"></div>
                               <span className="text-[9px] font-medium text-slate-400 tracking-wide">UL</span>
                           </div>
                           {/* PPPoE & Hotspot Badges inline with legend */}
                           <div className="flex gap-1 ml-auto shrink-0">
                             {rt.pppoe_active > 0 && <span className="px-1.5 py-0.5 rounded bg-[#1e293b]/80 border border-blue-500/20 text-[8px] font-bold tracking-wider text-[#38bdf8]">P:{rt.pppoe_active}</span>}
                             {rt.hotspot_active > 0 && <span className="px-1.5 py-0.5 rounded bg-[#1e293b]/80 border border-amber-500/20 text-[8px] font-bold tracking-wider text-amber-500">H:{rt.hotspot_active}</span>}
                           </div>
                        </div>

                        {/* Chart Area */}
                        <div className="flex-1 -mx-1 opacity-90 group-hover:opacity-100 transition-opacity">
                           <ResponsiveContainer width="100%" height="100%">
                             <AreaChart data={sparkData} margin={{ top: 4, right: 3, left: 0, bottom: 0 }}>
                                <defs>
                                  <linearGradient id={`dl_${rt.id}`} x1="0" y1="0" x2="0" y2="1">
                                    <stop offset="5%" stopColor="#38bdf8" stopOpacity={0.35}/>
                                    <stop offset="95%" stopColor="#38bdf8" stopOpacity={0}/>
                                  </linearGradient>
                                  <linearGradient id={`ul_${rt.id}`} x1="0" y1="0" x2="0" y2="1">
                                    <stop offset="5%" stopColor="#f472b6" stopOpacity={0.5}/>
                                    <stop offset="95%" stopColor="#f472b6" stopOpacity={0}/>
                                  </linearGradient>
                                </defs>
                                <RechartsTooltip
                                   content={({ active, payload }) => {
                                     if (!active || !payload?.length) return null;
                                     const dl = payload.find(p => p.dataKey === 'dl')?.value ?? 0;
                                     const ul = payload.find(p => p.dataKey === 'ul')?.value ?? 0;
                                     return (
                                       <div className="bg-[#1e293b]/95 backdrop-blur border border-slate-600 px-3 py-2 rounded-lg shadow-xl flex flex-col gap-1">
                                         <div className="flex items-center gap-2">
                                            <div className="w-2 h-2 rounded-full bg-[#38bdf8]" />
                                            <span className="text-[10px] font-bold text-slate-200">DL: {dl.toFixed(2)} M</span>
                                         </div>
                                         <div className="flex items-center gap-2">
                                            <div className="w-2 h-2 rounded-full bg-[#f472b6]" />
                                            <span className="text-[10px] font-bold text-slate-200">UL: {ul.toFixed(2)} M</span>
                                         </div>
                                       </div>
                                     );
                                   }}
                                   isAnimationActive={false}
                                   cursor={{stroke: 'rgba(148,163,184,0.15)', strokeWidth: 1}}
                                />
                                <Area type="monotone" dataKey="dl" stroke="#38bdf8" strokeWidth={1.5} fillOpacity={1} fill={`url(#dl_${rt.id})`} isAnimationActive={false} dot={false} />
                                <Area type="monotone" dataKey="ul" stroke="#f472b6" strokeWidth={2} fillOpacity={1} fill={`url(#ul_${rt.id})`} isAnimationActive={false} dot={false} />
                             </AreaChart>
                           </ResponsiveContainer>
                        </div>
                        
                        {/* Bottom Info Row */}
                        <div className="flex justify-between items-center px-1 mt-1 shrink-0">
                           <div className="text-[8px] font-mono text-slate-600 truncate mr-2">
                             {sparkData.length > 0 ? `${sparkData[0]?.name || ''} – ${sparkData[sparkData.length-1]?.name || ''}` : 'Menunggu data…'}
                           </div>
                           {(rt.ros_version || rt.version) && <div className="text-[8px] font-mono text-slate-500 shrink-0">v{rt.ros_version || rt.version}</div>}
                        </div>
                    </div>

                  </div>
                )
              })}
            </div>
          )}
        </div>

        {/* RIGHT SIDEBAR: ACTIVE ALERTS — hidden on mobile, shown on lg+ */}
        <div className="hidden lg:flex w-full lg:w-[290px] xl:w-[330px] flex-none flex-col bg-[#0f172a] border border-[#334155]/60 rounded-[20px] overflow-hidden shadow-2xl">
           <div className="px-5 py-4 border-b border-white/[0.04] bg-[#1e293b]/40 flex items-center justify-between">
             <div className="text-[11px] font-bold tracking-widest text-amber-500 uppercase flex items-center gap-2">
               <ShieldAlert className="w-4 h-4" strokeWidth={2} /> ACTIVE ALERTS
             </div>
             {warningCount > 0 && (
               <span className="px-2 py-0.5 rounded-full bg-amber-500/20 text-amber-500 text-[10px] font-bold border border-amber-500/30">
                 {warningCount}
               </span>
             )}
           </div>
           
           <div className="flex-1 overflow-y-auto p-4 space-y-3 custom-scrollbar">
             {warningCount === 0 ? (
                <div className="h-full flex flex-col items-center justify-center text-slate-500 opacity-60">
                   <ShieldAlert className="w-14 h-14 mb-4 opacity-50 text-slate-400" strokeWidth={1} />
                   <div className="text-sm font-bold tracking-widest uppercase mb-1">System Secure</div>
                   <div className="text-[11px] text-center max-w-[80%]">Semua metrik CPU, RAM, dan koneksi stabil. Tidak ada anomali terdeteksi.</div>
                </div>
             ) : (
                data.security_alerts.map((al, idx) => {
                  const isCrit = al.type === 'CRITICAL' || al.type === 'error';
                  return (
                    <div key={idx} className={`p-4 rounded-[14px] border border-l-4 ${isCrit ? 'bg-red-950/20 border-r-white/5 border-t-white/5 border-b-white/5 border-l-red-500' : 'bg-[#1e293b]/30 border-r-white/5 border-t-white/5 border-b-white/5 border-l-amber-500'}`}>
                       <div className="flex items-start gap-3">
                          <div className={`mt-0.5 p-1.5 rounded-lg flex-none ${isCrit ? 'bg-red-500/10 text-red-500' : 'bg-amber-500/10 text-amber-500'}`}>
                            {isCrit ? <WifiOff className="w-4 h-4" /> : <ShieldAlert className="w-4 h-4" />}
                          </div>
                          <div className="min-w-0 pr-1">
                             <h4 className={`text-[11px] font-bold uppercase tracking-widest truncate mb-1.5 drop-shadow-sm ${isCrit ? 'text-red-400' : 'text-amber-400'}`}>{al.title || 'WARNING'}</h4>
                             <p className="text-[12px] text-slate-300 leading-relaxed font-normal">{al.message}</p>
                             <div className="text-[10px] font-mono text-slate-500 mt-2">{al.time}</div>
                          </div>
                       </div>
                    </div>
                  );
                })
             )}
           </div>
        </div>

      </div>

      {/* ── DEVICE ACTION MODAL ── */}
      {selectedRouter && (
        <div
          className="fixed inset-0 z-50 bg-[#0f172a]/90 flex items-end sm:items-center justify-center"
          style={{ backdropFilter: 'blur(10px)' }}
          onClick={(e) => { if (e.target === e.currentTarget) { setSelectedRouter(null); setWinboxInfo(null); setTelemetryResult(null); setSnmpResult(null); } }}
        >
          {/* Sheet on mobile (slides from bottom), centered dialog on sm+ */}
          <div className="relative bg-[#1e293b] border border-[#334155] w-full sm:max-w-[420px] rounded-t-3xl sm:rounded-3xl overflow-hidden shadow-2xl flex flex-col max-h-[92dvh] sm:max-h-[90vh]">
            
            {/* Modal Header */}
            <div className="flex items-center justify-between px-6 pt-5 pb-4 border-b border-white/[0.04] flex-none">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-2xl bg-[#0f172a] shadow-inner shadow-black/40 border border-white/5 flex items-center justify-center flex-none">
                   <Server className="w-5 h-5 text-blue-400 drop-shadow-[0_0_8px_rgba(96,165,250,0.5)]" strokeWidth={1.5} />
                </div>
                <div>
                  <h3 className="text-base font-bold text-slate-100 tracking-wide leading-tight">{selectedRouter.name}</h3>
                  <p className="text-[10px] font-mono text-[#38bdf8] mt-0.5">{selectedRouter.ip}</p>
                </div>
              </div>
              <button onClick={() => { setSelectedRouter(null); setWinboxInfo(null); setTelemetryResult(null); setSnmpResult(null); }} className="w-8 h-8 flex items-center justify-center rounded-full hover:bg-slate-700/50 text-slate-500 hover:text-white transition-colors flex-none ml-2">
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Modal Scrollable Body */}
            <div className="overflow-y-auto overscroll-contain p-4 sm:p-5 space-y-2.5">

              {/* Winbox Button */}
              <button onClick={() => handleWinbox('desktop')} disabled={acting} className="w-full flex items-center gap-3.5 p-4 bg-[#0f172a]/80 hover:bg-blue-500/10 border border-white/5 hover:border-blue-500/30 rounded-xl transition-all disabled:opacity-50 text-left group shadow-inner active:scale-[0.98]">
                <div className="w-10 h-10 rounded-xl bg-[#1e293b] flex items-center justify-center text-slate-400 group-hover:text-blue-400 border border-white/5 shadow-inner shadow-black/40 flex-none">
                  <MonitorPlay className="w-5 h-5" />
                </div>
                <div>
                  <div className="text-[13px] font-bold text-slate-200 group-hover:text-blue-300 tracking-wide">WinBox Application</div>
                  <div className="text-[10px] text-slate-500 tracking-wide">Buka Winbox Desktop otomatis</div>
                </div>
              </button>

              {winboxInfo && (
                <div className="p-4 bg-black/40 border border-white/[0.02] shadow-inner rounded-xl">
                  <div className="flex items-center gap-2 mb-3 text-slate-400">
                     <Terminal className="w-4 h-4 text-[#38bdf8] flex-none" />
                     <div className="text-[10px] font-bold tracking-widest uppercase">Manual Remote URL</div>
                  </div>
                  <div className="flex items-center gap-2 bg-[#1e293b]/60 border border-white/5 rounded-lg p-2 pl-3">
                    <code className="flex-1 text-[11px] font-mono text-slate-300 truncate select-all">{winboxInfo.activeType === 'mobile' ? winboxInfo.mobile_url : winboxInfo.url}</code>
                    <button onClick={() => { navigator.clipboard.writeText(winboxInfo.activeType === 'mobile' ? winboxInfo.mobile_url : winboxInfo.url); alert("Disalin"); }} className="px-3 py-1.5 bg-[#38bdf8]/10 hover:bg-[#38bdf8]/20 text-[#38bdf8] text-[9px] font-bold tracking-widest uppercase rounded cursor-pointer transition-colors flex-none">Copy</button>
                  </div>
                </div>
              )}

              <div className="w-full h-px bg-white/5"></div>

              {/* Setup SNMP Telemetry Button */}
              <button
                onClick={handleSetupTelemetry}
                disabled={telemetryLoading}
                className="w-full flex items-center gap-3.5 p-4 bg-[#0f172a]/80 hover:bg-violet-500/10 border border-white/5 hover:border-violet-500/30 rounded-xl transition-all disabled:opacity-50 text-left group shadow-inner active:scale-[0.98]"
              >
                <div className="w-10 h-10 rounded-xl bg-[#1e293b] flex items-center justify-center text-slate-400 group-hover:text-violet-400 border border-white/5 shadow-inner shadow-black/40 flex-none">
                  {telemetryLoading
                    ? <div className="w-5 h-5 border-2 border-violet-500 border-t-transparent rounded-full animate-spin" />
                    : <Zap className="w-5 h-5" />}
                </div>
                <div>
                  <div className="text-[13px] font-bold text-slate-200 group-hover:text-violet-300 tracking-wide">
                    {(selectedRouter.snmp_active || selectedRouter.netflow_active) ? '🟢 Ulangi Setup SNMP' : 'Aktifkan SNMP Telemetry'}
                  </div>
                  <div className="text-[10px] text-slate-500 tracking-wide">Polling 5s aman & tanpa membebani router</div>
                </div>
              </button>

              {/* Telemetry Result Panel */}
              {telemetryResult && (
                <div className="p-4 bg-black/40 border border-white/[0.02] shadow-inner rounded-xl">
                  <div className={`text-[11px] font-bold mb-3 ${telemetryResult.fail_count === 0 ? 'text-emerald-400' : 'text-amber-400'}`}>
                    {telemetryResult.message}
                  </div>
                  {telemetryResult.noc_ip && (
                    <div className="text-[10px] text-slate-500 mb-2 font-mono">NOC IP: {telemetryResult.noc_ip}</div>
                  )}
                  <div className="space-y-1">
                    {(telemetryResult.results || []).map((r, i) => (
                      <div key={i} className="flex items-start gap-2">
                        {r.ok
                          ? <CheckCircle className="w-3 h-3 text-emerald-400 mt-0.5 flex-none" />
                          : <AlertTriangle className="w-3 h-3 text-red-400 mt-0.5 flex-none" />}
                        <div>
                          <div className={`text-[10px] font-semibold ${r.ok ? 'text-slate-300' : 'text-red-300'}`}>{r.step}</div>
                          {!r.ok && <div className="text-[9px] text-slate-500 leading-relaxed">{r.detail}</div>}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              <div className="w-full h-px bg-white/5"></div>

              {/* Test SNMP Button */}
              <button
                onClick={handleTestSnmp}
                disabled={snmpLoading}
                className="w-full flex items-center gap-3.5 p-4 bg-[#0f172a]/80 hover:bg-teal-500/10 border border-white/5 hover:border-teal-500/30 rounded-xl transition-all disabled:opacity-50 text-left group shadow-inner active:scale-[0.98]"
              >
                <div className="w-10 h-10 rounded-xl bg-[#1e293b] flex items-center justify-center text-slate-400 group-hover:text-teal-400 border border-white/5 shadow-inner shadow-black/40 flex-none">
                  {snmpLoading
                    ? <div className="w-5 h-5 border-2 border-teal-500 border-t-transparent rounded-full animate-spin" />
                    : <Activity className="w-5 h-5" />}
                </div>
                <div>
                  <div className="text-[13px] font-bold text-slate-200 group-hover:text-teal-300 tracking-wide">Test Koneksi SNMP</div>
                  <div className="text-[10px] text-slate-500 tracking-wide">Verifikasi SNMP aktif & community string</div>
                </div>
              </button>

              {/* SNMP Test Result Panel */}
              {snmpResult && (
                <div className={`p-4 rounded-xl border shadow-inner ${
                  snmpResult.success
                    ? 'bg-teal-950/20 border-teal-500/20'
                    : 'bg-red-950/20 border-red-500/20'
                }`}>
                  {snmpResult.success ? (
                    <>
                      <div className="flex items-center gap-2 mb-3">
                        <div className="w-2 h-2 rounded-full bg-teal-400 shadow-[0_0_8px_rgba(45,212,191,0.8)] animate-pulse flex-none" />
                        <span className="text-[11px] font-bold text-teal-300 tracking-wide">SNMP TERHUBUNG</span>
                      </div>
                      <div className="space-y-1.5">
                        <div className="flex gap-2 text-[10px]">
                          <span className="text-slate-500 w-20 flex-none">Host</span>
                          <span className="font-mono text-slate-300">{snmpResult.host}</span>
                        </div>
                        <div className="flex gap-2 text-[10px]">
                          <span className="text-slate-500 w-20 flex-none">Community</span>
                          <span className="font-mono text-teal-300 font-bold">{snmpResult.community}</span>
                        </div>
                        {snmpResult.sys_name && (
                          <div className="flex gap-2 text-[10px]">
                            <span className="text-slate-500 w-20 flex-none">Sys Name</span>
                            <span className="font-mono text-slate-300">{snmpResult.sys_name}</span>
                          </div>
                        )}
                        {snmpResult.ros_version && (
                          <div className="flex gap-2 text-[10px]">
                            <span className="text-slate-500 w-20 flex-none">RouterOS</span>
                            <span className="font-mono text-slate-200 font-bold">v{snmpResult.ros_version}</span>
                          </div>
                        )}
                        {snmpResult.sys_uptime && (
                          <div className="flex gap-2 text-[10px]">
                            <span className="text-slate-500 w-20 flex-none">Uptime</span>
                            <span className="font-mono text-slate-300">{snmpResult.sys_uptime}</span>
                          </div>
                        )}
                        {snmpResult.iface_count > 0 && (
                          <div className="flex gap-2 text-[10px]">
                            <span className="text-slate-500 w-20 flex-none">Interfaces</span>
                            <span className="font-mono text-slate-300">{snmpResult.iface_count} port terdeteksi</span>
                          </div>
                        )}
                      </div>
                    </>
                  ) : (
                    <>
                      <div className="flex items-center gap-2 mb-2">
                        <div className="w-2 h-2 rounded-full bg-red-500 flex-none" />
                        <span className="text-[11px] font-bold text-red-400 tracking-wide">SNMP TIDAK TERHUBUNG</span>
                      </div>
                      <p className="text-[10px] text-slate-400 leading-relaxed">{snmpResult.error}</p>
                      <div className="mt-2 pt-2 border-t border-white/5 text-[9px] text-slate-500 space-y-0.5">
                        <div>• Pastikan SNMP aktif di IP Services MikroTik</div>
                        <div>• Cek community string: <span className="font-mono text-amber-400">noc-sentinel</span></div>
                        <div>• Pastikan port 161/UDP tidak diblokir firewall</div>
                      </div>
                    </>
                  )}
                </div>
              )}

              {/* Reboot */}
              <div className="w-full pt-1 pb-2">
                <button onClick={handleReboot} disabled={acting} className="w-full flex items-center justify-center gap-2 p-3.5 bg-red-950/20 hover:bg-red-950/40 border border-red-500/20 rounded-xl transition-all disabled:opacity-50 text-red-400 hover:text-red-300 group active:scale-[0.98]">
                  <RotateCcw className={`w-4 h-4 flex-none ${acting ? 'animate-spin' : ''}`} />
                  <span className="text-[13px] font-bold tracking-wide">Restart Router (Reboot)</span>
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

    </div>
  );
}
