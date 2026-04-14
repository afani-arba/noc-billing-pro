import { useState, useEffect } from "react";
import { Key, ShieldCheck, ShieldAlert, Cpu, Zap, CheckCircle, XCircle } from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import api from "@/lib/api";
import { useEdition } from "@/App";

export default function LicensePage() {

  const { edition, edition_name, features } = useEdition();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [keyInput, setKeyInput] = useState("");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    fetchLicense();
  }, []);

  const fetchLicense = async () => {
    try {
      const res = await api.get("/system/license");
      setData(res.data);
    } catch (err) {
      console.error(err);
      toast.error("Gagal mengambil data lisensi");
    } finally {
      setLoading(false);
    }
  };

  const handleActivate = async (e) => {
    e.preventDefault();
    const key = keyInput.trim();

    // ── LAYER 1: Validasi format client-side ───────────────────────────────────
    const proPattern  = /^ArBa-Pro-[A-F0-9]{4}-[A-F0-9]{4}$/i;
    const entPattern  = /^ArBa-ENT-[A-F0-9]{4}-[A-F0-9]{4}$/i;
    const legacyNOC   = /^NOC-[A-F0-9]{4}-[A-F0-9]{4}-[A-F0-9]{4}$/i;  // Support key lama

    if (!proPattern.test(key) && !entPattern.test(key) && !legacyNOC.test(key)) {
      toast.error(
        `Format key tidak valid. Gunakan: ${edition === 'enterprise' ? 'ArBa-ENT-XXXX-XXXX' : 'ArBa-Pro-XXXX-XXXX'}`,
        { duration: 5000 }
      );
      return;
    }

    // Edition mismatch check (frontend enforcement)
    if (edition === "enterprise" && proPattern.test(key)) {
      toast.error(
        "Anda menggunakan NOC-Sentinel Enterprise. " +
        "Lisensi Pro (ArBa-Pro-...) tidak dapat digunakan di sini. " +
        "Hubungi admin untuk mendapatkan lisensi ArBa-ENT-XXXX-XXXX.",
        { duration: 7000 }
      );
      return;
    }

    if (edition === "pro" && entPattern.test(key)) {
      // Enterprise key DI-IZINKAN di Pro — beri info saja
      toast.info("Menggunakan lisensi Enterprise di edisi Pro. Melanjutkan aktivasi...");
    }

    if (!key) return;
    setSubmitting(true);
    try {
      const res = await api.post("/system/license", { license_key: key });
      toast.success(res.data.message);
      setData((prev) => ({ ...prev, ...res.data.data }));
      setKeyInput("");
      
      // Reload page after 1.5s to restore access
      setTimeout(() => window.location.href = "/admin", 1500);
    } catch (err) {
      toast.error(err.response?.data?.detail || "Gagal aktivasi lisensi");
      fetchLicense(); // Refresh status
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) return <div className="p-8 text-center text-muted-foreground">Memuat informasi lisensi...</div>;

  const isValid = data?.status === 'valid';

  const featureList = [
    { key: "monitoring", label: "Dashboard & Monitoring", always: true },
    { key: "genieacs", label: "GenieACS / TR-069 CPE" },
    { key: "billing", label: "Billing PPPoE & Hotspot" },
    { key: "customers", label: "Manajemen Pelanggan" },
    { key: "finance_report", label: "Laporan Keuangan" },
    { key: "auto_isolir", label: "Auto Isolir & Reminder" },
    { key: "n8n", label: "Integrasi n8n / WhatsApp" },
  ];



  return (
    <div className="p-8 max-w-4xl mx-auto space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Manajemen Lisensi</h1>
        <p className="text-muted-foreground">
          Kelola lisensi NOC Sentinel untuk memastikan fitur aplikasi berjalan maksimal.
        </p>
      </div>

      {/* Edition Card */}
      <Card className={edition === "enterprise" ? "border-cyan-500/40" : "border-primary/40"}>
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2 text-base">
            <Zap className={edition === "enterprise" ? "text-cyan-400 w-4 h-4" : "text-primary w-4 h-4"} />
            Edisi Aktif: <span className={edition === "enterprise" ? "text-cyan-400" : "text-primary"}>{edition_name || "NOC-Sentinel Pro"}</span>
          </CardTitle>
          <CardDescription>Fitur yang tersedia pada edisi ini</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
            {featureList.map(f => {
              const enabled = f.always || features?.[f.key];
              return (
                <div key={f.key} className={`flex items-center gap-2 text-xs px-2 py-1.5 rounded ${enabled ? "text-green-400" : "text-muted-foreground/50"}`}>
                  {enabled
                    ? <CheckCircle className="w-3 h-3 flex-shrink-0 text-green-500" />
                    : <XCircle className="w-3 h-3 flex-shrink-0 text-muted-foreground/30" />
                  }
                  {f.label}
                </div>
              );
            })}
          </div>
          {edition === "pro" && (
            <p className="text-xs text-muted-foreground mt-3 pt-3 border-t border-border">
              💡 Upgrade ke <strong>Enterprise</strong> untuk mengaktifkan Billing, Laporan Keuangan, dan integrasi n8n.
            </p>
          )}
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">

        <Card className={isValid ? "border-green-500/50" : "border-red-500/50"}>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              {isValid ? <ShieldCheck className="text-green-500" /> : <ShieldAlert className="text-red-500" />}
              Status Lisensi
            </CardTitle>
            <CardDescription>Informasi status berlangganan saat ini</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex justify-between items-center p-3 bg-muted/50 rounded-md">
              <span className="text-sm font-medium">Status</span>
              <span className={`px-2 py-1 text-xs font-semibold rounded ${isValid ? 'bg-green-500/10 text-green-500' : 'bg-red-500/10 text-red-500'}`}>
                {data?.status?.toUpperCase()}
              </span>
            </div>
            
            <div className="flex justify-between items-center p-3 bg-muted/50 rounded-md">
              <span className="text-sm font-medium">Tipe Paket</span>
              <span className="text-sm uppercase">{data?.type || '-'}</span>
            </div>

            <div className="flex justify-between items-center p-3 bg-muted/50 rounded-md">
              <span className="text-sm font-medium">Edisi Lisensi</span>
              <span className={`text-xs font-bold px-2 py-1 rounded ${
                (data?.edition || 'pro') === 'enterprise'
                  ? 'bg-cyan-500/10 text-cyan-400'
                  : 'bg-blue-500/10 text-blue-400'
              }`}>
                {(data?.edition || 'pro') === 'enterprise' ? '⚡ Enterprise' : '🔵 Pro'}
              </span>
            </div>

            <div className="flex justify-between items-center p-3 bg-muted/50 rounded-md">
              <span className="text-sm font-medium">Berlaku Hingga</span>
              <span className="text-sm">{data?.expires_at ? new Date(data.expires_at).toLocaleDateString() : '-'}</span>
            </div>

            {data?.message && !isValid && (
              <div className="text-xs text-red-400 mt-2 p-2 bg-red-500/10 rounded">
                <b>Peringatan:</b> {data.message}
              </div>
            )}
            
            {/* Overlay Lock if invalid */}
            {!isValid && (
              <div className="p-4 bg-red-900/20 border border-red-500/50 text-red-400 rounded-lg text-sm mb-4">
                Sistem NOC Sentinel sedang terkunci karena lisensi tidak valid atau kadaluarsa. Silakan aktivasi dengan kunci lisensi baru untuk membuka kembali akses.
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2"><Key className="w-5 h-5"/> Aktivasi Lisensi</CardTitle>
            <CardDescription>Masukkan kunci lisensi untuk memperpanjang akses</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="mb-6 p-4 bg-blue-900/10 border border-blue-500/20 rounded-lg text-sm text-blue-400">
              <div className="flex items-center gap-2 mb-2">
                <Cpu className="w-4 h-4"/> <strong>Hardware ID (Server):</strong>
              </div>
              <code className="bg-background px-2 py-1 rounded block mt-1">{data?.hardware_id}</code>
              <p className="mt-2 text-xs">Berikan ID ini ke administrator saat membeli lisensi untuk mengikat lisensi ke server ini.</p>
            </div>

            <form onSubmit={handleActivate} className="space-y-4">
              <div className="space-y-2">
                <label className="text-sm font-medium">License Key</label>
                <Input 
                  placeholder={edition === 'enterprise' ? 'ArBa-ENT-XXXX-XXXX' : 'ArBa-Pro-XXXX-XXXX'}
                  value={keyInput}
                  onChange={e => setKeyInput(e.target.value)}
                  className="font-mono"
                  required
                />
                <p className="text-xs text-muted-foreground">
                  Format untuk edisi ini: <code className="text-primary font-mono text-xs">{
                    edition === 'enterprise' ? 'ArBa-ENT-XXXX-XXXX' : 'ArBa-Pro-XXXX-XXXX'
                  }</code>
                  {edition === 'enterprise' && (
                    <span className="text-yellow-500 ml-1">— Key Pro tidak dapat digunakan di Edisi Enterprise</span>
                  )}
                </p>
              </div>
              <Button type="submit" className="w-full" disabled={submitting}>
                {submitting ? "Memverifikasi..." : "Aktivasi Lisensi"}
              </Button>
            </form>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

