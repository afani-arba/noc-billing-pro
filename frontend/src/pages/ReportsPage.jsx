import { useState, useEffect } from "react";
import api from "@/lib/api";
import { BarChart3, Download, RefreshCw, Building2, User, Calendar, Shield, Printer, Server } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { toast } from "sonner";

// ─── Helpers ───────────────────────────────────────────────────────────────────
function tgl(iso) {
  try {
    return new Date(iso).toLocaleDateString("id-ID", { day: "2-digit", month: "long", year: "numeric" });
  } catch { return iso; }
}

function getInitials(name = "") {
  return name.split(" ").map(w => w[0]).filter(Boolean).slice(0, 2).join("").toUpperCase() || "A";
}

// ─── Print (export PDF via browser) ───────────────────────────────────────────
function printReport(report, companyName, clientName, engineerName) {
  if (!report) return;
  const win = window.open("", "_blank");
  if (!win) { toast.error("Popup diblokir browser. Izinkan popup lalu coba lagi."); return; }

  const s = report.summary;
  const av = report.availability || {};
  const devices = report.device_summary || [];
  const incidents = report.incidents || [];
  const pppoe = report.pppoe_stats || { active: 0, total: 0 };
  const hotspot = report.hotspot_stats || { active: 0, total: 0 };
  const health = s.devices.online / s.devices.total >= 0.9 ? "STABLE"
    : s.devices.online / s.devices.total >= 0.7 ? "WARNING" : "CRITICAL";
  const healthy = health === "STABLE";
  const initials = getInitials(companyName);
  // Use form state values directly (do NOT rely on report.client_name from API)
  const displayClient = clientName || report.client_name || "—";
  const displayEngineer = engineerName || report.engineer_name || "—";
  const displayDate = tgl(new Date().toISOString()); // always use current local date

  const statusStyle = (status) => {
    if (status === "online") return "background:#dcfce7;color:#15803d;border:1px solid #86efac;";
    if (status === "offline") return "background:#fee2e2;color:#dc2626;border:1px solid #fca5a5;";
    if (status === "warning") return "background:#fef9c3;color:#854d0e;border:1px solid #fde047;";
    return "background:#f4f4f5;color:#71717a;border:1px solid #d4d4d8;";
  };
  const statusLabel = (s) => ({ online: "ONLINE", offline: "OFFLINE", warning: "WARNING" }[s] || "UNKNOWN");

  const actionStyle = (a) => {
    if (a === "URGENT") return "color:#dc2626;font-weight:bold;";
    if (a === "Investigate") return "color:#ea580c;font-weight:bold;";
    return "color:#15803d;font-weight:bold;";
  };

  const sevStyle = (sev) => {
    if (sev === "CRITICAL") return "background:#fee2e2;color:#dc2626;";
    if (sev === "WARNING") return "background:#fef9c3;color:#854d0e;";
    return "background:#dbeafe;color:#1d4ed8;";
  };

  const incStatus = (st) => st === "OPEN"
    ? "background:#fee2e2;color:#dc2626;font-weight:bold;"
    : "background:#dcfce7;color:#15803d;font-weight:bold;";

  const devRows = devices.map((d, i) => `
    <tr style="background:${i % 2 === 0 ? "#fff" : "#f8fafc"};">
      <td style="text-align:center">${i + 1}</td>
      <td style="color:#1e3a5f;font-weight:600">${d.name}</td>
      <td style="font-family:monospace;font-size:10px">${d.ip_address}</td>
      <td>${d.location || "—"}</td>
      <td><span style="padding:2px 6px;border-radius:3px;font-size:10px;font-weight:700;${statusStyle(d.status)}">${statusLabel(d.status)}</span></td>
      <td style="text-align:center">${d.uptime || "—"}</td>
      <td style="text-align:center;color:${d.cpu > 80 ? "#dc2626" : d.cpu > 60 ? "#d97706" : "#16a34a"};font-weight:600">${d.cpu}%</td>
      <td style="text-align:center;color:${d.memory > 85 ? "#dc2626" : d.memory > 70 ? "#d97706" : "#16a34a"};font-weight:600">${d.memory}%</td>
      <td style="text-align:center;font-family:monospace;font-size:10px">${d.bw_in || 0}M / ${d.bw_out || 0}M</td>
      <td style="${actionStyle(d.action)}">${d.action || "OK"}</td>
    </tr>
  `).join("");

  // SVG Bandwidth Chart
  const buildBwSvgChart = (devices) => {
    if (!devices || devices.length === 0) return "";
    const maxBw = Math.max(...devices.flatMap(d => [d.bw_in || 0, d.bw_out || 0]), 1);
    const rowH = 28;
    const labelW = 120;
    const barMaxW = 300;
    const chartH = devices.length * rowH + 40;
    const rows = devices.map((d, i) => {
      const dlW = Math.round(((d.bw_in || 0) / maxBw) * barMaxW);
      const ulW = Math.round(((d.bw_out || 0) / maxBw) * barMaxW);
      const y = i * rowH + 30;
      return `
        <text x="${labelW - 4}" y="${y + 10}" text-anchor="end" font-size="9" fill="#475569" font-family="'IBM Plex Mono','Courier New',monospace">${d.name.substring(0, 16)}</text>
        <rect x="${labelW}" y="${y}" width="${dlW}" height="10" rx="2" fill="#3b82f6" opacity="0.8"/>
        <text x="${labelW + dlW + 3}" y="${y + 9}" font-size="8" fill="#1d4ed8">${d.bw_in || 0}M</text>
        <rect x="${labelW}" y="${y + 13}" width="${ulW}" height="10" rx="2" fill="#22c55e" opacity="0.8"/>
        <text x="${labelW + ulW + 3}" y="${y + 21}" font-size="8" fill="#15803d">${d.bw_out || 0}M</text>
      `;
    }).join("");
    return `
      <div style="page-break-inside:avoid;margin-top:24px;">
        <h3 style="font-size:12px;font-weight:700;color:#1e3a5f;margin-bottom:8px;">📊 Grafik Bandwidth per Device (Snapshot)</h3>
        <svg width="${labelW + barMaxW + 60}" height="${chartH}" xmlns="http://www.w3.org/2000/svg" style="font-family:'Inter','Segoe UI',sans-serif">
          <text x="${labelW}" y="16" font-size="9" fill="#64748b">* Download (biru)</text>
          <text x="${labelW + 120}" y="16" font-size="9" fill="#64748b">* Upload (hijau)</text>
          ${rows}
        </svg>
      </div>`;
  };
  const bwChart = buildBwSvgChart(devices);

  const incRows = incidents.length === 0
    ? `<tr><td colspan="7" style="text-align:center;color:#6b7280;padding:16px">✅ Tidak ada incident pada periode ini</td></tr>`
    : incidents.map((inc, i) => `
        <tr style="background:${i % 2 === 0 ? "#fff" : "#f8fafc"};">
          <td style="font-family:monospace;white-space:nowrap">${inc.time}</td>
          <td style="font-weight:600">${inc.device}</td>
          <td><span style="padding:2px 6px;border-radius:3px;font-size:10px;font-weight:700;${sevStyle(inc.severity)}">${(inc.severity || "").toUpperCase()}</span></td>
          <td style="max-width:180px;overflow:hidden">${inc.description}</td>
          <td>${inc.action}</td>
          <td><span style="padding:2px 6px;border-radius:3px;font-size:10px;${incStatus(inc.status)}">${inc.status}</span></td>
          <td>${inc.pic}</td>
        </tr>
      `).join("");

  const html = `<!DOCTYPE html>
<html lang="id">
<head>
<meta charset="utf-8">
<title>Laporan Monitoring - ${companyName}</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: 'Inter', 'Segoe UI', system-ui, -apple-system, sans-serif; font-size: 11px; color: #1e293b; background: #fff; }

  /* ── HEADER ── */
  .header { background: #0f172a; color: #fff; padding: 18px 24px 14px; display: flex; align-items: flex-start; justify-content: space-between; }
  .header h1 { font-size: 22px; font-weight: 800; letter-spacing: -0.5px; margin-bottom: 3px; }
  .header .sub1 { font-size: 11px; color: #94a3b8; }
  .header .sub2 { font-size: 10px; color: #64748b; margin-top: 1px; }
  .logo-box { width: 52px; height: 52px; border-radius: 8px; background: #2563eb; display: flex; align-items: center; justify-content: center; font-size: 18px; font-weight: 900; color: #fff; flex-shrink: 0; }

  /* ── META BAR ── */
  .meta-bar { background: #f1f5f9; border-top: 1px solid #e2e8f0; padding: 8px 24px; display: grid; grid-template-columns: 1fr 1fr 1fr 1fr; gap: 6px 16px; }
  .meta-bar .mkey { color: #94a3b8; font-size: 10px; }
  .meta-bar .mval { color: #0f172a; font-weight: 700; font-size: 11px; }

  /* ── SECTION HEADER ── */
  .section-hdr { background: #1e3a8a; color: #fff; padding: 6px 16px; font-size: 11px; font-weight: 700; letter-spacing: 0.5px; text-transform: uppercase; margin-top: 12px; }

  /* ── EXEC SUMMARY ── */
  .exec-title { font-size: 11px; font-weight: 700; color: #1d4ed8; text-transform: uppercase; letter-spacing: 0.5px; padding: 10px 24px 4px; }
  .exec-divider { border: none; border-top: 1.5px solid #dbeafe; margin: 0 24px 8px; }
  .exec-cards { display: grid; grid-template-columns: repeat(6, 1fr); gap: 8px; padding: 0 24px 10px; }
  .exec-card { border: 1px solid #e2e8f0; border-radius: 4px; padding: 10px; background: #f8fafc; border-left: 3px solid; }
  .exec-card .ec-label { font-size: 8px; color: #6b7280; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 4px; }
  .exec-card .ec-value { font-size: 15px; font-weight: 900; line-height: 1; margin-bottom: 3px; }
  .ec-critical { font-size: 12px !important; }
  .exec-card .ec-sub { font-size: 9px; color: #6b7280; }

  /* ── ALERT BADGES (in exec) ── */
  .issue-badge { display: inline-block; padding: 2px 6px; border-radius: 3px; font-size: 10px; font-weight: 700; }
  .ib-red { background:#fee2e2;color:#dc2626;border:1px solid #fca5a5; }
  .ib-yellow { background:#fef9c3;color:#854d0e;border:1px solid #fde047; }

  /* ── TABLES ── */
  .tbl-wrap { padding: 0 24px 4px; overflow: hidden; }
  table { width: 100%; border-collapse: collapse; font-size: 10px; }
  th { background: #1e3a8a; color: #fff; padding: 5px 6px; text-align: left; font-size: 9.5px; font-weight: 700; letter-spacing: 0.3px; white-space: nowrap; }
  td { padding: 4px 6px; border-bottom: 1px solid #f1f5f9; vertical-align: middle; }
  tr:hover td { background: #f0f9ff !important; }

  /* ── PERF SECTION ── */
  .perf-grid { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 12px; padding: 10px 24px; }
  .perf-box { }
  .perf-box h4 { font-size: 10px; font-weight: 700; color: #1d4ed8; margin-bottom: 6px; border-bottom: 1px solid #dbeafe; padding-bottom: 3px; }
  .perf-row { display: flex; justify-content: space-between; padding: 2px 0; font-size: 10px; border-bottom: 1px dotted #f1f5f9; }
  .perf-row .plabel { color: #64748b; }
  .perf-row .pval { font-weight: 700; font-family: 'IBM Plex Mono', 'Courier New', monospace; font-size: 10px; }
  .pval-green { color: #15803d; }
  .pval-yellow { color: #d97706; }
  .pval-red { color: #dc2626; }

  /* ── AVAIL CARDS ── */
  .avail-cards { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; padding: 10px 24px 14px; }
  .avail-card { background: #1d4ed8; color: #fff; border-radius: 4px; padding: 12px 14px; }
  .avail-card .av-label { font-size: 9px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px; color: #bfdbfe; margin-bottom: 4px; }
  .avail-card .av-value { font-size: 26px; font-weight: 900; line-height: 1.1; }
  .avail-card .av-sub { font-size: 9px; color: #93c5fd; margin-top: 2px; }

  /* ── FOOTER ── */
  .footer { text-align: center; padding: 8px 24px; font-size: 9px; color: #94a3b8; border-top: 1px solid #f1f5f9; margin-top: 10px; }

  /* ── PRINT ── */
  @media print {
    body { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
    .no-print { display: none !important; }
    .section-hdr { break-before: auto; }
    .page2 { page-break-before: always; }
    @page { size: A4 landscape; margin: 8mm 10mm; }
  }
</style>
</head>
<body>

<!-- PRINT BUTTON (hidden on print) -->
<div class="no-print" style="background:#1e3a8a;padding:8px 24px;display:flex;align-items:center;justify-content:space-between;">
  <span style="color:#fff;font-size:12px;font-weight:600">Preview Laporan – Siap untuk di-print/save sebagai PDF</span>
  <button onclick="window.print()" style="background:#2563eb;color:#fff;padding:6px 16px;border-radius:4px;border:none;cursor:pointer;font-size:12px;font-weight:700">Print / Save PDF</button>
</div>

<!-- ── HEADER ──────────────────────────────────────────────────────────── -->
<div class="header">
  <div>
    <h1>${companyName}</h1>
    <div class="sub1">Laporan Monitoring Harian – Managed Service Provider</div>
    <div class="sub2">Daily Network Monitoring Report</div>
  </div>
  <div class="logo-box">${initials}</div>
</div>

<!-- ── META ────────────────────────────────────────────────────────────── -->
<div class="meta-bar">
  <div><div class="mkey">Client Name:</div><div class="mval">${displayClient}</div></div>
  <div><div class="mkey">Tanggal Laporan:</div><div class="mval">${displayDate}</div></div>
  <div><div class="mkey">Engineer on Duty:</div><div class="mval">${displayEngineer}</div></div>
  <div><div class="mkey">Periode Monitoring:</div><div class="mval">00:00 – 23:59 WIB</div></div>
</div>

<!-- ── RINGKASAN EKSEKUTIF ────────────────────────────────────────────── -->
<div class="exec-title">Ringkasan Eksekutif</div>
<hr class="exec-divider">
<div class="exec-cards">
  <div class="exec-card" style="border-left-color:${healthy ? "#16a34a" : "#dc2626"}">
    <div class="ec-label">Network Health Status</div>
    <div class="ec-value ec-critical" style="color:${healthy ? "#16a34a" : "#dc2626"}">
      <span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${healthy ? "#16a34a" : "#dc2626"};margin-right:4px;"></span>${health}
    </div>
    <div class="ec-sub">Overall Performance ${healthy ? "Good" : "Check Required"}</div>
  </div>
  <div class="exec-card" style="border-left-color:#2563eb">
    <div class="ec-label">Device Availability</div>
    <div class="ec-value" style="color:#2563eb">${s.devices.online} / ${s.devices.total}</div>
    <div class="ec-sub">Total Online Devices</div>
  </div>
  <div class="exec-card" style="border-left-color:#16a34a">
    <div class="ec-label">Average Bandwidth</div>
    <div class="ec-value" style="color:#16a34a">${s.avg_bandwidth.download} Mbps</div>
    <div class="ec-sub">Upload: ${s.avg_bandwidth.upload} Mbps</div>
  </div>
  <div class="exec-card" style="border-left-color:#9333ea">
    <div class="ec-label">Peak Traffic</div>
    <div class="ec-value" style="color:#9333ea">${s.peak_bandwidth.download} Mbps</div>
    <div class="ec-sub">Upload peak: ${s.peak_bandwidth.upload} Mbps</div>
  </div>
  <div class="exec-card" style="border-left-color:#0891b2">
    <div class="ec-label">Ping / Jitter</div>
    <div class="ec-value" style="color:#0891b2">${s.avg_ping} ms</div>
    <div class="ec-sub">Jitter: ${s.avg_jitter} ms</div>
  </div>
  <div class="exec-card" style="border-left-color:#ea580c">
    <div class="ec-label">SLA Compliance</div>
    <div class="ec-value" style="color:#ea580c">${av.uptime_pct ?? 100}%</div>
    <div class="ec-sub">Target: ${av.sla_target ?? 99.5}%</div>
  </div>
</div>

<!-- ── SECTION 1 ────────────────────────────────────────────────────────── -->
<div class="section-hdr">Section 1: Status Perangkat (MikroTik Devices)</div>
<div class="tbl-wrap" style="padding-top:6px">
  <table>
    <thead>
      <tr>
        <th>No</th><th>Device Name</th><th>IP Address</th><th>Lokasi</th>
        <th>Status</th><th>Uptime</th><th>CPU</th><th>RAM</th>
        <th>Bandwidth (In/Out)</th><th>Action</th>
      </tr>
    </thead>
    <tbody>${devRows || '<tr><td colspan="10" style="text-align:center;color:#6b7280;padding:12px">Tidak ada data perangkat</td></tr>'}</tbody>
  </table>
</div>
<div class="tbl-wrap">${bwChart}</div>

<!-- PAGE 2 -->
<div class="page2">

<!-- ── SECTION 2 ────────────────────────────────────────────────────────── -->
<div class="section-hdr" style="margin-top:0">Section 2: Analisis Performa</div>
<div class="perf-grid" style="grid-template-columns:1fr 1fr 1fr 1fr">
  <div class="perf-box">
    <h4>A. CPU Usage Analysis</h4>
    <div class="perf-row"><span class="plabel">Normal (0-60%)</span><span class="pval pval-green">${s.cpu_categories?.normal ?? 0} Devices</span></div>
    <div class="perf-row"><span class="plabel">Warning (61-80%)</span><span class="pval pval-yellow">${s.cpu_categories?.warning ?? 0} Device</span></div>
    <div class="perf-row"><span class="plabel">Critical (&gt;80%)</span><span class="pval pval-red">${s.cpu_categories?.critical ?? 0} Device</span></div>
  </div>
  <div class="perf-box">
    <h4>B. Memory Usage Analysis</h4>
    <div class="perf-row"><span class="plabel">Normal (0-70%)</span><span class="pval pval-green">${s.mem_categories?.normal ?? 0} Devices</span></div>
    <div class="perf-row"><span class="plabel">Warning (71-85%)</span><span class="pval pval-yellow">${s.mem_categories?.warning ?? 0} Device</span></div>
    <div class="perf-row"><span class="plabel">Critical (&gt;85%)</span><span class="pval pval-red">${s.mem_categories?.critical ?? 0} Device</span></div>
  </div>
  <div class="perf-box">
    <h4>C. Bandwidth Utilization</h4>
    <div class="perf-row"><span class="plabel">Avg Traffic</span><span class="pval">${s.avg_bandwidth.download} Mbps</span></div>
    <div class="perf-row"><span class="plabel">Peak Traffic</span><span class="pval">${s.peak_bandwidth.download} Mbps</span></div>
    <div class="perf-row"><span class="plabel">Ping</span><span class="pval">${s.avg_ping} ms</span></div>
    <div class="perf-row"><span class="plabel">Jitter</span><span class="pval">${s.avg_jitter} ms</span></div>
  </div>
  <div class="perf-box">
    <h4>D. User Active Analysis</h4>
    <div class="perf-row"><span class="plabel">PPPoE Aktif</span><span class="pval pval-green">${pppoe.active} User</span></div>
    <div class="perf-row"><span class="plabel">PPPoE Total</span><span class="pval">${pppoe.total} User</span></div>
    <div class="perf-row"><span class="plabel">Hotspot Aktif</span><span class="pval pval-green">${hotspot.active} User</span></div>
    <div class="perf-row"><span class="plabel">Hotspot Total</span><span class="pval">${hotspot.total} User</span></div>
  </div>
</div>

<!-- ── SECTION 3 ────────────────────────────────────────────────────────── -->
<div class="section-hdr">Section 3: Incident &amp; Issue Log</div>
<div class="tbl-wrap" style="padding-top:6px">
  <table>
    <thead>
      <tr><th>Time</th><th>Device</th><th>Severity</th><th>Issue Description</th><th>Action Taken</th><th>Status</th><th>PIC</th></tr>
    </thead>
    <tbody>${incRows}</tbody>
  </table>
</div>

<!-- ── SECTION 4 ────────────────────────────────────────────────────────── -->
<div class="section-hdr">Section 4: Network Availability Stats</div>
<div class="avail-cards">
  <div class="avail-card">
    <div class="av-label">Total Downtime</div>
    <div class="av-value">${av.total_downtime_mins ?? 0} Mins</div>
    <div class="av-sub">Accumulated today</div>
  </div>
  <div class="avail-card">
    <div class="av-label">SLA Compliance</div>
    <div class="av-value">${av.uptime_pct ?? 100}%</div>
    <div class="av-sub">Target: ${av.sla_target ?? 99.5}%</div>
  </div>
  <div class="avail-card">
    <div class="av-label">100% Uptime</div>
    <div class="av-value">${av.full_uptime_devices ?? 0} / ${s.devices.total}</div>
    <div class="av-sub">Devices with 0 issues</div>
  </div>
</div>

</div><!-- end page2 -->

<div class="footer">
  ${companyName} &nbsp;|&nbsp; Daily Network Monitoring Report &nbsp;|&nbsp; Digenerate: ${new Date().toLocaleString("id-ID")} WIB
</div>

</body>
</html>`;

  win.document.write(html);
  win.document.close();
}

