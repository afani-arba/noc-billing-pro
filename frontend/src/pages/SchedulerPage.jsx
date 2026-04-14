import { useState, useEffect, useCallback } from "react";
import api from "@/lib/api";
import { Calendar, Clock, Save, Play, RefreshCw, CheckCircle2, XCircle, Activity,
  Wifi, Server, AlertTriangle, GitBranch, Settings2, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { toast } from "sonner";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend
} from "recharts";

const ttStyle = {
  contentStyle: {
    backgroundColor: "#121214", borderColor: "#27272a", borderRadius: "4px",
    color: "#fafafa", fontSize: "12px"
  }
};

// â”€â”€ Tab: Backup Scheduler â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
function BackupTab() {
  const [config, setConfig] = useState({ enabled: true, hour_wib: 2, minute: 0, retention_days: 30 });
  const [status, setStatus] = useState(null);
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [running, setRunning] = useState(false);

  const fetchAll = useCallback(async () => {
    try {
      const [cfg, st, hist] = await Promise.all([
        api.get("/scheduler/config"),
        api.get("/scheduler/backup/status"),
        api.get("/scheduler/backup/history?limit=10"),
      ]);
      setConfig(cfg.data);
      setStatus(st.data);
      setHistory(hist.data);
    } catch (e) { toast.error("Gagal load data scheduler"); }
    setLoading(false);
  }, []);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  const handleSave = async () => {
    setSaving(true);
    try {
      await api.put("/scheduler/config", config);
      toast.success("Konfigurasi backup berhasil disimpan");
    } catch (e) { toast.error(e.response?.data?.detail || "Gagal simpan"); }
    setSaving(false);
  };

  const handleRunNow = async () => {
    setRunning(true);
    try {
      await api.post("/scheduler/backup/run-now");
      toast.success("Backup dimulai! Cek halaman Backups untuk hasilnya.");
      setTimeout(fetchAll, 5000);
    } catch (e) { toast.error("Gagal memulai backup"); }
    setRunning(false);
  };

  if (loading) return <div className="text-sm text-muted-foreground py-8 text-center">Loading...</div>;

  return (
    <div className="space-y-4">
      {/* Config Card */}
      <div className="bg-card border border-border rounded-sm p-4 sm:p-5">
        <div className="flex items-center justify-between mb-4">
          <h3 className="font-semibold text-base flex items-center gap-2">
            <Calendar className="w-4 h-4 text-primary" /> Jadwal Backup Otomatis
          </h3>
          <Badge className={`rounded-sm text-[10px] border ${config.enabled
            ? "bg-green-500/10 text-green-400 border-green-500/20"
            : "bg-secondary/50 text-muted-foreground border-border"
          }`}>
            {config.enabled ? "AKTIF" : "NONAKTIF"}
          </Badge>
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4">
          <div className="space-y-1.5">
            <Label className="text-[10px] text-muted-foreground uppercase tracking-wider">Status</Label>
            <select
              value={config.enabled ? "true" : "false"}
              onChange={e => setConfig({ ...config, enabled: e.target.value === "true" })}
              className="w-full h-9 rounded-sm bg-background border border-border text-sm px-2"
            >
              <option value="true">Aktif</option>
              <option value="false">Nonaktif</option>
            </select>
          </div>
          <div className="space-y-1.5">
            <Label className="text-[10px] text-muted-foreground uppercase tracking-wider">Jam WIB (0-23)</Label>
            <Input
              type="number" min="0" max="23"
              value={config.hour_wib ?? 2}
              onChange={e => setConfig({ ...config, hour_wib: parseInt(e.target.value) })}
              className="rounded-sm bg-background h-9 text-sm"
            />
          </div>
          <div className="space-y-1.5">
            <Label className="text-[10px] text-muted-foreground uppercase tracking-wider">Menit (0-59)</Label>
            <Input
              type="number" min="0" max="59"
              value={config.minute ?? 0}
              onChange={e => setConfig({ ...config, minute: parseInt(e.target.value) })}
              className="rounded-sm bg-background h-9 text-sm"
            />
          </div>
          <div className="space-y-1.5">
            <Label className="text-[10px] text-muted-foreground uppercase tracking-wider">Retensi (hari)</Label>
            <Input
              type="number" min="1" max="365"
              value={config.retention_days ?? 30}
              onChange={e => setConfig({ ...config, retention_days: parseInt(e.target.value) })}
              className="rounded-sm bg-background h-9 text-sm"
            />
          </div>
        </div>
        <p className="text-[10px] text-muted-foreground mb-4">
          Backup akan berjalan setiap hari pukul{" "}
          <span className="font-mono text-foreground">{String(config.hour_wib ?? 2).padStart(2, "0")}:{String(config.minute ?? 0).padStart(2, "0")} WIB</span>{" "}
          ke semua device online. Backup lebih dari{" "}
          <span className="font-mono text-foreground">{config.retention_days ?? 30} hari</span> akan dihapus otomatis.
        </p>
        <div className="flex gap-2">
          <Button size="sm" onClick={handleSave} disabled={saving} className="rounded-sm gap-2">
            <Save className="w-3.5 h-3.5" />{saving ? "Menyimpan..." : "Simpan"}
          </Button>
          <Button size="sm" variant="outline" onClick={handleRunNow} disabled={running} className="rounded-sm gap-2">
            <Play className="w-3.5 h-3.5" />{running ? "Memulai..." : "Jalankan Sekarang"}
          </Button>
        </div>
      </div>

      {/* Status Terakhir */}
      {status && status.timestamp && (
        <div className="bg-card border border-border rounded-sm p-4">
          <h4 className="text-sm font-semibold mb-2 flex items-center gap-2">
            <Clock className="w-3.5 h-3.5 text-muted-foreground" /> Run Terakhir
          </h4>
          <div className="grid grid-cols-3 gap-3 text-xs">
            <div><p className="text-muted-foreground">Waktu</p><p className="font-mono">{new Date(status.timestamp).toLocaleString("id-ID")}</p></div>
            <div>
              <p className="text-muted-foreground">Berhasil</p>
              <p className="font-semibold text-green-400">{status.success}/{status.total}</p>
            </div>
            <div>
              <p className="text-muted-foreground">Gagal</p>
              <p className={`font-semibold ${status.failed > 0 ? "text-red-400" : "text-muted-foreground"}`}>{status.failed}</p>
            </div>
          </div>
          {status.errors?.length > 0 && (
            <div className="mt-2 p-2 bg-red-500/10 border border-red-500/20 rounded-sm">
              <p className="text-[10px] text-red-400 font-semibold mb-1">Error:</p>
              {status.errors.map((e, i) => <p key={i} className="text-[10px] text-red-300 font-mono">{e}</p>)}
            </div>
          )}
        </div>
      )}

      {/* History */}
      {history.length > 0 && (
        <div className="bg-card border border-border rounded-sm p-4">
          <h4 className="text-sm font-semibold mb-3">History Backup Otomatis</h4>
          <div className="space-y-2">
            {history.map((h, i) => (
              <div key={i} className="flex items-center justify-between py-1.5 border-b border-border/30 last:border-0">
                <span className="text-xs text-muted-foreground font-mono">
                  {new Date(h.timestamp).toLocaleString("id-ID")}
                </span>
                <div className="flex items-center gap-3 text-xs">
                  <span className="text-green-400">{h.success} OK</span>
                  {h.failed > 0 && <span className="text-red-400">{h.failed} Gagal</span>}
                  <span className="text-muted-foreground">/{h.total} device</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// â”€â”€ Tab: BGP/OSPF Alert â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
function RoutingAlertTab() {
  const [state, setState] = useState({ bgp: [], ospf: [] });
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetch = async () => {
      try {
        const [st, hist] = await Promise.all([
          api.get("/routing-alerts/state"),
          api.get("/routing-alerts/history?limit=30"),
        ]);
        setState(st.data);
        setHistory(hist.data);
      } catch { toast.error("Gagal load routing alerts"); }
      setLoading(false);
    };
    fetch();
    const iv = setInterval(fetch, 30000);
    return () => clearInterval(iv);
  }, []);

  if (loading) return <div className="text-sm text-muted-foreground py-8 text-center">Loading...</div>;

  return (
    <div className="space-y-4">
      {/* Summary */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {[
          { label: "BGP Peers", value: state.total_bgp_peers, color: "text-blue-400" },
          { label: "BGP Established", value: state.bgp_established, color: "text-green-400" },
          { label: "BGP Down", value: state.bgp_down, color: state.bgp_down > 0 ? "text-red-400" : "text-muted-foreground" },
          { label: "OSPF Full", value: state.ospf_full, color: "text-cyan-400" },
        ].map(c => (
          <div key={c.label} className="bg-card border border-border rounded-sm p-3">
            <p className="text-[10px] text-muted-foreground uppercase tracking-wider">{c.label}</p>
            <p className={`text-2xl font-bold ${c.color}`}>{c.value ?? 0}</p>
          </div>
        ))}
      </div>

      {/* BGP Peer List */}
      <div className="bg-card border border-border rounded-sm p-4">
        <h4 className="text-sm font-semibold mb-3 flex items-center gap-2">
          <GitBranch className="w-3.5 h-3.5 text-blue-400" /> Status BGP Peers
        </h4>
        {state.bgp.length === 0 ? (
          <p className="text-xs text-muted-foreground">Belum ada data BGP peer. Monitor akan mulai setelah device online terdeteksi.</p>
        ) : (
          <div className="space-y-2">
            {state.bgp.map((p, i) => (
              <div key={i} className={`flex items-center justify-between p-2 rounded-sm border text-xs ${p.state === "established"
                ? "bg-green-500/5 border-green-500/20" : "bg-red-500/5 border-red-500/20"
              }`}>
                <div className="flex items-center gap-3">
                  <div className={`w-2 h-2 rounded-full ${p.state === "established" ? "bg-green-500 animate-pulse" : "bg-red-500"}`} />
                  <div>
                    <span className="font-semibold">{p.peer_name || p.remote_address}</span>
                    <span className="text-muted-foreground ml-2">AS{p.remote_as}</span>
                  </div>
                </div>
                <div className="flex items-center gap-3">
                  <span className="text-muted-foreground">{p.device_name}</span>
                  <Badge className={`rounded-sm text-[10px] border ${p.state === "established"
                    ? "bg-green-500/10 text-green-400 border-green-500/20"
                    : "bg-red-500/10 text-red-400 border-red-500/20"
                  }`}>{p.state}</Badge>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Alert History */}
      {history.length > 0 && (
        <div className="bg-card border border-border rounded-sm p-4">
          <h4 className="text-sm font-semibold mb-3">Routing Alert History</h4>
          <div className="space-y-1.5">
            {history.map((h, i) => {
              const isDown = h.type.includes("down");
              return (
                <div key={i} className={`flex items-start gap-3 p-2 rounded-sm text-xs border ${
                  isDown ? "bg-red-500/5 border-red-500/15" : "bg-green-500/5 border-green-500/15"
                }`}>
                  {isDown
                    ? <XCircle className="w-3.5 h-3.5 text-red-400 mt-0.5 flex-shrink-0" />
                    : <CheckCircle2 className="w-3.5 h-3.5 text-green-400 mt-0.5 flex-shrink-0" />}
                  <div className="flex-1 min-w-0">
                    <p><span className="font-semibold">{h.device_name}</span> — {h.peer_name || h.neighbor_address}
                      {h.remote_as && <span className="text-muted-foreground"> (AS{h.remote_as})</span>}
                    </p>
                    <p className="text-muted-foreground">{h.prev_state} → <span className={isDown ? "text-red-400" : "text-green-400"}>{h.current_state}</span></p>
                  </div>
                  <span className="text-muted-foreground font-mono flex-shrink-0">
                    {new Date(h.timestamp).toLocaleString("id-ID", { hour: "2-digit", minute: "2-digit", day: "2-digit", month: "2-digit" })}
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

// â”€â”€ Tab: Speed Test â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
function SpeedTestTab() {
  const [results, setResults] = useState([]);
  const [config, setConfig] = useState({ enabled: true, interval_minutes: 60, ping_count: 5 });
  const [selectedDevice, setSelectedDevice] = useState(null);
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState("");
  const [saving, setSaving] = useState(false);

  const fetchAll = useCallback(async () => {
    try {
      const [res, cfg] = await Promise.all([
        api.get("/speedtest/results"),
        api.get("/speedtest/config"),
      ]);
      setResults(res.data);
      setConfig(cfg.data);
    } catch { toast.error("Gagal load data speed test"); }
    setLoading(false);
  }, []);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  const fetchHistory = async (deviceId) => {
    try {
      const r = await api.get(`/speedtest/history/${deviceId}?limit=24`);
      setHistory(r.data);
    } catch { setHistory([]); }
  };

  const handleRun = async (deviceId) => {
    setRunning(deviceId);
    try {
      await api.post(`/speedtest/run/${deviceId}`);
      toast.success("Speed test selesai!");
      fetchAll();
      if (selectedDevice === deviceId) fetchHistory(deviceId);
    } catch (e) { toast.error("Speed test gagal"); }
    setRunning("");
  };

  const handleRunAll = async () => {
    setRunning("all");
    try {
      await api.post("/speedtest/run-all");
      toast.success("Speed test dimulai untuk semua device!");
      setTimeout(fetchAll, 15000);
    } catch { toast.error("Gagal"); }
    setRunning("");
  };

  const handleSaveConfig = async () => {
    setSaving(true);
    try {
      await api.put("/speedtest/config", config);
      toast.success("Konfigurasi speed test disimpan");
    } catch (e) { toast.error(e.response?.data?.detail || "Gagal"); }
    setSaving(false);
  };

  const handleSelectDevice = (deviceId) => {
    setSelectedDevice(deviceId);
    fetchHistory(deviceId);
  };

  if (loading) return <div className="text-sm text-muted-foreground py-8 text-center">Loading...</div>;

  const pingColor = (ms) => {
    if (ms === null || ms === undefined) return "text-muted-foreground";
    if (ms < 20) return "text-green-400";
    if (ms < 80) return "text-yellow-400";
    return "text-red-400";
  };

  return (
    <div className="space-y-4">
      {/* Config */}
      <div className="bg-card border border-border rounded-sm p-4">
        <h3 className="text-sm font-semibold mb-3 flex items-center gap-2">
          <Settings2 className="w-3.5 h-3.5 text-primary" /> Konfigurasi Speed Test
        </h3>
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 mb-3">
          <div className="space-y-1.5">
            <Label className="text-[10px] text-muted-foreground uppercase tracking-wider">Status</Label>
            <select
              value={config.enabled ? "true" : "false"}
              onChange={e => setConfig({ ...config, enabled: e.target.value === "true" })}
              className="w-full h-9 rounded-sm bg-background border border-border text-sm px-2"
            >
              <option value="true">Aktif</option>
              <option value="false">Nonaktif</option>
            </select>
          </div>
          <div className="space-y-1.5">
            <Label className="text-[10px] text-muted-foreground uppercase tracking-wider">Interval (menit)</Label>
            <Input type="number" min="10" max="1440" value={config.interval_minutes}
              onChange={e => setConfig({ ...config, interval_minutes: parseInt(e.target.value) })}
              className="rounded-sm bg-background h-9 text-sm"
            />
          </div>
          <div className="space-y-1.5">
            <Label className="text-[10px] text-muted-foreground uppercase tracking-wider">Jumlah Ping</Label>
            <Input type="number" min="1" max="20" value={config.ping_count}
              onChange={e => setConfig({ ...config, ping_count: parseInt(e.target.value) })}
              className="rounded-sm bg-background h-9 text-sm"
            />
          </div>
        </div>
        <div className="flex gap-2">
          <Button size="sm" onClick={handleSaveConfig} disabled={saving} className="rounded-sm gap-2">
            <Save className="w-3.5 h-3.5" />{saving ? "Menyimpan..." : "Simpan"}
          </Button>
          <Button size="sm" variant="outline" onClick={handleRunAll} disabled={running === "all"} className="rounded-sm gap-2">
            <Play className="w-3.5 h-3.5" />{running === "all" ? "Memulai..." : "Test Semua Device"}
          </Button>
        </div>
      </div>

      {/* Results Table */}
      <div className="bg-card border border-border rounded-sm p-4">
        <h4 className="text-sm font-semibold mb-3 flex items-center gap-2">
          <Wifi className="w-3.5 h-3.5 text-cyan-400" /> Hasil Terakhir
          {results.length === 0 && (
            <span className="text-xs text-muted-foreground font-normal">
              — Belum ada data. Klik "Test Semua Device" untuk mulai.
            </span>
          )}
        </h4>
        {results.length > 0 && (
          <div className="space-y-2">
            {results.map((r, i) => (
              <div
                key={i}
                onClick={() => handleSelectDevice(r.device_id)}
                className={`flex items-center gap-3 p-2.5 rounded-sm border cursor-pointer transition-colors text-xs ${
                  selectedDevice === r.device_id
                    ? "border-primary/50 bg-primary/5"
                    : "border-border/50 hover:border-border hover:bg-secondary/30"
                }`}
              >
                <div className="flex-1 min-w-0">
                  <p className="font-semibold truncate">{r.device_name}</p>
                  <p className="text-muted-foreground font-mono">{r.ip_address}</p>
                </div>
                <div className="flex items-center gap-4">
                  <div className="text-center">
                    <p className="text-[9px] text-muted-foreground">PING</p>
                    <p className={`font-mono font-semibold ${pingColor(r.ping_ms)}`}>
                      {r.ping_ms != null ? `${r.ping_ms}ms` : "—"}
                    </p>
                  </div>
                  <div className="text-center">
                    <p className="text-[9px] text-muted-foreground">HTTP</p>
                    <p className={`font-mono font-semibold ${pingColor(r.http_ms)}`}>
                      {r.http_ms != null ? `${r.http_ms}ms` : "—"}
                    </p>
                  </div>
                  <div className="text-center">
                    <p className="text-[9px] text-muted-foreground">TCP</p>
                    <p className={`font-mono font-semibold ${pingColor(r.tcp_ms)}`}>
                      {r.tcp_ms != null ? `${r.tcp_ms}ms` : "—"}
                    </p>
                  </div>
                  <Button
                    variant="ghost" size="sm"
                    className="h-7 w-7 p-0 rounded-sm"
                    onClick={e => { e.stopPropagation(); handleRun(r.device_id); }}
                    disabled={running === r.device_id}
                  >
                    <RefreshCw className={`w-3.5 h-3.5 ${running === r.device_id ? "animate-spin" : ""}`} />
                  </Button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* History Chart */}
      {selectedDevice && history.length > 0 && (
        <div className="bg-card border border-border rounded-sm p-4">
          <h4 className="text-sm font-semibold mb-3">
            Tren Latency — {results.find(r => r.device_id === selectedDevice)?.device_name}
          </h4>
          <div className="h-48">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={history}>
                <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
                <XAxis dataKey="timestamp" tick={{ fill: "#a1a1aa", fontSize: 10 }}
                  tickFormatter={v => new Date(v).toLocaleTimeString("id-ID", { hour: "2-digit", minute: "2-digit" })}
                  tickLine={false} axisLine={{ stroke: "#27272a" }}
                />
                <YAxis tick={{ fill: "#a1a1aa", fontSize: 10 }} tickLine={false} axisLine={{ stroke: "#27272a" }} unit="ms" />
                <Tooltip {...ttStyle} labelFormatter={v => new Date(v).toLocaleString("id-ID")} />
                <Legend iconType="line" wrapperStyle={{ fontSize: "11px", color: "#a1a1aa" }} />
                <Line type="monotone" dataKey="ping_ms" stroke="#06b6d4" strokeWidth={2} dot={false} name="Ping (ms)" connectNulls />
                <Line type="monotone" dataKey="http_ms" stroke="#f59e0b" strokeWidth={2} dot={false} name="HTTP (ms)" connectNulls strokeDasharray="5 3" />
                <Line type="monotone" dataKey="tcp_ms" stroke="#8b5cf6" strokeWidth={2} dot={false} name="TCP (ms)" connectNulls strokeDasharray="3 2" />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}
    </div>
  );
}

// â”€â”€ Main Page â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
const TABS = [
  { id: "backup", label: "Auto Backup", icon: Calendar },
  { id: "routing", label: "BGP/OSPF Alert", icon: GitBranch },
  { id: "speedtest", label: "Speed Test", icon: Activity },
];

export default function SchedulerPage() {
  const [activeTab, setActiveTab] = useState("backup");

  return (
    <div className="space-y-4 pb-16">
      <div>
        <h1 className="text-xl sm:text-2xl md:text-3xl font-bold tracking-tight">Scheduler & Monitor</h1>
        <p className="text-xs sm:text-sm text-muted-foreground">Backup otomatis, BGP/OSPF alert, dan speed test terjadwal</p>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 border-b border-border">
        {TABS.map(tab => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`flex items-center gap-2 px-4 py-2.5 text-xs font-medium border-b-2 transition-colors ${
              activeTab === tab.id
                ? "border-primary text-primary"
                : "border-transparent text-muted-foreground hover:text-foreground"
            }`}
          >
            <tab.icon className="w-3.5 h-3.5" />
            {tab.label}
          </button>
        ))}
      </div>

      {activeTab === "backup" && <BackupTab />}
      {activeTab === "routing" && <RoutingAlertTab />}
      {activeTab === "speedtest" && <SpeedTestTab />}
    </div>
  );
}

