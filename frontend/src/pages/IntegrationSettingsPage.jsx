import { useState, useEffect } from "react";
import api from "@/lib/api";
import {
  Webhook, MessageSquare, CreditCard,
  Save, Cable, Bot, Send, Cloud, RefreshCw, CheckCircle2, XCircle, Loader2, Eye, EyeOff,
  WifiOff, Smartphone, AlertTriangle, Activity, MessageCircle
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { toast } from "sonner";
import { useAllowedDevices } from "@/hooks/useAllowedDevices";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

function IntegrationSection({ selectedDevice }) {
  const [cfg, setCfg] = useState({ n8n_webhook_url: "", wa_gateway_type: "fonnte", wa_api_url: "https://api.fonnte.com/send", wa_token: "", wa_delay_ms: 10000 });
  const [saving, setSaving] = useState(false);
  const [testMode, setTestMode] = useState(false);
  const [testPhone, setTestPhone] = useState("");
  useEffect(() => { api.get("/billing/settings", { params: { device_id: selectedDevice } }).then(r => setCfg(c => ({ ...c, ...r.data }))).catch(() => {}); }, [selectedDevice]);
  const handleSave = async () => { setSaving(true); try { await api.put("/billing/settings", { ...cfg, device_id: selectedDevice }); toast.success("Disimpan"); } catch { toast.error("Gagal"); } setSaving(false); };
  const handleTestWa = async () => { if (!testPhone) return toast.error("Masukkan nomor"); setTestMode(true); try { await api.post("/notifications/test", { phone: testPhone, fonnte_token: cfg.wa_token }); toast.success("Test terkirim!"); } catch { toast.error("Gagal"); } setTestMode(false); };
  return (
    <div className="space-y-6">
      <div className="bg-card border border-border rounded-sm p-4 sm:p-6 space-y-4">
        <div className="flex items-center gap-3 border-b border-border/50 pb-4">
          <div className="w-8 h-8 rounded-sm bg-orange-500/10 flex items-center justify-center"><Webhook className="w-4 h-4 text-orange-400" /></div>
          <div><h2 className="text-base font-semibold">N8N Webhook</h2><p className="text-[10px] text-muted-foreground">Integrasikan NOC Sentinel dengan N8N untuk notifikasi pembayaran otomatis</p></div>
        </div>
        <div className="space-y-2">
          <Label className="text-xs text-muted-foreground">URL Webhook N8N (POST)</Label>
          <Input value={cfg.n8n_webhook_url || ""} onChange={e => setCfg(c => ({ ...c, n8n_webhook_url: e.target.value }))} placeholder="https://n8n.domain.com/webhook/payment" className="rounded-sm font-mono text-xs" />
        </div>
        <div className="space-y-2 pt-2">
          <div className="flex items-center gap-2 mb-1"><CreditCard className="w-4 h-4 text-blue-400" /><Label className="text-xs font-semibold">Moota Mutasi (Auto-Pay) — Webhook Endpoint</Label></div>
          <Input readOnly value={`${window.location.protocol}//${window.location.host}/api/v1/billing/webhook/moota`} className="rounded-sm font-mono text-[10px] bg-secondary/50 text-muted-foreground cursor-copy" onClick={e => { e.target.select(); document.execCommand("copy"); toast.success("Disalin"); }} />
        </div>
      </div>
      <div className="bg-card border border-border rounded-sm p-4 sm:p-6 space-y-4">
        <div className="flex items-center gap-3 border-b border-border/50 pb-4">
          <div className="w-8 h-8 rounded-sm bg-green-500/10 flex items-center justify-center"><MessageSquare className="w-4 h-4 text-green-500" /></div>
          <div><h2 className="text-base font-semibold">WhatsApp Gateway</h2><p className="text-[10px] text-muted-foreground">Konfigurasi gateway WA untuk notifikasi tagihan dan isolir</p></div>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
          <div className="space-y-1.5"><Label className="text-xs text-muted-foreground">Tipe Gateway</Label>
            <select value={cfg.wa_gateway_type} onChange={e => setCfg(c => ({ ...c, wa_gateway_type: e.target.value }))} className="flex h-9 w-full rounded-sm border border-input bg-background px-3 py-1 text-xs">
              <option value="fonnte">Fonnte API</option><option value="wablas">Wablas API</option><option value="custom">Custom URL</option>
            </select>
          </div>
          <div className="space-y-1.5"><Label className="text-xs text-muted-foreground">Delay Antar Pesan (ms)</Label><Input type="number" value={cfg.wa_delay_ms} onChange={e => setCfg(c => ({ ...c, wa_delay_ms: parseInt(e.target.value)||0 }))} className="rounded-sm text-xs" /></div>
          <div className="space-y-1.5 lg:col-span-2"><Label className="text-xs text-muted-foreground">API URL</Label><Input value={cfg.wa_api_url} onChange={e => setCfg(c => ({ ...c, wa_api_url: e.target.value }))} className="rounded-sm font-mono text-xs" /></div>
          <div className="space-y-1.5 sm:col-span-2 lg:col-span-3"><Label className="text-xs text-muted-foreground">Authorization Token / API Key</Label><Input value={cfg.wa_token} onChange={e => setCfg(c => ({ ...c, wa_token: e.target.value }))} type="password" placeholder="Token..." className="rounded-sm font-mono text-xs" /></div>
          <div className="space-y-1.5"><Label className="text-xs text-background">Test</Label><div className="flex gap-1"><Input value={testPhone} onChange={e => setTestPhone(e.target.value)} placeholder="08123..." className="rounded-sm text-xs" /><Button onClick={handleTestWa} disabled={testMode} variant="secondary" size="sm" className="rounded-sm h-9">Tes</Button></div></div>
        </div>
      </div>
      <div className="flex"><Button onClick={handleSave} disabled={saving} className="rounded-sm gap-2 bg-orange-600 hover:bg-orange-700 text-white"><Save className="w-3.5 h-3.5" />{saving ? "Menyimpan..." : "Simpan Pengaturan Integrasi"}</Button></div>
    </div>
  );
}

// ── Cloudflare Tunnel Section ──────────────────────────────────────────────
function CloudflareSection() {
  const [cfg, setCfg] = useState({ token: "", enabled: false, token_set: false });
  const [showToken, setShowToken] = useState(false);
  const [status, setStatus] = useState({ status: "unknown", enabled: false, has_token: false });
  const [saving, setSaving] = useState(false);
  const [restarting, setRestarting] = useState(false);

  const fetchAll = () => {
    api.get("/cloudflare/config").then(r => setCfg(c => ({ ...c, ...r.data }))).catch(() => {});
    api.get("/cloudflare/status").then(r => setStatus(r.data)).catch(() => {});
  };

  useEffect(() => {
    fetchAll();
    const iv = setInterval(fetchAll, 8000);
    return () => clearInterval(iv);
  }, []);

  const handleSave = async (enabled) => {
    setSaving(true);
    try {
      const payload = { token: cfg.token || "", enabled };
      const r = await api.put("/cloudflare/config", payload);
      toast.success(r.data.message || "Disimpan");
      setTimeout(fetchAll, 3000);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal menyimpan");
    }
    setSaving(false);
  };

  const handleRestart = async () => {
    setRestarting(true);
    try {
      const r = await api.post("/cloudflare/restart");
      toast.success(r.data.message);
      setTimeout(fetchAll, 8000);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal restart");
    }
    setRestarting(false);
  };

  const statusColor = {
    running: "text-green-400 bg-green-500/10 border-green-500/20",
    stopped: "text-yellow-400 bg-yellow-500/10 border-yellow-500/20",
    error: "text-red-400 bg-red-500/10 border-red-500/20",
    unknown: "text-muted-foreground bg-muted/40 border-border",
  }[status.status] || "text-muted-foreground bg-muted/40 border-border";

  const statusLabel = { running: "🟢 Aktif", stopped: "🟡 Berhenti", error: "🔴 Error", unknown: "⚪ Tidak Diketahui" }[status.status] || status.status;

  return (
    <div className="bg-card border border-border rounded-sm p-4 sm:p-6 space-y-4">
      <div className="flex items-center justify-between gap-3 border-b border-border/50 pb-4">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-sm bg-orange-500/10 flex items-center justify-center">
            <Cloud className="w-4 h-4 text-orange-400" />
          </div>
          <div>
            <h2 className="text-base font-semibold flex items-center gap-2">
              Cloudflare Tunnel
              <span className="text-[10px] bg-blue-500/10 text-blue-400 border border-blue-500/20 px-2 py-0.5 rounded-full">Zero-Trust Access</span>
            </h2>
            <p className="text-[10px] text-muted-foreground">Akses dashboard dari internet tanpa buka port — gratis via Cloudflare Zero Trust</p>
          </div>
        </div>
        <div className={`text-[10px] font-mono px-2 py-1 rounded border ${statusColor}`}>{statusLabel}</div>
      </div>

      {/* Info Card */}
      <div className="bg-blue-500/5 border border-blue-500/10 rounded-sm p-3 text-xs text-muted-foreground space-y-1">
        <p className="font-semibold text-blue-400">📋 Cara Mendapatkan Token:</p>
        <ol className="list-decimal list-inside space-y-0.5 text-[11px]">
          <li>Buka <span className="font-mono text-foreground">dash.cloudflare.com</span> → Zero Trust → Networks → Tunnels</li>
          <li>Buat tunnel baru, pilih <b>cloudflared</b></li>
          <li>Salin token dari perintah instalasi (panjang ~300 karakter)</li>
          <li>Paste di kolom token di bawah lalu klik <b>Aktifkan</b></li>
        </ol>
      </div>

      {/* Token Input */}
      <div className="space-y-1.5">
        <Label className="text-xs font-semibold">Tunnel Token</Label>
        <div className="flex gap-2">
          <div className="relative flex-1">
            <Input
              type={showToken ? "text" : "password"}
              value={cfg.token}
              onChange={e => setCfg(c => ({ ...c, token: e.target.value }))}
              placeholder={cfg.token_set ? "Token tersimpan (isi untuk ganti)" : "eyJhbGci..."}
              className="rounded-sm font-mono text-xs pr-10"
            />
            <button
              type="button"
              onClick={() => setShowToken(s => !s)}
              className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
            >
              {showToken ? <EyeOff className="w-3.5 h-3.5" /> : <Eye className="w-3.5 h-3.5" />}
            </button>
          </div>
        </div>
        {cfg.token_set && !cfg.token && (
          <p className="text-[10px] text-muted-foreground">Token sudah tersimpan — kosongkan untuk menggunakan token lama</p>
        )}
      </div>

      {/* Action Buttons */}
      <div className="flex flex-wrap gap-2 pt-1">
        <Button
          onClick={() => handleSave(true)}
          disabled={saving}
          className="gap-2 bg-orange-600 hover:bg-orange-700 text-white rounded-sm h-8 text-xs"
        >
          {saving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <CheckCircle2 className="w-3.5 h-3.5" />}
          {saving ? "Menyimpan..." : "Aktifkan Tunnel"}
        </Button>
        {status.enabled && (
          <>
            <Button
              onClick={() => handleSave(false)}
              disabled={saving}
              variant="outline"
              className="gap-2 rounded-sm h-8 text-xs border-red-500/30 text-red-400 hover:bg-red-500/10"
            >
              <XCircle className="w-3.5 h-3.5" /> Nonaktifkan
            </Button>
            <Button
              onClick={handleRestart}
              disabled={restarting}
              variant="outline"
              className="gap-2 rounded-sm h-8 text-xs"
            >
              {restarting ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <RefreshCw className="w-3.5 h-3.5" />}
              Restart
            </Button>
          </>
        )}
      </div>
    </div>
  );
}

function AIIntegrationSection() {
  const [cfg, setCfg] = useState({ gemini_api_key: "", telegram_bot_token: "", telegram_chat_id_noc: "" });
  const [aiCfg, setAiCfg] = useState({ model: "gemini-1.5-flash", system_prompt: "", company_name: "", ai_name: "Asisten AI", payment_info: "", extra_context: "", temperature: 0.7, max_tokens: 1000, feature_modem_reprovision: true, feature_cable_alert: true, feature_needs_cs: true });
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);

  useEffect(() => {
    api.get("/system/integrations").then(r => setCfg(c => ({ ...c, ...r.data }))).catch(() => {});
    api.get("/system/ai-chat-config").then(r => setAiCfg(c => ({ ...c, ...r.data }))).catch(() => {});
  }, []);

  const handleSave = async () => {
    setSaving(true);
    try {
      await api.put("/system/integrations", cfg);
      await api.put("/system/ai-chat-config", aiCfg);
      toast.success("Konfigurasi AI & Telegram disimpan ✓");
    } catch { toast.error("Gagal menyimpan"); }
    setSaving(false);
  };

  const handleTestTelegram = async () => {
    if (!cfg.telegram_bot_token || !cfg.telegram_chat_id_noc) return toast.error("Token dan Chat ID NOC wajib diisi");
    setTesting(true);
    try {
      const resp = await fetch(`https://api.telegram.org/bot${cfg.telegram_bot_token}/sendMessage`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ chat_id: cfg.telegram_chat_id_noc, text: "✅ Test koneksi Telegram dari NOC Sentinel berhasil!" })
      });
      const data = await resp.json();
      if (data.ok) toast.success("Pesan test Telegram terkirim!");
      else toast.error(`Gagal: ${data.description}`);
    } catch { toast.error("Gagal koneksi ke Telegram API"); }
    setTesting(false);
  };

  return (
    <div className="bg-card border border-border rounded-sm p-4 sm:p-6 space-y-4 shadow-sm relative overflow-hidden">
      <div className="flex items-center gap-3 border-b border-border/50 pb-4">
        <div className="w-8 h-8 rounded-sm bg-violet-500/10 flex items-center justify-center">
          <Bot className="w-4 h-4 text-violet-400" />
        </div>
        <div>
          <h2 className="text-base sm:text-lg font-semibold flex items-center gap-2">
            AI Chat (Gemini) & Telegram NOC
            <span className="text-[10px] bg-violet-500/10 text-violet-400 border border-violet-500/20 px-2 py-0.5 rounded-full">In-App Chat</span>
          </h2>
          <p className="text-[10px] sm:text-xs text-muted-foreground">
            Aktifkan AI otomatis untuk chat portal pelanggan. Alert Telegram untuk deteksi gangguan fisik.
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 relative z-10">
        {/* Gemini */}
        <div className="space-y-2">
          <Label className="text-xs font-semibold flex items-center gap-1.5">
            <Bot className="w-3.5 h-3.5 text-violet-400" /> Google Gemini API Key
            <span className="text-[10px] text-muted-foreground font-normal">(Gratis di aistudio.google.com)</span>
          </Label>
          <Input
            value={cfg.gemini_api_key || ""}
            onChange={e => setCfg(c => ({ ...c, gemini_api_key: e.target.value }))}
            type="password"
            placeholder="AIza..."
            className="rounded-sm font-mono text-xs max-w-2xl"
          />
        </div>

        {/* Custom AI Behavior */}
        <div className="p-4 bg-violet-500/5 rounded-md border border-violet-500/10 space-y-4">
          <h3 className="text-sm font-semibold flex items-center gap-2 border-b border-violet-500/10 pb-2"><Bot className="w-4 h-4 text-violet-400"/> Perilaku AI & Personalisasi (Bebas Kustom)</h3>
          
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 max-w-5xl">
            <div className="space-y-1.5">
              <Label className="text-[11px] text-muted-foreground">Nama Tampilan AI di Chat</Label>
              <Input value={aiCfg.ai_name || ""} onChange={e => setAiCfg(c => ({...c, ai_name: e.target.value}))} placeholder="Niken" className="rounded-sm text-xs" />
            </div>
            <div className="space-y-1.5">
              <Label className="text-[11px] text-muted-foreground">Model AI (Bisa diisi manual)</Label>
              <Input list="gemini-models" value={aiCfg.model || "gemini-1.5-flash"} onChange={e => setAiCfg(c => ({...c, model: e.target.value}))} placeholder="gemini-2.5-flash" className="rounded-sm text-xs" />
              <datalist id="gemini-models">
                <option value="gemini-2.5-flash">Gemini 2.5 Flash</option>
                <option value="gemini-2.0-flash">Gemini 2.0 Flash</option>
                <option value="gemini-1.5-pro">Gemini 1.5 Pro</option>
                <option value="gemini-1.5-flash">Gemini 1.5 Flash</option>
              </datalist>
            </div>
            <div className="space-y-1.5">
              <Label className="text-[11px] text-muted-foreground">Suhu (Temperature) AI</Label>
              <Input type="number" step="0.1" value={aiCfg.temperature || 0.7} onChange={e => setAiCfg(c => ({ ...c, temperature: parseFloat(e.target.value) }))} className="rounded-sm text-xs" />
            </div>
            <div className="space-y-1.5">
              <Label className="text-[11px] text-muted-foreground">Max Tokens (Panjang Jawaban)</Label>
              <Input type="number" step="100" value={aiCfg.max_tokens || 1000} onChange={e => setAiCfg(c => ({ ...c, max_tokens: parseInt(e.target.value) }))} className="rounded-sm text-xs" />
            </div>
          </div>

          <div className="space-y-2 pt-1 border-t border-violet-500/10 mt-3 pt-3">
            <Label className="text-[12px] font-semibold text-foreground">Kustomisasi Instruksi Sistem (System Prompt / Persona AI)</Label>
            <textarea value={aiCfg.system_prompt || ""} onChange={e => setAiCfg(c => ({ ...c, system_prompt: e.target.value }))} rows={6} placeholder="Contoh: Kamu adalah Aji, teknisi ramah dari ISP Arba Nusantara. Jawab pertanyaan dengan sopan menggunakan sapaan Kakak. Jika ditanya cara bayar, arahkan ke menu Tagihan di aplikasi." className="w-full text-xs p-3 rounded-sm border border-input bg-background outline-none hover:border-violet-500/50 focus:border-violet-500 focus:ring-1 focus:ring-violet-500 resize-y my-1 transition-all" />
            <p className="text-[11px] text-muted-foreground bg-secondary/50 p-2 rounded-sm italic border-l-2 border-violet-400">
              💡 <b>Catatan Penting:</b> Anda bebas menuliskan sifat/instruksi apa saja. Aturan teknis otomatis NOC (seperti reset modem via TR-069, eskalasi CS, alert kabel putus) <b>akan disisipkan secara ghaib</b> di akhir instruksi ini oleh sistem. Jangan khawatir automasi akan rusak akibat mengubah instruksi di sini.
            </p>
          </div>

          <div className="space-y-2 pt-3 border-t border-violet-500/10">
            <Label className="text-[12px] font-semibold text-foreground">Integrasi Fitur AI Otomatis (Self-Healing)</Label>
            <div className="space-y-2.5 mt-2 bg-background p-3 rounded-sm border border-border">
              <label className="flex items-center gap-3 text-xs text-foreground cursor-pointer group">
                <input type="checkbox" checked={aiCfg.feature_modem_reprovision} onChange={e => setAiCfg(c => ({...c, feature_modem_reprovision: e.target.checked}))} className="rounded text-violet-500 w-4 h-4 cursor-pointer focus:ring-violet-500/20" />
                <span><span className="font-semibold text-violet-400">🔄 Reset Modem Otomatis:</span> AI akan kirim ulang konfigurasi PPPoE+WiFi via GenieACS otomatis jika dia mendeteksi masalah reset modem.</span>
              </label>
              <label className="flex items-center gap-3 text-xs text-foreground cursor-pointer group">
                <input type="checkbox" checked={aiCfg.feature_cable_alert} onChange={e => setAiCfg(c => ({...c, feature_cable_alert: e.target.checked}))} className="rounded text-violet-500 w-4 h-4 cursor-pointer focus:ring-violet-500/20" />
                <span><span className="font-semibold text-red-400">📡 Deteksi Kabel Putus (LOS):</span> Jika pelanggan kirim foto lampu PON merah/LOS, AI otomatis kirim Alert Telegram ke grup NOC.</span>
              </label>
              <label className="flex items-center gap-3 text-xs text-foreground cursor-pointer group">
                <input type="checkbox" checked={aiCfg.feature_needs_cs} onChange={e => setAiCfg(c => ({...c, feature_needs_cs: e.target.checked}))} className="rounded text-violet-500 w-4 h-4 cursor-pointer focus:ring-violet-500/20" />
                <span><span className="font-semibold text-blue-400">👤 Eskalasi Otomatis ke CS Manusia:</span> Indikator menyala (warna merah di Dashboard Admin) jika obrolan buntu dan butuh bantuan manusia.</span>
              </label>
            </div>
          </div>
        </div>

        {/* Telegram */}
        <div className="space-y-3 pt-4 border-t border-border/50">
          <Label className="text-xs font-semibold flex items-center gap-1.5">
            <Send className="w-3.5 h-3.5 text-blue-400" /> Telegram Bot — Alert NOC
          </Label>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 max-w-2xl">
            <div className="space-y-1.5">
              <Label className="text-[11px] text-muted-foreground">Bot Token (dari @BotFather)</Label>
              <Input
                value={cfg.telegram_bot_token || ""}
                onChange={e => setCfg(c => ({ ...c, telegram_bot_token: e.target.value }))}
                type="password"
                placeholder="1234567890:ABCdef..."
                className="rounded-sm font-mono text-xs"
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-[11px] text-muted-foreground">Chat ID Grup NOC</Label>
              <div className="flex gap-2">
                <Input
                  value={cfg.telegram_chat_id_noc || ""}
                  onChange={e => setCfg(c => ({ ...c, telegram_chat_id_noc: e.target.value }))}
                  placeholder="-100123456789"
                  className="rounded-sm font-mono text-xs"
                />
                <Button onClick={handleTestTelegram} disabled={testing} variant="secondary" size="sm" className="h-9 rounded-sm whitespace-nowrap">
                  {testing ? "..." : "Test"}
                </Button>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className="flex pt-2">
        <Button onClick={handleSave} disabled={saving} className="rounded-sm gap-2 bg-violet-600 hover:bg-violet-700 text-white shadow-sm">
          <Save className="w-3.5 h-3.5" /> {saving ? "Menyimpan..." : "Simpan Konfigurasi AI & Telegram"}
        </Button>
      </div>
    </div>
  );
}

