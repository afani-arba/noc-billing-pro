import { useState, useEffect, useCallback, useRef } from "react";
import { useAuth } from "@/App";
import api from "@/lib/api";
import { useAllowedDevices } from "@/hooks/useAllowedDevices";
import { toast } from "sonner";
import { printInvoiceWithProfile } from "@/lib/printUtils";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import {
  ResponsiveContainer, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend
} from "recharts";
import { 
  Users, Package, LayoutDashboard, RefreshCw, Plus,
  Search, CheckCircle2, Clock, AlertTriangle, Trash2, Edit2,
  MessageCircle, ChevronDown, X, Download, Upload,
  PhoneCall, ArrowUpDown, WifiOff, Wifi, Printer, Send, TrendingUp,
  Settings, Save, BookOpen, FileDown, ChevronLeft, ChevronRight, History,
  BarChart3, Percent, UserX, CalendarClock, CalendarCheck,
  Layout, MapPin, CreditCard, ShoppingCart, Smartphone, Eye, EyeOff, Activity
} from "lucide-react";

const RpIcon = ({ className = "w-5 h-5" }) => (
  <div className={`${className} flex items-center justify-center font-bold text-[9px] border-[1.5px] border-current rounded-[3px] leading-none select-none pt-[1px] px-[1px]`} style={{ fontFamily: 'Inter, sans-serif' }}>
    Rp
  </div>
);
import BillingGuidePage from "@/pages/BillingGuidePage";
import { PackagesTab, PackageForm } from "@/components/BillingPackages";
import PaymentGatewayModal from "@/components/PaymentGatewayModal";

// Ã¢â€â‚¬Ã¢â€â‚¬ Utilities Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬

const Rp = (n) => `Rp ${(Number(n) || 0).toLocaleString("id-ID")}`;
const fmtRpShort = (val) => {
  if (val >= 1_000_000_000) return `Rp ${(val / 1_000_000_000).toFixed(1)}M`;
  if (val >= 1_000_000) return `Rp ${(val / 1_000_000).toFixed(1)}jt`;
  if (val >= 1_000) return `Rp ${(val / 1_000).toFixed(0)}rb`;
  return Rp(val);
};

function BillingSummaryCard({ icon: Icon, label, value, sub, accent, iconColor }) {
  return (
    <div className={`bg-card border border-border rounded-sm p-4 relative overflow-hidden border-l-2 ${accent}`}>
      <div className="flex items-start justify-between relative z-10">
        <div className="flex-1 min-w-0">
          <p className="text-[10px] text-muted-foreground uppercase tracking-widest font-semibold">{label}</p>
          <p className="text-2xl font-bold font-mono mt-1 truncate">{value}</p>
          {sub && <p className="text-[10px] text-muted-foreground mt-1 line-clamp-1">{sub}</p>}
        </div>
        <div className={`w-9 h-9 rounded-sm flex items-center justify-center flex-shrink-0 ml-3 ${iconColor}`}>
          <Icon className="w-4.5 h-4.5" />
        </div>
      </div>
    </div>
  );
}

function fmtDate(isoStr) {
  if (!isoStr) return "";
  const p = String(isoStr).substring(0, 10).split("-");
  return p.length === 3 ? `${p[2]}/${p[1]}/${p[0]}` : isoStr;
}

const STATUS_MAP = {
  paid: { label: "Lunas", cls: "bg-green-500/15 text-green-400 border-green-500/30" },
  unpaid: { label: "Belum Bayar", cls: "bg-amber-500/15 text-amber-400 border-amber-500/30" },
  overdue: { label: "Jatuh Tempo", cls: "bg-red-500/15 text-red-400 border-red-500/30" },
};

function StatusBadge({ status }) {
  const s = STATUS_MAP[status] || STATUS_MAP.unpaid;
  return (
    <span className={`inline-flex items-center gap-1 text-[10px] font-semibold px-2 py-0.5 rounded-sm border ${s.cls}`}>
      {status === "paid" && <CheckCircle2 className="w-2.5 h-2.5" />}
      {status === "overdue" && <AlertTriangle className="w-2.5 h-2.5" />}
      {status === "unpaid" && <Clock className="w-2.5 h-2.5" />}
      {s.label}
    </span>
  );
}

// Ã¢â€â‚¬Ã¢â€â‚¬ Print Invoice (CSS print-only) Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬


// Ã¢â€â‚¬Ã¢â€â‚¬ Stat Card Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬

function StatCard({ label, value, sub, color, badge }) {
  return (
    <div className={`bg-card border border-border rounded-sm p-4 border-l-2 ${color}`}>
      <p className="text-[10px] text-muted-foreground uppercase tracking-wider">{label}</p>
      <div className="flex items-end gap-2 mt-1">
        <p className="text-xl font-bold font-mono">{value}</p>
        {badge && <span className="text-xs font-semibold text-green-400 mb-0.5">{badge}</span>}
      </div>
      {sub && <p className="text-[10px] text-muted-foreground mt-0.5">{sub}</p>}
    </div>
  );
}

// â”€â”€ ConfirmDialog â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
function ConfirmDialog({ open, title, message, onConfirm, onCancel, danger }) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-[60] bg-black/70 flex items-center justify-center p-4">
      <div className="bg-card border border-border rounded-sm w-full max-w-sm shadow-2xl p-5 max-h-[90vh] overflow-y-auto">
        <h3 className={`font-semibold mb-2 ${danger ? 'text-destructive' : ''}`}>{title}</h3>
        <p className="text-sm text-muted-foreground mb-5">{message}</p>
        <div className="flex flex-col-reverse sm:flex-row gap-2 justify-end">
          <Button variant="outline" size="sm" className="rounded-sm" onClick={onCancel}>Batal</Button>
          <Button size="sm" className={`rounded-sm ${danger ? 'bg-destructive hover:bg-destructive/90' : ''}`} onClick={onConfirm}>
            Ya, Lanjutkan
          </Button>
        </div>
      </div>
    </div>
  );
}

// Ã¢â€â‚¬Ã¢â€â‚¬ Invoice Detail Modal Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬

