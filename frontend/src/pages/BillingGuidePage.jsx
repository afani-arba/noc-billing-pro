import React from "react";
import { Link } from "react-router-dom";
import { 
  BookOpen, Plug, Server, MessageSquare, CreditCard,
  ArrowRight, ShieldCheck, FileText, CheckCircle2 
} from "lucide-react";

export default function BillingGuidePage() {
  return (
    <div className="space-y-6 max-w-5xl mx-auto animate-in fade-in duration-500">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-bold tracking-tight text-foreground flex items-center gap-2">
            <BookOpen className="w-5 h-5 text-primary" />
            Panduan Billing & Auto-Payment PPPoE
          </h2>
          <p className="text-muted-foreground mt-1 text-sm">
            Pelajari cara kerja sistem penagihan bulanan dan otomatisasi pembayaran (Moota/Cekmutasi) di NOC Sentinel v3.
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        
        {/* Kolom Kiri: Workflow */}
        <div className="space-y-6">
          <div className="bg-card border border-border rounded-lg p-5">
            <h2 className="text-lg font-semibold flex items-center gap-2 mb-4">
              <ShieldCheck className="w-5 h-5 text-green-500" />
              Alur Otomatisasi (Workflow)
            </h2>
            <div className="space-y-6 relative before:absolute before:inset-0 before:ml-[1.4rem] before:w-0.5 before:bg-border before:-z-10 z-0">
              
              <div className="flex gap-4">
                <div className="w-12 h-12 rounded-full bg-primary/20 text-primary flex items-center justify-center font-bold shadow-sm shrink-0 border border-primary/30 z-10 bg-card">1</div>
                <div>
                  <h4 className="font-medium text-foreground text-sm flex items-center gap-2">
                    <FileText className="w-4 h-4 text-blue-400" /> Buat Invoice Bulanan
                  </h4>
                  <p className="text-xs text-muted-foreground mt-1">
                    Gunakan tombol <strong>Bulk Create</strong> pada halaman Billing untuk membuat invoice serentak. Sistem akan otomatis menambahkan <span className="text-primary font-semibold">kode unik acak (1-999)</span> ke nominal tagihan (Misal: Rp 150.000 menjadi Rp 150.123).
                  </p>
                </div>
              </div>

              <div className="flex gap-4">
                <div className="w-12 h-12 rounded-full bg-primary/20 text-primary flex items-center justify-center font-bold shadow-sm shrink-0 border border-primary/30 z-10 bg-card">2</div>
                <div>
                  <h4 className="font-medium text-foreground text-sm flex items-center gap-2">
                    <MessageSquare className="w-4 h-4 text-green-400" /> API Kirim Broadcast WA
                  </h4>
                  <p className="text-xs text-muted-foreground mt-1">
                    Kirim tagihan massal via WhatsApp. Pelanggan akan melihat tagihan mereka dengan nominal mentah (bersama kode unik) dan instruksi transfer ke nomor rekening ISP Anda.
                  </p>
                </div>
              </div>

              <div className="flex gap-4">
                <div className="w-12 h-12 rounded-full bg-primary/20 text-primary flex items-center justify-center font-bold shadow-sm shrink-0 border border-primary/30 z-10 bg-card">3</div>
                <div>
                  <h4 className="font-medium text-foreground text-sm flex items-center gap-2">
                    <CreditCard className="w-4 h-4 text-orange-400" /> Pelanggan Transfer
                  </h4>
                  <p className="text-xs text-muted-foreground mt-1">
                    Pelanggan mentransfer uang sebesar Rp 150.123. Layanan robot mutasi pihak ketiga (Moota/Cekmutasi) mendeteksi uang masuk ke rekening Anda dalam hitungan menit.
                  </p>
                </div>
              </div>

              <div className="flex gap-4">
                <div className="w-12 h-12 rounded-full bg-primary/20 text-primary flex items-center justify-center font-bold shadow-sm shrink-0 border border-primary/30 z-10 bg-card">4</div>
                <div>
                  <h4 className="font-medium text-foreground text-sm flex items-center gap-2">
                    <CheckCircle2 className="w-4 h-4 text-teal-400" /> Auto-Unblock & Lunas
                  </h4>
                  <p className="text-xs text-muted-foreground mt-1">
                    Robot mutasi menembak <strong>Webhook NOC Sentinel</strong>. Sistem melunasi invoice tersebut secara otomatis, melepas isolir dari MikroTik, dan mengirim WA terima kasih ke pelanggan detik itu juga.
                  </p>
                </div>
              </div>

            </div>
          </div>
        </div>

        {/* Kolom Kanan: Setup moota */}
        <div className="space-y-6">
          <div className="bg-card border border-border rounded-lg p-5">
            <h2 className="text-lg font-semibold flex items-center gap-2 mb-4">
              <Plug className="w-5 h-5 text-indigo-400" />
              Setup Integrasi Webhook (Moota)
            </h2>
            <p className="text-xs text-muted-foreground mb-4">
              Agar sistem di atas berfungsi, Anda perlu mendaftar ke layanan Mutasi Bank seperti Moota.co atau sejenisnya, lalu mengatur API Webhook-nya mengarah ke server NOC Sentinel Anda.
            </p>
            
            <div className="space-y-4">
              <div className="bg-secondary/40 border border-border p-3 rounded-md">
                <label className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider block mb-1">Webhook URL Endpoint</label>
                <div className="font-mono text-xs bg-black text-green-400 p-2 rounded break-all select-all">
                  https://[DOMAIN-ANDA]/api/billing/webhook/moota
                </div>
                <p className="text-[10px] text-muted-foreground mt-2">
                  Masukkan URL di atas pada dashboard Moota Anda (Menu: Integrasi -&gt; Webhook). Pastikan domain server NOC Sentinel Anda bisa diakses secara publik (HTTPS).
                </p>
              </div>
              
              <div className="bg-secondary/40 border border-border p-3 rounded-md">
                <label className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider block mb-1">Pengaturan Mutasi Masuk (Credit)</label>
                <p className="text-xs text-muted-foreground mb-2">Sistem ini bekerja dengan mendeteksi mutasi bertipe <code>CR</code> (Credit / Uang Masuk). Setiap mutasi masuk akan dicocokkan dengan data <strong>Total Murni</strong> (termasuk kode unik) pada invoice yang berstatus `unpaid` atau `overdue`.</p>
                <div className="bg-amber-500/10 border border-amber-500/20 p-2 rounded text-xs text-amber-500/90 flex gap-2">
                  <div className="shrink-0 pt-0.5">⚠️</div>
                  <p><strong>Penting:</strong> Edukasi pelanggan Anda agar TIDAK membulatkan nominal saat transfer. Pecahan puluhan rupiah di belakang (kode unik) menjadi penentu utama agar proses bisa otomatis tanpa intervensi admin.</p>
                </div>
              </div>

            </div>
          </div>
          
          <div className="bg-card border border-border rounded-lg p-5">
            <h2 className="text-lg font-semibold flex items-center gap-2 mb-4">
              <Server className="w-5 h-5 text-cyan-500" />
              Sistem Auto-Isolasi MikroTik
            </h2>
            <p className="text-xs text-muted-foreground">
              Apakah fitur isolasi otomatis sudah berjalan? Ya. NOC Sentinel melakukan "Disable" secret PPPoE/Hotspot pada MikroTik secara otomatis ketika status invoice berubah menjadi <code>overdue</code> (jatuh tempo). Ketika pelanggan membayar dan Moota mendeteksinya, status invoice berubah jadi <code>paid</code> dan user kembali di-enable pada MikroTik.
            </p>
            <div className="mt-4 p-3 bg-secondary/30 border border-border rounded text-xs">
               Status Isolasi Manual dapat Anda pantau/kendalikan dari tabel tagihan di halaman <strong>Billing PPPoE</strong>.
            </div>
          </div>
        </div>

      </div>
    </div>
  );
}