// ─── STATUS BADGE ───────────────────────────────────────────────────────────────
function StatusBadge({ status }) {
  const map = {
    online: "bg-green-100 text-green-700 border-green-300 dark:bg-green-900/30 dark:text-green-400",
    offline: "bg-red-100 text-red-700 border-red-300 dark:bg-red-900/30 dark:text-red-400",
    warning: "bg-yellow-100 text-yellow-700 border-yellow-300 dark:bg-yellow-900/30 dark:text-yellow-500",
  };
  const cls = map[status] || "bg-zinc-100 text-zinc-500 border-zinc-300";
  const lbl = { online: "ONLINE", offline: "OFFLINE", warning: "WARNING" }[status] || "UNKNOWN";
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-[3px] text-[10px] font-bold border ${cls}`}>
      {status === "online" && <span className="w-1.5 h-1.5 rounded-full bg-current animate-pulse" />}
      {lbl}
    </span>
  );
}

// ─── MAIN ───────────────────────────────────────────────────────────────────────
export default function ReportsPage() {
  const [period, setPeriod] = useState("daily");
  const [selectedDevice, setSelectedDevice] = useState("all");
  const [deviceList, setDeviceList] = useState([]);
  const [clientName, setClientName] = useState("");
  const [engineerName, setEngineerName] = useState("");
  const [companyName, setCompanyName] = useState("PT ARSYA BAROKAH ABADI");
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    api.get("/devices").then(r => setDeviceList(r.data || [])).catch(() => {});
  }, []);

  const generate = async () => {
    setLoading(true);
    try {
      const r = await api.post("/reports/generate", {
        period,
        device_id: selectedDevice === "all" ? null : selectedDevice,
        client_name: clientName,
        engineer_name: engineerName,
        company_name: companyName,
      });
      setReport(r.data);
      toast.success("Laporan berhasil dibuat");
    } catch { toast.error("Gagal membuat laporan"); }
    setLoading(false);
  };

  const s = report?.summary;
  const av = report?.availability || {};
  const devices = report?.device_summary || [];
  const incidents = report?.incidents || [];

  return (
    <div className="space-y-4 pb-16" data-testid="reports-page">
      {/* Page header */}
      <div>
        <h1 className="text-xl sm:text-2xl md:text-3xl font-bold tracking-tight">Laporan Monitoring</h1>
        <p className="text-xs sm:text-sm text-muted-foreground">Generate laporan harian dan export sebagai PDF</p>
      </div>

      {/* Config */}
      <div className="bg-card border border-border rounded-sm p-4">
        <h3 className="text-sm font-semibold mb-3 flex items-center gap-2">
          <BarChart3 className="w-4 h-4 text-primary" /> Konfigurasi Laporan
        </h3>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3 mb-3">
          <div className="space-y-1">
            <label className="text-[10px] text-muted-foreground uppercase tracking-wider flex items-center gap-1">
              <Building2 className="w-3 h-3" /> Nama Perusahaan
            </label>
            <Input value={companyName} onChange={e => setCompanyName(e.target.value)}
              placeholder="PT ARSYA BAROKAH ABADI" className="rounded-sm bg-background h-9 text-xs" />
          </div>
          <div className="space-y-1">
            <label className="text-[10px] text-muted-foreground uppercase tracking-wider flex items-center gap-1">
              <User className="w-3 h-3" /> Nama Client
            </label>
            <Input value={clientName} onChange={e => setClientName(e.target.value)}
              placeholder="PT Air Lintas Barokah..." className="rounded-sm bg-background h-9 text-xs" />
          </div>
          <div className="space-y-1">
            <label className="text-[10px] text-muted-foreground uppercase tracking-wider flex items-center gap-1">
              <Shield className="w-3 h-3" /> Engineer on Duty
            </label>
            <Input value={engineerName} onChange={e => setEngineerName(e.target.value)}
              placeholder="Nama engineer..." className="rounded-sm bg-background h-9 text-xs" />
          </div>
          <div className="space-y-1">
            <label className="text-[10px] text-muted-foreground uppercase tracking-wider flex items-center gap-1">
              <Calendar className="w-3 h-3" /> Periode
            </label>
            <Select value={period} onValueChange={setPeriod}>
              <SelectTrigger className="rounded-sm bg-background h-9 text-xs" data-testid="report-period-select">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="daily">Harian (24 Jam)</SelectItem>
                <SelectItem value="weekly">Mingguan (7 Hari)</SelectItem>
                <SelectItem value="monthly">Bulanan (30 Hari)</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1">
            <label className="text-[10px] text-muted-foreground uppercase tracking-wider flex items-center gap-1">
              <Server className="w-3 h-3" /> Device
            </label>
            <Select value={selectedDevice} onValueChange={setSelectedDevice}>
              <SelectTrigger className="rounded-sm bg-background h-9 text-xs" data-testid="report-device-select">
                <SelectValue placeholder="Pilih device..." />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">🌐 Semua Device</SelectItem>
                {deviceList.map(d => (
                  <SelectItem key={d.id} value={d.id}>
                    <span className="flex items-center gap-2">
                      <span className={`inline-block w-1.5 h-1.5 rounded-full ${d.status === "online" ? "bg-green-500" : "bg-red-500"}`} />
                      {d.name}
                    </span>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>
        <div className="flex gap-2">
          <Button onClick={generate} disabled={loading} size="sm" className="rounded-sm gap-2" data-testid="generate-report-btn">
            <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />
            {loading ? "Memproses..." : "Generate Laporan"}
          </Button>
          {report && (
            <Button onClick={() => printReport(report, companyName, clientName, engineerName)} variant="outline" size="sm"
              className="rounded-sm gap-2" data-testid="export-pdf-btn">
              <Printer className="w-4 h-4" /> Export PDF
            </Button>
          )}
        </div>
      </div>

      {/* ── LAPORAN PREVIEW ── */}
      {report && s && (
        <div className="border border-border rounded-sm overflow-hidden shadow-lg">

          {/* HEADER */}
          <div className="bg-[#0f172a] flex items-start justify-between px-6 py-5">
            <div>
              <h2 className="text-[22px] font-black text-white tracking-tight">{report.company_name}</h2>
              <p className="text-[11px] text-slate-400 mt-0.5">Laporan Monitoring Harian – Managed Service Provider</p>
              <p className="text-[10px] text-slate-500 mt-0.5">Daily Network Monitoring Report</p>
            </div>
            <div className="w-14 h-14 rounded-lg bg-blue-600 flex items-center justify-center text-xl font-black text-white flex-shrink-0">
              {getInitials(report.company_name)}
            </div>
          </div>

          {/* META BAR */}
          <div className="bg-slate-100 dark:bg-slate-800/60 border-y border-border grid grid-cols-2 sm:grid-cols-4 px-6 py-2.5 gap-x-8 gap-y-1">
            {[
            ["Client Name:", clientName || report.client_name || "—"],
            ["Tanggal Laporan:", tgl(new Date().toISOString())],
            ["Engineer on Duty:", engineerName || report.engineer_name || "—"],
            ["Periode Monitoring:", "00:00 – 23:59 WIB"],
            ].map(([k, v]) => (
              <div key={k} className="text-xs">
                <span className="text-muted-foreground">{k} </span>
                <span className="font-bold text-foreground">{v}</span>
              </div>
            ))}
          </div>

          {/* RINGKASAN EKSEKUTIF */}
          <div className="px-6 pt-3 pb-1">
            <p className="text-[10px] font-bold text-blue-600 dark:text-blue-400 uppercase tracking-widest mb-1">Ringkasan Eksekutif</p>
            <div className="border-t-2 border-blue-200 dark:border-blue-900 mb-3" />
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2">
              {(() => {
                const health = s.devices.online / s.devices.total >= 0.9 ? "STABLE" : "WARNING";
                const healthy = health === "STABLE";
                return [
                  { label: "Network Health Status", value: health, color: healthy ? "text-green-600" : "text-yellow-600", border: healthy ? "border-l-green-500" : "border-l-yellow-500", dot: true, sub: "Overall Performance" },
                  { label: "Device Availability", value: `${s.devices.online} / ${s.devices.total}`, color: "text-blue-600", border: "border-l-blue-500", sub: "Total Online Devices" },
                  { label: "Average Bandwidth", value: `${s.avg_bandwidth.download} Mbps`, color: "text-green-600", border: "border-l-green-500", sub: `Upload: ${s.avg_bandwidth.upload} Mbps` },
                  { label: "Peak Traffic", value: `${s.peak_bandwidth.download} Mbps`, color: "text-purple-600", border: "border-l-purple-500", sub: "Today peak" },
                  { label: "Ping / Jitter", value: `${s.avg_ping} ms`, color: "text-cyan-600", border: "border-l-cyan-500", sub: `Jitter: ${s.avg_jitter} ms` },
                  { label: "SLA Compliance", value: `${av.uptime_pct ?? 100}%`, color: "text-orange-600", border: "border-l-orange-500", sub: `Target: ${av.sla_target ?? 99.5}%` },
                ];
              })().map(c => (
                <div key={c.label} className={`border border-border rounded-sm p-2.5 bg-background/50 border-l-2 ${c.border}`}>
                  <p className="text-[8px] text-muted-foreground uppercase tracking-wider mb-1">{c.label}</p>
                  <p className={`text-base font-black leading-none mb-1 ${c.color}`}>
                    {c.dot && <span className={`inline-block w-2 h-2 rounded-full ${c.color.replace("text-", "bg-")} mr-1 animate-pulse`} />}
                    {c.value}
                  </p>
                  <p className="text-[9px] text-muted-foreground">{c.sub}</p>
                </div>
              ))}
            </div>
          </div>

          {/* SECTION 1: STATUS PERANGKAT */}
          <div className="mt-3">
            <div className="bg-blue-900 px-6 py-1.5">
              <h3 className="text-white text-[11px] font-bold tracking-widest uppercase">Section 1: Status Perangkat (MikroTik Devices)</h3>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-[11px]">
                <thead>
                  <tr className="bg-blue-950/30 dark:bg-blue-950/60">
                    {["No", "Device Name", "IP Address", "Lokasi", "Status", "Uptime", "CPU", "RAM", "Bandwidth (In/Out)", "Action"].map(h => (
                      <th key={h} className="px-3 py-2 text-left text-[10px] font-bold text-blue-300 uppercase tracking-wide whitespace-nowrap border-b border-blue-900/30">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {devices.length === 0 ? (
                    <tr><td colSpan={10} className="px-3 py-6 text-center text-muted-foreground text-xs">Tidak ada data perangkat</td></tr>
                  ) : devices.map((d, i) => (
                    <tr key={d.name} className={`border-b border-border/40 hover:bg-muted/20 transition-colors ${i % 2 === 0 ? "" : "bg-muted/10"}`}>
                      <td className="px-3 py-2 text-muted-foreground font-mono">{i + 1}</td>
                      <td className="px-3 py-2 font-semibold text-blue-700 dark:text-blue-400 whitespace-nowrap">{d.name}</td>
                      <td className="px-3 py-2 font-mono text-muted-foreground">{d.ip_address}</td>
                      <td className="px-3 py-2 text-muted-foreground whitespace-nowrap">{d.location || "—"}</td>
                      <td className="px-3 py-2"><StatusBadge status={d.status} /></td>
                      <td className="px-3 py-2 font-mono whitespace-nowrap">{d.uptime || "—"}</td>
                      <td className={`px-3 py-2 font-mono font-bold ${d.cpu > 80 ? "text-red-500" : d.cpu > 60 ? "text-yellow-500" : "text-green-600"}`}>{d.cpu}%</td>
                      <td className={`px-3 py-2 font-mono font-bold ${d.memory > 85 ? "text-red-500" : d.memory > 70 ? "text-yellow-500" : "text-foreground"}`}>{d.memory}%</td>
                      <td className="px-3 py-2 font-mono text-muted-foreground whitespace-nowrap">{d.bw_in || 0}M / {d.bw_out || 0}M</td>
                      <td className={`px-3 py-2 font-bold whitespace-nowrap ${d.action === "URGENT" ? "text-red-500" : d.action === "Investigate" ? "text-orange-500" : "text-green-600"}`}>{d.action || "OK"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* SECTION 2: ANALISIS PERFORMA */}
          <div className="mt-3">
            <div className="bg-blue-900 px-6 py-1.5">
              <h3 className="text-white text-[11px] font-bold tracking-widest uppercase">Section 2: Analisis Performa</h3>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 p-4">
              {[
                {
                  title: "A. CPU Usage Analysis",
                  rows: [
                    ["Normal (0-60%)", s.cpu_categories?.normal ?? 0, "text-green-600"],
                    ["Warning (61-80%)", s.cpu_categories?.warning ?? 0, "text-yellow-500"],
                    ["Critical (>80%)", s.cpu_categories?.critical ?? 0, "text-red-500"],
                  ]
                },
                {
                  title: "B. Memory Usage Analysis",
                  rows: [
                    ["Normal (0-70%)", s.mem_categories?.normal ?? 0, "text-green-600"],
                    ["Warning (71-85%)", s.mem_categories?.warning ?? 0, "text-yellow-500"],
                    ["Critical (>85%)", s.mem_categories?.critical ?? 0, "text-red-500"],
                  ]
                },
                {
                  title: "C. Bandwidth Utilization",
                  rows: [
                    ["Avg Traffic", `${s.avg_bandwidth.download} Mbps`, "text-foreground"],
                    ["Peak Traffic", `${s.peak_bandwidth.download} Mbps`, "text-foreground"],
                    ["Ping", `${s.avg_ping} ms`, "text-foreground"],
                  ]
                },
              ].map(sec => (
                <div key={sec.title}>
                  <h4 className="text-[10px] font-bold text-blue-600 dark:text-blue-400 border-b border-blue-200 dark:border-blue-900 pb-1 mb-2">{sec.title}</h4>
                  <div className="space-y-1">
                    {sec.rows.map(([label, val, clr]) => (
                      <div key={label} className="flex justify-between text-[11px] border-b border-dashed border-border/50 pb-0.5">
                        <span className="text-muted-foreground">{label}</span>
                        <span className={`font-bold font-mono ${clr}`}>{typeof val === "number" ? `${val} Device${val !== 1 ? "s" : ""}` : val}</span>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* SECTION 3: INCIDENT LOG */}
          <div className="mt-3">
            <div className="bg-blue-900 px-6 py-1.5">
              <h3 className="text-white text-[11px] font-bold tracking-widest uppercase">Section 3: Incident &amp; Issue Log</h3>
            </div>
            {incidents.length === 0 ? (
              <div className="p-6 text-center">
                <p className="text-sm text-muted-foreground">✅ Tidak ada incident pada periode ini</p>
                <p className="text-xs text-muted-foreground mt-1">Incident berasal dari Syslog messages yang diterima server</p>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-[11px]">
                  <thead>
                    <tr className="bg-blue-950/30 dark:bg-blue-950/60">
                      {["Time", "Device", "Severity", "Issue Description", "Action Taken", "Status", "PIC"].map(h => (
                        <th key={h} className="px-3 py-2 text-left text-[10px] font-bold text-blue-300 uppercase tracking-wide border-b border-blue-900/30">{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {incidents.map((inc, i) => (
                      <tr key={i} className={`border-b border-border/40 hover:bg-muted/20 ${i % 2 === 0 ? "" : "bg-muted/10"}`}>
                        <td className="px-3 py-2 font-mono whitespace-nowrap">{inc.time}</td>
                        <td className="px-3 py-2 font-semibold whitespace-nowrap">{inc.device}</td>
                        <td className="px-3 py-2">
                          <span className={`px-2 py-0.5 rounded-[3px] text-[10px] font-bold ${inc.severity === "CRITICAL" ? "bg-red-100 dark:bg-red-900/30 text-red-600" : inc.severity === "WARNING" ? "bg-yellow-100 dark:bg-yellow-900/30 text-yellow-700" : "bg-blue-100 dark:bg-blue-900/30 text-blue-600"}`}>
                            {(inc.severity || "INFO").toUpperCase()}
                          </span>
                        </td>
                        <td className="px-3 py-2 text-muted-foreground max-w-[200px] truncate">{inc.description}</td>
                        <td className="px-3 py-2 text-muted-foreground">{inc.action}</td>
                        <td className="px-3 py-2">
                          <span className={`px-2 py-0.5 rounded-[3px] text-[10px] font-bold border ${inc.status === "OPEN" ? "bg-red-100/50 text-red-600 border-red-300" : "bg-green-100/50 text-green-600 border-green-300"}`}>
                            {inc.status}
                          </span>
                        </td>
                        <td className="px-3 py-2 text-muted-foreground">{inc.pic}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          {/* SECTION 4: AVAILABILITY */}
          <div className="mt-3">
            <div className="bg-blue-900 px-6 py-1.5">
              <h3 className="text-white text-[11px] font-bold tracking-widest uppercase">Section 4: Network Availability Stats</h3>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 p-4">
              {[
                { label: "Total Downtime", value: `${av.total_downtime_mins ?? 0} Mins`, sub: "Accumulated today" },
                { label: "SLA Compliance", value: `${av.uptime_pct ?? 100}%`, sub: `Target: ${av.sla_target ?? 99.5}%` },
                { label: "100% Uptime", value: `${av.full_uptime_devices ?? 0} / ${s.devices.total}`, sub: "Devices with 0 issues" },
              ].map(c => (
                <div key={c.label} className="bg-blue-600 dark:bg-blue-700 rounded-sm p-4 text-white">
                  <p className="text-[9px] font-bold uppercase tracking-widest text-blue-200 mb-1">{c.label}</p>
                  <p className="text-3xl font-black leading-none ">{c.value}</p>
                  <p className="text-[10px] text-blue-200 mt-1">{c.sub}</p>
                </div>
              ))}
            </div>
          </div>

        </div>
      )}
    </div>
  );
}