function InvoiceModal({ invoice, packages, onClose, onPaid, onDelete }) {
  const [method, setMethod] = useState("cash");
  const [paying, setPaying] = useState(false);
  const [waLoading, setWaLoading] = useState(false);
  const [disabling, setDisabling] = useState(false);
  const [mtDisabled, setMtDisabled] = useState(invoice.mt_disabled || false);
  const [showJanji, setShowJanji] = useState(false);
  const [promiseDate, setPromiseDate] = useState(invoice.promise_date || null);

  const handlePay = async () => {
    setPaying(true);
    try {
      const r = await api.patch(`/billing/invoices/${invoice.id}/pay`, { payment_method: method });
      toast.success(r.data.message || "Invoice ditandai lunas!");
      onPaid();
    } catch (e) { toast.error(e.response?.data?.detail || "Gagal"); }
    setPaying(false);
  };

  const sendWa = async () => {
    setWaLoading(true);
    try {
      await api.post(`/billing/invoices/${invoice.id}/send-wa`);
      toast.success("WhatsApp tagihan berhasil dikirim via Gateway");
    } catch (e) { 
      toast.error(e.response?.data?.detail || "Gagal mengirim WhatsApp"); 
    }
    setWaLoading(false);
  };

  const toggleMikroTik = async () => {
    setDisabling(true);
    try {
      const action = mtDisabled ? "enable" : "disable";
      const r = await api.post(`/billing/invoices/${invoice.id}/${action}-user`);
      toast.success(r.data.message);
      setMtDisabled(!mtDisabled);
    } catch (e) { toast.error(e.response?.data?.detail || "Gagal"); }
    setDisabling(false);
  };

  const handlePrint = () => {
    const pkg = packages.find(p => p.id === invoice.package_id);
    printInvoiceWithProfile(invoice, pkg?.name, invoice.customer_name, invoice.customer_username, invoice.customer_phone, invoice.customer_address);
  };

  const pkg = packages.find(p => p.id === invoice.package_id) || {};

  return (
    <div className="fixed inset-0 z-50 bg-black/70 flex items-center justify-center p-4">
      <div className="bg-card border border-border rounded-sm w-full max-w-md shadow-2xl flex flex-col max-h-[90vh]">
        <div className="flex items-center justify-between p-4 border-b border-border flex-shrink-0">
          <div className="min-w-0 pr-2">
            <p className="text-xs font-mono text-muted-foreground truncate">{invoice.invoice_number}</p>
            <h3 className="font-semibold truncate">{invoice.customer_name || "â€”"}</h3>
          </div>
          <div className="flex items-center gap-1 sm:gap-2 flex-shrink-0 flex-wrap justify-end">
            <StatusBadge status={invoice.status} />
            {promiseDate && (
              <span className="hidden sm:flex text-[10px] px-1.5 py-0.5 rounded-sm border border-amber-500/30 text-amber-400 items-center gap-1">
                <CalendarClock className="w-2.5 h-2.5" /> Janji
              </span>
            )}
            {mtDisabled && (
              <span className="hidden sm:flex text-[10px] px-1.5 py-0.5 rounded-sm border border-orange-500/30 text-orange-400 items-center gap-1">
                <WifiOff className="w-2.5 h-2.5" /> Putus
              </span>
            )}
            <Button size="icon" variant="ghost" className="h-7 w-7" onClick={onClose}>
              <X className="w-4 h-4" />
            </Button>
          </div>
        </div>

        <div className="p-4 space-y-3 overflow-y-auto">
          {promiseDate && (
            <div className="sm:hidden text-[10px] px-2 py-1 mb-1 rounded-sm border border-amber-500/30 text-amber-400 flex items-center justify-center gap-1">
              <CalendarClock className="w-3 h-3" /> Janji Bayar Aktif
            </div>
          )}
          {mtDisabled && (
            <div className="sm:hidden text-[10px] px-2 py-1 mb-1 rounded-sm border border-orange-500/30 text-orange-400 flex items-center justify-center gap-1">
              <WifiOff className="w-3 h-3" /> User Terisolir
            </div>
          )}
          {/* Info */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs">
            {[
              ["Username", invoice.customer_username],
              ["Telepon", invoice.customer_phone || "â€”"],
              ["Paket", invoice.package_name || pkg.name || "â€”"],
              ["Periode", `${fmtDate(invoice.period_start)} s/d ${fmtDate(invoice.period_end)}`],
              ["Jatuh Tempo", fmtDate(invoice.due_date)],
            ].map(([k, v]) => (
              <div key={k} className="bg-secondary/20 rounded-sm p-2">
                <p className="text-muted-foreground text-[10px]">{k}</p>
                <p className="font-medium">{v}</p>
              </div>
            ))}
            <div className="bg-secondary/20 rounded-sm p-2">
              <p className="text-muted-foreground text-[10px]">Total</p>
              <p className="font-bold text-primary">{Rp(invoice.total)}</p>
            </div>
          </div>

          {/* Prorata info */}
          {invoice.is_prorata && (
            <div className="flex items-start gap-2 p-2 bg-blue-500/10 border border-blue-500/20 rounded-sm text-xs text-blue-300">
              <CalendarCheck className="w-3.5 h-3.5 flex-shrink-0 mt-0.5" />
              <span><strong>Tagihan Prorata:</strong> {invoice.prorata_description}</span>
            </div>
          )}

          {invoice.status !== "paid" && (
            <div className="space-y-2 pt-1">
              <Label className="text-xs text-muted-foreground">Metode Pembayaran</Label>
              <div className="flex gap-2">
                {["cash", "transfer", "qris"].map(m => (
                  <button key={m} onClick={() => setMethod(m)}
                    className={`flex-1 py-1.5 text-xs rounded-sm border capitalize transition-colors ${method === m ? "border-primary bg-primary/10 text-primary" : "border-border text-muted-foreground"
                      }`}>{m}</button>
                ))}
              </div>
              <Button onClick={handlePay} disabled={paying} className="w-full rounded-sm gap-2">
                <CheckCircle2 className="w-4 h-4" />{paying ? "Memproses..." : "Tandai Lunas"}
              </Button>
            </div>
          )}

          {invoice.status === "paid" && (
            <div className="p-2 bg-green-500/10 border border-green-500/20 rounded-sm text-xs text-green-400">
              (v) Lunas via <strong>{invoice.payment_method}</strong> - {invoice.paid_at?.slice(0, 10)}
            </div>
          )}
        </div>

        {/* Action buttons */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 p-4 pt-0 border-t border-border mt-3 flex-shrink-0">
          <Button variant="outline" size="sm" className="rounded-sm gap-1 text-xs"
            onClick={sendWa} disabled={waLoading}>
            <MessageCircle className="w-3.5 h-3.5 text-green-400" />
            {waLoading ? "..." : "Kirim WA"}
          </Button>
          <Button variant="outline" size="sm" className="rounded-sm gap-1 text-xs"
            onClick={handlePrint}>
            <Printer className="w-3.5 h-3.5 text-blue-400" /> Cetak
          </Button>
          {invoice.status !== "paid" && (
            <Button variant="outline" size="sm"
              className="rounded-sm gap-1 text-xs border-amber-500/30 text-amber-400 hover:bg-amber-500/10"
              onClick={() => setShowJanji(true)}>
              <CalendarClock className="w-3.5 h-3.5" />
              Janji Bayar
            </Button>
          )}
          <Button variant="outline" size="sm"
            className={`rounded-sm gap-1 text-xs ${mtDisabled ? "border-green-500/30 text-green-400 hover:bg-green-500/10" : "border-orange-500/30 text-orange-400 hover:bg-orange-500/10"
              }`}
            onClick={toggleMikroTik} disabled={disabling}>
            {mtDisabled ? <Wifi className="w-3.5 h-3.5" /> : <WifiOff className="w-3.5 h-3.5" />}
            {disabling ? "..." : mtDisabled ? "Enable User" : "Putus User"}
          </Button>
          <Button variant="outline" size="sm" className="rounded-sm gap-1 text-xs text-destructive hover:bg-destructive/10"
            onClick={onDelete}>
            <Trash2 className="w-3.5 h-3.5" /> Hapus
          </Button>
        </div>
        {/* Janji Bayar sub-modal */}
        {showJanji && (
          <JanjiBayarModal
            invoice={{ ...invoice, promise_date: promiseDate }}
            onClose={() => setShowJanji(false)}
            onSaved={(d) => setPromiseDate(d)}
          />
        )}
      </div>
    </div>
  );
}

// â”€â”€ Janji Bayar Modal â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
function JanjiBayarModal({ invoice, onClose, onSaved }) {
  const today = new Date().toISOString().split('T')[0];
  const [date, setDate] = useState(invoice.promise_date || "");
  const [saving, setSaving] = useState(false);

  const handleSave = async () => {
    setSaving(true);
    try {
      const r = await api.patch(`/billing/invoices/${invoice.id}/promise-date`, {
        promise_date: date || null,
      });
      toast.success(r.data.message);
      onSaved(date || null);
      onClose();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Gagal menyimpan Janji Bayar");
    }
    setSaving(false);
  };

  const handleClear = async () => {
    setSaving(true);
    try {
      const r = await api.patch(`/billing/invoices/${invoice.id}/promise-date`, { promise_date: null });
      toast.success(r.data.message);
      onSaved(null);
      onClose();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Gagal menghapus");
    }
    setSaving(false);
  };

  return (
    <div className="fixed inset-0 z-[70] bg-black/70 flex items-center justify-center p-4">
      <div className="bg-card border border-border rounded-sm w-full max-w-sm shadow-2xl flex flex-col max-h-[90vh]">
        <div className="flex items-center justify-between p-4 border-b border-border flex-shrink-0">
          <div className="flex items-center gap-2">
            <CalendarClock className="w-4 h-4 text-amber-400" />
            <p className="font-semibold text-sm">Atur Janji Bayar</p>
          </div>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground"><X className="w-4 h-4" /></button>
        </div>
        <div className="p-4 space-y-4 overflow-y-auto">
          <p className="text-xs text-muted-foreground">
            Invoice <span className="font-mono text-foreground">{invoice.invoice_number}</span> &mdash; {invoice.customer_name}.
            Jika Janji Bayar aktif, sistem <strong>tidak akan mengaktifkan isolir</strong> sampai tanggal tersebut.
          </p>
          <div className="space-y-1.5">
            <Label className="text-xs text-muted-foreground uppercase">Tanggal Janji Bayar</Label>
            <Input
              type="date"
              min={today}
              value={date}
              onChange={e => setDate(e.target.value)}
              className="rounded-sm text-xs h-8"
            />
          </div>
          {invoice.promise_date && (
            <div className="p-2 bg-amber-500/10 border border-amber-500/20 rounded-sm text-xs text-amber-300 flex items-center gap-2">
              <CalendarCheck className="w-3.5 h-3.5 flex-shrink-0" />
              Janji Bayar aktif: <strong>{fmtDate(invoice.promise_date)}</strong>
            </div>
          )}
          <div className="flex gap-2">
            {invoice.promise_date && (
              <Button variant="outline" size="sm" className="rounded-sm text-xs flex-1 border-red-500/30 text-red-400 hover:bg-red-500/10"
                onClick={handleClear} disabled={saving}>
                Hapus Janji Bayar
              </Button>
            )}
            <Button size="sm" className="rounded-sm text-xs flex-1 bg-amber-600 hover:bg-amber-700 text-white"
              onClick={handleSave} disabled={saving || !date}>
              {saving ? "Menyimpan..." : "Simpan"}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}


// â”€â”€ Main Page â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

export default function BillingPage() {
  const [tab, setTab] = useState("dashboard");
  const [packages, setPackages] = useState([]);
  const [customers, setCustomers] = useState([]);
  const [unbilledPPPoE, setUnbilledPPPoE] = useState([]);
  const [notifDismissed, setNotifDismissed] = useState(false);
  const today = new Date();
  const [month, setMonth] = useState(today.getMonth() + 1);
  const [year, setYear] = useState(today.getFullYear());
  const { devices, isLocked, defaultDeviceId, loading: devicesLoading } = useAllowedDevices();
  const [globalDeviceId, setGlobalDeviceId] = useState("");

  const loadPackages = useCallback(() => {
    api.get("/billing/packages").then(r => setPackages(r.data)).catch(() => { });
  }, []);

  const loadCustomers = useCallback(() => {
    api.get("/customers").then(r => setCustomers(r.data)).catch(() => { });
  }, []);

  useEffect(() => { loadPackages(); loadCustomers(); }, [loadPackages, loadCustomers]);

  // Inisialisasi globalDeviceId: jika terkunci ke 1 device, langsung auto-select
  useEffect(() => {
    if (isLocked && defaultDeviceId) {
      setGlobalDeviceId(defaultDeviceId);
    }
  }, [isLocked, defaultDeviceId]);

  // Deteksi PPPoE user baru yang belum ada billing record
  useEffect(() => {
    const checkUnbilled = async () => {
      try {
        const [devRes, custRes] = await Promise.all([
          api.get("/devices"),
          api.get("/customers")
        ]);
        const onlineDevs = (devRes.data || []).filter(d => d.status === "online");
        const billedSet = new Set(
          (custRes.data || []).map(c => c.pppoe_username || c.username).filter(Boolean)
        );
        let allPPPoE = [];
        for (const dev of onlineDevs.slice(0, 5)) {
          try {
            const r = await api.get("/pppoe-users", { params: { device_id: dev.id } });
            allPPPoE.push(...(r.data || []).map(u => ({ ...u, device_name: dev.name })));
          } catch {}
        }
        const unregistered = allPPPoE.filter(u => u.name && !billedSet.has(u.name));
        setUnbilledPPPoE(unregistered);
      } catch {}
    };
    checkUnbilled();
  }, []);

  const tabs = [
    { id: "dashboard", label: "Dashboard", icon: LayoutDashboard },
    { id: "invoices", label: "Tagihan", icon: RpIcon },
    { id: "customers", label: "Pelanggan", icon: Users },
    { id: "packages", label: "Paket", icon: Package },
    { id: "monitoring", label: "Monitoring PPPoE", icon: Activity },
    { id: "settings", label: "Pengaturan", icon: Settings },
    { id: "guide", label: "Panduan", icon: BookOpen },
  ];

  const MONTHS = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agt", "Sep", "Okt", "Nov", "Des"];

  return (
    <div className="space-y-4 pb-16">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <h1 className="text-xl sm:text-2xl font-bold tracking-tight flex items-center gap-2">
            <RpIcon className="w-6 h-6 text-primary" /> Billing Management
          </h1>
          <p className="text-xs text-muted-foreground">Manajemen tagihan berlangganan PPPoE &amp; Hotspot</p>
        </div>
        {/* Month selector */}
        <div className="flex flex-wrap items-center gap-2 self-start">
          <select value={globalDeviceId} onChange={e => !isLocked && setGlobalDeviceId(e.target.value)}
            disabled={isLocked}
            className={`h-8 text-xs rounded-sm border border-border bg-secondary px-2 text-foreground min-w-[140px] ${isLocked ? "opacity-80 cursor-not-allowed" : ""}`}>
            {!isLocked && <option value="">Semua Router</option>}
            {devices.map(d => <option key={d.id} value={d.id}>{d.name}</option>)}
          </select>
          <select value={month} onChange={e => setMonth(Number(e.target.value))}
            className="h-8 text-xs rounded-sm border border-border bg-secondary px-2 text-foreground">
            {MONTHS.map((m, i) => <option key={i} value={i + 1}>{m}</option>)}
          </select>
          <div className="flex items-center bg-secondary rounded-sm border border-border h-8 px-2">
             <input value={year} onChange={e => setYear(Number(e.target.value))} type="number"
                className="w-16 bg-transparent text-xs outline-none" min="2020" max="2099" />
          </div>
        </div>
      </div>

      {/* Notifikasi PPPoE user belum ada billing */}
      {unbilledPPPoE.length > 0 && !notifDismissed && (
        <div className="bg-amber-500/10 border border-amber-500/30 rounded-sm p-3 flex items-start gap-3">
          <AlertTriangle className="w-4 h-4 text-amber-500 flex-shrink-0 mt-0.5" />
          <div className="flex-1 min-w-0">
            <p className="text-sm font-semibold text-amber-400">
              {unbilledPPPoE.length} user PPPoE baru belum diatur paket billing
            </p>
            <p className="text-[10px] text-muted-foreground mt-0.5">
              User: {unbilledPPPoE.slice(0, 4).map(u => u.name).join(", ")}
              {unbilledPPPoE.length > 4 && ` +${unbilledPPPoE.length - 4} lainnya`}
            </p>
          </div>
          <div className="flex gap-1.5 flex-shrink-0">
            <Button size="sm" variant="outline"
              className="rounded-sm text-xs h-7 border-amber-500/30 text-amber-400 hover:bg-amber-500/10"
              onClick={() => setTab("customers")}>
              Atur Paket
            </Button>
            <Button size="icon" variant="ghost" className="h-7 w-7" onClick={() => setNotifDismissed(true)}>
              <X className="w-3.5 h-3.5" />
            </Button>
          </div>
        </div>
      )}

      {/* Tabs */}
      <div className="flex flex-wrap border-b border-border gap-x-1 pb-0">
        {tabs.map(t => (
          <button key={t.id} onClick={() => setTab(t.id)}
            className={`flex items-center gap-1.5 px-3 py-2.5 text-sm border-b-2 transition-colors whitespace-nowrap ${tab === t.id ? "border-primary text-primary" : "border-transparent text-muted-foreground hover:text-foreground"
              }`}>
            <t.icon className="w-3.5 h-3.5" />{t.label}
          </button>
        ))}
      </div>

      {/* Content */}
      <div className="bg-card border border-border rounded-sm p-4">
        {tab === "dashboard" && <DashboardTab month={month} year={year} deviceId={globalDeviceId} />}
        {tab === "invoices" && <InvoicesTab month={month} year={year} packages={packages} customers={customers} deviceId={globalDeviceId} />}
        {tab === "customers" && <CustomersTab packages={packages} devices={devices} onRefresh={loadCustomers} deviceId={globalDeviceId} isLocked={isLocked} />}
        {tab === "packages" && <PackagesTab packages={packages} onRefresh={loadPackages} deviceId={globalDeviceId} defaultServiceType="pppoe" />}
        {tab === "monitoring" && <PpoeMonitoringTab deviceId={globalDeviceId} />}
        {tab === "settings" && <SettingsTab />}
        {tab === "guide" && <BillingGuidePage />}
      </div>
    </div>
  );
}

function DashboardTab({ month, year, deviceId }) {
  const [stats, setStats] = useState(null);
  const [recent, setRecent] = useState([]);
  const [trend, setTrend] = useState([]);
  const [trendMonths, setTrendMonths] = useState(6);
  const [report, setReport] = useState(null);

  useEffect(() => {
    api.get("/billing/stats", { params: { month, year, device_id: deviceId } })
      .then(r => setStats(r.data)).catch(() => {});
    api.get("/billing/invoices", { params: { month, year, status: "overdue", device_id: deviceId } })
      .then(r => setRecent((r.data?.data || r.data || []).slice(0, 5))).catch(() => {});
    api.get("/billing/financial-report", { params: { month, year, device_id: deviceId } })
      .then(r => setReport(r.data)).catch(() => {});
  }, [month, year, deviceId]);

  // FIX B10: Hapus month/year dari deps â€” monthly-summary tidak butuh itu
  // Ini mencegah reload chart yang tidak diperlukan setiap bulan/tahun diganti
  useEffect(() => {
    api.get("/billing/monthly-summary", { params: { months: trendMonths, device_id: deviceId } })
      .then(r => setTrend(r.data)).catch(() => {});
  }, [trendMonths, deviceId]); // eslint-disable-line

  const fmtRp = (val) => {
    if (val >= 1_000_000) return `Rp ${(val / 1_000_000).toFixed(1)}jt`;
    if (val >= 1_000) return `Rp ${(val / 1_000).toFixed(0)}rb`;
    return Rp(val);
  };

  const collectionRate = stats?.paid_amount && stats?.total_amount
    ? Math.min(Math.round((stats.paid_amount / stats.total_amount) * 100), 100)
    : 0;

  return (
    <div className="space-y-6 animate-in fade-in duration-500">
      {/* â”€â”€ Professional Header â”€â”€ */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 bg-card/30 p-4 rounded-sm border border-border/50 backdrop-blur-sm">
        <div>
          <h2 className="text-lg font-bold flex items-center gap-2">
            <TrendingUp className="w-5 h-5 text-primary" />
            Laporan Keuangan PPPoE
          </h2>
          <p className="text-xs text-muted-foreground mt-0.5">Analisis pendapatan, penagihan, dan efisiensi koleksi.</p>
        </div>
        <div className="flex items-center gap-2 bg-secondary/50 p-1 rounded-sm border border-border/50">
          <Badge variant="outline" className="rounded-sm bg-background/50 border-primary/20 text-primary font-mono text-[10px] px-2 py-1 uppercase tracking-wider">
            Periode: {report?.period?.label || "Memuat..."}
          </Badge>
        </div>
      </div>

      {report && (
        <div className="space-y-6">
          {/* â”€â”€ Financial Cards â”€â”€ */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            <BillingSummaryCard 
              label="TOTAL TAGIHAN" 
              value={fmtRpShort(report.summary.total_projected)} 
              sub="Proyeksi total seluruh user aktif" 
              icon={RpIcon} 
              accent="border-l-blue-500"
              iconColor="bg-blue-500/10 text-blue-500" 
            />
            <BillingSummaryCard 
              label="TOTAL DITERIMA" 
              value={fmtRpShort(report.summary.total_collected)} 
              sub={`${report.summary.paid_count} lunas`} 
              icon={CheckCircle2} 
              accent="border-l-emerald-500"
              iconColor="bg-emerald-500/10 text-emerald-500" 
            />
            <BillingSummaryCard 
              label="SALDO PIUTANG" 
              value={fmtRpShort(report.summary.total_outstanding)} 
              sub={`${report.summary.overdue_count} tagihan jatuh tempo`} 
              icon={Clock} 
              accent="border-l-amber-500"
              iconColor="bg-amber-500/10 text-amber-500" 
            />
            <BillingSummaryCard 
              label="COLLECTION RATE" 
              value={`${report.summary.collection_rate}%`} 
              sub={`${report.summary.paid_count} dari ${report.summary.total_invoices} invoice`} 
              icon={Percent} 
              accent="border-l-purple-500"
              iconColor="bg-purple-500/10 text-purple-500" 
            />
          </div>

          {/* â”€â”€ Efficiency Metrics (Bars) â”€â”€ */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="bg-card/50 border border-border rounded-sm p-4">
              <div className="flex justify-between items-end mb-2">
                <span className="text-[10px] font-bold text-emerald-500 uppercase">LUNAS</span>
                <span className="text-xs font-mono font-bold">{report.summary.paid_count}</span>
              </div>
              <div className="h-1.5 w-full bg-emerald-500/10 rounded-full overflow-hidden">
                <div className="h-full bg-emerald-500" style={{ width: `${(report.summary.paid_count / (report.summary.total_invoices || 1)) * 100}%` }} />
              </div>
              <p className="text-[9px] text-muted-foreground mt-2">{Math.round((report.summary.paid_count / (report.summary.total_invoices || 1)) * 100)}% dari total</p>
            </div>
            <div className="bg-card/50 border border-border rounded-sm p-4">
              <div className="flex justify-between items-end mb-2">
                <span className="text-[10px] font-bold text-amber-500 uppercase">BELUM BAYAR</span>
                <span className="text-xs font-mono font-bold">{report.summary.unpaid_count}</span>
              </div>
              <div className="h-1.5 w-full bg-amber-500/10 rounded-full overflow-hidden">
                <div className="h-full bg-amber-500" style={{ width: `${(report.summary.unpaid_count / (report.summary.total_invoices || 1)) * 100}%` }} />
              </div>
              <p className="text-[9px] text-muted-foreground mt-2">{Math.round((report.summary.unpaid_count / (report.summary.total_invoices || 1)) * 100)}% dari total</p>
            </div>
            <div className="bg-card/50 border border-border rounded-sm p-4">
              <div className="flex justify-between items-end mb-2">
                <span className="text-[10px] font-bold text-red-500 uppercase">JATUH TEMPO</span>
                <span className="text-xs font-mono font-bold">{report.summary.overdue_count}</span>
              </div>
              <div className="h-1.5 w-full bg-red-500/10 rounded-full overflow-hidden">
                <div className="h-full bg-red-500" style={{ width: `${(report.summary.overdue_count / (report.summary.total_invoices || 1)) * 100}%` }} />
              </div>
              <p className="text-[9px] text-muted-foreground mt-2">{Math.round((report.summary.overdue_count / (report.summary.total_invoices || 1)) * 100)}% dari total</p>
            </div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* â”€â”€ Recent Payments â”€â”€ */}
            <div className="bg-card border border-border rounded-sm p-4">
              <h3 className="text-xs font-bold flex items-center gap-2 mb-4">
                <History className="w-4 h-4 text-emerald-400" />
                Riwayat Pembayaran Terbaru
              </h3>
              <div className="space-y-1">
                {report.payment_details?.length > 0 ? report.payment_details.slice(0, 5).map((pay, i) => (
                  <div key={i} className="flex items-center justify-between p-2 hover:bg-secondary/30 rounded-sm transition-colors border-b border-border/30 last:border-0">
                    <div className="flex items-center gap-3">
                      <div className="w-8 h-8 rounded-full bg-emerald-500/10 flex items-center justify-center text-[10px] font-bold text-emerald-500">
                        {pay.payment_method?.substring(0, 2).toUpperCase() || "CA"}
                      </div>
                      <div className="min-w-0 flex-1">
                        <p className="text-xs font-bold truncate">{pay.customer_name}</p>
                        <p className="text-[10px] text-muted-foreground">{pay.invoice_number} Ã¢â‚¬Â¢ {new Date(pay.paid_at).toLocaleDateString("id-ID")}</p>
                      </div>
                    </div>
                    <p className="text-xs font-mono font-bold text-emerald-400 shrink-0">+{Rp(pay.total)}</p>
                  </div>
                )) : <p className="text-[10px] text-center py-8 text-muted-foreground italic">Belum ada pembayaran bulan ini</p>}
              </div>
            </div>

            {/* â”€â”€ Arrears (Daftar Tunggakan) â”€â”€ */}
            <div className="bg-card border border-border rounded-sm p-4">
              <h3 className="text-xs font-bold flex items-center gap-2 mb-4">
                <AlertTriangle className="w-4 h-4 text-amber-400" />
                Daftar Tunggakan (Overdue)
              </h3>
              <div className="space-y-1">
                {report.overdue_list?.length > 0 ? report.overdue_list.slice(0, 5).map((over, i) => (
                  <div key={i} className="flex items-center justify-between p-2 hover:bg-red-500/5 rounded-sm transition-colors border-b border-border/30 last:border-0 border-l-2 border-l-red-500/30">
                    <div className="flex items-center gap-3">
                      <div className="w-8 h-8 rounded-full bg-red-500/10 flex items-center justify-center shrink-0">
                        <UserX className="w-4 h-4 text-red-500" />
                      </div>
                      <div className="min-w-0 flex-1">
                        <p className="text-xs font-bold truncate">{over.customer_name}</p>
                        <p className="text-[10px] text-red-400/70 font-mono mt-0.5">Tempo: {over.due_date}</p>
                      </div>
                    </div>
                    <div className="text-right shrink-0">
                      <p className="text-xs font-mono font-bold text-foreground">{Rp(over.total)}</p>
                      <Badge variant="outline" className="text-[8px] h-4 px-1 bg-red-500/5 text-red-400 border-red-500/20 uppercase">OVERDUE</Badge>
                    </div>
                  </div>
                )) : <p className="text-[10px] text-center py-8 text-muted-foreground italic">Tidak ada tunggakan saat ini. Bagus!</p>}
              </div>
            </div>
          </div>

          {/* â”€â”€ Revenue Progress Chart â”€â”€ */}
          <div className="bg-card border border-border rounded-sm p-5">
            <div className="flex items-center justify-between mb-6">
              <h3 className="text-xs font-bold flex items-center gap-2">
                <BarChart3 className="w-4 h-4 text-primary" />
                Tren Pendapatan Bulanan
              </h3>
            </div>
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={report.daily_breakdown || [{day:1, total:100}]}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="rgba(255,255,255,0.05)" />
                  <XAxis dataKey="day" axisLine={false} tickLine={false} fontSize={10} stroke="#94a3b8" />
                  <YAxis axisLine={false} tickLine={false} fontSize={10} stroke="#94a3b8" tickFormatter={(v) => `Rp ${v/1000}k`} />
                  <Tooltip 
                    cursor={{fill: 'rgba(255,255,255,0.05)'}}
                    contentStyle={{backgroundColor:'#0f172a', borderColor:'rgba(255,255,255,0.1)', borderRadius:'4px', fontSize:'11px'}}
                    itemStyle={{color:'#38bdf8'}}
                    formatter={(v) => Rp(v)}
                  />
                  <Bar dataKey="total" fill="url(#colorTotal)" radius={[2, 2, 0, 0]} />
                  <defs>
                    <linearGradient id="colorTotal" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.8}/>
                      <stop offset="95%" stopColor="#3b82f6" stopOpacity={0.2}/>
                    </linearGradient>
                  </defs>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}


// -- Invoices Tab --

const PAGE_SIZE = 20;

function InvoicesTab({ month, year, packages, customers, deviceId }) {
  const [allInvoices, setAllInvoices] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [activeTab, setActiveTab] = useState("nunggak"); // "nunggak" | "lunas"
  const [serviceTypeFilter, setServiceTypeFilter] = useState("pppoe"); // Kunci pppoe
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState(null);
  const [showCreate, setShowCreate] = useState(false);
  const [bulking, setBulking] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [showReminderModal, setShowReminderModal] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [confirm, setConfirm] = useState(null);
  const [paymentInv, setPaymentInv] = useState(null);
  const { user } = useAuth();
  const isAdmin = user?.role === "administrator";

  const loadPage = useCallback(async (pg) => {
    setLoading(true);
    try {
      const status = activeTab === "nunggak" ? "unpaid,overdue" : "paid";
      const r = await api.get("/billing/invoices", {
        params: { month, year, status, search, device_id: deviceId, service_type: serviceTypeFilter, page: pg, limit: PAGE_SIZE }
      });
      if (Array.isArray(r.data)) {
        setAllInvoices(r.data);
        setTotal(r.data.length);
      } else {
        setAllInvoices(r.data.data || []);
        setTotal(r.data.total || 0);
      }
    } catch { toast.error("Gagal memuat tagihan"); }
    setLoading(false);
  }, [month, year, activeTab, search, deviceId, serviceTypeFilter]);

  // FIX B1: Hanya 1 effect yang memicu load. Filter change selalu reset ke page 1.
  // Tidak ada double-effect yang menyebabkan 2 API call sekaligus.
  useEffect(() => {
    setPage(1);
    loadPage(1);
  }, [month, year, activeTab, search, deviceId, serviceTypeFilter]); // eslint-disable-line

  // Effect terpisah HANYA untuk paginasi â€” tidak tumpang tindih dengan filter change
  const handlePageChange = useCallback((newPage) => {
    setPage(newPage);
    loadPage(newPage);
  }, [loadPage]);

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  const bulkCreate = async () => {
    setBulking(true);
    try {
      // FIX B7: Selalu kirim service_type=pppoe agar tidak generate invoice hotspot
      const r = await api.post("/billing/invoices/bulk-create", null, {
        params: { month, year, service_type: "pppoe", device_id: deviceId }
      });
      toast.success(r.data.message);
      loadPage(1); setPage(1);
    } catch (e) { toast.error(e.response?.data?.detail || "Gagal"); }
    setBulking(false);
  };

  const syncDisable = () => setConfirm({
    title: "Putus Semua Overdue?",
    message: "Semua pelanggan dengan tagihan JATUH TEMPO akan diputus koneksinya dari MikroTik.",
    danger: true,
    onConfirm: async () => {
      setConfirm(null); setSyncing(true);
      try {
        const r = await api.post("/billing/invoices/sync-status", null, { params: { action: "disable", status_filter: "overdue" } });
        toast.success(r.data.message);
        if (r.data.errors?.length) toast.warning(r.data.errors.slice(0, 3).join("; "));
        loadPage(page);
      } catch (e) { toast.error(e.response?.data?.detail || "Gagal"); }
      setSyncing(false);
    }
  });

  const deleteInv = (id) => setConfirm({
    title: "Hapus Invoice?",
    message: "Invoice yang dihapus tidak dapat dikembalikan.",
    danger: true,
    onConfirm: async () => {
      setConfirm(null);
      try {
        await api.delete(`/billing/invoices/${id}`);
        toast.success("Invoice dihapus");
        setSelected(null);
        loadPage(page);
      } catch (e) { toast.error(e.response?.data?.detail || "Gagal"); }
    }
  });

  const exportCsv = async () => {
    setExporting(true);
    try {
      const status = activeTab === "nunggak" ? "unpaid,overdue" : "paid";
      const params = new URLSearchParams({ month, year, status, ...(deviceId && { device_id: deviceId }) });
      const token = localStorage.getItem("access_token") || sessionStorage.getItem("access_token") || "";
      const resp = await fetch(`/api/billing/invoices/export-csv?${params}`, { headers: { Authorization: `Bearer ${token}` } });
      if (!resp.ok) throw new Error("Export gagal");
      const blob = await resp.blob();
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = `invoice-${year}-${String(month).padStart(2, "0")}.csv`;
      a.click();
      toast.success("CSV berhasil diunduh");
    } catch (e) { toast.error("Gagal export: " + e.message); }
    setExporting(false);
  };

  const unpaidWithPhone = allInvoices.filter(i => i.status !== "paid" && i.customer_phone);

  return (
    <div className="space-y-3">
      {/* Tab Filter Lunas/Nunggak */}
      <div className="grid grid-cols-2 sm:flex bg-secondary/30 p-1 rounded-sm border border-border w-full sm:w-fit overflow-x-auto text-[10px] sm:text-xs">
        <button
          onClick={() => setActiveTab("nunggak")}
          className={`flex-1 sm:px-6 py-1.5 text-xs font-semibold rounded-[2px] transition-all ${activeTab === "nunggak" ? "bg-card shadow-sm border border-border/50 text-foreground" : "text-muted-foreground hover:text-foreground"}`}
        >
          Belum Lunas / Nunggak
        </button>
        <button
          onClick={() => setActiveTab("lunas")}
          className={`flex-1 sm:px-6 py-1.5 text-xs font-semibold rounded-[2px] transition-all ${activeTab === "lunas" ? "bg-card shadow-sm border border-border/50 text-foreground" : "text-muted-foreground hover:text-foreground"}`}
        >
          Sudah Lunas
        </button>
      </div>

      {/* Filter Tipe Layanan dihapus (Kunci PPPoE) */}

      {/* Toolbar */}
      <div className="flex flex-wrap gap-2 items-center">
        <div className="relative flex-1 min-w-[180px]">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
          <Input value={search} onChange={e => setSearch(e.target.value)} placeholder="Cari nama / username..."
            className="pl-8 h-8 rounded-sm text-xs" onKeyDown={e => e.key === "Enter" && (setPage(1), loadPage(1))} />
        </div>
        <Button size="sm" variant="outline" className="rounded-sm h-8 gap-1 text-xs" onClick={() => { setPage(1); loadPage(1); }}>
          <RefreshCw className="w-3.5 h-3.5" />
        </Button>
        <Button size="sm" variant="outline" className="rounded-sm h-8 gap-1 text-xs" onClick={exportCsv} disabled={exporting}>
          <FileDown className="w-3.5 h-3.5" />{exporting ? "..." : "CSV"}
        </Button>
        {isAdmin && <>
          <Button size="sm" variant="outline" className="rounded-sm h-8 gap-1 text-xs" onClick={bulkCreate} disabled={bulking}>
            <Download className="w-3.5 h-3.5" />{bulking ? "Membuat..." : "Generate Massal"}
          </Button>
          <Button size="sm" variant="outline"
            className="rounded-sm h-8 gap-1 text-xs border-orange-500/40 text-orange-400 hover:bg-orange-500/10"
            onClick={syncDisable} disabled={syncing}>
            <WifiOff className="w-3.5 h-3.5" />{syncing ? "Memutus..." : "Putus Overdue"}
          </Button>
          {unpaidWithPhone.length > 0 && (
            <Button size="sm" variant="outline"
              className="rounded-sm h-8 gap-1 text-xs border-green-500/40 text-green-400 hover:bg-green-500/10"
              onClick={() => setShowReminderModal(true)}>
              <Send className="w-3.5 h-3.5" /> Reminder ({unpaidWithPhone.length})
            </Button>
          )}
          <Button size="sm" className="rounded-sm h-8 gap-1 text-xs" onClick={() => setShowCreate(true)}>
            <Plus className="w-3.5 h-3.5" /> Tambah
          </Button>
        </>}
      </div>

      {loading ? (
        <p className="text-muted-foreground text-sm text-center py-8 animate-pulse">Memuat tagihan...</p>
      ) : allInvoices.length === 0 ? (
        <div className="text-center py-10">
          <RpIcon className="w-10 h-10 text-muted-foreground/30 mx-auto mb-2" />
          <p className="text-muted-foreground text-sm">Tidak ada tagihan</p>
        </div>
      ) : (
        <>
          <div className="hidden md:block overflow-x-auto">
            <table className="w-full text-left min-w-[700px]">
              <thead>
                <tr className="border-b border-border">
                  {["No. Invoice", "Pelanggan", "WhatsApp", "Paket", "Total", "Bayar Via", "Jatuh Tempo", "Status", "Aksi"].map(h => (
                    <th key={h} className="px-3 py-2 text-[10px] text-muted-foreground uppercase tracking-wider font-medium text-center">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {allInvoices.map(inv => (
                  <tr key={inv.id} className="border-b border-border/30 hover:bg-secondary/20 transition-colors text-center">
                    <td className="px-3 py-2.5 text-[10px] font-mono text-muted-foreground">{inv.invoice_number}</td>
                    <td className="px-3 py-2.5 text-left">
                      <p className="text-xs font-medium">{inv.customer_name}</p>
                      <p className="text-[10px] text-muted-foreground mt-0.5">{inv.customer_username}</p>
                    </td>
                    <td className="px-3 py-2.5 text-[10px] font-mono text-muted-foreground">
                      {inv.customer_phone || "â€”"}
                    </td>
                    <td className="px-3 py-2.5 text-xs text-muted-foreground">{inv.package_name}</td>
                    <td className="px-3 py-2.5 text-xs font-mono font-bold text-primary">{Rp(inv.total)}</td>
                    <td className="px-3 py-2.5">
                      {inv.payment_method ? (
                        <span className={`inline-block px-1.5 py-0.5 rounded-sm border text-[9px] font-semibold tracking-wide uppercase ${
                          inv.payment_method === 'cash' ? 'bg-green-500/10 text-green-400 border-green-500/20' : 
                          inv.payment_method === 'transfer' ? 'bg-blue-500/10 text-blue-400 border-blue-500/20' : 
                          'bg-purple-500/10 text-purple-400 border-purple-500/20'
                        }`}>
                          {inv.payment_method}
                        </span>
                      ) : (
                        <span className="text-[10px] text-muted-foreground italic">Belum bayar</span>
                      )}
                    </td>
                    <td className="px-3 py-2.5 text-[10px] text-muted-foreground">
                      <p>{fmtDate(inv.due_date)}</p>
                    </td>
                    <td className="px-3 py-2.5">
                      <div className="flex items-center justify-center gap-1">
                        <StatusBadge status={inv.status} />
                        {inv.mt_disabled && <WifiOff className="w-3 h-3 text-orange-400" title="Diisolir" />}
                      </div>
                    </td>
                    <td className="px-3 py-2.5 text-right w-[150px]">
                      <div className="flex gap-1 justify-end flex-wrap">
                        {inv.status !== "paid" && (
                          <Button size="sm" variant="outline" className="rounded-sm h-6 text-[10px] px-2 text-emerald-400 hover:bg-emerald-500/10 border-emerald-500/30" onClick={() => setPaymentInv(inv)}>VA/QRIS</Button>
                        )}
                        <Button size="sm" variant="outline" className="rounded-sm h-6 text-[10px] px-2 text-blue-500 hover:bg-blue-500/10 hover:text-blue-400 border-blue-500/30" onClick={() => printInvoiceWithProfile(inv, inv.package_name, inv.customer_name, inv.customer_username, inv.customer_phone, inv.customer_address)}>Cetak</Button>
                        <Button size="sm" variant="outline" className="rounded-sm h-6 text-[10px] px-2" onClick={() => setSelected(inv)}>Detail</Button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="md:hidden space-y-3 mt-4">
            {allInvoices.map(inv => (
              <div key={inv.id} className="bg-card border border-border p-3 rounded-lg shadow-sm space-y-2">
                <div className="flex justify-between items-center border-b border-border/50 pb-2">
                  <span className="text-xs font-mono text-muted-foreground flex items-center gap-1">
                    <RpIcon className="w-3.5 h-3.5" />{inv.invoice_number}
                  </span>
                  <div className="flex items-center gap-1">
                    <StatusBadge status={inv.status} />
                    {inv.mt_disabled && <WifiOff className="w-3 h-3 text-orange-400" />}
                  </div>
                </div>
                <div>
                  <p className="font-bold text-sm">{inv.customer_name}</p>
                  <p className="text-[10px] text-muted-foreground">{inv.customer_username} - {inv.package_name}</p>
                </div>
                <div className="flex justify-between items-end pt-1">
                  <div>
                    <p className="text-[10px] text-muted-foreground">Jatuh Tempo</p>
                    <p className="text-xs font-medium">{fmtDate(inv.due_date)}</p>
                  </div>
                  <p className="font-bold font-mono text-primary text-base">{Rp(inv.total)}</p>
                </div>
                <div className="flex gap-2 mt-2 flex-wrap">
                  {inv.status !== "paid" && (
                    <Button size="sm" variant="outline" className="flex-1 h-8 text-xs text-emerald-400 hover:bg-emerald-500/10 border-emerald-500/30" onClick={() => setPaymentInv(inv)}>VA/QRIS</Button>
                  )}
                  <Button size="sm" variant="outline" className="flex-1 h-8 text-xs text-blue-500 hover:bg-blue-500/10 hover:text-blue-400 border-blue-500/30" onClick={() => printInvoiceWithProfile(inv, inv.package_name, inv.customer_name, inv.customer_username, inv.customer_phone, inv.customer_address)}>Cetak</Button>
                  <Button size="sm" variant="outline" className="flex-1 h-8 text-xs" onClick={() => setSelected(inv)}>Lihat Detail</Button>
                </div>
              </div>
            ))}
          </div>

          <div className="flex items-center justify-between mt-3">
            <p className="text-[10px] text-muted-foreground font-mono">
              {total} tagihan - Hal {page}/{totalPages}
            </p>
            <div className="flex gap-1">
              <Button size="sm" variant="outline" className="rounded-sm h-7 px-2 text-xs"
                disabled={page <= 1} onClick={() => handlePageChange(Math.max(1, page - 1))}>
                <ChevronLeft className="w-3.5 h-3.5" />
              </Button>
              <Button size="sm" variant="outline" className="rounded-sm h-7 px-2 text-xs"
                disabled={page >= totalPages} onClick={() => handlePageChange(Math.min(totalPages, page + 1))}>
                <ChevronRight className="w-3.5 h-3.5" />
              </Button>
            </div>
          </div>
        </>
      )}

      {selected && (
        <InvoiceModal invoice={selected} packages={packages}
          onClose={() => setSelected(null)}
          onPaid={() => { setSelected(null); loadPage(page); }}
          onDelete={() => deleteInv(selected.id)} />
      )}
      {showCreate && (
        <CreateInvoiceModal packages={packages} customers={customers}
          month={month} year={year} serviceType={serviceTypeFilter}
          onClose={() => setShowCreate(false)}
          onCreated={() => { setShowCreate(false); loadPage(1); setPage(1); }} />
      )}
      {showReminderModal && (
        <BulkReminderModal invoices={unpaidWithPhone} onClose={() => setShowReminderModal(false)} />
      )}
      {paymentInv && (
        <PaymentGatewayModal
          invoice={paymentInv}
          onClose={() => setPaymentInv(null)}
          onPaid={() => { setPaymentInv(null); loadPage(page); }}
        />
      )}
      <ConfirmDialog open={!!confirm} title={confirm?.title} message={confirm?.message}
        danger={confirm?.danger} onConfirm={confirm?.onConfirm} onCancel={() => setConfirm(null)} />
    </div>
  );
}

// â”€â”€ Create Invoice Modal â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

function CreateInvoiceModal({ packages, customers, month, year, serviceType, onClose, onCreated }) {
  const [form, setForm] = useState({
    customer_id: "", package_id: "", amount: "", discount: "0",
    period_start: `${year}-${String(month).padStart(2, "0")}-01`,
    period_end: "", due_date: "", notes: "",
  });
  const [saving, setSaving] = useState(false);

  const set = (k, v) => setForm(f => ({ ...f, [k]: v }));

  const selectedCustomer = customers.find(c => c.id === form.customer_id);
  const selectedPkg = packages.find(p => p.id === form.package_id);

  useEffect(() => {
    if (selectedPkg && !form.amount) set("amount", String(selectedPkg.price));
  }, [selectedPkg]); // eslint-disable-line

  const submit = async () => {
    if (!form.customer_id || !form.package_id || !form.amount || !form.period_end || !form.due_date) {
      toast.error("Isi semua field yang wajib"); return;
    }
    setSaving(true);
    try {
      await api.post("/billing/invoices", {
        ...form, amount: Number(form.amount), discount: Number(form.discount || 0),
      });
      toast.success("Invoice berhasil dibuat");
      onCreated();
    } catch (e) { toast.error(e.response?.data?.detail || "Gagal"); }
    setSaving(false);
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/70 flex items-center justify-center p-4">
      <div className="bg-card border border-border rounded-sm w-full max-w-md shadow-2xl">
        <div className="flex items-center justify-between p-4 border-b border-border">
          <h3 className="font-semibold">Buat Invoice Baru</h3>
          <Button size="icon" variant="ghost" className="h-7 w-7" onClick={onClose}><X className="w-4 h-4" /></Button>
        </div>
        <div className="p-4 space-y-3 max-h-[70vh] overflow-y-auto">
          <div className="space-y-1.5">
            <Label className="text-xs text-muted-foreground">Pelanggan *</Label>
            <select value={form.customer_id} onChange={e => set("customer_id", e.target.value)}
              className="w-full h-8 text-xs rounded-sm border border-border bg-secondary px-2 text-foreground">
              <option value="">Pilih pelanggan...</option>
              {/* FIX B3: Fallback ke field 'type' jika 'service_type' tidak ada */}
              {customers.filter(c => c.active && (c.service_type === serviceType || c.type === serviceType)).map(c => (
                <option key={c.id} value={c.id}>{c.name} ({c.username})</option>
              ))}
            </select>
          </div>
          <div className="space-y-1.5">
            <Label className="text-xs text-muted-foreground">Paket *</Label>
            <select value={form.package_id} onChange={e => {
                set("package_id", e.target.value);
                const p = packages.find(x => x.id === e.target.value);
                if (p) { set("amount", String(p.price)); }
              }}
              className="w-full h-8 text-xs rounded-sm border border-border bg-secondary px-2 text-foreground">
              <option value="">Pilih paket...</option>
              {/* FIX B3: Fallback ke field 'type' agar paket lama tetap muncul */}
              {packages.filter(p => (p.service_type === serviceType || p.type === serviceType) && p.active !== false).map(p => (
                <option key={p.id} value={p.id}>{p.name} â€” {Rp(p.price)}</option>
              ))}
            </select>
          </div>
          <div className="grid grid-cols-2 gap-2">
            <div className="space-y-1.5">
              <Label className="text-xs text-muted-foreground">Tagihan (Rp) *</Label>
              <Input value={form.amount} onChange={e => set("amount", e.target.value)} className="h-8 rounded-sm text-xs" type="number" />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs text-muted-foreground">Diskon (Rp)</Label>
              <Input value={form.discount} onChange={e => set("discount", e.target.value)} className="h-8 rounded-sm text-xs" type="number" />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-2">
            <div className="space-y-1.5">
              <Label className="text-xs text-muted-foreground">Mulai Periode *</Label>
              <Input value={form.period_start} onChange={e => {
                  set("period_start", e.target.value);
                  // FIX B12: Auto-fill period_end ke akhir bulan dari period_start
                  if (e.target.value) {
                    const d = new Date(e.target.value);
                    const lastDay = new Date(d.getFullYear(), d.getMonth() + 1, 0);
                    const yy = lastDay.getFullYear();
                    const mm = String(lastDay.getMonth() + 1).padStart(2, "0");
                    const dd = String(lastDay.getDate()).padStart(2, "0");
                    set("period_end", `${yy}-${mm}-${dd}`);
                  }
                }} className="h-8 rounded-sm text-xs" type="date" />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs text-muted-foreground">Akhir Periode *</Label>
              <Input value={form.period_end} onChange={e => set("period_end", e.target.value)} className="h-8 rounded-sm text-xs" type="date" />
            </div>
          </div>
          <div className="space-y-1.5">
            <Label className="text-xs text-muted-foreground">Jatuh Tempo * {selectedCustomer && <span className="text-muted-foreground">(tgl {selectedCustomer.due_day} tiap bulan)</span>}</Label>
            <Input value={form.due_date} onChange={e => set("due_date", e.target.value)} className="h-8 rounded-sm text-xs" type="date" />
          </div>
        </div>
        <div className="flex gap-2 p-4 border-t border-border">
          <Button variant="outline" className="flex-1 rounded-sm text-xs" onClick={onClose}>Batal</Button>
          <Button className="flex-1 rounded-sm text-xs" onClick={submit} disabled={saving}>
            {saving ? "Menyimpan..." : "Buat Invoice"}
          </Button>
        </div>
      </div>
    </div>
  );
}

// â”€â”€ Customers Tab â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

function CustomersTab({ packages, devices, onRefresh, deviceId, isLocked }) {
  const [customers, setCustomers] = useState([]);
  const [loading, setLoading] = useState(false);
  const [search, setSearch] = useState("");
  const [selectedRouter, setSelectedRouter] = useState(deviceId || "");
  const [showForm, setShowForm] = useState(false);
  const [editTarget, setEditTarget] = useState(null);
  const [showImport, setShowImport] = useState(false);
  const [showImportCsv, setShowImportCsv] = useState(false);
  const [selectedIds, setSelectedIds] = useState([]);
  const [showBulkModal, setShowBulkModal] = useState(false);
  const [showBulkDelete, setShowBulkDelete] = useState(false);
  const [bulkDeleting, setBulkDeleting] = useState(false);
  const [editPhone, setEditPhone] = useState({});
  const [savingPhone, setSavingPhone] = useState({});
  const [showPwd, setShowPwd] = useState({});  // { [customerId]: bool }
  const { user } = useAuth();
  const isAdmin = ["administrator", "super_admin", "branch_admin"].includes(user?.role);

  // Sync selectedRouter jika parent mengubah deviceId (RBAC lock)
  useEffect(() => {
    if (deviceId !== undefined) setSelectedRouter(deviceId);
  }, [deviceId]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await api.get("/customers", { params: { search, device_id: selectedRouter } });
      setCustomers(r.data);
      setSelectedIds([]);
    }
    catch { toast.error("Gagal memuat pelanggan"); }
    setLoading(false);
  }, [search, selectedRouter]);

  useEffect(() => { load(); }, [load]);

  const toggleSelectAll = () => {
    if (customers.length === 0) return;
    if (selectedIds.length === customers.length) setSelectedIds([]);
    else setSelectedIds(customers.map(c => c.id));
  };

  const toggleSelect = (id) => {
    setSelectedIds(prev => prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id]);
  };

  const deleteCust = async (id) => {
    if (!window.confirm("Hapus pelanggan ini?")) return;
    try { await api.delete(`/customers/${id}`); toast.success("Dihapus"); load(); }
    catch (e) { toast.error(e.response?.data?.detail || "Gagal"); }
  };

  const savePhone = async (customerId) => {
    const phone = editPhone[customerId];
    if (phone === undefined) return;
    setSavingPhone(s => ({ ...s, [customerId]: true }));
    try {
      await api.put(`/customers/${customerId}`, { phone });
      toast.success("No. WA disimpan");
      setEditPhone(p => { const n = { ...p }; delete n[customerId]; return n; });
      load();
    } catch (e) { toast.error(e.response?.data?.detail || "Gagal simpan"); }
    setSavingPhone(s => ({ ...s, [customerId]: false }));
  };

  const unsubscribeCust = async (c) => {
    const msg = "Berhenti berlangganan untuk \"" + c.name + "\"?\n\nIni akan:\n- Disable user PPPoE di MikroTik\n- Hapus active session (kick)\n- Set status Non-aktif";
    if (!window.confirm(msg)) return;
    try {
      const r = await api.post("/customers/" + c.id + "/unsubscribe");
      toast.success(r.data.message);
      load();
    } catch (e) { toast.error(e.response?.data?.detail || "Gagal unsubscribe"); }
  };

  const bulkDelete = async () => {
    setBulkDeleting(true);
    try {
      const r = await api.post("/customers/bulk-delete", { customer_ids: selectedIds, delete_invoices: true });
      toast.success(r.data.message);
      setSelectedIds([]);
      load();
    } catch (e) { toast.error(e.response?.data?.detail || "Gagal hapus massal"); }
    setBulkDeleting(false);
    setShowBulkDelete(false);
  };

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2 items-center">
        <div className="relative flex-1 min-w-[180px]">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
          <Input value={search} onChange={e => setSearch(e.target.value)} placeholder="Cari nama / username / telepon..."
            className="pl-8 h-8 rounded-sm text-xs" />
        </div>
        <select value={selectedRouter} onChange={e => !isLocked && setSelectedRouter(e.target.value)}
          disabled={isLocked}
          className={`h-8 text-xs rounded-sm border border-border bg-secondary px-2 text-foreground min-w-[140px] ${isLocked ? "opacity-80 cursor-not-allowed" : ""}`}>
          {!isLocked && <option value="">Semua Router</option>}
          {devices?.map(d => <option key={d.id} value={d.id}>{d.name}</option>)}
        </select>
        <Button size="sm" variant="outline" className="rounded-sm h-8 gap-1 text-xs" onClick={load}><RefreshCw className="w-3.5 h-3.5" /></Button>
        {isAdmin && selectedIds.length > 0 && (
          <>
            <Button size="sm" variant="default" className="rounded-sm h-8 gap-1 text-xs bg-blue-600 hover:bg-blue-700 text-white" onClick={() => setShowBulkModal(true)}>
              <Edit2 className="w-3.5 h-3.5" /> Set Paket ({selectedIds.length})
            </Button>
            <Button size="sm" variant="default"
              className="rounded-sm h-8 gap-1 text-xs bg-red-600 hover:bg-red-700 text-white"
              onClick={() => setShowBulkDelete(true)} disabled={bulkDeleting}>
              <Trash2 className="w-3.5 h-3.5" /> Hapus ({selectedIds.length})
            </Button>
          </>
        )}
        {isAdmin && <>
          <Button size="sm" variant="outline" className="rounded-sm h-8 gap-1 text-xs border-green-500/40 text-green-500 hover:bg-green-500/10" onClick={() => setShowImportCsv(true)}>
            <FileDown className="w-3.5 h-3.5" /> Import Excel (CSV)
          </Button>
          <Button size="sm" variant="outline" className="rounded-sm h-8 gap-1 text-xs" onClick={() => setShowImport(true)}>
            <Upload className="w-3.5 h-3.5" /> Import MikroTik
          </Button>
          <Button size="sm" className="rounded-sm h-8 gap-1 text-xs" onClick={() => { setEditTarget(null); setShowForm(true); }}>
            <Plus className="w-3.5 h-3.5" /> Tambah
          </Button>
        </>}
      </div>

      {loading ? (
        <p className="text-muted-foreground text-sm text-center py-8 animate-pulse">Memuat...</p>
      ) : (
        <>
          {/* Desktop Table */}
          <div className="hidden md:block overflow-x-auto">
            <table className="w-full text-left min-w-[800px]">
              <thead>
                <tr className="border-b border-border">
                  <th className="px-3 py-2 w-10">
                    <input type="checkbox" className="rounded border-border bg-secondary/50 accent-blue-500 cursor-pointer"
                      checked={customers.length > 0 && selectedIds.length === customers.length}
                      onChange={toggleSelectAll}
                    />
                  </th>
                  {["ID Pel", "Nama", "No. WA", "Username", "Password", "Router", "Paket", "Tgl", "Status", "Aksi"].map(h => (
                    <th key={h} className="px-3 py-2 text-[10px] text-muted-foreground uppercase tracking-wider font-medium">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {customers.map(c => {
                  const pkg = packages.find(p => p.id === c.package_id);
                  const isSelected = selectedIds.includes(c.id);
                  const dev = devices?.find(d => d.id === c.device_id);
                  return (
                    <tr key={c.id} className={`border-b border-border/30 hover:bg-secondary/20 ${isSelected ? "bg-secondary/10" : ""}`}>
                      <td className="px-3 py-2.5">
                        <input type="checkbox" className="rounded border-border bg-secondary/50 accent-blue-500 cursor-pointer"
                          checked={isSelected}
                          onChange={() => toggleSelect(c.id)}
                        />
                      </td>
                      <td className="px-3 py-2.5">
                        <span className="text-[10px] font-mono text-indigo-400 bg-indigo-500/10 px-1 py-0.5 rounded-sm">{c.client_id || c.id.substring(0, 8)}</span>
                      </td>
                      <td className="px-3 py-2.5">
                        <p className="text-xs font-medium">{c.name}</p>
                      </td>
                      <td className="px-3 py-2.5">
                        {isAdmin ? (
                          <div className="flex items-center gap-1">
                            <input type="text"
                              value={editPhone[c.id] !== undefined ? editPhone[c.id] : (c.phone || "")}
                              onChange={e => setEditPhone(prev => ({ ...prev, [c.id]: e.target.value }))}
                              onKeyDown={e => { if (e.key === "Enter") savePhone(c.id); }}
                              placeholder="08xx..."
                              className="h-6 w-24 text-[10px] rounded-sm border border-border bg-secondary px-1.5 text-foreground font-mono"
                            />
                            {editPhone[c.id] !== undefined && (
                              <button className="h-6 px-1.5 text-[10px] rounded-sm bg-primary text-primary-foreground"
                                onClick={() => savePhone(c.id)} disabled={savingPhone[c.id]}>
                                {savingPhone[c.id] ? "..." : "OK"}
                              </button>
                            )}
                          </div>
                        ) : (
                          <span className="text-[10px] text-muted-foreground font-mono">{c.phone || "â€”"}</span>
                        )}
                      </td>
                      <td className="px-3 py-2.5 text-xs font-mono">{c.username}</td>
                      <td className="px-3 py-2.5">
                        {c.password ? (
                          <div className="flex items-center gap-1">
                            <span className="text-[10px] font-mono text-muted-foreground">
                            {showPwd[c.id] ? c.password : "●●●●●●●●"}
                            </span>
                            <button
                              onClick={() => setShowPwd(p => ({ ...p, [c.id]: !p[c.id] }))}
                              className="text-muted-foreground hover:text-foreground transition-colors"
                              title={showPwd[c.id] ? "Sembunyikan" : "Tampilkan"}
                            >
                              {showPwd[c.id]
                                ? <EyeOff className="w-3 h-3" />
                                : <Eye className="w-3 h-3" />}
                            </button>
                          </div>
                        ) : (
                          <span className="text-[10px] text-muted-foreground/40">â€”</span>
                        )}
                      </td>
                      <td className="px-3 py-2.5 text-xs text-muted-foreground">{dev?.name || "â€”"}</td>
                      <td className="px-3 py-2.5 text-xs text-muted-foreground">{pkg?.name || <span className="text-amber-400/80 text-[10px]">Belum ada paket</span>}</td>
                      <td className="px-3 py-2.5 text-[10px] text-muted-foreground">Tgl {c.due_day}</td>
                      <td className="px-3 py-2.5">
                        <span className={`text-[10px] px-1.5 py-0.5 rounded-sm border ${c.active ? "border-green-500/30 text-green-400" : "border-red-500/30 text-red-400"}`}>
                          {c.active ? "Aktif" : "Non-aktif"}
                        </span>
                      </td>
                      <td className="px-3 py-2.5">
                        {isAdmin && (
                          <div className="flex gap-1">
                            <Button size="icon" variant="ghost" className="h-6 w-6" onClick={() => { setEditTarget(c); setShowForm(true); }}>
                              <Edit2 className="w-3 h-3" />
                            </Button>
                            <Button size="icon" variant="ghost"
                              className="h-6 w-6 text-orange-400 hover:text-orange-300 hover:bg-orange-500/10"
                              title="Berhenti Berlangganan"
                              onClick={() => unsubscribeCust(c)}>
                              <UserX className="w-3 h-3" />
                            </Button>
                            <Button size="icon" variant="ghost" className="h-6 w-6" onClick={() => deleteCust(c.id)}>
                              <Trash2 className="w-3 h-3 text-destructive" />
                            </Button>
                          </div>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {/* Mobile Cards */}
          <div className="md:hidden space-y-3 mt-4">
            <div className="flex items-center gap-2 mb-2 px-1">
              <input type="checkbox" className="rounded border-border bg-secondary/50 accent-blue-500 cursor-pointer w-4 h-4"
                checked={customers.length > 0 && selectedIds.length === customers.length}
                onChange={toggleSelectAll}
              />
              <span className="text-xs text-muted-foreground">Pilih Semua ({selectedIds.length} terpilih)</span>
            </div>
            {customers.map(c => {
              const pkg = packages.find(p => p.id === c.package_id);
              const isSelected = selectedIds.includes(c.id);
              const dev = devices?.find(d => d.id === c.device_id);
              return (
                <div key={c.id} className={`bg-card border p-3 rounded-lg shadow-sm space-y-2 relative transition-colors ${isSelected ? "border-blue-500/50 bg-blue-500/5" : "border-border"}`} onClick={() => toggleSelect(c.id)}>
                   <div className="flex justify-between items-start">
                      <div className="flex gap-2 items-start">
                         <input type="checkbox" className="mt-1 rounded border-border bg-secondary/50 accent-blue-500 cursor-pointer pointer-events-none"
                           checked={isSelected} readOnly
                         />
                         <div>
                           <span className="text-[10px] font-mono text-indigo-400 mb-0.5">{c.client_id || c.id.substring(0, 8)}</span>
                           <p className="font-bold text-sm leading-tight text-white">{c.name}</p>
                           <p className="text-xs text-muted-foreground font-mono">{c.username}</p>
                           <p className="text-[10px] text-muted-foreground mt-0.5">{c.phone || "Tidak ada HP"}</p>
                         </div>
                      </div>
                      <div className="flex flex-col items-end gap-1">
                        <span className={`text-[9px] font-bold px-1.5 py-0.5 rounded border ${c.active ? "border-green-500/30 text-green-400 bg-green-500/10" : "border-red-500/30 text-red-400 bg-red-500/10"}`}>
                          {c.active ? "AKTIF" : "NON-AKTIF"}
                        </span>
                      </div>
                   </div>
                   <div className="grid grid-cols-2 gap-2 text-xs pt-2 border-t border-border/50">
                      <div><span className="text-muted-foreground text-[10px] block">Router</span> {dev?.name || "â€”"}</div>
                      <div><span className="text-muted-foreground text-[10px] block">Jatuh Tempo</span> Tgl {c.due_day}</div>
                   </div>
                   <div className="text-xs pb-1">
                      <span className="text-muted-foreground text-[10px] block">Paket</span> 
                      {pkg?.name || <span className="text-amber-400">Belum ada paket</span>}
                   </div>
                   {isAdmin && (
                      <div className="flex gap-2 pt-2 border-t border-border/50" onClick={e => e.stopPropagation()}>
                         <Button size="sm" variant="outline" className="flex-1 h-7 text-xs" onClick={() => { setEditTarget(c); setShowForm(true); }}>
                           <Edit2 className="w-3 h-3 mr-1" /> Edit
                         </Button>
                         <Button size="sm" variant="outline" className="flex-1 h-7 text-xs text-red-400 hover:text-red-300 hover:bg-red-500/10" onClick={() => deleteCust(c.id)}>
                           <Trash2 className="w-3 h-3 mr-1" /> Hapus
                         </Button>
                      </div>
                   )}
                </div>
              );
            })}
          </div>

          <p className="text-[10px] text-muted-foreground mt-3 text-right font-mono">{customers.length} pelanggan</p>
        </>
      )}

      {showForm && <CustomerForm packages={packages} initial={editTarget}
        onClose={() => setShowForm(false)} onSaved={() => { setShowForm(false); load(); onRefresh?.(); }} />}
      {showImport && <ImportModal onClose={() => setShowImport(false)} onImported={() => { setShowImport(false); load(); }} />}
      {showImportCsv && <ImportCsvModal onClose={() => setShowImportCsv(false)} onImported={() => { setShowImportCsv(false); load(); }} />}
      {showBulkModal && <BulkPackageModal packages={packages} selectedIds={selectedIds}
        onClose={() => setShowBulkModal(false)} onSaved={() => { setShowBulkModal(false); load(); onRefresh?.(); setSelectedIds([]); }} />}
      {showBulkDelete && (
        <div className="fixed inset-0 z-50 bg-black/70 flex items-center justify-center p-4">
          <div className="bg-card border border-red-500/40 rounded-sm w-full max-w-sm shadow-2xl">
            <div className="p-4 border-b border-red-500/20">
              <h3 className="font-semibold text-red-400">Hapus {selectedIds.length} Pelanggan?</h3>
            </div>
            <div className="p-4 text-sm text-muted-foreground">
              Semua data pelanggan yang dipilih beserta <strong className="text-foreground">seluruh invoice tagihan</strong> mereka akan dihapus permanen. Tidak dapat dibatalkan!
            </div>
            <div className="flex gap-2 p-4 border-t border-border">
              <button className="flex-1 h-8 rounded-sm border border-border text-xs hover:bg-secondary"
                onClick={() => setShowBulkDelete(false)} disabled={bulkDeleting}>Batal</button>
              <button className="flex-1 h-8 rounded-sm bg-red-600 hover:bg-red-700 text-white text-xs font-medium"
                onClick={bulkDelete} disabled={bulkDeleting}>
                {bulkDeleting ? "Menghapus..." : "Ya, Hapus Semua"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// â”€â”€ Bulk Package Modal â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

function BulkPackageModal({ packages, selectedIds, onClose, onSaved }) {
  const [targetPackageId, setTargetPackageId] = useState("");
  const [saving, setSaving] = useState(false);

  const handleSave = async () => {
    if (!targetPackageId) return toast.error("Pilih paket terlebih dahulu");
    setSaving(true);
    try {
      await api.put("/customers/bulk-update", { customer_ids: selectedIds, package_id: targetPackageId });
      toast.success("Berhasil mengubah paket secara massal");
      onSaved();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Gagal mengubah paket");
    }
    setSaving(false);
  };

  return (
    <div className="fixed inset-0 z-50 bg-background/80 backdrop-blur-sm flex items-center justify-center p-4">
      <div className="bg-card w-full max-w-sm rounded-lg shadow-xl border border-border p-5 relative">
        <Button variant="ghost" size="icon" className="absolute right-3 top-3 h-6 w-6" onClick={onClose} disabled={saving}>
          <X className="w-4 h-4" />
        </Button>
        <h3 className="font-semibold mb-4">Set Paket Massal ({selectedIds.length} Pelanggan)</h3>
        <div className="space-y-4 max-h-[85vh] overflow-y-auto pr-1">
          <div className="space-y-1.5">
            <Label className="text-xs">Pilih Paket Layanan</Label>
            <select value={targetPackageId} onChange={e => setTargetPackageId(e.target.value)}
              className="w-full text-xs rounded border border-border bg-secondary p-2 text-foreground" disabled={saving}>
              <option value="">-- Pilih Paket --</option>
              {packages.map(p => (
                <option key={p.id} value={p.id}>{p.name} - Rp {p.price.toLocaleString("id-ID")}</option>
              ))}
            </select>
          </div>
          <div className="flex gap-2 justify-end pt-2">
            <Button variant="outline" size="sm" onClick={onClose} disabled={saving}>Batal</Button>
            <Button size="sm" onClick={handleSave} disabled={saving}>
              {saving ? "Menyimpan..." : "Simpan Perubahan"}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}

// â”€â”€ Customer Form Modal â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

function CustomerForm({ packages, initial, onClose, onSaved }) {
  const [form, setForm] = useState({
    name: initial?.name || "", 
    phone: initial?.phone || "", 
    address: initial?.address || "",
    service_type: "pppoe", 
    username: initial?.username || "",
    device_id: initial?.device_id || "", 
    package_id: initial?.package_id || "",
    due_day: initial?.due_day || 10, 
    active: initial?.active ?? true,
    pppoe_password: "", 
    installation_fee: "", 
    billing_type: initial?.billing_type || "postpaid", 
    payment_status: "belum_bayar",
    payment_method: "transfer",
    auth_method: initial?.auth_method || "radius",
  });
  const [devices, setDevices] = useState([]);
  const [saving, setSaving] = useState(false);

  useEffect(() => { 
    api.get("/devices")
      .then(r => setDevices(Array.isArray(r.data) ? r.data : []))
      .catch((err) => { 
        console.error("Failed to load devices:", err);
        setDevices([]);
      }); 
  }, []);

  const set = (k, v) => setForm(f => ({ ...f, [k]: v }));
  const isEdit = !!initial;

  // Reset package_id saat device berubah (agar paket yang tampil sesuai router)
  const handleDeviceChange = (deviceId) => {
    setForm(f => ({ ...f, device_id: deviceId, package_id: "" }));
  };

  const genPass = () => set("pppoe_password", Math.random().toString(36).slice(-8) + Math.random().toString(36).slice(-4));

  const handleNameChange = (val) => {
    set("name", val);
    if (!isEdit && !form.username) {
      set("username", val.toLowerCase().replace(/[^a-z0-9]/g, ""));
    }
  };

  const submit = async () => {
    if (!form.name || !form.username || (!isEdit && !form.device_id)) { 
      toast.error("Nama, username, dan device wajib"); return; 
    }

    if (!isEdit) {
      const selectedDev = devices.find(d => d.id === form.device_id);
      if (selectedDev && !selectedDev.ip_address) {
        toast.error("Router MikroTik yang dipilih tidak memiliki alamat IP/Host. Silakan lengkapi data router di menu Devices.");
        return;
      }
    }
    setSaving(true);
    try {
      if (isEdit) { 
        const editPayload = { 
          name: form.name, phone: form.phone, address: form.address, 
          package_id: form.package_id, due_day: Number(form.due_day), active: form.active,
          auth_method: form.auth_method
        };
        if (form.pppoe_password) editPayload.password = form.pppoe_password;
        await api.put(`/customers/${initial.id}`, editPayload); 
      }
      else { 
        if (!form.pppoe_password) {
          toast.error("Password PPPoE wajib diisi"); setSaving(false); return;
        }
        await api.post("/customers", { 
          ...form, 
          password: form.pppoe_password,
          due_day: Number(form.due_day), 
          installation_fee: Number(form.installation_fee) || 0 
        }); 
      }
      toast.success(isEdit ? "Pelanggan diupdate" : "Pelanggan baru dan Akun MikroTik berhasil dibuat");
      onSaved();
    } catch (e) { 
      const detail = e.response?.data?.detail || e.response?.data?.message;
      toast.error(typeof detail === "string" ? detail : "Gagal menyimpan. Pastikan MikroTik online dan API aktif."); 
    }
    setSaving(false);
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/70 flex items-center justify-center p-4">
      <div className="bg-card border border-border rounded-sm w-full max-w-lg shadow-2xl flex flex-col max-h-[95vh]">
        <div className="flex items-center justify-between p-4 border-b border-border shrink-0">
          <div>
            <h2 className="text-sm font-bold flex items-center gap-2">
              <Plus className="w-4 h-4 text-primary" />
              {isEdit ? "Edit Pelanggan PPPoE" : "Registrasi Pelanggan PPPoE Baru"}
            </h2>
            {!isEdit && <p className="text-xs text-muted-foreground mt-1">Sistem otomatis membuatkan Serial PPPoE di MikroTik dan merilis Invoice pertama.</p>}
          </div>
          <Button size="icon" variant="ghost" className="h-7 w-7" onClick={onClose}><X className="w-4 h-4" /></Button>
        </div>
        <div className="p-0 overflow-y-auto custom-scrollbar flex-1 bg-secondary/5">
          <div className="p-4 space-y-6">
            {/* Section 1: Identitas */}
            <div className="space-y-4">
              <div className="flex items-center gap-2 pb-1 border-b border-border/50">
                <div className="p-1 rounded-sm bg-primary/10">
                  <Users className="w-3.5 h-3.5 text-primary" />
                </div>
                <h3 className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground">Identitas Pelanggan</h3>
              </div>
              
              <div className="grid grid-cols-1 gap-4">
                <div className="space-y-1.5">
                  <Label className="text-xs font-medium flex items-center gap-1.5">
                    Nama Pelanggan <span className="text-red-500">*</span>
                  </Label>
                  <Input 
                    value={form.name} 
                    onChange={e => handleNameChange(e.target.value)} 
                    placeholder="Contoh: Budi Santoso" 
                    className="h-9 rounded-sm text-xs bg-background border-border/50 focus:border-primary/50" 
                  />
                </div>
                
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div className="space-y-1.5">
                    <Label className="text-xs font-medium flex items-center gap-1.5">
                      <PhoneCall className="w-3 h-3 text-muted-foreground" /> No. Telepon / WhatsApp
                    </Label>
                    <Input 
                      value={form.phone} 
                      onChange={e => set("phone", e.target.value)} 
                      type="tel" 
                      placeholder="0812xxxx" 
                      className="h-9 rounded-sm text-xs bg-background border-border/50" 
                    />
                  </div>
                  <div className="space-y-1.5">
                    <Label className="text-xs font-medium flex items-center gap-1.5">
                      <MapPin className="w-3 h-3 text-muted-foreground" /> Alamat Lengkap
                    </Label>
                    <Input 
                      value={form.address} 
                      onChange={e => set("address", e.target.value)} 
                      placeholder="Jl. Merdeka No. 10" 
                      className="h-9 rounded-sm text-xs bg-background border-border/50" 
                    />
                  </div>
                </div>
              </div>
            </div>

            {/* Section 2: Koneksi */}
            <div className="space-y-4">
              <div className="flex items-center gap-2 pb-1 border-b border-border/50">
                <div className="p-1 rounded-sm bg-blue-500/10">
                  <Wifi className="w-3.5 h-3.5 text-blue-400" />
                </div>
                <h3 className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground">Konfigurasi Koneksi</h3>
              </div>

              <div className="space-y-4">
                {!isEdit && (
                  <div className="space-y-1.5">
                    <Label className="text-xs font-bold text-primary flex items-center gap-1.5">
                      Target Router MikroTik <span className="text-red-500">*</span>
                    </Label>
                    <select 
                      value={form.device_id} 
                      onChange={e => handleDeviceChange(e.target.value)}
                      className="w-full h-9 text-xs rounded-sm border border-border/50 bg-background px-3 text-foreground font-medium focus:ring-1 focus:ring-primary/30 outline-none transition-all">
                      <option value="">Pilih Router MikroTik...</option>
                      {devices.map(d => (
                        <option key={d.id} value={d.id} disabled={!d.ip_address} className={!d.ip_address ? "text-red-400" : ""}>
                          {d.name} {d.ip_address ? `(${d.ip_address})` : "[Ã¢Å¡Â Ã¯Â¸Â TANPA IP/HOST]"}
                        </option>
                      ))}
                    </select>
                  </div>
                )}

                {/* Username & Password */}
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div className="space-y-1.5">
                    <Label className="text-xs font-medium">Username PPPoE <span className="text-red-500">*</span></Label>
                    <Input 
                      value={form.username} 
                      onChange={e => set("username", e.target.value)} 
                      placeholder="budi_123" 
                      className="h-9 rounded-sm text-xs bg-background border-border/50" 
                    />
                  </div>

                  <div className="space-y-1.5">
                    <Label className="text-xs font-medium">
                      {isEdit ? "Password Baru (opsional)" : <>Password PPPoE <span className="text-red-500">*</span></>}
                    </Label>
                    <div className="flex gap-1.5">
                      <Input
                        value={form.pppoe_password}
                        onChange={e => set("pppoe_password", e.target.value)}
                        type="text"
                        placeholder={isEdit ? "Kosongkan jika tidak diganti" : "Password..."}
                        className="h-9 rounded-sm text-xs flex-1 bg-background border-border/50 font-mono"
                      />
                      <Button variant="secondary" size="icon" onClick={genPass} className="h-9 w-9 shrink-0 bg-blue-500/10 hover:bg-blue-500/20 text-blue-400 border border-blue-500/20" title="Generate password acak">
                        <RefreshCw className="w-3.5 h-3.5"/>
                      </Button>
                    </div>
                    {isEdit && form.pppoe_password && (
                      <p className="text-[10px] text-amber-400 leading-relaxed">
                        âš  Password baru akan disimpan ke database (RADIUS) dan MikroTik (jika local mode).
                      </p>
                    )}
                  </div>
                </div>

                <div className="sm:col-span-2 space-y-1.5 p-3 rounded-sm border border-border/50 bg-secondary/10 flex items-start gap-2 mt-1">
                  <input
                    type="checkbox"
                    id="opt_auth_method"
                    checked={form.auth_method === "radius"}
                    onChange={e => set("auth_method", e.target.checked ? "radius" : "local")}
                    className="mt-1 w-4 h-4 rounded border-border text-primary cursor-pointer"
                  />
                  <div>
                    <Label htmlFor="opt_auth_method" className="text-xs font-bold cursor-pointer inline-block">Gunakan RADIUS Server (Rekomendasi)</Label>
                    <p className="text-[10px] text-muted-foreground mt-0.5 leading-relaxed">
                      Jika dicentang, authentikasi dan pemutusan (isolir) sepenuhnya dikelola oleh RADIUS server terpusat. PPPoE Secret di router MikroTik tidak akan dibuat agar resource lebih ringan.
                    </p>
                  </div>
                </div>
              </div>
            </div>

            {/* Section 3: Billing */}
            <div className="space-y-4">
              <div className="flex items-center gap-2 pb-1 border-b border-border/50">
                <div className="p-1 rounded-sm bg-emerald-500/10">
                  <RpIcon className="w-3.5 h-3.5 text-emerald-400" />
                </div>
                <h3 className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground">Paket & Tagihan</h3>
              </div>

              <div className="grid grid-cols-1 gap-4">
                <div className="space-y-1.5">
                  <Label className="text-xs font-medium">Pilih Paket Berlangganan</Label>
                  {(() => {
                    // Filter: hanya tampilkan paket PPPoE dari router yang dipilih
                    const filteredPkgs = packages.filter(p => {
                      const isPppoe = p.service_type === "pppoe" || p.type === "pppoe";
                      // jika belum milih router, tampilkan semua paket PPPoE
                      if (!form.device_id) return isPppoe; 
                      return isPppoe && (p.device_id === form.device_id || p.source_device_id === form.device_id);
                    });

                    return (
                      <>
                        <select 
                          value={form.package_id} 
                          onChange={e => set("package_id", e.target.value)}
                          className="w-full h-9 text-xs rounded-sm border border-border/50 bg-background px-3 text-emerald-500 font-bold focus:ring-1 focus:ring-emerald-500/30 outline-none transition-all">
                          <option value="">— Belum ada paket dipilih —</option>
                          {filteredPkgs.map(p => (
                            <option key={p.id} value={p.id} className="text-foreground">{p.name} ({Rp(p.price)})</option>
                          ))}
                        </select>
                        {form.device_id && filteredPkgs.length === 0 && (
                           <p className="text-[10px] text-amber-500 mt-1 font-bold">
                             ⚠️ Router ini belum memiliki paket. Buat atau Sync Paket terlebih dahulu!
                           </p>
                        )}
                      </>
                    );
                  })()}
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div className="space-y-1.5">
                    <Label className="text-xs font-medium">Siklus Billing</Label>
                    <select 
                      value={form.billing_type} 
                      onChange={e => set("billing_type", e.target.value)} 
                      disabled={isEdit}
                      className="w-full h-9 text-xs rounded-sm border border-border/50 bg-background px-3 text-foreground focus:ring-1 focus:ring-primary/30 outline-none">
                      <option value="postpaid">Pascabayar (Pakai dulu)</option>
                      <option value="prepaid">Prabayar (Bayar dulu)</option>
                    </select>
                  </div>
                  <div className="space-y-1.5">
                    <Label className="text-xs font-medium flex items-center gap-1.5">
                      <CalendarClock className="w-3 h-3 text-muted-foreground" /> Tgl Jatuh Tempo
                    </Label>
                    <Input 
                      value={form.due_day} 
                      onChange={e => set("due_day", e.target.value)} 
                      type="number" 
                      min="1" 
                      max="28" 
                      className="h-9 rounded-sm text-xs bg-background border-border/50" 
                    />
                  </div>
                </div>

                {!isEdit && (
                  <div className="p-3 rounded-sm border border-border bg-card/50 space-y-4">
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                      <div className="space-y-1.5">
                        <Label className="text-[10px] uppercase font-bold text-muted-foreground">Biaya Pasang</Label>
                        <Input 
                          value={form.installation_fee} 
                          onChange={e => set("installation_fee", e.target.value)} 
                          type="number" 
                          placeholder="Rp 0" 
                          className="h-8 rounded-sm text-xs bg-background" 
                        />
                      </div>
                      <div className="space-y-1.5">
                        <Label className="text-[10px] uppercase font-bold text-muted-foreground">Status Awal</Label>
                        <select 
                          value={form.payment_status} 
                          onChange={e => set("payment_status", e.target.value)}
                          className={`w-full h-8 text-[11px] rounded-sm border px-2 font-bold focus:outline-none ${
                            form.payment_status === 'sudah_bayar' ? 'bg-green-500/10 text-green-500 border-green-500/30' : 'bg-amber-500/10 text-amber-500 border-amber-500/30'
                          }`}>
                          <option value="belum_bayar">BELUM LUNAS</option>
                          <option value="sudah_bayar">SUDAH LUNAS</option>
                        </select>
                      </div>
                    </div>
                    
                    <div className="space-y-1.5">
                      <Label className="text-[10px] uppercase font-bold text-muted-foreground flex items-center gap-1.5">
                        <CreditCard className="w-3 h-3" /> Metode Pembayaran Awal
                      </Label>
                      <select 
                        value={form.payment_method} 
                        onChange={e => set("payment_method", e.target.value)}
                        className="w-full h-8 text-[11px] rounded-sm border border-border bg-background px-2 text-foreground font-semibold">
                        <option value="transfer">Transfer Bank (Tambah Kode Unik)</option>
                        <option value="cash">Tunai / Cash (Tanpa Kode Unik)</option>
                      </select>
                    </div>
                  </div>
                )}
              </div>
            </div>

            {isEdit && (
              <label className="flex items-center gap-2 cursor-pointer p-3 bg-primary/5 border border-primary/10 rounded-sm group">
                <div className={`p-1 rounded-full flex items-center justify-center transition-colors ${form.active ? 'bg-primary text-white' : 'bg-muted text-muted-foreground'}`}>
                   <CheckCircle2 className="w-3 h-3" />
                </div>
                <input type="checkbox" checked={form.active} onChange={e => set("active", e.target.checked)} className="hidden" />
                <span className="text-xs font-bold text-primary uppercase tracking-tight">Akun Berstatus Aktif</span>
              </label>
            )}

          </div>
        </div>
        <div className="flex gap-2 p-4 border-t border-border bg-muted/10 shrink-0">
          <Button variant="outline" className="flex-1 rounded-sm text-xs font-semibold" onClick={onClose} disabled={saving}>Batalkan</Button>
          <Button className="flex-1 rounded-sm text-xs font-semibold gap-2" onClick={submit} disabled={saving}>
            {saving ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" />}
            {saving ? "Menyimpan ke MikroTik..." : isEdit ? "Update Perubahan" : "Simpan & Buat Otomatis"}
          </Button>
        </div>
      </div>
    </div>
  );
}

// â”€â”€ Import Modal â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

function ImportModal({ onClose, onImported }) {
  const [devices, setDevices] = useState([]);
  const [deviceId, setDeviceId] = useState("");
  const [type, setType] = useState("pppoe");
  const [dueDay, setDueDay] = useState(10);
  const [loading, setLoading] = useState(false);
  const [checking, setChecking] = useState(false);
  const [result, setResult] = useState(null);
  const [packageCheck, setPackageCheck] = useState(null); // { ok: bool, zeroPricePackages: [] }

  useEffect(() => { api.get("/devices").then(r => setDevices(r.data)).catch(() => { }); }, []);

  // Pre-check harga paket setiap kali device dipilih
  const handleDeviceChange = async (newDeviceId) => {
    setDeviceId(newDeviceId);
    setPackageCheck(null);
    if (!newDeviceId) return;
    setChecking(true);
    try {
      const r = await api.get("/billing/packages");
      const allPkgs = r.data || [];
      // Ambil paket PPPoE dari device yang dipilih
      const devicePkgs = allPkgs.filter(p =>
        p.source_device_id === newDeviceId &&
        (p.service_type === "pppoe" || p.type === "pppoe" || p.service_type === "both" || p.type === "both")
      );
      const zeroPricePkgs = devicePkgs.filter(p => !p.price || p.price === 0);

      if (devicePkgs.length === 0) {
        setPackageCheck({ ok: false, noPackages: true, zeroPricePackages: [] });
      } else if (zeroPricePkgs.length > 0) {
        setPackageCheck({ ok: false, noPackages: false, zeroPricePackages: zeroPricePkgs });
      } else {
        setPackageCheck({ ok: true, noPackages: false, zeroPricePackages: [], totalPackages: devicePkgs.length });
      }
    } catch (e) {
      setPackageCheck(null);
    }
    setChecking(false);
  };

  const canImport = packageCheck?.ok === true && !loading;

  const doImport = async () => {
    if (!deviceId) { toast.error("Pilih device dahulu"); return; }
    if (!canImport) { toast.error("Selesaikan validasi paket terlebih dahulu"); return; }
    setLoading(true);
    try {
      const r = await api.post(`/customers/import/${type}`, null, { params: { device_id: deviceId, due_day: dueDay } });
      setResult(r.data);
      toast.success(r.data.message);
    } catch (e) { toast.error(e.response?.data?.detail || "Import gagal"); }
    setLoading(false);
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/70 flex items-center justify-center p-4">
      <div className="bg-card border border-border rounded-sm w-full max-w-sm shadow-2xl">
        <div className="flex items-center justify-between p-4 border-b border-border">
          <h3 className="font-semibold">Import dari MikroTik</h3>
          <Button size="icon" variant="ghost" className="h-7 w-7" onClick={onClose}><X className="w-4 h-4" /></Button>
        </div>
        <div className="p-4 space-y-3 max-h-[85vh] overflow-y-auto">
          <div className="space-y-1.5">
            <Label className="text-xs text-muted-foreground">Device MikroTik</Label>
            <select value={deviceId} onChange={e => handleDeviceChange(e.target.value)}
              className="w-full h-8 text-xs rounded-sm border border-border bg-secondary px-2 text-foreground">
              <option value="">Pilih device...</option>
              {devices.map(d => <option key={d.id} value={d.id}>{d.name}</option>)}
            </select>
          </div>

          {/* Validasi harga paket */}
          {checking && (
            <div className="flex items-center gap-2 p-2 bg-secondary/40 rounded-sm text-xs text-muted-foreground">
              <RefreshCw className="w-3 h-3 animate-spin" /> Memeriksa paket...
            </div>
          )}
          {packageCheck && !checking && (
            <>
              {packageCheck.ok && (
                <div className="p-2.5 bg-green-500/10 border border-green-500/20 rounded-sm">
                  <p className="text-xs text-green-400 flex items-center gap-1.5">
                    âœ“ Semua {packageCheck.totalPackages} paket sudah memiliki harga â€” import siap dilakukan
                  </p>
                </div>
              )}
              {packageCheck.noPackages && (
                <div className="p-2.5 bg-amber-500/10 border border-amber-500/20 rounded-sm space-y-1">
                  <p className="text-xs font-semibold text-amber-400">âš  Device belum memiliki paket ter-sync</p>
                  <p className="text-[10px] text-muted-foreground">Lakukan Sync Profile dari tab Paket terlebih dahulu sebelum import pelanggan.</p>
                </div>
              )}
              {!packageCheck.ok && !packageCheck.noPackages && packageCheck.zeroPricePackages.length > 0 && (
                <div className="p-2.5 bg-red-500/10 border border-red-500/20 rounded-sm space-y-2">
                  <p className="text-xs font-semibold text-red-400">
                    âœ— Import diblokir â€” {packageCheck.zeroPricePackages.length} paket belum ada harga
                  </p>
                  <p className="text-[10px] text-muted-foreground mb-1">Isi harga paket berikut di <b>tab Paket</b> dahulu:</p>
                  <div className="space-y-1 max-h-28 overflow-y-auto">
                    {packageCheck.zeroPricePackages.map(p => (
                      <div key={p.id} className="flex items-center justify-between text-[10px] bg-secondary/40 px-2 py-1 rounded-sm">
                        <span className="font-mono">{p.name}</span>
                        <span className="text-amber-400">Rp 0</span>
                      </div>
                    ))}
                  </div>
                  <p className="text-[10px] text-red-400/70 italic">Tutup dialog ini â†’ buka Tab Paket â†’ isi harga â†’ buka kembali dialog ini</p>
                </div>
              )}
            </>
          )}

          <div className="space-y-1.5">
            <Label className="text-xs text-muted-foreground">Default Jatuh Tempo</Label>
            <Input value={dueDay} onChange={e => setDueDay(e.target.value)} type="number" min="1" max="28" className="h-8 rounded-sm text-xs" />
          </div>
          {result && (
            <div className="p-2 bg-green-500/10 border border-green-500/20 rounded-sm text-xs text-green-300">
              âœ“ {result.message}
            </div>
          )}
        </div>
        <div className="flex gap-2 p-4 border-t border-border">
          <Button variant="outline" className="flex-1 rounded-sm text-xs" onClick={result ? onImported : onClose}>{result ? "Selesai" : "Batal"}</Button>
          {!result && (
            <Button
              className={`flex-1 rounded-sm text-xs gap-1 ${!canImport ? "opacity-50 cursor-not-allowed" : ""}`}
              onClick={doImport}
              disabled={!canImport}
            >
              <Upload className="w-3.5 h-3.5" />{loading ? "Mengimport..." : "Import"}
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}


// â”€â”€ Bulk Reminder Modal (WA Massal) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

function BulkReminderModal({ invoices, onClose }) {
  const [sending, setSending] = useState(false);
  const [progress, setProgress] = useState(0);
  const [done, setDone] = useState(false);

  const sendAll = async () => {
    setSending(true);
    try {
      const ids = invoices.map(i => i.id);
      const r = await api.post("/billing/invoices/bulk-reminder", { invoice_ids: ids });
      toast.success(r.data.message);
      setDone(true);
      if (onClose) setTimeout(onClose, 2500); // Tutup otomatis 2.5s jika sukses
    } catch (e) {
      toast.error(e.response?.data?.detail || "Gagal mengirim request");
    }
    setSending(false);
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/70 flex items-center justify-center p-4">
      <div className="bg-card border border-border rounded-sm w-full max-w-md shadow-2xl">
        <div className="flex items-center justify-between p-4 border-b border-border">
          <h3 className="font-semibold flex items-center gap-2">
            <Send className="w-4 h-4 text-green-400" /> Reminder Massal WhatsApp
          </h3>
          <Button size="icon" variant="ghost" className="h-7 w-7" onClick={onClose}><X className="w-4 h-4" /></Button>
        </div>
        <div className="p-4 space-y-3">
          <p className="text-sm text-muted-foreground">
            Akan mengirim pesan tagihan ke <strong className="text-foreground">{invoices.length} pelanggan</strong> yang belum bayar dan memiliki nomor telepon.
          </p>
          <div className="bg-blue-500/10 border border-blue-500/20 rounded-sm p-3 text-xs text-blue-400">
            â„¹ï¸ Proses pengiriman akan berjalan bertahap secara otomatis di server (*Background Task*). Anda bebas menutup modal/tab ini setelah menekan "Kirim Semua".
          </div>
          <div className="max-h-48 overflow-y-auto space-y-1.5 border border-border rounded-sm p-2">
            {invoices.map((inv, i) => (
              <div key={inv.id} className={`flex items-center justify-between text-xs p-1.5 rounded-sm ${i < progress ? "bg-green-500/10 text-green-400" : "text-muted-foreground"
                }`}>
                <span>{i < progress ? "(v)" : `${i + 1}.`} {inv.customer_name}</span>
                <span className="font-mono">{Rp(inv.total)}</span>
              </div>
            ))}
          </div>
          {sending && (
            <div className="p-2 bg-secondary/50 border border-border rounded-sm text-xs text-muted-foreground text-center animate-pulse">
              Memproses pengiriman ke antrean server...
            </div>
          )}
          {done && (
            <div className="p-2 bg-green-500/10 border border-green-500/20 rounded-sm text-xs text-green-400 text-center">
              (v) Selesai! Reminder massal masuk ke proses background.
            </div>
          )}
        </div>
        <div className="flex gap-2 p-4 border-t border-border">
          <Button variant="outline" className="flex-1 rounded-sm text-xs" onClick={onClose}>
            {done ? "Tutup" : "Batal"}
          </Button>
          {!done && (
            <Button className="flex-1 rounded-sm text-xs gap-1" onClick={sendAll} disabled={sending}>
              <Send className="w-3.5 h-3.5" />
              {sending ? `Mengirim ${progress}/${invoices.length}...` : "Kirim Semua"}
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}

// â”€â”€ Settings Tab â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

function SettingsTab() {
  const [settings, setSettings] = useState({
    wa_gateway_type: "fonnte",
    wa_api_url: "https://api.fonnte.com/send",
    wa_token: "",
    wa_delay_ms: 10000,
    wa_template_unpaid: "",
    wa_template_paid: "",
    wa_template_h1: "",
    wa_template_isolir: "",
    fcm_template_h3: "",
    fcm_template_h2: "",
    fcm_template_h1: "",
    fcm_template_due: "",
    fcm_template_overdue: "",
    fcm_template_paid: "",
    fcm_template_network_error: "",
    auto_isolir_enabled: false,
    auto_isolir_method: "whatsapp",
    auto_isolir_time: "00:05",
    auto_isolir_grace_days: 0,
    n8n_webhook_url: "",
    moota_webhook_secret: "",
    payment_gateway_enabled: false,
    default_payment_provider: "xendit",
    xendit_secret_key: "",
    xendit_webhook_token: "",
    xendit_va_bank: "BNI",
    xendit_enabled: false,
    bca_client_id: "",
    bca_client_secret: "",
    bca_company_code: "",
    bca_api_key: "",
    bca_api_secret: "",
    bca_enabled: false,
    bri_client_id: "",
    bri_client_secret: "",
    bri_institution_code: "",
    bri_enabled: false,
  });
  
  const [pppoeSettings, setPppoeSettings] = useState({
    pool_name: "pppoe-pool",
    pool_ranges: "10.20.30.2-10.20.30.254",
    gateway_ip: "10.20.30.1",
    dns_servers: "8.8.8.8,1.1.1.1",
    profile_name: "default"
  });
  
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [savingPppoe, setSavingPppoe] = useState(false);

  useEffect(() => {
    setLoading(true);
    Promise.all([
      api.get("/billing/settings").then(r => setSettings(p => ({ ...p, ...r.data }))),
      api.get("/pppoe-settings").then(r => setPppoeSettings(p => ({ ...p, ...r.data })))
    ]).catch(() => toast.error("Gagal memuat pengaturan")).finally(() => setLoading(false));
  }, []);

  const handleSave = async () => {
    setSaving(true);
    try {
      await api.put("/billing/settings", settings);
      toast.success("Pengaturan WhatsApp tersimpan!");
    } catch {
      toast.error("Gagal menyimpan pengaturan");
    }
    setSaving(false);
  };

  const handleSavePppoe = async () => {
    setSavingPppoe(true);
    try {
      const r = await api.post("/pppoe-setup-pool", pppoeSettings);
      toast.success(r.data.message);
    } catch (e) {
      toast.error(e.response?.data?.detail || "Gagal menyimpan konfigurasi PPPoE Pool");
    }
    setSavingPppoe(false);
  };

  if (loading) return <p className="text-muted-foreground text-sm text-center py-8 animate-pulse">Memuat pengaturan...</p>;

  return (
    <div className="space-y-6 max-w-4xl">
      <div className="bg-card border border-border rounded-sm p-4 space-y-4">
        <h3 className="font-semibold text-sm flex items-center gap-2 border-b border-border/50 pb-2 mb-2">
          <Send className="w-4 h-4 text-green-400" /> Konfigurasi Auto WhatsApp Gateway
        </h3>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div className="space-y-1.5">
            <Label className="text-xs text-muted-foreground">Jenis Gateway API</Label>
            <select value={settings.wa_gateway_type || "fonnte"} onChange={e => setSettings({ ...settings, wa_gateway_type: e.target.value })}
              className="w-full h-8 text-xs rounded-sm border border-border bg-secondary px-2 text-foreground">
              <option value="fonnte">Fonnte (Default)</option>
              <option value="wablas">Wablas</option>
              <option value="custom">Custom Server JSON</option>
            </select>
          </div>

          <div className="space-y-1.5">
            <Label className="text-xs text-muted-foreground">Jeda Antar Pesan (Rekomendasi 10000ms)</Label>
            <Input value={settings.wa_delay_ms || 10000} onChange={e => setSettings({ ...settings, wa_delay_ms: Number(e.target.value) })}
              type="number" className="h-8 rounded-sm text-xs font-mono" />
          </div>
        </div>

        <div className="space-y-1.5">
          <Label className="text-xs text-muted-foreground">URL Endpoint API</Label>
          <Input value={settings.wa_api_url || ""} onChange={e => setSettings({ ...settings, wa_api_url: e.target.value })}
            placeholder="https://api.fonnte.com/send" className="h-8 rounded-sm text-xs font-mono" />
        </div>

        <div className="space-y-1.5">
          <Label className="text-xs text-muted-foreground">API Token / Authorization Header</Label>
          <Input value={settings.wa_token || ""} onChange={e => setSettings({ ...settings, wa_token: e.target.value })}
            type="password" placeholder="Key token untuk validasi WA..." className="h-8 rounded-sm text-xs font-mono" />
        </div>

        <div className="pt-4 mt-2 border-t border-border/50">
          <div className="mb-4">
            <h4 className="font-semibold text-sm text-foreground flex items-center gap-2">
              <MessageCircle className="w-4 h-4 text-green-500" /> Template Pesan WhatsApp
            </h4>
            <p className="text-[10px] text-muted-foreground mt-1">
              Variabel otomatis yang bisa digunakan: <code className="bg-secondary/50 px-1 py-0.5 rounded text-primary">{'{customer_name}'}</code> <code className="bg-secondary/50 px-1 py-0.5 rounded text-primary">{'{invoice_number}'}</code> <code className="bg-secondary/50 px-1 py-0.5 rounded text-primary">{'{package_name}'}</code> <code className="bg-secondary/50 px-1 py-0.5 rounded text-primary">{'{period}'}</code> <code className="bg-secondary/50 px-1 py-0.5 rounded text-primary">{'{total}'}</code> <code className="bg-secondary/50 px-1 py-0.5 rounded text-primary">{'{due_date}'}</code> <code className="bg-secondary/50 px-1 py-0.5 rounded text-primary">{'{payment_method}'}</code>
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="space-y-1.5 bg-secondary/10 p-3 rounded-sm border border-border/50 shadow-sm">
              <Label className="text-xs font-semibold text-foreground">Tagihan Baru (Unpaid)</Label>
              <textarea
                value={settings.wa_template_unpaid || ""}
                onChange={e => setSettings({ ...settings, wa_template_unpaid: e.target.value })}
                className="w-full h-24 text-xs rounded-sm border border-input bg-background/80 p-2 text-foreground resize-y font-mono mt-1 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                placeholder="Halo {customer_name}, tagihan #{invoice_number} sebesar {total} jatuh tempo {due_date}..."
              />
            </div>

            <div className="space-y-1.5 bg-secondary/10 p-3 rounded-sm border border-border/50 shadow-sm">
              <Label className="text-xs font-semibold text-foreground">Pembayaran Lunas</Label>
              <textarea
                value={settings.wa_template_paid || ""}
                onChange={e => setSettings({ ...settings, wa_template_paid: e.target.value })}
                className="w-full h-24 text-xs rounded-sm border border-input bg-background/80 p-2 text-foreground resize-y font-mono mt-1 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                placeholder="Terima kasih {customer_name}, pembayaran {invoice_number} via {payment_method} telah diterima."
              />
            </div>

            <div className="space-y-1.5 bg-secondary/10 p-3 rounded-sm border border-border/50 shadow-sm">
              <Label className="text-xs font-semibold flex items-center gap-1.5 text-foreground">
                Pengingat H-1 (Besok Jatuh Tempo)
              </Label>
              <textarea
                value={settings.wa_template_h1 || ""}
                onChange={e => setSettings({ ...settings, wa_template_h1: e.target.value })}
                className="w-full h-24 text-xs rounded-sm border border-input bg-background/80 p-2 text-foreground resize-y font-mono mt-1 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                placeholder="Besok adalah batas akhir pembayaran..."
              />
            </div>

            <div className="space-y-1.5 bg-secondary/10 p-3 rounded-sm border border-border/50 shadow-sm">
              <Label className="text-xs font-semibold text-foreground">Layanan Terisolir / Diputus</Label>
              <textarea
                value={settings.wa_template_isolir || ""}
                onChange={e => setSettings({ ...settings, wa_template_isolir: e.target.value })}
                className="w-full h-24 text-xs rounded-sm border border-input bg-background/80 p-2 text-foreground resize-y font-mono mt-1 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                placeholder="Yth. {customer_name}, koneksi Anda telah diisolir karena tunggakan..."
              />
            </div>
          </div>
        </div>

        <Button onClick={handleSave} disabled={saving} className="w-full sm:w-auto text-xs h-8 rounded-sm gap-2 mt-4">
          <Save className="w-3.5 h-3.5" /> {saving ? "Menyimpan..." : "Simpan Pengaturan"}
        </Button>
      </div>

      {/* FCM Push Notifications Settings */}
      <div className="bg-card border border-border rounded-sm p-4 space-y-4">
        <h3 className="font-semibold text-sm flex items-center gap-2 border-b border-border/50 pb-2 mb-2">
          <Smartphone className="w-4 h-4 text-purple-400" /> Template Notifikasi Aplikasi Android (Push)
        </h3>
        <p className="text-[10px] text-muted-foreground mt-1">
          Variabel otomatis yang bisa digunakan: <code className="bg-secondary/50 px-1 py-0.5 rounded text-primary">{'{customer_name}'}</code> <code className="bg-secondary/50 px-1 py-0.5 rounded text-primary">{'{invoice_number}'}</code> <code className="bg-secondary/50 px-1 py-0.5 rounded text-primary">{'{package_name}'}</code> <code className="bg-secondary/50 px-1 py-0.5 rounded text-primary">{'{total}'}</code> <code className="bg-secondary/50 px-1 py-0.5 rounded text-primary">{'{due_date}'}</code> <code className="bg-secondary/50 px-1 py-0.5 rounded text-primary">{'{payment_method}'}</code>
        </p>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-2">
          <div className="space-y-1.5 bg-secondary/10 p-3 rounded-sm border border-border/50 shadow-sm">
            <Label className="text-xs font-semibold text-foreground">H-3 (3 Hari Sebelum Jatuh Tempo)</Label>
            <textarea
              value={settings.fcm_template_h3 || ""}
              onChange={e => setSettings({ ...settings, fcm_template_h3: e.target.value })}
              className="w-full h-24 text-xs rounded-sm border border-input bg-background/80 p-2 text-foreground resize-y font-mono mt-1"
              placeholder="Tagihan internet Anda {total} jatuh tempo dalam 3 hari pada {due_date}."
            />
          </div>

          <div className="space-y-1.5 bg-secondary/10 p-3 rounded-sm border border-border/50 shadow-sm">
            <Label className="text-xs font-semibold text-foreground">H-2 (2 Hari Sebelum Jatuh Tempo)</Label>
            <textarea
              value={settings.fcm_template_h2 || ""}
              onChange={e => setSettings({ ...settings, fcm_template_h2: e.target.value })}
              className="w-full h-24 text-xs rounded-sm border border-input bg-background/80 p-2 text-foreground resize-y font-mono mt-1"
              placeholder="Tagihan internet Anda {total} jatuh tempo dalam 2 hari pada {due_date}."
            />
          </div>

          <div className="space-y-1.5 bg-secondary/10 p-3 rounded-sm border border-border/50 shadow-sm">
            <Label className="text-xs font-semibold text-foreground">H-1 (Besok Jatuh Tempo)</Label>
            <textarea
              value={settings.fcm_template_h1 || ""}
              onChange={e => setSettings({ ...settings, fcm_template_h1: e.target.value })}
              className="w-full h-24 text-xs rounded-sm border border-input bg-background/80 p-2 text-foreground resize-y font-mono mt-1"
              placeholder="Besok adalah batas akhir pembayaran tagihan internet Anda sebesar {total}."
            />
          </div>

          <div className="space-y-1.5 bg-secondary/10 p-3 rounded-sm border border-border/50 shadow-sm">
            <Label className="text-xs font-semibold text-foreground">Hari Jatuh Tempo / Due Date</Label>
            <textarea
              value={settings.fcm_template_due || ""}
              onChange={e => setSettings({ ...settings, fcm_template_due: e.target.value })}
              className="w-full h-24 text-xs rounded-sm border border-input bg-background/80 p-2 text-foreground resize-y font-mono mt-1"
              placeholder="HARI INI jatuh tempo pembayaran internet {total}. Mohon segera dilunasi."
            />
          </div>

          <div className="space-y-1.5 bg-secondary/10 p-3 rounded-sm border border-border/50 shadow-sm">
            <Label className="text-xs font-semibold text-foreground">Terisolir / Overdue Lanjut</Label>
            <textarea
              value={settings.fcm_template_overdue || ""}
              onChange={e => setSettings({ ...settings, fcm_template_overdue: e.target.value })}
              className="w-full h-24 text-xs rounded-sm border border-input bg-background/80 p-2 text-foreground resize-y font-mono mt-1"
              placeholder="Layanan Anda telah TERISOLIR karena melewati batas waktu pembayaran. Segera lunasi {total}."
            />
          </div>

          <div className="space-y-1.5 bg-secondary/10 p-3 rounded-sm border border-border/50 shadow-sm">
            <Label className="text-xs font-semibold text-foreground">Pembayaran Lunas & Dikonfirmasi</Label>
            <textarea
              value={settings.fcm_template_paid || ""}
              onChange={e => setSettings({ ...settings, fcm_template_paid: e.target.value })}
              className="w-full h-24 text-xs rounded-sm border border-input bg-background/80 p-2 text-foreground resize-y font-mono mt-1"
              placeholder="Terima kasih {customer_name}! Pembayaran tagihan #{invoice_number} berhasil."
            />
          </div>

          <div className="space-y-1.5 bg-secondary/10 p-3 rounded-sm border border-orange-500/30 shadow-sm md:col-span-2 relative">
            <Label className="text-xs font-semibold text-orange-400 flex items-center gap-2">
              <AlertTriangle className="w-4 h-4 text-orange-400" /> Pemberitahuan Jaringan Error (Push Manual)
            </Label>
            <textarea
              value={settings.fcm_template_network_error || ""}
              onChange={e => setSettings({ ...settings, fcm_template_network_error: e.target.value })}
              className="w-full h-16 text-xs rounded-sm border border-orange-500/30 bg-orange-500/5 p-2 text-foreground resize-y font-mono mt-1 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-orange-500/50"
              placeholder="Yth {customer_name}, terdapat gangguan jaringan pada sistem kami. Mohon maaf atas ketidaknyamanan ini."
            />
            <Button
              onClick={async () => {
                if(!confirm("Kirim Push Notifikasi gangguan massal ke SEMUA Pelanggan di Aplikasi Android sekarang?")) return;
                try {
                  const r = await api.post("/billing/push/network-error");
                  if (r.data.ok) {
                    toast.success(r.data.message || "Push Terkirim âœ…");
                  } else {
                    // ok:false = belum ada device terdaftar, bukan error fatal
                    toast.warning(r.data.message || "Belum ada perangkat terdaftar.");
                  }
                } catch(e) {
                  toast.error(e.response?.data?.detail || e.message || "Gagal mengirim Push Notifikasi");
                }
              }}
              variant="outline"
              size="sm"
              className="mt-2 text-[10px] h-7 border-orange-500/30 text-orange-400 hover:bg-orange-500/10 gap-1 w-full sm:w-auto"
            >
              <Send className="w-3 h-3" /> Push Manual ke Semua Pelanggan
            </Button>
          </div>
        </div>

        <Button onClick={handleSave} disabled={saving} className="w-full sm:w-auto text-xs h-8 rounded-sm gap-2 mt-4 border-purple-500/30 text-purple-400 hover:bg-purple-500/10" variant="outline">
          <Save className="w-3.5 h-3.5" /> {saving ? "Menyimpan..." : "Simpan Pengaturan Aplikasi"}
        </Button>
      </div>

      <div className="bg-card border border-border rounded-sm p-4 space-y-4">
        <h3 className="font-semibold text-sm flex items-center gap-2 border-b border-border/50 pb-2 mb-2">
          <WifiOff className="w-4 h-4 text-orange-400" /> Konfigurasi Auto Isolir (Otomatis Putus)
        </h3>
        
        <div className="space-y-3 bg-secondary/10 rounded-sm">
          <label className="flex items-center gap-2 cursor-pointer">
            <input type="checkbox" checked={settings.auto_isolir_enabled || false} onChange={e => setSettings({ ...settings, auto_isolir_enabled: e.target.checked })} className="rounded" />
            <span className="text-sm font-medium">Aktifkan Auto Isolir Pelanggan</span>
          </label>
          <p className="text-[10px] text-muted-foreground pl-6">Sistem akan otomatis memutus koneksi pelanggan di MikroTik yang memiliki tagihan overdue sesuai jadwal eksekusi di bawah.</p>
          
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 pl-6 pt-2">
            <div className="space-y-1.5">
              <Label className="text-xs text-muted-foreground">Metode Notifikasi Isolir</Label>
              <select value={settings.auto_isolir_method || "whatsapp"} onChange={e => setSettings({ ...settings, auto_isolir_method: e.target.value })}
                className="w-full h-8 text-xs rounded-sm border border-border bg-secondary px-2 text-foreground break-all" disabled={!settings.auto_isolir_enabled}>
                <option value="whatsapp">Hanya Kirim Pesan WhatsApp</option>
                <option value="ssid">Hanya Ganti Nama WiFi (SSID)</option>
                <option value="both">Keduanya (WA + Ganti Nama WiFi)</option>
              </select>
            </div>
            
            <div className="space-y-1.5">
              <Label className="text-xs text-muted-foreground">Jam Eksekusi Harian</Label>
              <Input value={settings.auto_isolir_time || "00:05"} onChange={e => setSettings({ ...settings, auto_isolir_time: e.target.value })}
                type="time" className="h-8 rounded-sm text-xs font-mono" disabled={!settings.auto_isolir_enabled} />
            </div>

            <div className="space-y-1.5 sm:col-span-2">
              <Label className="text-xs text-muted-foreground">Toleransi Keterlambatan (Hari lewat jatuh tempo)</Label>
              <Input value={settings.auto_isolir_grace_days ?? 0} onChange={e => setSettings({ ...settings, auto_isolir_grace_days: Number(e.target.value) })}
                type="number" min="0" className="h-8 rounded-sm text-xs font-mono" disabled={!settings.auto_isolir_enabled} />
            </div>
          </div>
        </div>

        <Button onClick={handleSave} disabled={saving} className="w-full sm:w-auto text-xs h-8 rounded-sm gap-2 mt-4 border-orange-500/30 text-orange-400 hover:bg-orange-500/10" variant="outline">
          <Save className="w-3.5 h-3.5" /> {saving ? "Menyimpan..." : "Simpan Pengaturan Isolir"}
        </Button>
      </div>

      <div className="bg-card border border-border rounded-sm p-4 space-y-4">
        <h3 className="font-semibold text-sm flex items-center gap-2 border-b border-border/50 pb-2 mb-2">
          Webhook & Integrasi Eksternal
        </h3>
        
        <div className="space-y-1.5">
          <Label className="text-xs text-muted-foreground">Moota Webhook Secret (Verifikasi Keamanan Bank)</Label>
          <Input value={settings.moota_webhook_secret || ""} onChange={e => setSettings({ ...settings, moota_webhook_secret: e.target.value })}
            type="password" placeholder="Simpan rahasia dari Moota di sini (opsional tapi sangat disarankan)" className="h-8 rounded-sm text-xs font-mono" />
          <p className="text-[10px] text-muted-foreground">Isi dengan fitur <b>Secret / Signature</b> dari web dashboard Moota agar tidak ada attacker yang bisa memalsukan transaksi.</p>
        </div>

        <div className="space-y-1.5">
          <Label className="text-xs text-muted-foreground">N8N Webhook URL (Notifikasi Pembayaran Eksternal)</Label>
          <Input value={settings.n8n_webhook_url || ""} onChange={e => setSettings({ ...settings, n8n_webhook_url: e.target.value })}
            placeholder="https://n8n.domain.com/webhook/..." className="h-8 rounded-sm text-xs font-mono" />
        </div>

        <Button onClick={handleSave} disabled={saving} className="w-full sm:w-auto text-xs h-8 rounded-sm gap-2 mt-4 border-blue-500/30 text-blue-400 hover:bg-blue-500/10" variant="outline">
          <Save className="w-3.5 h-3.5" /> {saving ? "Menyimpan..." : "Simpan Pengaturan Integrasi"}
        </Button>
      </div>

      {/* Payment Gateway Settings */}
      <div className="bg-card border border-border rounded-sm p-4 space-y-4">
        <h3 className="font-semibold text-sm flex items-center gap-2 border-b border-border/50 pb-2 mb-2">
          <CreditCard className="w-4 h-4 text-emerald-400" /> Payment Gateway (VA / QRIS / E-Wallet)
        </h3>
        <div className="flex items-center gap-3 p-3 bg-secondary/30 rounded-sm border border-border/50">
          <input type="checkbox" id="pg_enabled" checked={!!settings.payment_gateway_enabled}
            onChange={e => setSettings({ ...settings, payment_gateway_enabled: e.target.checked })}
            className="w-4 h-4 rounded" />
          <label htmlFor="pg_enabled" className="text-xs font-medium cursor-pointer">
            Aktifkan Payment Gateway (VA / QRIS / E-Wallet untuk Pembayaran Tagihan PPPoE)
          </label>
        </div>

        {settings.payment_gateway_enabled && (
          <div className="space-y-4">
            <div className="p-3 bg-blue-500/5 border border-blue-500/20 rounded-sm text-[10px] text-blue-300 space-y-1">
              <p className="font-semibold">Webhook URLs — Daftarkan ke dashboard masing-masing provider:</p>
              <p className="font-mono">Xendit: <span className="text-sky-300">[domain]/api/webhook/xendit</span></p>
              <p className="font-mono">BCA SNAP: <span className="text-sky-300">[domain]/api/webhook/bca</span></p>
              <p className="font-mono">BRI BRIVA: <span className="text-sky-300">[domain]/api/webhook/bri</span></p>
            </div>

            {/* Xendit */}
            <div className="border border-border/50 rounded-sm p-3 space-y-3">
              <div className="flex items-center gap-2">
                <input type="checkbox" id="xendit_enabled" checked={!!settings.xendit_enabled}
                  onChange={e => setSettings({ ...settings, xendit_enabled: e.target.checked })} className="w-3.5 h-3.5" />
                <label htmlFor="xendit_enabled" className="text-xs font-semibold text-emerald-400 cursor-pointer">Xendit (VA + QRIS + E-Wallet)</label>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div className="space-y-1">
                  <Label className="text-[10px] text-muted-foreground">Secret Key</Label>
                  <Input type="password" value={settings.xendit_secret_key || ""} onChange={e => setSettings({ ...settings, xendit_secret_key: e.target.value })}
                    className="h-7 rounded-sm text-xs font-mono" placeholder="xnd_production_..." />
                </div>
                <div className="space-y-1">
                  <Label className="text-[10px] text-muted-foreground">Webhook Token</Label>
                  <Input type="password" value={settings.xendit_webhook_token || ""} onChange={e => setSettings({ ...settings, xendit_webhook_token: e.target.value })}
                    className="h-7 rounded-sm text-xs font-mono" placeholder="token dari dashboard Xendit" />
                </div>
                <div className="space-y-1">
                  <Label className="text-[10px] text-muted-foreground">Bank VA Default</Label>
                  <select value={settings.xendit_va_bank || "BNI"} onChange={e => setSettings({ ...settings, xendit_va_bank: e.target.value })}
                    className="w-full h-7 text-xs rounded-sm border border-border bg-secondary px-2">
                    {["BNI","BCA","BRI","MANDIRI","PERMATA","BSI","BJB"].map(b => <option key={b}>{b}</option>)}
                  </select>
                </div>
              </div>
            </div>

            {/* BCA */}
            <div className="border border-border/50 rounded-sm p-3 space-y-3">
              <div className="flex items-center gap-2">
                <input type="checkbox" id="bca_enabled" checked={!!settings.bca_enabled}
                  onChange={e => setSettings({ ...settings, bca_enabled: e.target.checked })} className="w-3.5 h-3.5" />
                <label htmlFor="bca_enabled" className="text-xs font-semibold text-blue-400 cursor-pointer">BCA SNAP (Virtual Account BCA)</label>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {[["bca_client_id","Client ID"],["bca_client_secret","Client Secret"],["bca_company_code","Company Code"],["bca_api_key","API Key"],["bca_api_secret","API Secret"]].map(([k,lb]) => (
                  <div key={k} className="space-y-1">
                    <Label className="text-[10px] text-muted-foreground">{lb}</Label>
                    <Input type="password" value={settings[k] || ""} onChange={e => setSettings({ ...settings, [k]: e.target.value })}
                      className="h-7 rounded-sm text-xs font-mono" />
                  </div>
                ))}
              </div>
            </div>

            {/* BRI */}
            <div className="border border-border/50 rounded-sm p-3 space-y-3">
              <div className="flex items-center gap-2">
                <input type="checkbox" id="bri_enabled" checked={!!settings.bri_enabled}
                  onChange={e => setSettings({ ...settings, bri_enabled: e.target.checked })} className="w-3.5 h-3.5" />
                <label htmlFor="bri_enabled" className="text-xs font-semibold text-sky-400 cursor-pointer">BRI BRIVA (Virtual Account BRI)</label>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {[["bri_client_id","Client ID"],["bri_client_secret","Client Secret"],["bri_institution_code","Institution Code"]].map(([k,lb]) => (
                  <div key={k} className="space-y-1">
                    <Label className="text-[10px] text-muted-foreground">{lb}</Label>
                    <Input type="password" value={settings[k] || ""} onChange={e => setSettings({ ...settings, [k]: e.target.value })}
                      className="h-7 rounded-sm text-xs font-mono" />
                  </div>
                ))}
              </div>
            </div>

            <Button onClick={handleSave} disabled={saving} className="w-full sm:w-auto text-xs h-8 rounded-sm gap-2 border-emerald-500/30 text-emerald-400 hover:bg-emerald-500/10" variant="outline">
              <Save className="w-3.5 h-3.5" /> {saving ? "Menyimpan..." : "Simpan Konfigurasi Gateway"}
            </Button>
          </div>
        )}
      </div>

      <div className="bg-card border border-border rounded-sm p-4 space-y-4">
        <h3 className="font-semibold text-sm flex items-center gap-2 border-b border-border/50 pb-2 mb-2">
          <Activity className="w-4 h-4 text-primary" /> Setup Otomatis IP Pool &amp; DNS PPPoE
        </h3>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div className="space-y-1.5">
            <Label className="text-xs text-muted-foreground">Nama IP Pool</Label>
            <Input value={pppoeSettings.pool_name || ""} onChange={e => setPppoeSettings({ ...pppoeSettings, pool_name: e.target.value })}
              className="h-8 rounded-sm text-xs" />
          </div>
          <div className="space-y-1.5">
            <Label className="text-xs text-muted-foreground">Range IP Pool</Label>
            <Input value={pppoeSettings.pool_ranges || ""} onChange={e => setPppoeSettings({ ...pppoeSettings, pool_ranges: e.target.value })}
              className="h-8 rounded-sm text-xs font-mono" placeholder="10.20.30.2-10.20.30.254" />
          </div>
          <div className="space-y-1.5">
            <Label className="text-xs text-muted-foreground">IP Local (Gateway Pelanggan)</Label>
            <Input value={pppoeSettings.gateway_ip || ""} onChange={e => setPppoeSettings({ ...pppoeSettings, gateway_ip: e.target.value })}
              className="h-8 rounded-sm text-xs font-mono" placeholder="10.20.30.1" />
          </div>
          <div className="space-y-1.5">
            <Label className="text-xs text-muted-foreground">Nama Profile MikroTik Target</Label>
            <Input value={pppoeSettings.profile_name || ""} onChange={e => setPppoeSettings({ ...pppoeSettings, profile_name: e.target.value })}
              className="h-8 rounded-sm text-xs" placeholder="default" />
          </div>
          <div className="space-y-1.5 sm:col-span-2">
            <Label className="text-xs text-muted-foreground">DNS Servers</Label>
            <Input value={pppoeSettings.dns_servers || ""} onChange={e => setPppoeSettings({ ...pppoeSettings, dns_servers: e.target.value })}
              className="h-8 rounded-sm text-xs font-mono" placeholder="8.8.8.8,1.1.1.1" />
            <p className="text-[10px] text-muted-foreground">DNS yang akan diterima client. Contoh: 8.8.8.8,1.1.1.1</p>
          </div>
        </div>

        <Button onClick={handleSavePppoe} disabled={savingPppoe} className="w-full sm:w-auto text-xs h-8 rounded-sm gap-2 mt-4 border-primary/30 text-primary hover:bg-primary/10" variant="outline">
          <Save className="w-3.5 h-3.5" /> {savingPppoe ? "Menyimpan & Push ke Mikrotik..." : "Simpan & Konfigurasikan MikroTik"}
        </Button>
      </div>
    </div>
  );
}

// â”€â”€ Import CSV Modal â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

function ImportCsvModal({ onClose, onImported }) {
  const [file, setFile] = useState(null);
  const [loading, setLoading] = useState(false);

  const downloadTemplate = async () => {
    try {
      const resp = await api.get("/customers/template.csv", { responseType: 'blob' });
      const url = window.URL.createObjectURL(new Blob([resp.data]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', 'template_import_pelanggan.csv');
      document.body.appendChild(link);
      link.click();
      link.remove();
    } catch (e) { toast.error("Gagal mendownload template"); }
  };

  const submit = async () => {
    if (!file) return toast.error("Pilih file CSV terlebih dahulu");
    setLoading(true);
    const fd = new FormData();
    fd.append("file", file);
    try {
      const r = await api.post("/customers/import-csv", fd);
      toast.success(r.data.message);
      if (r.data.errors && r.data.errors.length) {
        toast.warning(r.data.errors.slice(0, 3).join("; "));
      }
      onImported();
      onClose();
    } catch (e) {
      toast.error("Gagal mengimpor data");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-card border border-border p-6 rounded-sm w-full max-w-md space-y-4">
        <h3 className="font-semibold">Import Pelanggan (CSV)</h3>
        <input type="file" accept=".csv" onChange={e => setFile(e.target.files[0])} className="text-xs" />
        <div className="flex gap-2">
          <Button variant="outline" onClick={downloadTemplate} className="text-xs h-8">Download Template</Button>
          <Button onClick={submit} disabled={loading} className="text-xs h-8 flex-1">
            {loading ? "Memproses..." : "Upload & Import"}
          </Button>
        </div>
        <Button variant="ghost" onClick={onClose} className="w-full text-xs h-8">Batal</Button>
      </div>
    </div>
  );
}

// â”€â”€ Monitoring PPPoE Tab â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
// This file is appended to BillingPage.jsx by the build script

function PpoeMonitoringTab({ deviceId }) {
  const [actives, setActives]       = useState([]);
  const [loading, setLoading]       = useState(false);
  const [showPwd, setShowPwd]       = useState({});
  const [search, setSearch]         = useState("");
  const [kickingUser, setKicking]   = useState(null);
  const [enabled, setEnabled]       = useState(() => {
    try { return JSON.parse(localStorage.getItem("ppoe_monitoring_enabled") ?? "true"); }
    catch { return true; }
  });
  const [countdown, setCountdown]   = useState(15);
  const intervalRef  = useRef(null);
  const countdownRef = useRef(null);
  const loadData = useCallback(async () => {
    if (!enabled) return;
    if (!deviceId) {
      setActives([]);
      return;
    }
    setLoading(true);
    setCountdown(30);
    try {
      const { data } = await api.get(`/pppoe-active-monitoring?router_id=${deviceId}`);
      setActives(data || []);
    } catch (e) {
      toast.error("Gagal load data monitoring PPPoE");
    } finally {
      setLoading(false);
    }
  }, [enabled, deviceId]);

  useEffect(() => {
    clearInterval(intervalRef.current);
    clearInterval(countdownRef.current);
    if (enabled) {
      if (deviceId) {
        loadData();
        intervalRef.current  = setInterval(loadData, 30000);
        countdownRef.current = setInterval(() => setCountdown(c => c <= 1 ? 30 : c - 1), 1000);
      } else {
        setActives([]);
      }
    } else {
      setActives([]);
      setCountdown(30);
    }
    return () => { clearInterval(intervalRef.current); clearInterval(countdownRef.current); };
  }, [enabled, deviceId, loadData]); // eslint-disable-line

  const toggleEnabled = () => {
    const next = !enabled;
    setEnabled(next);
    localStorage.setItem("ppoe_monitoring_enabled", JSON.stringify(next));
    if (next) toast.success("Monitoring PPPoE diaktifkan");
    else       toast.info("Monitoring PPPoE dinonaktifkan - beban MikroTik berkurang");
  };

  const handleKick = async (a) => {
    if (!window.confirm(`Putus koneksi "${a.name}" dari ${a.router_name}?`)) return;
    setKicking(a.name);
    try {
      await api.post("/pppoe-kick", { username: a.name, router_id: a.router_id });
      toast.success(`[OK] Koneksi "${a.name}" berhasil diputus`);
      setTimeout(loadData, 1500);
    } catch (e) {
      toast.error(`Gagal kick "${a.name}": ${e?.response?.data?.detail || e.message}`);
    } finally {
      setKicking(null);
    }
  };

  const togglePwd = (u) => setShowPwd(p => ({ ...p, [u]: !p[u] }));

  const formatBytes = (b) => {
    const num = Number(b);
    if (!b || isNaN(num) || num === 0) return "0 B";
    if (num > 1024**3) return (num / 1024**3).toFixed(2) + " GB";
    if (num > 1024**2) return (num / 1024**2).toFixed(2) + " MB";
    if (num > 1024)    return (num / 1024).toFixed(2) + " KB";
    return num + " B";
  };

  const formatBps = (bps) => {
    const num = Number(bps);
    if (!bps || isNaN(num) || num === 0) return null;
    if (num > 1_000_000) return (num / 1_000_000).toFixed(1) + " Mbps";
    if (num > 1_000)     return (num / 1_000).toFixed(1) + " kbps";
    return num + " bps";
  };

  const BpsCell = ({ txBps, rxBps }) => {
    const tx = formatBps(txBps);
    const rx = formatBps(rxBps);
    return (
      <div className="tabular-nums text-[11px] space-y-1">
        <div className="flex items-center gap-1.5">
          <Download className="w-3 h-3 text-green-500 shrink-0"/>
          {tx ? <span className="text-green-500 font-semibold flex items-center gap-1">
                  <span className="w-1.5 h-1.5 rounded-full bg-green-500 animate-pulse inline-block"/>
                  {tx}
                </span>
              : <span className="text-muted-foreground">0 bps</span>}
        </div>
        <div className="flex items-center gap-1.5">
          <Upload className="w-3 h-3 text-blue-500 shrink-0"/>
          {rx ? <span className="text-blue-500 font-semibold flex items-center gap-1">
                  <span className="w-1.5 h-1.5 rounded-full bg-blue-500 animate-pulse inline-block"/>
                  {rx}
                </span>
              : <span className="text-muted-foreground">0 bps</span>}
        </div>
      </div>
    );
  };

  const q = search.toLowerCase().trim();
  const filtered = (q
    ? actives.filter(a =>
        a.name.toLowerCase().includes(q) ||
        (a.customer_name || "").toLowerCase().includes(q) ||
        (a.address || "").toLowerCase().includes(q) ||
        (a.caller_id || "").toLowerCase().includes(q) ||
        (a.router_name || "").toLowerCase().includes(q)
      )
    : [...actives]).sort((a, b) => {
      // Urutkan berdasarkan total bandwidth (rx_bps + tx_bps) tertinggi, fallback ke bytes rx+tx
      const bTotalBps = (b.rx_bps || 0) + (b.tx_bps || 0);
      const aTotalBps = (a.rx_bps || 0) + (a.tx_bps || 0);
      if (bTotalBps !== aTotalBps) return bTotalBps - aTotalBps;
      
      const bTotalBytes = (b.rx_byte || 0) + (b.tx_byte || 0);
      const aTotalBytes = (a.rx_byte || 0) + (a.tx_byte || 0);
      return bTotalBytes - aTotalBytes;
    });

  return (
    <div className="space-y-4">
      {/* Header Controls */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 bg-card p-4 rounded-sm border border-border">
        <div>
          <h2 className="text-base font-bold flex items-center gap-2">
            <Activity className={`w-4 h-4 ${enabled ? "text-green-500 animate-pulse" : "text-muted-foreground"}`}/>
            Monitoring PPPoE Aktif
            {enabled && deviceId && (
              <span className="text-[10px] font-normal text-muted-foreground bg-secondary px-2 py-0.5 rounded-full">
                Refresh dalam {countdown}s
              </span>
            )}
          </h2>
          <p className="text-xs text-muted-foreground mt-0.5">
            Pantau sesi PPPoE aktif - mendukung ROS 6, ROS 7, dan autentikasi RADIUS.
          </p>
        </div>

        <div className="flex items-center gap-2 flex-wrap">
          <Button onClick={loadData} disabled={loading || !enabled || !deviceId} size="sm" variant="outline" className="h-8 gap-1.5 text-xs">
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`}/> Refresh
          </Button>

          <button
            onClick={toggleEnabled}
            className={`h-8 px-3 rounded-sm text-xs font-semibold flex items-center gap-1.5 border transition-all ${
              enabled
                ? "bg-green-500/10 border-green-500/40 text-green-400 hover:bg-green-500/20"
                : "bg-red-500/10 border-red-500/40 text-red-400 hover:bg-red-500/20"
            }`}
          >
            {enabled ? <><Wifi className="w-3.5 h-3.5"/> Monitoring ON</> : <><WifiOff className="w-3.5 h-3.5"/> Monitoring OFF</>}
          </button>
        </div>
      </div>

      {/* Disabled state */}
      {!enabled && (
        <div className="flex flex-col items-center justify-center py-16 space-y-4 bg-card border border-border rounded-sm">
          <WifiOff className="w-12 h-12 text-muted-foreground/30"/>
          <div className="text-center">
            <p className="font-semibold text-muted-foreground">Monitoring dinonaktifkan</p>
            <p className="text-xs text-muted-foreground/60 mt-1 max-w-xs">
              Polling ke MikroTik dihentikan. Klik <strong>Monitoring OFF</strong> untuk mengaktifkan.
            </p>
          </div>
          <button onClick={toggleEnabled} className="text-xs bg-primary text-primary-foreground px-4 py-2 rounded-sm font-semibold hover:opacity-90 transition-opacity">
            Aktifkan Monitoring
          </button>
        </div>
      )}

      {/* Search + Table */}
      {enabled && (
        !deviceId ? (
          <div className="flex flex-col items-center justify-center py-16 space-y-4 bg-card border border-border rounded-sm">
            <Activity className="w-12 h-12 text-muted-foreground/30"/>
            <div className="text-center">
              <p className="font-semibold text-muted-foreground">Pilih Router Terlebih Dahulu</p>
              <p className="text-xs text-muted-foreground/60 mt-1 max-w-xs mx-auto">
                Kunci aktif: Data monitoring PPPoE hanya ditampilkan untuk spesifik device. Pilih dari dropdown pojok kanan atas.
              </p>
            </div>
          </div>
        ) : (
        <>
          <div className="relative">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground pointer-events-none"/>
            <input
              value={search}
              onChange={e => setSearch(e.target.value)}
              placeholder="Cari username, IP, MAC, nama pelanggan, router..."
              className="w-full h-8 pl-8 pr-3 text-xs bg-card border border-border rounded-sm focus:outline-none focus:ring-1 focus:ring-primary/50"
            />
            {search && (
              <button onClick={() => setSearch("")} className="absolute right-2.5 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground">
                <X className="w-3.5 h-3.5"/>
              </button>
            )}
          </div>

          <div className="rounded-sm border border-border overflow-x-auto bg-card">
            <table className="w-full text-xs text-left whitespace-nowrap min-w-[900px]">
              <thead className="bg-secondary/50">
                <tr>
                  <th className="p-3 border-b border-border/50 font-semibold">User (Pelanggan)</th>
                  <th className="p-3 border-b border-border/50 font-semibold">Password</th>
                  <th className="p-3 border-b border-border/50 font-semibold">Alamat IP &amp; MAC</th>
                  <th className="p-3 border-b border-border/50 font-semibold">Router</th>
                  <th className="p-3 border-b border-border/50 font-semibold">Waktu Terhubung</th>
                  <th className="p-3 border-b border-border/50 font-semibold">Total Data</th>
                  <th className="p-3 border-b border-border/50 font-semibold">Bandwidth Saat Ini</th>
                  <th className="p-3 border-b border-border/50 font-semibold">Aksi</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border/50">
                {loading && actives.length === 0 ? (
                  <tr><td colSpan={8} className="p-8 text-center text-muted-foreground">
                    <RefreshCw className="w-4 h-4 animate-spin inline mr-2"/>Memuat data PPPoE aktif...
                  </td></tr>
                ) : filtered.length === 0 ? (
                  <tr><td colSpan={8} className="p-8 text-center text-muted-foreground">
                    {search ? `Tidak ditemukan untuk "${search}"` : `Tidak ada sesi PPPoE aktif pada router ini`}
                  </td></tr>
                ) : filtered.map((a, i) => (
                  <tr key={i} className={`hover:bg-secondary/20 transition-colors ${loading ? "opacity-60" : ""}`}>
                    <td className="p-3">
                      <div className="flex items-center gap-1.5 flex-wrap">
                        <span className="font-semibold">{a.name}</span>
                        {a.is_radius && (
                          <span className="text-[9px] px-1 py-0.5 rounded bg-purple-500/15 text-purple-400 border border-purple-500/30 font-semibold">RADIUS</span>
                        )}
                      </div>
                      <span className="text-[10px] text-muted-foreground">{a.customer_name !== a.name ? a.customer_name : "-"}</span>
                    </td>
                    <td className="p-3">
                      {a.is_radius ? (
                        <span className="text-[10px] text-muted-foreground italic">via RADIUS</span>
                      ) : (
                        <div className="flex items-center gap-1.5">
                          <span className="font-mono bg-secondary/50 px-1 py-0.5 rounded text-[11px] min-w-[70px] inline-block">
                            {showPwd[a.name] ? (a.password || "-") : "●●●●●●●●"}
                          </span>
                          <button onClick={() => togglePwd(a.name)} className="text-muted-foreground hover:text-foreground">
                            {showPwd[a.name] ? <EyeOff className="w-3.5 h-3.5"/> : <Eye className="w-3.5 h-3.5"/>}
                          </button>
                        </div>
                      )}
                    </td>
                    <td className="p-3 font-mono text-[11px]">
                      <span className="text-primary font-semibold">{a.address || "-"}</span><br/>
                      <span className="text-muted-foreground text-[10px]">{a.caller_id || "-"}</span>
                    </td>
                    <td className="p-3">
                      <span className="px-2 py-0.5 rounded-sm bg-accent/20 border border-accent/30 text-accent-foreground text-[10px]">
                        {a.router_name}
                      </span>
                    </td>
                    <td className="p-3 font-medium">
                      <div className="flex items-center gap-1.5">
                        <Clock className="w-3.5 h-3.5 text-muted-foreground shrink-0"/>
                        {a.uptime || "-"}
                      </div>
                    </td>
                    <td className="p-3 tabular-nums text-[11px] space-y-1">
                      <div className="flex items-center gap-1.5">
                        <Download className="w-3 h-3 text-muted-foreground shrink-0"/>
                        <span className="font-medium">{formatBytes(a.tx_byte)}</span>
                      </div>
                      <div className="flex items-center gap-1.5">
                        <Upload className="w-3 h-3 text-muted-foreground shrink-0"/>
                        <span className="font-medium">{formatBytes(a.rx_byte)}</span>
                      </div>
                    </td>
                    <td className="p-3">
                      <BpsCell txBps={a.tx_bps} rxBps={a.rx_bps}/>
                    </td>
                    <td className="p-3">
                      <button
                        onClick={() => handleKick(a)}
                        disabled={kickingUser === a.name}
                        title={`Putus koneksi ${a.name}`}
                        className="flex items-center gap-1 px-2 py-1 rounded-sm text-[10px] font-semibold bg-red-500/10 border border-red-500/30 text-red-400 hover:bg-red-500/20 disabled:opacity-50 disabled:cursor-wait transition-all"
                      >
                        {kickingUser === a.name
                          ? <><RefreshCw className="w-3 h-3 animate-spin"/> Memutus...</>
                          : <><UserX className="w-3 h-3"/> Kick</>}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>

            {actives.length > 0 && (
              <div className="px-3 py-2 border-t border-border/50 flex items-center justify-between text-[10px] text-muted-foreground">
                <span>
                  {filtered.length !== actives.length
                    ? `${filtered.length} dari ${actives.length} sesi aktif`
                    : `${actives.length} sesi PPPoE aktif`}
                  {actives.filter(a => a.is_radius).length > 0 && (
                    <span className="ml-2 text-purple-400">
                      • {actives.filter(a => a.is_radius).length} via RADIUS
                    </span>
                  )}
                </span>
                {loading && <span className="flex items-center gap-1"><RefreshCw className="w-3 h-3 animate-spin"/> Memperbarui...</span>}
              </div>
            )}
          </div>
        </>
        )
      )}
    </div>
  );
}


