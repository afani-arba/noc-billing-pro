import { useState, useEffect, useCallback } from "react";
import api from "@/lib/api";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import {
  PieChart, Pie, Cell, BarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, Legend, ResponsiveContainer,
} from "recharts";
import {
  TrendingUp, AlertTriangle, Percent, RefreshCw,
  FileDown, FileText, Filter, Server, CheckCircle2, Clock,
  BarChart3, PieChart as PieIcon, Phone, Wifi
} from "lucide-react";

const RpIcon = ({ className = "w-5 h-5" }) => (
  <div className={`${className} flex items-center justify-center font-bold text-[9px] border-[1.5px] border-current rounded-[3px] leading-none select-none pt-[1px] px-[0.5px]`} style={{ fontFamily: 'Inter, sans-serif' }}>
    Rp
  </div>
);
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import jsPDF from "jspdf";
import autoTable from "jspdf-autotable";

// ── Utilities ────────────────────────────────────────────────────────────────

const Rp = (n) => `Rp ${(Number(n) || 0).toLocaleString("id-ID")}`;
const fmtRpShort = (val) => {
  if (val >= 1_000_000_000) return `Rp ${(val / 1_000_000_000).toFixed(1)}M`;
  if (val >= 1_000_000) return `Rp ${(val / 1_000_000).toFixed(1)}jt`;
  if (val >= 1_000) return `Rp ${(val / 1_000).toFixed(0)}rb`;
  return Rp(val);
};

function fmtDate(isoStr) {
  if (!isoStr) return "";
  const p = String(isoStr).substring(0, 10).split("-");
  return p.length === 3 ? `${p[2]}/${p[1]}/${p[0]}` : isoStr;
}

const MONTHS = [
  "Januari", "Februari", "Maret", "April", "Mei", "Juni",
  "Juli", "Agustus", "September", "Oktober", "November", "Desember",
];

const METHOD_COLORS = {
  cash: "#22c55e",
  transfer: "#3b82f6",
  qris: "#a855f7",
  other: "#f59e0b",
};

const PIE_PALETTE = ["#22c55e", "#3b82f6", "#a855f7", "#f59e0b", "#ec4899", "#14b8a6"];

const BAR_COLORS = ["#6366f1", "#8b5cf6", "#a78bfa", "#c4b5fd", "#ddd6fe"];

// ── Summary Card ─────────────────────────────────────────────────────────────

function SummaryCard({ icon: Icon, label, value, sub, accent, iconColor }) {
  return (
    <div
      className={`bg-card border border-border rounded-sm p-4 relative overflow-hidden border-l-2 ${accent}`}
    >
      <div className="flex items-start justify-between">
        <div className="flex-1 min-w-0">
          <p className="text-[10px] text-muted-foreground uppercase tracking-widest font-semibold">
            {label}
          </p>
          <p className="text-2xl font-bold font-mono mt-1 truncate">{value}</p>
          {sub && (
            <p className="text-[10px] text-muted-foreground mt-1">{sub}</p>
          )}
        </div>
        <div
          className={`w-9 h-9 rounded-sm flex items-center justify-center flex-shrink-0 ml-3 ${iconColor}`}
        >
          <Icon className="w-4.5 h-4.5" />
        </div>
      </div>
    </div>
  );
}

// ── Custom Tooltip ────────────────────────────────────────────────────────────

function CustomPieTooltip({ active, payload }) {
  if (active && payload && payload.length) {
    const d = payload[0];
    return (
      <div className="bg-card border border-border rounded-sm px-3 py-2 text-xs shadow-xl">
        <p className="capitalize font-semibold text-foreground">{d.name}</p>
        <p className="font-mono text-primary mt-0.5">{Rp(d.value)}</p>
      </div>
    );
  }
  return null;
}

function CustomBarTooltip({ active, payload, label }) {
  if (active && payload && payload.length) {
    return (
      <div className="bg-card border border-border rounded-sm px-3 py-2 text-xs shadow-xl max-w-[200px]">
        <p className="font-semibold text-foreground truncate">{label}</p>
        <p className="font-mono text-primary mt-0.5">{Rp(payload[0]?.value)}</p>
      </div>
    );
  }
  return null;
}

// ── Export Functions ──────────────────────────────────────────────────────────

