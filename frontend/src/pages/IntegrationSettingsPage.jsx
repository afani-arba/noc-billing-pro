import { useState, useEffect } from "react";
import api from "@/lib/api";
import {
  Webhook, MessageSquare, CreditCard,
  Save, Cable, Bot, Send
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { toast } from "sonner";

function IntegrationSection() {
  const [cfg, setCfg] = useState({ n8n_webhook_url: "", wa_gateway_type: "fonnte", wa_api_url: "https://api.fonnte.com/send", wa_token: "", wa_delay_ms: 10000 });
  const [saving, setSaving] = useState(false);
  const [testMode, setTestMode] = useState(false);
  const [testPhone, setTestPhone] = useState("");
  useEffect(() => { api.get("/billing/settings").then(r => setCfg(c => ({ ...c, ...r.data }))).catch(() => {}); }, []);
  const handleSave = async () => { setSaving(true); try { await api.put("/billing/settings", cfg); toast.success("Disimpan"); } catch { toast.error("Gagal"); } setSaving(false); };
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

export default function IntegrationSettingsPage() {
  return (
    <div className="space-y-4 pb-16">
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 rounded-sm bg-orange-500/10 flex items-center justify-center"><Cable className="w-5 h-5 text-orange-400" /></div>
        <div><h1 className="text-xl sm:text-2xl font-bold tracking-tight">Integrasi & Otomasi</h1><p className="text-xs sm:text-sm text-muted-foreground">Webhook N8N, WhatsApp Gateway, AI Chat, dan Telegram NOC</p></div>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        {[
          { icon: Webhook, color: "text-orange-400", bg: "bg-orange-500/10", title: "N8N Webhook", sub: "Notifikasi pembayaran ke N8N" },
          { icon: MessageSquare, color: "text-green-500", bg: "bg-green-500/10", title: "WhatsApp Gateway", sub: "Fonnte / Wablas / Custom API" },
          { icon: Bot, color: "text-violet-400", bg: "bg-violet-500/10", title: "AI Chat + Telegram", sub: "Gemini AI + Alert NOC" },
        ].map(s => (
          <div key={s.title} className="bg-card border border-border rounded-sm p-3 flex items-center gap-3">
            <div className={`w-8 h-8 rounded-sm ${s.bg} flex items-center justify-center flex-shrink-0`}><s.icon className={`w-4 h-4 ${s.color}`} /></div>
            <div><p className="text-xs font-semibold">{s.title}</p><p className="text-[10px] text-muted-foreground">{s.sub}</p></div>
          </div>
        ))}
      </div>
      <IntegrationSection />
      <AIIntegrationSection />
    </div>
  );
}