// ── Billing Settings Section (WA Templates, Auto Isolir, FCM, Payment Gateway) ─
function BillingSettingsSection({ selectedDevice }) {
  const [settings, setSettings] = useState({
    wa_template_unpaid: "", wa_template_paid: "", wa_template_h1: "", wa_template_isolir: "",
    fcm_template_h3: "", fcm_template_h2: "", fcm_template_h1: "", fcm_template_due: "",
    fcm_template_overdue: "", fcm_template_paid: "", fcm_template_network_error: "",
    auto_isolir_enabled: false, auto_isolir_method: "whatsapp", auto_isolir_time: "00:05",
    auto_isolir_grace_days: 0, moota_webhook_secret: "", n8n_webhook_url: "",
    payment_gateway_enabled: false, default_payment_provider: "xendit",
    xendit_secret_key: "", xendit_webhook_token: "", xendit_va_bank: "BNI", xendit_enabled: false,
    bca_client_id: "", bca_client_secret: "", bca_company_code: "", bca_api_key: "", bca_api_secret: "", bca_enabled: false,
    bri_client_id: "", bri_client_secret: "", bri_institution_code: "", bri_enabled: false,
  });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setLoading(true);
    api.get("/billing/settings", { params: { device_id: selectedDevice } })
      .then(r => setSettings(p => ({ ...p, ...r.data })))
      .catch(() => toast.error("Gagal memuat pengaturan billing"))
      .finally(() => setLoading(false));
  }, [selectedDevice]);

  const handleSave = async () => {
    setSaving(true);
    try { await api.put("/billing/settings", { ...settings, device_id: selectedDevice }); toast.success("Pengaturan Billing disimpan ✓"); }
    catch { toast.error("Gagal menyimpan"); }
    setSaving(false);
  };

  const VARS = "{customer_name} {invoice_number} {package_name} {period} {total} {due_date} {payment_method}";

  if (loading) return <div className="bg-card border border-border rounded-sm p-6 text-center text-sm text-muted-foreground animate-pulse">Memuat konfigurasi billing...</div>;

  return (
    <div className="space-y-4">

      {/* WA Templates */}
      <div className="bg-card border border-border rounded-sm p-4 sm:p-6 space-y-4">
        <div className="flex items-center gap-3 border-b border-border/50 pb-4">
          <div className="w-8 h-8 rounded-sm bg-green-500/10 flex items-center justify-center"><MessageCircle className="w-4 h-4 text-green-500" /></div>
          <div>
            <h2 className="text-base font-semibold">Template Pesan WhatsApp</h2>
            <p className="text-[10px] text-muted-foreground">Variabel: <code className="bg-secondary/50 px-1 rounded text-primary text-[10px]">{VARS}</code></p>
          </div>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {[
            ["wa_template_unpaid", "Tagihan Baru (Unpaid)"],
            ["wa_template_paid", "Pembayaran Lunas"],
            ["wa_template_h1", "Pengingat H-1"],
            ["wa_template_isolir", "Layanan Terisolir"],
          ].map(([key, label]) => (
            <div key={key} className="space-y-1.5 bg-secondary/10 p-3 rounded-sm border border-border/50">
              <label className="text-xs font-semibold text-foreground">{label}</label>
              <textarea
                value={settings[key] || ""}
                onChange={e => setSettings({ ...settings, [key]: e.target.value })}
                className="w-full h-20 text-xs rounded-sm border border-input bg-background p-2 text-foreground resize-y font-mono mt-1 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
              />
            </div>
          ))}
        </div>
        <button onClick={handleSave} disabled={saving} className="inline-flex items-center gap-2 text-xs h-8 px-3 rounded-sm bg-green-600 hover:bg-green-700 text-white disabled:opacity-50 transition-colors">
          <Save className="w-3.5 h-3.5" />{saving ? "Menyimpan..." : "Simpan Template WA"}
        </button>
      </div>

      {/* Auto Isolir */}
      <div className="bg-card border border-border rounded-sm p-4 sm:p-6 space-y-4">
        <div className="flex items-center gap-3 border-b border-border/50 pb-4">
          <div className="w-8 h-8 rounded-sm bg-orange-500/10 flex items-center justify-center"><WifiOff className="w-4 h-4 text-orange-400" /></div>
          <div><h2 className="text-base font-semibold">Auto Isolir</h2><p className="text-[10px] text-muted-foreground">Putus otomatis pelanggan overdue sesuai jadwal</p></div>
        </div>
        <label className="flex items-center gap-2 cursor-pointer">
          <input type="checkbox" checked={settings.auto_isolir_enabled || false} onChange={e => setSettings({ ...settings, auto_isolir_enabled: e.target.checked })} className="rounded" />
          <span className="text-sm font-medium">Aktifkan Auto Isolir Pelanggan</span>
        </label>
        {settings.auto_isolir_enabled && (
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 pl-6">
            <div className="space-y-1.5">
              <label className="text-xs text-muted-foreground">Metode Notifikasi</label>
              <select value={settings.auto_isolir_method || "whatsapp"} onChange={e => setSettings({ ...settings, auto_isolir_method: e.target.value })}
                className="w-full h-8 text-xs rounded-sm border border-border bg-secondary px-2 text-foreground">
                <option value="whatsapp">Hanya WhatsApp</option>
                <option value="ssid">Hanya Ganti SSID</option>
                <option value="both">WA + Ganti SSID</option>
              </select>
            </div>
            <div className="space-y-1.5">
              <label className="text-xs text-muted-foreground">Jam Eksekusi Harian</label>
              <input type="time" value={settings.auto_isolir_time || "00:05"} onChange={e => setSettings({ ...settings, auto_isolir_time: e.target.value })}
                className="w-full h-8 text-xs rounded-sm border border-border bg-secondary px-2 text-foreground font-mono" />
            </div>
            <div className="space-y-1.5">
              <label className="text-xs text-muted-foreground">Toleransi (Hari)</label>
              <input type="number" min="0" value={settings.auto_isolir_grace_days ?? 0} onChange={e => setSettings({ ...settings, auto_isolir_grace_days: Number(e.target.value) })}
                className="w-full h-8 text-xs rounded-sm border border-border bg-secondary px-2 text-foreground font-mono" />
            </div>
          </div>
        )}
        <button onClick={handleSave} disabled={saving} className="inline-flex items-center gap-2 text-xs h-8 px-3 rounded-sm border border-orange-500/30 text-orange-400 hover:bg-orange-500/10 transition-colors">
          <Save className="w-3.5 h-3.5" />{saving ? "Menyimpan..." : "Simpan Isolir"}
        </button>
      </div>

      {/* FCM Templates */}
      <div className="bg-card border border-border rounded-sm p-4 sm:p-6 space-y-4">
        <div className="flex items-center gap-3 border-b border-border/50 pb-4">
          <div className="w-8 h-8 rounded-sm bg-purple-500/10 flex items-center justify-center"><Smartphone className="w-4 h-4 text-purple-400" /></div>
          <div><h2 className="text-base font-semibold">Template Push Notification (FCM)</h2><p className="text-[10px] text-muted-foreground">Notifikasi aplikasi portal pelanggan Android</p></div>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {[
            ["fcm_template_h3", "H-3 (3 Hari Sebelum JT)"],
            ["fcm_template_h2", "H-2"],
            ["fcm_template_h1", "H-1 (Besok JT)"],
            ["fcm_template_due", "Hari Jatuh Tempo"],
            ["fcm_template_overdue", "Terisolir / Overdue"],
            ["fcm_template_paid", "Pembayaran Lunas"],
          ].map(([key, label]) => (
            <div key={key} className="space-y-1.5 bg-secondary/10 p-3 rounded-sm border border-border/50">
              <label className="text-xs font-semibold text-foreground">{label}</label>
              <textarea
                value={settings[key] || ""}
                onChange={e => setSettings({ ...settings, [key]: e.target.value })}
                className="w-full h-16 text-xs rounded-sm border border-input bg-background p-2 text-foreground resize-y font-mono mt-1"
              />
            </div>
          ))}
          <div className="space-y-1.5 bg-secondary/10 p-3 rounded-sm border border-orange-500/30 md:col-span-2">
            <label className="text-xs font-semibold text-orange-400 flex items-center gap-2">
              <AlertTriangle className="w-3.5 h-3.5" /> Gangguan Jaringan (Push Manual)
            </label>
            <textarea
              value={settings.fcm_template_network_error || ""}
              onChange={e => setSettings({ ...settings, fcm_template_network_error: e.target.value })}
              className="w-full h-12 text-xs rounded-sm border border-orange-500/30 bg-orange-500/5 p-2 text-foreground resize-y font-mono mt-1"
            />
            <button
              onClick={async () => {
                if(!confirm("Kirim Push Notifikasi gangguan ke SEMUA pelanggan sekarang?")) return;
                try { const r = await api.post("/billing/push/network-error"); r.data.ok ? toast.success(r.data.message) : toast.warning(r.data.message); }
                catch(e) { toast.error(e.response?.data?.detail || "Gagal"); }
              }}
              className="inline-flex items-center gap-1 text-[10px] h-7 px-2 rounded-sm border border-orange-500/30 text-orange-400 hover:bg-orange-500/10 transition-colors mt-1"
            >
              <Send className="w-3 h-3" /> Push Manual ke Semua Pelanggan
            </button>
          </div>
        </div>
        <button onClick={handleSave} disabled={saving} className="inline-flex items-center gap-2 text-xs h-8 px-3 rounded-sm border border-purple-500/30 text-purple-400 hover:bg-purple-500/10 transition-colors">
          <Save className="w-3.5 h-3.5" />{saving ? "Menyimpan..." : "Simpan Template FCM"}
        </button>
      </div>

      {/* Payment Gateway */}
      <div className="bg-card border border-border rounded-sm p-4 sm:p-6 space-y-4">
        <div className="flex items-center gap-3 border-b border-border/50 pb-4">
          <div className="w-8 h-8 rounded-sm bg-emerald-500/10 flex items-center justify-center"><CreditCard className="w-4 h-4 text-emerald-400" /></div>
          <div><h2 className="text-base font-semibold">Payment Gateway</h2><p className="text-[10px] text-muted-foreground">Xendit (VA/QRIS), BCA SNAP, BRI BRIVA</p></div>
        </div>
        <label className="flex items-center gap-2 cursor-pointer">
          <input type="checkbox" checked={!!settings.payment_gateway_enabled} onChange={e => setSettings({ ...settings, payment_gateway_enabled: e.target.checked })} className="w-4 h-4 rounded" />
          <span className="text-xs font-medium">Aktifkan Payment Gateway</span>
        </label>
        {settings.payment_gateway_enabled && (
          <div className="space-y-4">
            <div className="p-3 bg-blue-500/5 border border-blue-500/20 rounded-sm text-[10px] text-blue-300 space-y-1">
              <p className="font-semibold">Webhook URLs — Daftarkan ke dashboard provider:</p>
              <p className="font-mono">Xendit: <span className="text-sky-300">[domain]/api/webhook/xendit</span></p>
              <p className="font-mono">BCA SNAP: <span className="text-sky-300">[domain]/api/webhook/bca</span></p>
              <p className="font-mono">BRI BRIVA: <span className="text-sky-300">[domain]/api/webhook/bri</span></p>
            </div>
            {/* Xendit */}
            <div className="border border-border/50 rounded-sm p-3 space-y-3">
              <div className="flex items-center gap-2">
                <input type="checkbox" checked={!!settings.xendit_enabled} onChange={e => setSettings({ ...settings, xendit_enabled: e.target.checked })} className="w-3.5 h-3.5" />
                <label className="text-xs font-semibold text-emerald-400">Xendit (VA + QRIS + E-Wallet)</label>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                {[["xendit_secret_key","Secret Key","xnd_production_..."],["xendit_webhook_token","Webhook Token","token dari dashboard"]].map(([k,lb,ph]) => (
                  <div key={k} className="space-y-1">
                    <label className="text-[10px] text-muted-foreground">{lb}</label>
                    <input type="password" value={settings[k] || ""} onChange={e => setSettings({ ...settings, [k]: e.target.value })}
                      placeholder={ph} className="w-full h-7 text-xs rounded-sm border border-border bg-background px-2 font-mono" />
                  </div>
                ))}
                <div className="space-y-1">
                  <label className="text-[10px] text-muted-foreground">Bank VA Default</label>
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
                <input type="checkbox" checked={!!settings.bca_enabled} onChange={e => setSettings({ ...settings, bca_enabled: e.target.checked })} className="w-3.5 h-3.5" />
                <label className="text-xs font-semibold text-blue-400">BCA SNAP (Virtual Account BCA)</label>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {[["bca_client_id","Client ID"],["bca_client_secret","Client Secret"],["bca_company_code","Company Code"],["bca_api_key","API Key"],["bca_api_secret","API Secret"]].map(([k,lb]) => (
                  <div key={k} className="space-y-1">
                    <label className="text-[10px] text-muted-foreground">{lb}</label>
                    <input type="password" value={settings[k] || ""} onChange={e => setSettings({ ...settings, [k]: e.target.value })}
                      className="w-full h-7 text-xs rounded-sm border border-border bg-background px-2 font-mono" />
                  </div>
                ))}
              </div>
            </div>
            {/* BRI */}
            <div className="border border-border/50 rounded-sm p-3 space-y-3">
              <div className="flex items-center gap-2">
                <input type="checkbox" checked={!!settings.bri_enabled} onChange={e => setSettings({ ...settings, bri_enabled: e.target.checked })} className="w-3.5 h-3.5" />
                <label className="text-xs font-semibold text-sky-400">BRI BRIVA (Virtual Account BRI)</label>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {[["bri_client_id","Client ID"],["bri_client_secret","Client Secret"],["bri_institution_code","Institution Code"]].map(([k,lb]) => (
                  <div key={k} className="space-y-1">
                    <label className="text-[10px] text-muted-foreground">{lb}</label>
                    <input type="password" value={settings[k] || ""} onChange={e => setSettings({ ...settings, [k]: e.target.value })}
                      className="w-full h-7 text-xs rounded-sm border border-border bg-background px-2 font-mono" />
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}
        <button onClick={handleSave} disabled={saving} className="inline-flex items-center gap-2 text-xs h-8 px-3 rounded-sm border border-emerald-500/30 text-emerald-400 hover:bg-emerald-500/10 transition-colors">
          <Save className="w-3.5 h-3.5" />{saving ? "Menyimpan..." : "Simpan Konfigurasi Gateway"}
        </button>
      </div>
    </div>
  );
}

export default function IntegrationSettingsPage() {
  const { devices, isLocked, defaultDeviceId, loading: loadingDevices } = useAllowedDevices();
  const [selectedDevice, setSelectedDevice] = useState("GLOBAL");

  useEffect(() => {
    if (isLocked && defaultDeviceId) setSelectedDevice(defaultDeviceId);
  }, [isLocked, defaultDeviceId]);

  return (
    <div className="space-y-4 pb-16">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-sm bg-orange-500/10 flex items-center justify-center"><Cable className="w-5 h-5 text-orange-400" /></div>
          <div><h1 className="text-xl sm:text-2xl font-bold tracking-tight">Integrasi & Otomasi</h1><p className="text-xs sm:text-sm text-muted-foreground">Webhook, WhatsApp, AI, Telegram NOC, Notifikasi Billing & Payment Gateway</p></div>
        </div>

        {/* Global Filter */}
        <div className="flex items-center gap-2">
            {loadingDevices ? (
              <div className="h-9 px-3 rounded-sm border border-border flex items-center text-xs text-muted-foreground bg-card"><Loader2 className="w-3.5 h-3.5 animate-spin mr-2"/> Memuat router...</div>
            ) : isLocked ? (
              <div className="h-9 px-3 rounded-sm border border-border flex items-center text-xs text-foreground bg-card/50">
                  <span className="truncate max-w-[150px]">{devices.find(d => d.id === selectedDevice)?.name || "Router"}</span>
                  <span className="ml-2 text-[9px] bg-secondary px-1 py-0.5 rounded text-muted-foreground">Terkunci</span>
              </div>
            ) : (
                <Select value={selectedDevice} onValueChange={setSelectedDevice}>
                    <SelectTrigger className="w-full sm:w-[240px] h-9 bg-card text-xs">
                        <SelectValue placeholder="Pilih Router..." />
                    </SelectTrigger>
                    <SelectContent>
                        <SelectItem value="GLOBAL"><span className="font-semibold text-primary">🌍 Pengaturan Pusat (Global)</span></SelectItem>
                        {devices.map(d => (
                            <SelectItem key={d.id} value={d.id}>{d.name}</SelectItem>
                        ))}
                    </SelectContent>
                </Select>
            )}
        </div>
      </div>
      <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
        {[
          { icon: Webhook, color: "text-orange-400", bg: "bg-orange-500/10", title: "N8N Webhook", sub: "Notifikasi ke N8N" },
          { icon: MessageSquare, color: "text-green-500", bg: "bg-green-500/10", title: "WhatsApp Gateway", sub: "Fonnte / Wablas" },
          { icon: Cloud, color: "text-orange-400", bg: "bg-orange-500/10", title: "Cloudflare Tunnel", sub: "Akses publik" },
          { icon: Bot, color: "text-violet-400", bg: "bg-violet-500/10", title: "AI Chat + Telegram", sub: "Gemini AI + NOC" },
          { icon: CreditCard, color: "text-emerald-400", bg: "bg-emerald-500/10", title: "Billing & PG", sub: "Template & Gateway" },
        ].map(s => (
          <div key={s.title} className="bg-card border border-border rounded-sm p-3 flex items-center gap-3">
            <div className={`w-8 h-8 rounded-sm ${s.bg} flex items-center justify-center flex-shrink-0`}><s.icon className={`w-4 h-4 ${s.color}`} /></div>
            <div><p className="text-xs font-semibold">{s.title}</p><p className="text-[10px] text-muted-foreground">{s.sub}</p></div>
          </div>
        ))}
      </div>
      <IntegrationSection selectedDevice={selectedDevice} />
      <CloudflareSection />
      <AIIntegrationSection />
      <div>
        <div className="flex flex-col sm:flex-row sm:items-center justify-between mb-4 mt-6 gap-2">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-sm bg-emerald-500/10 flex items-center justify-center"><Activity className="w-4 h-4 text-emerald-400" /></div>
            <div>
              <h2 className="text-base font-semibold">Konfigurasi Notifikasi & Pembayaran Billing</h2>
              <p className="text-xs text-muted-foreground">Template WA, Auto Isolir, Template Push Notification, Payment Gateway</p>
            </div>
          </div>
          {selectedDevice === "GLOBAL" ? (
            <Badge variant="outline" className="text-[10px] sm:self-start mt-1 sm:mt-0 font-normal bg-blue-500/10 text-blue-400 border-blue-500/20 px-2 py-0.5">Memodifikasi: 🌍 Pengaturan Pusat (Global)</Badge>
          ) : (
            <Badge variant="outline" className="text-[10px] sm:self-start mt-1 sm:mt-0 font-normal bg-orange-500/10 text-orange-400 border-orange-500/20 px-2 py-0.5">Memodifikasi Spesifik: {devices.find(d => d.id === selectedDevice)?.name}</Badge>
          )}
        </div>
        <BillingSettingsSection selectedDevice={selectedDevice} />
      </div>
    </div>
  );
}