function exportPDF(report, period, deviceName) {
  const doc = new jsPDF();
  const { summary, method_breakdown, top_packages, overdue_list } = report;

  // Header
  doc.setFontSize(16);
  doc.setFont("helvetica", "bold");
  doc.text("Laporan Keuangan Billing PPPoE", 14, 18);
  doc.setFontSize(10);
  doc.setFont("helvetica", "normal");
  doc.setTextColor(100);
  doc.text(
    `Periode: ${period}${deviceName ? ` | Router: ${deviceName}` : ""}`,
    14,
    26
  );
  doc.text(`Dicetak: ${new Date().toLocaleString("id-ID")}`, 14, 32);

  // Summary
  doc.setFontSize(11);
  doc.setFont("helvetica", "bold");
  doc.setTextColor(0);
  doc.text("Ringkasan Pendapatan", 14, 42);

  autoTable(doc, {
    startY: 46,
    head: [["Keterangan", "Nilai"]],
    body: [
      ["Total Tagihan", Rp(summary.total_billed)],
      ["Total Diterima", Rp(summary.total_collected)],
      ["Saldo Piutang", Rp(summary.total_outstanding)],
      ["Collection Rate", `${summary.collection_rate}%`],
      ["Invoice Lunas", `${summary.paid_count} invoice`],
      ["Invoice Belum Bayar", `${summary.unpaid_count} invoice`],
      ["Invoice Overdue", `${summary.overdue_count} invoice`],
    ],
    styles: { fontSize: 9, cellPadding: 3 },
    headStyles: { fillColor: [37, 56, 120] },
    alternateRowStyles: { fillColor: [245, 247, 255] },
  });

  const y1 = doc.lastAutoTable.finalY + 10;

  // Metode Pembayaran
  doc.setFont("helvetica", "bold");
  doc.text("Metode Pembayaran", 14, y1);
  const methodRows = Object.entries(method_breakdown || {}).map(([m, v]) => [
    m.charAt(0).toUpperCase() + m.slice(1),
    Rp(v),
  ]);
  autoTable(doc, {
    startY: y1 + 4,
    head: [["Metode", "Nominal"]],
    body: methodRows.length ? methodRows : [["—", "—"]],
    styles: { fontSize: 9, cellPadding: 3 },
    headStyles: { fillColor: [37, 56, 120] },
  });

  const y2 = doc.lastAutoTable.finalY + 10;

  // Top Paket
  doc.setFont("helvetica", "bold");
  doc.text("Top Paket (Pendapatan)", 14, y2);
  autoTable(doc, {
    startY: y2 + 4,
    head: [["#", "Nama Paket", "Pendapatan"]],
    body: (top_packages || []).map((p, i) => [i + 1, p.name, Rp(p.revenue)]),
    styles: { fontSize: 9, cellPadding: 3 },
    headStyles: { fillColor: [37, 56, 120] },
  });

  // New page for overdue list if needed
  const y3 = doc.lastAutoTable.finalY + 10;
  if (y3 > 240) doc.addPage();

  const overdueY = y3 > 240 ? 18 : y3;
  doc.setFont("helvetica", "bold");
  doc.text("Daftar Tunggakan Terbesar", 14, overdueY);
  autoTable(doc, {
    startY: overdueY + 4,
    head: [["No. Invoice", "Nama", "Username", "Paket", "Total", "Jatuh Tempo"]],
    body: (overdue_list || []).map((o) => [
      o.invoice_number || "—",
      o.customer_name,
      o.customer_username,
      o.package_name,
      Rp(o.total),
      fmtDate(o.due_date),
    ]),
    styles: { fontSize: 8, cellPadding: 2.5 },
    headStyles: { fillColor: [180, 30, 30] },
    alternateRowStyles: { fillColor: [255, 248, 248] },
  });

  doc.save(`laporan-keuangan-${period.replace(/ /g, "-")}.pdf`);
  toast.success("Laporan PDF berhasil diunduh!");
}

