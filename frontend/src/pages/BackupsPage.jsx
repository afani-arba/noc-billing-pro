import { useState, useEffect } from "react";
import api from "@/lib/api";
import { HardDrive, Download, Trash2, RefreshCw, Server, Play, FileText, Clock, Database } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { toast } from "sonner";

function formatSize(bytes) {
  if (!bytes) return "0 B";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

function formatDate(iso) {
  if (!iso) return "-";
  try {
    const d = new Date(iso);
    return d.toLocaleString("id-ID", { dateStyle: "short", timeStyle: "short" });
  } catch { return iso; }
}

export default function BackupsPage() {
  const [backups, setBackups] = useState([]);
  const [devices, setDevices] = useState([]);
  const [selectedDevice, setSelectedDevice] = useState("");
  const [loading, setLoading] = useState(true);
  const [triggering, setTriggering] = useState("");

  const fetchBackups = async () => {
    setLoading(true);
    try {
      const r = await api.get("/backups");
      setBackups(r.data);
    } catch (e) {
      toast.error("Gagal memuat daftar backup");
    }
    setLoading(false);
  };

  useEffect(() => {
    fetchBackups();
    api.get("/devices").then(r => setDevices(r.data)).catch(() => {});
  }, []);

  const handleTrigger = async () => {
    if (!selectedDevice) { toast.error("Pilih device terlebih dahulu"); return; }
    setTriggering(selectedDevice);
    try {
      const r = await api.post(`/backups/trigger/${selectedDevice}`);
      toast.success(`Backup berhasil: ${r.data.filename}`);
      fetchBackups();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Backup gagal");
    }
    setTriggering("");
  };

  const handleDelete = async (filename) => {
    if (!window.confirm(`Hapus backup "${filename}"?`)) return;
    try {
      await api.delete(`/backups/${filename}`);
      toast.success("Backup dihapus");
      fetchBackups();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Gagal menghapus");
    }
  };

  const handleDownload = (filename) => {
    const token = localStorage.getItem("noc_token");
    const baseUrl = process.env.REACT_APP_BACKEND_URL;
    const url = `${baseUrl}/api/backups/download/${filename}`;
    const a = document.createElement("a");
    a.href = url;
    a.setAttribute("download", filename);
    // Add auth header via fetch + blob for security
    fetch(url, { headers: { Authorization: `Bearer ${token}` } })
      .then(r => r.blob())
      .then(blob => {
        const bUrl = URL.createObjectURL(blob);
        a.href = bUrl;
        a.download = filename;
        a.click();
        URL.revokeObjectURL(bUrl);
      })
      .catch(() => toast.error("Download gagal"));
  };

  return (
    <div className="space-y-5 pb-16" data-testid="backups-page">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <h1 className="text-xl sm:text-2xl md:text-3xl font-bold tracking-tight">Backup Konfigurasi</h1>
          <p className="text-xs sm:text-sm text-muted-foreground">Backup otomatis konfigurasi MikroTik</p>
        </div>
        <Button variant="outline" onClick={fetchBackups} size="sm" className="rounded-sm gap-2 w-full sm:w-auto">
          <RefreshCw className="w-4 h-4" /> Refresh
        </Button>
      </div>

      {/* Trigger Manual Backup */}
      <div className="bg-card border border-border rounded-sm p-4 space-y-3">
        <h2 className="text-base font-semibold flex items-center gap-2">
          <Play className="w-4 h-4 text-green-500" /> Backup Manual
        </h2>
        <div className="flex flex-col sm:flex-row gap-2">
          <Select value={selectedDevice} onValueChange={setSelectedDevice}>
            <SelectTrigger className="rounded-sm bg-background text-xs h-9 flex-1 sm:max-w-xs">
              <SelectValue placeholder="Pilih device..." />
            </SelectTrigger>
            <SelectContent>
              {devices.map(d => (
                <SelectItem key={d.id} value={d.id}>
                  <span className="flex items-center gap-2">
                    <div className={`w-1.5 h-1.5 rounded-full ${d.status === "online" ? "bg-green-500" : "bg-red-500"}`} />
                    {d.name}
                  </span>
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Button
            onClick={handleTrigger}
            disabled={!!triggering || !selectedDevice}
            size="sm"
            className="rounded-sm gap-2"
          >
            <HardDrive className="w-4 h-4" />
            {triggering ? "Membackup..." : "Backup Sekarang"}
          </Button>
        </div>
        <p className="text-[10px] text-muted-foreground/70">
          Backup akan mengunduh konfigurasi RSC export dari MikroTik dan menyimpannya di server.
        </p>
      </div>

      {/* Backup List */}
      <div className="bg-card border border-border rounded-sm">
        <div className="p-4 border-b border-border flex items-center justify-between">
          <h2 className="text-base font-semibold flex items-center gap-2">
            <Database className="w-4 h-4 text-primary" /> Daftar Backup
            <Badge variant="outline" className="rounded-sm text-xs ml-1">{backups.length}</Badge>
          </h2>
        </div>

        {loading ? (
          <div className="p-8 text-center text-sm text-muted-foreground">Memuat...</div>
        ) : backups.length === 0 ? (
          <div className="p-12 text-center">
            <FileText className="w-12 h-12 mx-auto mb-3 text-muted-foreground/20" />
            <p className="text-sm text-muted-foreground">Belum ada file backup</p>
            <p className="text-xs text-muted-foreground/60 mt-1">Trigger backup manual di atas atau tunggu backup otomatis</p>
          </div>
        ) : (
          <div className="divide-y divide-border/50">
            {backups.map(b => (
              <div key={b.filename} className="flex items-center gap-3 p-3 hover:bg-secondary/20 transition-colors">
                <div className="w-8 h-8 rounded-sm bg-secondary flex items-center justify-center flex-shrink-0">
                  <FileText className="w-4 h-4 text-muted-foreground" />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-xs font-mono truncate font-medium">{b.filename}</p>
                  <div className="flex items-center gap-2 mt-0.5">
                    <Badge variant="outline" className="rounded-sm text-[10px] px-1.5">
                      {b.type?.toUpperCase()}
                    </Badge>
                    <span className="text-[10px] text-muted-foreground">{formatSize(b.size)}</span>
                    <span className="text-[10px] text-muted-foreground flex items-center gap-1">
                      <Clock className="w-2.5 h-2.5" /> {formatDate(b.created_at)}
                    </span>
                  </div>
                </div>
                <div className="flex items-center gap-1 flex-shrink-0">
                  <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => handleDownload(b.filename)} title="Download">
                    <Download className="w-3.5 h-3.5" />
                  </Button>
                  <Button variant="ghost" size="icon" className="h-7 w-7 text-destructive" onClick={() => handleDelete(b.filename)} title="Hapus">
                    <Trash2 className="w-3.5 h-3.5" />
                  </Button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

