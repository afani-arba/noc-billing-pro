import { useState, useEffect, useRef } from "react";
import api from "@/lib/api";
import { toast } from "sonner";
import {
  RefreshCw, CheckCircle2, AlertTriangle,
  GitBranch, Terminal, Package,
  ArrowUpCircle, Loader2, History, GitCommit, User
} from "lucide-react";
import { useTheme } from "@/context/ThemeContext";

// ── Komponen helper ───────────────────────────────────────────────────────────
function Card({ children, className = "" }) {
  const { theme } = useTheme();
  const isCyber = theme === "cyber";
  return (
    <div className={`rounded-xl p-5 ${ isCyber ? "glass-card border-none" : "border border-white/10 bg-white/[0.03] backdrop-blur" } ${className}`}>
      {children}
    </div>
  );
}

function StatusBadge({ status }) {
  const map = {
    idle:     { cls: "bg-slate-700 text-slate-300",                             label: "Idle" },
    checking: { cls: "bg-blue-500/20 text-blue-300",                            label: "Memeriksa..." },
    running:  { cls: "bg-yellow-500/20 text-yellow-300 animate-pulse",          label: "Updating..." },
    success:  { cls: "bg-green-500/20 text-green-300",                          label: "Berhasil" },
    failed:   { cls: "bg-red-500/20 text-red-300",                              label: "Gagal" },
  };
  const s = map[status] || map.idle;
  return (
    <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold ${s.cls}`}>
      {status === "running" && <Loader2 className="w-3 h-3 animate-spin" />}
      {s.label}
    </span>
  );
}

// ── Halaman utama ─────────────────────────────────────────────────────────────
export default function UpdatePage() {
  const { theme } = useTheme();
  const isCyber = theme === "cyber";
  const [appInfo, setAppInfo]         = useState(null);
  const [updateInfo, setUpdateInfo]   = useState(null);
  const [status, setStatus]           = useState("idle");
  const [log, setLog]                 = useState([]);
  const [elapsed, setElapsed]         = useState(0);
  const [checking, setChecking]       = useState(false);
  const [reloadCountdown, setReloadCountdown] = useState(0);
  const [repoCommits, setRepoCommits] = useState([]);
  const [changelogLoading, setChangelogLoading] = useState(true);
  const [changelogError, setChangelogError] = useState(false);

  const logRef  = useRef(null);
  const pollRef = useRef(null);
  const cdRef   = useRef(null);

  // Mount: ambil info versi + changelog
  useEffect(() => {
    fetchAppInfo();
    fetchChangelog();
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
      if (cdRef.current)   clearInterval(cdRef.current);
    };
  }, []);

  // Auto-scroll log ke bawah
  useEffect(() => {
    if (logRef.current) {
      logRef.current.scrollTop = logRef.current.scrollHeight;
    }
  }, [log]);

  // ── Fetch functions ──────────────────────────────────────────────────────────

  const fetchAppInfo = async () => {
    try {
      const r = await api.get("/system/app-info");
      setAppInfo(r.data);
    } catch (e) {
      console.error("app-info error", e);
    }
  };

  const fetchChangelog = async () => {
    setChangelogLoading(true);
    setChangelogError(false);
    try {
      const r = await fetch(
        "https://api.github.com/repos/afani-arba/noc-sentinel-v3/commits?per_page=8",
        { headers: { "Accept": "application/vnd.github.v3+json" } }
      );
      if (!r.ok) throw new Error(`GitHub API: ${r.status}`);
      const data = await r.json();
      if (Array.isArray(data) && data.length > 0) {
        setRepoCommits(data.filter(c => !(c.commit?.message || "").toLowerCase().includes("(license-server)")));
      } else {
        setChangelogError(true);
      }
    } catch (e) {
      console.error("Changelog fetch failed:", e);
      setChangelogError(true);
    } finally {
      setChangelogLoading(false);
    }
  };

  const checkUpdate = async () => {
    setChecking(true);
    setUpdateInfo(null);
    setStatus("checking");
    try {
      const r = await api.get("/system/check-update");
      setUpdateInfo(r.data);
      setStatus("idle");
    } catch (e) {
      setUpdateInfo({ has_update: false, message: "Gagal mengecek update: " + (e.response?.data?.detail || e.message) });
      setStatus("idle");
    } finally {
      setChecking(false);
    }
  };

  // ── Start Update ─────────────────────────────────────────────────────────────

  const startUpdate = async () => {
    if (status === "running") return;

    setStatus("running");
    setLog(["🚀 Memulai proses update..."]);
    setElapsed(0);

    await new Promise(r => setTimeout(r, 200));

    try {
      await api.post("/system/perform-update");
    } catch (e) {
      setLog(prev => [...prev, "❌ Gagal memulai update: " + (e.response?.data?.detail || e.message)]);
      setStatus("failed");
      return;
    }

    setLog(prev => [...prev, "⏳ Update berjalan di background..."]);

    const localStartTime = Date.now();
    let errCount = 0;
    let restartMsgShown = false;
    const MAX_ERR = 90; // Toleransi 90 * 2 detik = 3 menit (untuk build process)

    const doSuccess = () => {
      clearInterval(pollRef.current);
      setStatus("success");
      toast.success("✅ Update berhasil! Halaman akan di-reload dalam 5 detik.", { duration: 8000 });
      // Refresh semua data setelah berhasil
      setTimeout(fetchAppInfo, 1500);
      setTimeout(fetchChangelog, 2000);
      setTimeout(checkUpdate, 3000); // cek update lagi → akan menampilkan "Sudah versi terbaru"
      let cd = 5;
      setReloadCountdown(cd);
      cdRef.current = setInterval(() => {
        cd -= 1;
        setReloadCountdown(cd);
        if (cd <= 0) { clearInterval(cdRef.current); window.location.reload(); }
      }, 1000);
    };

    const doFailed = (msg = "") => {
      clearInterval(pollRef.current);
      setStatus("failed");
      if (msg) setLog(prev => [...prev, msg]);
      toast.error("❌ Update gagal! Periksa log untuk detail.", { duration: 10000 });
    };

    pollRef.current = setInterval(async () => {
      const localElapsed = Math.round((Date.now() - localStartTime) / 1000);
      setElapsed(localElapsed);

      try {
        const r = await api.get("/system/update-status");
        const d = r.data;
        errCount = 0;

        const serverElapsed = d.elapsed || 0;

        // Skenario 3: server baru restart — elapsed reset tapi sudah jalan lama
        if (
          !d.running && !d.done &&
          serverElapsed < 5 &&
          localElapsed > 45 &&
          d.log?.length === 0
        ) {
          setLog(prev => [...prev, "✅ Server berhasil di-restart! Update selesai."]);
          doSuccess();
          return;
        }

        // Sync log dari server
        if (Array.isArray(d.log) && d.log.length > 0) {
          setLog(d.log);
        }

        // Skenario 1: selesai normal
        if (d.done) {
          if (d.success) {
            setLog(prev => [...prev, "✅ Update selesai!"]);
            doSuccess();
          } else {
            doFailed(`❌ Update gagal: ${d.error || "Lihat log di atas"}`);
          }
          return;
        }

        if (serverElapsed > 0) setElapsed(serverElapsed);

      } catch {
        // Skenario 2: server sedang restart/build (network error)
        errCount += 1;

        if (errCount === 2 && !restartMsgShown) {
          restartMsgShown = true;
          setLog(prev => {
            const last = prev[prev.length - 1] || "";
            if (last.includes("Menunggu")) return prev;
            return [...prev, "⏳ Menunggu server mem-build dan restart... (bisa memakan waktu 1-3 menit)"];
          });
        }

        if (errCount >= MAX_ERR) {
          setLog(prev => [...prev, "✅ Server kemungkinan sudah restart, atau build timeout. Coba refresh."]);
          doSuccess();
        }
      }
    }, 2000);
  };

  // ── Render ────────────────────────────────────────────────────────────────────
  return (
    <div
      className="max-w-4xl mx-auto space-y-6 pb-20"
    >
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-border pb-6">
        <div>
          <h1 className={`text-3xl font-bold tracking-tight flex items-center gap-3 ${ isCyber ? "gradient-text font-mono" : "text-white" }`}>
            <Package className={`w-8 h-8 ${ isCyber ? "" : "text-blue-500" }`} style={isCyber ? { color: "hsl(162,100%,50%)" } : {}} />
            {isCyber ? "> System Updater" : "System Updater"}
          </h1>
          <p className={`mt-2 text-sm ${ isCyber ? "font-mono text-[hsl(185,100%,35%)]" : "text-slate-400" }`}>
            Update core engine NOC Billing Sentinel ke versi terbaru dari GitHub secara otomatis.
          </p>
        </div>
        <StatusBadge status={status} />
      </div>

      {/* Versi Info + Aksi */}
      <Card className={isCyber ? "border-[hsl(162,100%,50%)]/30 bg-black/40" : ""}>
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          {/* Info versi */}
          <div className="space-y-1.5">
            <div className="flex items-center gap-2">
              <GitBranch className="w-4 h-4 text-blue-400" />
              <span className="text-sm font-semibold text-white">Versi Terpasang</span>
            </div>
            {appInfo ? (
              <div className="text-xs text-slate-400 space-y-0.5 pl-6">
                <p>
                  Commit:{" "}
                  <span className="font-mono text-slate-200">
                    {appInfo.commit === "docker" ? "docker" : (appInfo.commit?.slice(0, 7) || "docker")}
                  </span>
                </p>
                <p className="text-slate-500 truncate max-w-xs">
                  {appInfo.message || "Docker Deployment"}
                </p>
              </div>
            ) : (
              <p className="text-xs text-slate-500 pl-6">Memuat info versi...</p>
            )}

            {/* Status update info */}
            {updateInfo && (
              <div className={`mt-2 pl-6 text-xs font-medium flex items-center gap-1.5 ${
                updateInfo.has_update ? "text-amber-400" : "text-green-400"
              }`}>
                {updateInfo.has_update ? (
                  <>
                    <AlertTriangle className="w-3.5 h-3.5 flex-shrink-0" />
                    <span>
                      Update tersedia:{" "}
                      <span className="font-mono">{updateInfo.latest_commit}</span>
                      {updateInfo.latest_message && (
                        <span className="text-slate-400 ml-1">— {updateInfo.latest_message.slice(0, 50)}</span>
                      )}
                    </span>
                  </>
                ) : (
                  <>
                    <CheckCircle2 className="w-3.5 h-3.5 flex-shrink-0" />
                    <span>
                      Aplikasi sudah versi terbaru{" "}
                      {updateInfo.latest_commit && (
                        <span className="font-mono text-green-300">({updateInfo.latest_commit})</span>
                      )}
                    </span>
                  </>
                )}
              </div>
            )}
          </div>

          {/* Tombol Aksi */}
          <div className="flex items-center gap-3 flex-shrink-0">
            <button
              onClick={checkUpdate}
              disabled={checking || status === "running"}
              className="flex items-center gap-2 px-4 py-2 rounded-lg border border-white/15 text-sm text-slate-300 hover:text-white hover:bg-white/5 transition-all disabled:opacity-40"
            >
              {checking
                ? <Loader2 className="w-4 h-4 animate-spin" />
                : <RefreshCw className="w-4 h-4" />}
              Cek Update
            </button>

            {/* Tombol Update: hanya tampil jika ada update atau force */}
            <button
              onClick={startUpdate}
              disabled={status === "running"}
              className={`flex items-center gap-2 px-5 py-2 rounded-lg text-sm font-semibold transition-all ${
                status === "running"
                  ? "bg-yellow-500/20 text-yellow-300 border border-yellow-500/30 cursor-not-allowed"
                  : updateInfo?.has_update
                  ? "bg-gradient-to-r from-blue-600 to-cyan-600 text-white hover:opacity-90 shadow-lg shadow-blue-900/40"
                  : "bg-white/10 text-white border border-white/15 hover:bg-white/15"
              }`}
            >
              {status === "running" ? (
                <><Loader2 className="w-4 h-4 animate-spin" /> Updating...</>
              ) : (
                <><ArrowUpCircle className="w-4 h-4" /> {updateInfo?.has_update ? "Update Sekarang" : "Paksa Update"}</>
              )}
            </button>
          </div>
        </div>
      </Card>

      {/* Log Terminal — hanya muncul saat ada log */}
      {log.length > 0 && (
        <Card>
          <div className="flex items-center gap-2 mb-3">
            <Terminal className="w-4 h-4 text-green-400" />
            <span className="text-sm font-semibold text-white">Log Update</span>
            <span className="text-[10px] text-slate-500 ml-auto">{elapsed}s</span>
          </div>
          <div
            ref={logRef}
            className="bg-black/60 rounded-lg p-3 h-48 overflow-y-auto font-mono text-[11px] space-y-0.5 border border-white/5"
          >
            {log.map((line, i) => (
              <p key={i} className={`leading-relaxed ${
                line.includes("❌") ? "text-red-400"
                : line.includes("✅") || line.includes("🎉") ? "text-green-400"
                : line.includes("⏰") || line.includes("⚠") ? "text-amber-400"
                : "text-slate-300"
              }`}>{line}</p>
            ))}
          </div>
          {reloadCountdown > 0 && (
            <div className="mt-3 flex items-center gap-2 text-sm text-green-400">
              <CheckCircle2 className="w-4 h-4" />
              <span>Reload halaman dalam <strong>{reloadCountdown}</strong> detik...</span>
            </div>
          )}
        </Card>
      )}

      {/* Changelog — dinamis dari GitHub */}
      <Card>
        <div className="flex items-center justify-between gap-2 mb-4">
          <div className="flex items-center gap-2">
            <History className="w-4 h-4 text-purple-400" />
            <h2 className="text-sm font-semibold text-white">Changelog</h2>
            <span className="text-[10px] text-slate-500">Riwayat commit terbaru</span>
          </div>
          <button
            onClick={fetchChangelog}
            disabled={changelogLoading}
            className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg border border-white/10 text-[11px] text-slate-400 hover:text-white hover:bg-white/5 transition-all disabled:opacity-40"
          >
            {changelogLoading
              ? <Loader2 className="w-3 h-3 animate-spin" />
              : <RefreshCw className="w-3 h-3" />}
            Refresh
          </button>
        </div>

        <div className="space-y-3">
          {changelogLoading ? (
            <div className="text-center p-8 flex flex-col items-center gap-2">
              <Loader2 className="w-6 h-6 animate-spin text-purple-400 opacity-60" />
              <p className="text-sm text-slate-500">Mengambil data dari GitHub...</p>
            </div>
          ) : changelogError ? (
            <div className="text-center p-6 flex flex-col items-center gap-3">
              <p className="text-sm text-slate-500">Gagal memuat changelog.</p>
              <button
                onClick={fetchChangelog}
                className="flex items-center gap-2 px-3 py-1.5 rounded-lg border border-white/10 text-xs text-slate-400 hover:text-white hover:bg-white/5 transition-all"
              >
                <RefreshCw className="w-3 h-3" /> Coba Lagi
              </button>
            </div>
          ) : (
            repoCommits.map((c, i) => {
              const isLatest = i === 0;
              const fullMsg  = c.commit?.message || "";
              const title    = fullMsg.split("\n")[0] || "(no message)";
              const body     = fullMsg.split("\n").slice(1).join("\n").trim();
              const dateStr  = c.commit?.author?.date
                ? new Date(c.commit.author.date).toLocaleDateString("id-ID", {
                    day: "2-digit", month: "short", year: "numeric",
                    hour: "2-digit", minute: "2-digit"
                  })
                : "-";

              return (
                <div
                  key={c.sha}
                  className={`rounded-lg border p-4 transition-all ${
                    isLatest
                      ? "border-cyan-500/30 bg-cyan-500/[0.05]"
                      : "border-white/8 bg-white/[0.015]"
                  }`}
                >
                  {/* Header row */}
                  <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-2 mb-2">
                    <div className="flex items-center gap-2 min-w-0">
                      <GitCommit className={`w-3.5 h-3.5 flex-shrink-0 ${isLatest ? "text-cyan-400" : "text-slate-500"}`} />
                      <span className={`font-mono text-xs font-bold px-1.5 py-0.5 rounded ${
                        isLatest ? "text-cyan-300 bg-cyan-500/15" : "text-slate-500 bg-white/5"
                      }`}>
                        {c.sha?.slice(0, 7)}
                      </span>
                      {isLatest && (
                        <span className="text-[9px] font-bold text-cyan-400 bg-cyan-500/20 px-1.5 py-0.5 rounded-full flex-shrink-0">
                          TERBARU
                        </span>
                      )}
                      <span className={`text-[12px] font-semibold truncate ${isLatest ? "text-white" : "text-slate-300"}`}>
                        {title}
                      </span>
                    </div>
                    <span className="text-[10px] text-slate-500 flex-shrink-0 whitespace-nowrap">{dateStr}</span>
                  </div>

                  {/* Body (detail pesan commit) */}
                  {body && (
                    <div className="ml-6 mb-2 text-[11px] text-slate-500 whitespace-pre-wrap border-l-2 border-slate-700/50 pl-2">
                      {body.slice(0, 200)}{body.length > 200 ? "..." : ""}
                    </div>
                  )}

                  {/* Author */}
                  <div className="ml-6 flex items-center gap-1.5 mt-1">
                    {c.author?.avatar_url ? (
                      <img
                        src={c.author.avatar_url}
                        alt={c.commit?.author?.name}
                        className="w-4 h-4 rounded-full opacity-70"
                      />
                    ) : (
                      <User className="w-3.5 h-3.5 text-slate-600" />
                    )}
                    <span className="text-[10px] text-slate-600">{c.commit?.author?.name || "Unknown"}</span>
                  </div>
                </div>
              );
            })
          )}
        </div>
      </Card>
    </div>
  );
}