function exportCSV(report, period) {
  const { summary, method_breakdown, top_packages, overdue_list } = report;
  const rows = [];

  rows.push(["LAPORAN KEUANGAN BILLING PPPOE"]);
  rows.push([`Periode: ${period}`]);
  rows.push([`Dicetak: ${new Date().toLocaleString("id-ID")}`]);
  rows.push([]);
  rows.push(["=== RINGKASAN PENDAPATAN ==="]);
  rows.push(["Total Tagihan", summary.total_billed]);
  rows.push(["Total Diterima", summary.total_collected]);
  rows.push(["Saldo Piutang", summary.total_outstanding]);
  rows.push(["Collection Rate (%)", summary.collection_rate]);
  rows.push(["Invoice Lunas", summary.paid_count]);
  rows.push(["Invoice Belum Bayar", summary.unpaid_count]);
  rows.push(["Invoice Overdue", summary.overdue_count]);
  rows.push([]);
  rows.push(["=== METODE PEMBAYARAN ==="]);
  rows.push(["Metode", "Nominal"]);
  for (const [m, v] of Object.entries(method_breakdown || {})) rows.push([m, v]);
  rows.push([]);
  rows.push(["=== TOP PAKET (PENDAPATAN) ==="]);
  rows.push(["#", "Nama Paket", "Pendapatan"]);
  (top_packages || []).forEach((p, i) => rows.push([i + 1, p.name, p.revenue]));
  rows.push([]);
  rows.push(["=== DAFTAR TUNGGAKAN TERBESAR ==="]);
  rows.push(["No. Invoice", "Nama", "Username", "Paket", "Total", "Jatuh Tempo", "Telepon"]);
  (overdue_list || []).forEach((o) =>
    rows.push([
      o.invoice_number,
      o.customer_name,
      o.customer_username,
      o.package_name,
      o.total,
      fmtDate(o.due_date),
      o.customer_phone || "",
    ])
  );

  const csv = rows
    .map((r) => r.map((c) => `"${String(c).replace(/"/g, '""')}"`).join(","))
    .join("\n");
  const blob = new Blob(["\uFEFF" + csv], { type: "text/csv;charset=utf-8;" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `laporan-keuangan-${period.replace(/ /g, "-")}.csv`;
  a.click();
  toast.success("Laporan Excel (CSV) berhasil diunduh!");
}

// ── Main Page ────────────────────────────────────────────────────────────────

export default function FinanceReportPage() {
  const today = new Date();
  const [month, setMonth] = useState(today.getMonth() + 1);
  const [year, setYear] = useState(today.getFullYear());
  const [deviceId, setDeviceId] = useState("");
  const [devices, setDevices] = useState([]);
  const [report, setReport] = useState(null);
  const [hotspotReport, setHotspotReport] = useState(null);
  const [loading, setLoading] = useState(false);

  // Load device list once
  useEffect(() => {
    api
      .get("/devices", { params: { limit: 200 } })
      .then((r) => setDevices(r.data?.data || r.data || []))
      .catch(() => {});
  }, []);

  const loadReport = useCallback(async () => {
    setLoading(true);
    try {
      const [rPppoe, rHotspot] = await Promise.all([
        api.get("/billing/financial-report", { params: { month, year, device_id: deviceId || "" } }),
        api.get("/billing/hotspot-financial-report", { params: { month, year, device_id: deviceId || "" } })
      ]);
      setReport(rPppoe.data);
      setHotspotReport(rHotspot.data);
    } catch (e) {
      toast.error(e.response?.data?.detail || "Gagal memuat laporan");
    }
    setLoading(false);
  }, [month, year, deviceId]);

  useEffect(() => {
    loadReport();
  }, [loadReport]);

  const selectedDevice = devices.find((d) => d.id === deviceId);
  const period = `${MONTHS[month - 1]} ${year}`;

  // Prepare chart data
  const pieData = report
    ? Object.entries(report.method_breakdown || {}).map(([name, value]) => ({
        name: name.charAt(0).toUpperCase() + name.slice(1),
        value,
        originalKey: name,
      }))
    : [];

  const barData = (report?.top_packages || []).map((p) => ({
    name: p.name.length > 18 ? p.name.slice(0, 16) + "…" : p.name,
    fullName: p.name,
    revenue: p.revenue,
  }));

  const yearOptions = [];
  for (let y = today.getFullYear(); y >= 2023; y--) yearOptions.push(y);

  return (
    <div className="space-y-5">
      {/* ── Page Header ── */}
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold tracking-tight flex items-center gap-2">
            <TrendingUp className="w-5 h-5 text-primary" />
            Laporan Keuangan
          </h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            Ringkasan keuangan billing PPPoE — pendapatan, piutang, dan analisis paket
          </p>
        </div>

        {/* Export Buttons */}
        {report && (
          <div className="flex gap-2 flex-wrap">
            <Button
              variant="outline"
              size="sm"
              className="rounded-sm gap-1.5 text-xs h-8 border-blue-500/30 text-blue-400 hover:bg-blue-500/10"
              onClick={() => exportCSV(report, period)}
            >
              <FileDown className="w-3.5 h-3.5" />
              Export Excel
            </Button>
            <Button
              variant="outline"
              size="sm"
              className="rounded-sm gap-1.5 text-xs h-8 border-red-500/30 text-red-400 hover:bg-red-500/10"
              onClick={() =>
                exportPDF(report, period, selectedDevice?.name || "")
              }
            >
              <FileText className="w-3.5 h-3.5" />
              Export PDF
            </Button>
          </div>
        )}
      </div>

      {/* ── Filter Bar ── */}
      <div className="flex flex-wrap gap-3 items-center p-3 bg-card border border-border rounded-sm">
        <Filter className="w-4 h-4 text-muted-foreground flex-shrink-0" />

        {/* Month */}
        <div className="flex items-center gap-2">
          <label className="text-[10px] text-muted-foreground uppercase tracking-wider">
            Bulan
          </label>
          <select
            value={month}
            onChange={(e) => setMonth(Number(e.target.value))}
            className="h-8 text-xs rounded-sm border border-border bg-secondary px-2 text-foreground pr-7"
          >
            {MONTHS.map((m, i) => (
              <option key={i + 1} value={i + 1}>
                {m}
              </option>
            ))}
          </select>
        </div>

        {/* Year */}
        <div className="flex items-center gap-2">
          <label className="text-[10px] text-muted-foreground uppercase tracking-wider">
            Tahun
          </label>
          <select
            value={year}
            onChange={(e) => setYear(Number(e.target.value))}
            className="h-8 text-xs rounded-sm border border-border bg-secondary px-2 text-foreground pr-7"
          >
            {yearOptions.map((y) => (
              <option key={y} value={y}>
                {y}
              </option>
            ))}
          </select>
        </div>

        {/* Router / Device */}
        <div className="flex items-center gap-2">
          <Server className="w-3.5 h-3.5 text-muted-foreground" />
          <label className="text-[10px] text-muted-foreground uppercase tracking-wider">
            Router
          </label>
          <select
            value={deviceId}
            onChange={(e) => setDeviceId(e.target.value)}
            className="h-8 text-xs rounded-sm border border-border bg-secondary px-2 text-foreground pr-7 max-w-[200px]"
          >
            <option value="">Semua Router</option>
            {devices.map((d) => (
              <option key={d.id} value={d.id}>
                {d.name || d.host}
              </option>
            ))}
          </select>
        </div>

        <Button
          variant="outline"
          size="sm"
          className="rounded-sm h-8 gap-1.5 text-xs ml-auto"
          onClick={loadReport}
          disabled={loading}
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
          {loading ? "Memuat..." : "Refresh"}
        </Button>
      </div>

      {/* Period Label */}
      <div className="flex items-center gap-2">
        <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
          Laporan Periode:
        </span>
        <span className="text-sm font-bold text-foreground">{period}</span>
        {selectedDevice && (
          <>
            <span className="text-muted-foreground">·</span>
            <span className="text-xs text-primary flex items-center gap-1">
              <Server className="w-3 h-3" />
              {selectedDevice.name || selectedDevice.host}
            </span>
          </>
        )}
      </div>

      {loading && !report ? (
        <div className="flex items-center justify-center py-20 text-muted-foreground text-sm animate-pulse">
          Memuat data laporan keuangan...
        </div>
      ) : !report ? null : (
        <Tabs defaultValue="pppoe" className="space-y-4">
          <TabsList className="bg-secondary/50 border border-border h-10">
            <TabsTrigger value="pppoe" className="gap-2 text-xs">
              <TrendingUp className="w-3.5 h-3.5" />
              Billing PPPoE
            </TabsTrigger>
            <TabsTrigger value="hotspot" className="gap-2 text-xs">
              <Wifi className="w-3.5 h-3.5" />
              Laporan Keuangan Hotspot
            </TabsTrigger>
          </TabsList>

          <TabsContent value="pppoe" className="space-y-5 outline-none">
            {/* ── Summary Cards ── */}
            {/* Proyeksi vs Realisasi banner jika ada gap (ada invoice orphan) */}
            {report.summary.orphan_invoice_count > 0 && (
              <div className="flex items-start gap-2 px-3 py-2 bg-amber-500/10 border border-amber-500/20 rounded-sm text-xs text-amber-400">
                <AlertTriangle className="w-3.5 h-3.5 flex-shrink-0 mt-0.5" />
                <span>
                  <strong>Peringatan Invoice Orphan:</strong> Terdapat <strong>{report.summary.orphan_invoice_count} invoice</strong> senilai <strong>{fmtRpShort(report.summary.orphan_invoice_total)}</strong> dari pelanggan yang sudah dihapus.
                  Invoice ini tidak dihitung dalam proyeksi dan total tagihan aktif, namun masih tersimpan di database.
                  Untuk membersihkan, hapus invoice orphan melalui menu Tagihan.
                </span>
              </div>
            )}
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
              <SummaryCard
              icon={RpIcon}
              label="Proyeksi Tagihan"
              value={fmtRpShort(report.summary.total_projected)}
              sub={`Dari ${report.summary.active_customers_count ?? report.summary.total_invoices} pelanggan PPPoE aktif`}
              accent="border-l-primary"
              iconColor="bg-primary/10 text-primary"
            />
            <SummaryCard
              icon={CheckCircle2}
              label="Total Diterima"
              value={fmtRpShort(report.summary.total_collected)}
              sub={`${report.summary.paid_count} invoice lunas bulan ini`}
              accent="border-l-green-500"
              iconColor="bg-green-500/10 text-green-400"
            />
            <SummaryCard
              icon={Clock}
              label="Saldo Piutang"
              value={fmtRpShort(report.summary.total_outstanding)}
              sub={`${
                report.summary.unpaid_count + report.summary.overdue_count
              } belum bayar`}
              accent="border-l-amber-500"
              iconColor="bg-amber-500/10 text-amber-400"
            />
            <SummaryCard
              icon={Percent}
              label="Collection Rate"
              value={`${report.summary.collection_rate}%`}
              sub={`${report.summary.paid_count} dari ${report.summary.total_invoices} invoice`}
              accent={
                report.summary.collection_rate >= 80
                  ? "border-l-green-500"
                  : report.summary.collection_rate >= 50
                  ? "border-l-amber-500"
                  : "border-l-red-500"
              }
              iconColor={
                report.summary.collection_rate >= 80
                  ? "bg-green-500/10 text-green-400"
                  : report.summary.collection_rate >= 50
                  ? "bg-amber-500/10 text-amber-400"
                  : "bg-red-500/10 text-red-400"
              }
            />
          </div>

          {/* ── Status Breakdown Mini Bars ── */}
          <div className="grid grid-cols-3 gap-3">
            {[
              {
                label: "Lunas",
                count: report.summary.paid_count,
                total: report.summary.total_invoices,
                color: "bg-green-500",
                textColor: "text-green-400",
              },
              {
                label: "Belum Bayar",
                count: report.summary.unpaid_count,
                total: report.summary.total_invoices,
                color: "bg-amber-500",
                textColor: "text-amber-400",
              },
              {
                label: "Jatuh Tempo",
                count: report.summary.overdue_count,
                total: report.summary.total_invoices,
                color: "bg-red-500",
                textColor: "text-red-400",
              },
            ].map((item) => {
              const pct = report.summary.total_invoices
                ? Math.round((item.count / report.summary.total_invoices) * 100)
                : 0;
              return (
                <div
                  key={item.label}
                  className="bg-card border border-border rounded-sm p-3"
                >
                  <div className="flex items-center justify-between mb-2">
                    <p className="text-[10px] text-muted-foreground uppercase tracking-wider">
                      {item.label}
                    </p>
                    <span className={`text-sm font-bold font-mono ${item.textColor}`}>
                      {item.count}
                    </span>
                  </div>
                  <div className="w-full bg-secondary/50 rounded-full h-1.5">
                    <div
                      className={`${item.color} h-1.5 rounded-full transition-all duration-700`}
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                  <p className="text-[10px] text-muted-foreground mt-1">{pct}% dari total</p>
                </div>
              );
            })}
          </div>

          {/* ── Data Tabel Section ── */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {/* Detail Pembayaran Harian */}
            <div className="bg-card border border-border rounded-sm flex flex-col h-[400px]">
              <div className="p-4 border-b border-border flex items-center justify-between shrink-0">
                <h3 className="text-sm font-semibold flex items-center gap-2">
                  <CheckCircle2 className="w-4 h-4 text-green-400" />
                  Riwayat Pembayaran Terbaru
                </h3>
              </div>
              <div className="overflow-y-auto p-0 flex-1">
                {!report.payment_details || report.payment_details.length === 0 ? (
                  <div className="flex items-center justify-center py-12 text-muted-foreground text-xs">
                    Belum ada pembayaran bulan ini
                  </div>
                ) : (
                  <table className="w-full text-left text-[11px]">
                    <thead className="sticky top-0 bg-secondary/95 backdrop-blur-sm shadow-[0_1px_0_0_var(--border)] z-10">
                      <tr>
                        <th className="px-3 py-2 text-muted-foreground font-medium w-[25%] shrink-0">Waktu</th>
                        <th className="px-3 py-2 text-muted-foreground font-medium">Pelanggan</th>
                        <th className="px-3 py-2 text-muted-foreground font-medium text-center shrink-0">Metode</th>
                        <th className="px-3 py-2 text-muted-foreground font-medium text-right shrink-0">Nominal</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border/50">
                      {report.payment_details.map((pay, i) => (
                        <tr key={i} className="hover:bg-secondary/20">
                          <td className="px-3 py-2 text-muted-foreground whitespace-nowrap">
                            {pay.paid_at ? new Date(pay.paid_at).toLocaleString("id-ID", {dateStyle: "short", timeStyle: "short"}) : "—"}
                          </td>
                          <td className="px-3 py-2 font-medium truncate max-w-[140px]" title={pay.customer_name}>
                            {pay.customer_name}
                            <div className="text-[9px] text-muted-foreground font-normal truncate mt-0.5">{pay.package_name}</div>
                          </td>
                          <td className="px-3 py-2 text-center whitespace-nowrap">
                            <span className={`inline-block px-1.5 py-0.5 rounded-sm border text-[9px] font-semibold tracking-wide uppercase ${
                              pay.payment_method === 'cash' ? 'bg-green-500/10 text-green-400 border-green-500/20' : 
                              pay.payment_method === 'transfer' ? 'bg-blue-500/10 text-blue-400 border-blue-500/20' : 
                              'bg-purple-500/10 text-purple-400 border-purple-500/20'
                            }`}>
                              {pay.payment_method}
                            </span>
                          </td>
                          <td className="px-3 py-2 text-right font-mono font-bold text-primary whitespace-nowrap">
                            {fmtRpShort(pay.total)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>
            </div>

            {/* Daftar Tunggakan Ringkasan */}
            <div className="bg-card border border-border rounded-sm flex flex-col h-[400px]">
              <div className="p-4 border-b border-border flex items-center justify-between shrink-0">
                <h3 className="text-sm font-semibold flex items-center gap-2">
                  <AlertTriangle className="w-4 h-4 text-red-500" />
                  Daftar Tunggakan
                </h3>
              </div>
              <div className="p-6 flex flex-col items-center justify-center flex-1 text-center space-y-4">
                <div className="w-16 h-16 rounded-full bg-red-500/10 flex items-center justify-center">
                  <AlertTriangle className="w-8 h-8 text-red-500" />
                </div>
                <div>
                  <h4 className="text-2xl font-bold font-mono text-red-400 mb-1">
                    {fmtRpShort((report.overdue_list || []).reduce((a, o) => a + o.total, 0))}
                  </h4>
                  <p className="text-sm text-muted-foreground">
                    Total tagihan menunggak dari <strong className="text-foreground">{report.overdue_list?.length || 0} pelanggan</strong> bulan ini.
                  </p>
                </div>

                <Dialog>
                  <DialogTrigger asChild>
                    <Button variant="outline" className="border-red-500/30 text-red-400 hover:bg-red-500/10 font-semibold h-9 rounded-sm mt-2">
                      Lihat Daftar Pelanggan
                    </Button>
                  </DialogTrigger>
                  <DialogContent className="max-w-4xl max-h-[85vh] flex flex-col p-4 bg-background border border-border">
                    <DialogHeader className="px-2 shrink-0">
                      <DialogTitle className="flex items-center gap-2 text-red-400">
                        <AlertTriangle className="w-5 h-5" />
                        Daftar Tunggakan Pelanggan
                      </DialogTitle>
                    </DialogHeader>
                    <div className="overflow-y-auto mt-4 pr-2 border border-border rounded-sm min-h-[300px]" style={{flex: "1 1 auto"}}>
                      <table className="w-full text-left text-xs">
                        <thead className="bg-secondary/50 sticky top-0 backdrop-blur-sm border-b border-border z-10">
                          <tr>
                            <th className="px-4 py-3 text-muted-foreground font-semibold">Pelanggan</th>
                            <th className="px-4 py-3 text-muted-foreground font-semibold text-center">Jatuh Tempo</th>
                            <th className="px-4 py-3 text-muted-foreground font-semibold text-center">Status Tagihan</th>
                            <th className="px-4 py-3 text-muted-foreground font-semibold text-center">Status Jaringan</th>
                            <th className="px-4 py-3 text-muted-foreground font-semibold text-right">Total</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-border/50">
                          {(!report.overdue_list || report.overdue_list.length === 0) ? (
                            <tr>
                              <td colSpan="5" className="px-4 py-8 text-center text-muted-foreground">
                                Tidak ada tunggakan 🎉
                              </td>
                            </tr>
                          ) : report.overdue_list.map((o, idx) => (
                            <tr key={idx} className="hover:bg-red-500/5 transition-colors">
                              <td className="px-4 py-3">
                                <div className="font-semibold">{o.customer_name}</div>
                                <div className="text-[10px] text-muted-foreground">{o.customer_username} · {o.package_name}</div>
                              </td>
                              <td className="px-4 py-3 text-center text-muted-foreground whitespace-nowrap">
                                {fmtDate(o.due_date)}
                              </td>
                              <td className="px-4 py-3 text-center">
                                <span className="text-[10px] px-1.5 py-0.5 rounded-sm border border-red-500/30 bg-red-500/10 text-red-400 font-semibold uppercase">
                                  {o.status_billing}
                                </span>
                              </td>
                              <td className="px-4 py-3 text-center">
                                <span className={`text-[10px] px-1.5 py-0.5 rounded-sm border font-semibold uppercase ${
                                  o.status_mikrotik === 'Aktif' ? 'border-green-500/30 bg-green-500/10 text-green-400' :
                                  o.status_mikrotik === 'Isolir' ? 'border-orange-500/30 bg-orange-500/10 text-orange-400' :
                                  'border-red-500/30 bg-red-500/10 text-red-400'
                                }`}>
                                  {o.status_mikrotik}
                                </span>
                              </td>
                              <td className="px-4 py-3 text-right">
                                <span className="font-bold font-mono text-red-400">{Rp(o.total)}</span>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </DialogContent>
                </Dialog>
              </div>
            </div>
          </div>
          </TabsContent>

          <TabsContent value="hotspot" className="space-y-5 outline-none mt-4">
            {hotspotReport && (
              <>
                <div className="grid grid-cols-2 lg:grid-cols-3 gap-3">
                  <SummaryCard
                    icon={RpIcon}
                    label="Total Pendapatan Hotspot"
                    value={fmtRpShort(hotspotReport.summary.total_revenue)}
                    sub={`${hotspotReport.summary.wa_count + hotspotReport.summary.offline_count} total penjualan`}
                    accent="border-l-primary"
                    iconColor="bg-primary/10 text-primary"
                  />
                  <SummaryCard
                    icon={Phone}
                    label="Penjualan Online (WA)"
                    value={fmtRpShort(hotspotReport.summary.total_wa_sales)}
                    sub={`${hotspotReport.summary.wa_count} penjualan WA`}
                    accent="border-l-green-500"
                    iconColor="bg-green-500/10 text-green-400"
                  />
                  <SummaryCard
                    icon={FileText}
                    label="Penjualan Offline"
                    value={fmtRpShort(hotspotReport.summary.total_offline_sales)}
                    sub={`${hotspotReport.summary.offline_count} voucher cetak`}
                    accent="border-l-amber-500"
                    iconColor="bg-amber-500/10 text-amber-400"
                  />
                </div>

                <div className="bg-card border border-border rounded-sm p-4">
                  <h3 className="text-sm font-semibold mb-4 flex items-center gap-2">
                    <BarChart3 className="w-4 h-4 text-primary" />
                    Penjualan Harian Hotspot (Online & Offline)
                  </h3>
                  {(!hotspotReport.daily_breakdown || hotspotReport.daily_breakdown.length === 0) ? (
                    <div className="flex items-center justify-center h-48 text-muted-foreground text-xs">
                      Belum ada data penjualan hotspot bulan ini
                    </div>
                  ) : (
                    <ResponsiveContainer width="100%" height={260}>
                      <BarChart data={hotspotReport.daily_breakdown} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke="rgba(100,120,180,0.08)" vertical={false} />
                        <XAxis dataKey="day" tick={{ fontSize: 9, fill: "#ffffff" }} axisLine={false} tickLine={false} />
                        <YAxis tickFormatter={fmtRpShort} tick={{ fontSize: 9, fill: "#ffffff" }} axisLine={false} tickLine={false} />
                        <Tooltip
                          contentStyle={{ backgroundColor: "var(--card)", borderColor: "var(--border)", borderRadius: "4px", fontSize: "12px" }}
                          formatter={(value) => Rp(value)}
                          labelFormatter={(label) => `Tanggal ${label} ${MONTHS[month - 1]}`}
                        />
                        <Legend wrapperStyle={{ fontSize: '11px' }} />
                        <Bar name="Online (WA)" dataKey="wa_sales" stackId="a" fill="#22c55e" radius={[0, 0, 0, 0]} />
                        <Bar name="Offline (Cetak)" dataKey="offline_sales" stackId="a" fill="#f59e0b" radius={[3, 3, 0, 0]} />
                      </BarChart>
                    </ResponsiveContainer>
                  )}
                </div>

                <div className="bg-card border border-border rounded-sm overflow-hidden">
                  <div className="flex items-center justify-between p-4 border-b border-border">
                    <h3 className="text-sm font-semibold flex items-center gap-2">
                      <FileText className="w-4 h-4 text-primary" />
                      Detail Penjualan Hotspot per Hari
                    </h3>
                  </div>
                  <div className="overflow-x-auto">
                    <table className="w-full text-left">
                      <thead>
                        <tr className="border-b border-border bg-secondary/30">
                          {["Tanggal", "Online (WA)", "Offline", "Total Harian"].map((h) => (
                            <th key={h} className="px-4 py-3 text-[10px] text-muted-foreground uppercase tracking-wider font-medium">
                              {h}
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {hotspotReport.daily_breakdown.filter((d) => d.total > 0).map((d) => (
                          <tr key={d.date} className="border-b border-border/30 hover:bg-secondary/20 transition-colors">
                            <td className="px-4 py-3 text-xs font-semibold">
                              {d.day} {MONTHS[month - 1]} {year}
                            </td>
                            <td className="px-4 py-3">
                              <span className="text-xs font-mono text-green-400">{d.wa_sales > 0 ? Rp(d.wa_sales) : "-"}</span>
                            </td>
                            <td className="px-4 py-3">
                              <span className="text-xs font-mono text-amber-500">{d.offline_sales > 0 ? Rp(d.offline_sales) : "-"}</span>
                            </td>
                            <td className="px-4 py-3">
                              <span className="text-xs font-bold font-mono text-primary flex items-center gap-2">
                                {Rp(d.total)}
                              </span>
                            </td>
                          </tr>
                        ))}
                        {hotspotReport.daily_breakdown.filter((d) => d.total > 0).length === 0 && (
                          <tr>
                            <td colSpan="4" className="px-4 py-8 text-center text-muted-foreground text-xs">
                              Belum ada penjualan di periode ini.
                            </td>
                          </tr>
                        )}
                      </tbody>
                    </table>
                  </div>
                </div>
              </>
            )}
          </TabsContent>
        </Tabs>
      )}
    </div>
  );
}
