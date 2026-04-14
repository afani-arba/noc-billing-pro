import { useState, useEffect } from "react";
import api from "@/lib/api";
import { Bell, Plus, Trash2, Send, Save, Phone, Settings2, AlertTriangle, Info, Activity, Network, MessageSquare, Bot } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { toast } from "sonner";

function PhoneRow({ r, idx, onChange, onRemove }) {
  return (
    <div className="flex items-center gap-2 p-2 rounded-sm bg-secondary/30 border border-border/50">
      <div className="flex-1 grid grid-cols-1 sm:grid-cols-2 gap-2">
        <Input
          value={r.name}
          onChange={e => onChange(idx, "name", e.target.value)}
          placeholder="Nama (opsional)"
          className="rounded-sm bg-background text-xs h-8"
        />
        <Input
          value={r.phone}
          onChange={e => onChange(idx, "phone", e.target.value)}
          placeholder="628xxxxxxxxxx"
          className="rounded-sm bg-background font-mono text-xs h-8"
        />
      </div>
      <button
        className={`w-8 h-8 rounded-sm flex items-center justify-center text-xs border transition-colors ${r.active ? "bg-green-500/10 text-green-500 border-green-500/20 hover:bg-green-500/20" : "bg-secondary text-muted-foreground border-border"}`}
        onClick={() => onChange(idx, "active", !r.active)}
        title={r.active ? "Nonaktifkan" : "Aktifkan"}
      >
        {r.active ? "âœ“" : "âœ—"}
      </button>
      <Button variant="ghost" size="icon" className="h-8 w-8 text-destructive" onClick={() => onRemove(idx)}>
        <Trash2 className="w-3.5 h-3.5" />
      </Button>
    </div>
  );
}

const DEFAULT_SETTINGS = {
  enabled: false,
  fonnte_token: "",
  recipients: [],
  notify_offline: true,
  notify_cpu: true,
  notify_ping_high: false,
  notify_interface_down: false,
  watched_interfaces: [],
  thresholds: { cpu: 80, ping_ms: 100 },
  telegram_enabled: false,
  telegram_bot_token: "",
  telegram_chat_ids: [],
};

export default function NotificationsPage() {
  const [settings, setSettings] = useState(DEFAULT_SETTINGS);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testPhone, setTestPhone] = useState("");
  const [sendingTest, setSendingTest] = useState(false);

  useEffect(() => {
    api.get("/notifications/settings")
      .then(r => { setSettings({ ...DEFAULT_SETTINGS, ...r.data }); setLoading(false); })
      .catch(() => setLoading(false));
  }, []);

  const handleSave = async () => {
    setSaving(true);
    try {
      await api.put("/notifications/settings", settings);
      toast.success("Pengaturan notifikasi disimpan");
    } catch (e) {
      toast.error(e.response?.data?.detail || "Gagal menyimpan");
    }
    setSaving(false);
  };

  const handleTest = async () => {
    if (!testPhone) { toast.error("Masukkan nomor HP tujuan test"); return; }
    setSendingTest(true);
    try {
      const r = await api.post("/notifications/test", {
        phone: testPhone,
        fonnte_token: settings.fonnte_token,
      });
      toast.success(r.data.message || "Test berhasil dikirim!");
    } catch (e) {
      toast.error(e.response?.data?.detail || "Test gagal. Periksa token dan nomor HP.");
    }
    setSendingTest(false);
  };

  const addRecipient = () => {
    setSettings(s => ({ ...s, recipients: [...s.recipients, { phone: "", name: "", active: true }] }));
  };

  const updateRecipient = (idx, field, val) => {
    const recs = [...settings.recipients];
    recs[idx] = { ...recs[idx], [field]: val };
    setSettings(s => ({ ...s, recipients: recs }));
  };

  const removeRecipient = (idx) => {
    setSettings(s => ({ ...s, recipients: s.recipients.filter((_, i) => i !== idx) }));
  };

  // Interface list for interface-down monitoring
  const [devices, setDevices] = useState([]);
  const [ifaceDevice, setIfaceDevice] = useState("");
  const [interfaces, setInterfaces] = useState([]);
  const [loadingIfaces, setLoadingIfaces] = useState(false);

  useEffect(() => {
    api.get("/devices").then(r => {
      const onlineDevs = (r.data || []).filter(d => d.status === "online");
      setDevices(onlineDevs);
      if (onlineDevs.length > 0 && !ifaceDevice) setIfaceDevice(onlineDevs[0].id);
    }).catch(() => {});
  }, []);

  const fetchInterfaces = async (devId) => {
    if (!devId) return;
    setLoadingIfaces(true);
    try {
      const r = await api.get(`/devices/${devId}/interfaces`);
      setInterfaces((r.data || []).map(i => i.name).filter(Boolean));
    } catch {
      toast.error("Gagal mengambil daftar interface");
      setInterfaces([]);
    }
    setLoadingIfaces(false);
  };

  const toggleInterface = (name) => {
    const watched = settings.watched_interfaces || [];
    const updated = watched.includes(name)
      ? watched.filter(i => i !== name)
      : [...watched, name];
    setSettings(s => ({ ...s, watched_interfaces: updated }));
  };

  if (loading) return <div className="text-center text-muted-foreground py-12 text-sm">Loading...</div>;

  return (
    <div className="space-y-5 pb-16" data-testid="notifications-page">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <h1 className="text-xl sm:text-2xl md:text-3xl font-bold tracking-tight">Notifikasi</h1>
          <p className="text-xs sm:text-sm text-muted-foreground">Konfigurasi alert WhatsApp via Fonnte API</p>
        </div>
        <Button onClick={handleSave} disabled={saving} size="sm" className="rounded-sm gap-2 w-full sm:w-auto">
          <Save className="w-4 h-4" /> {saving ? "Menyimpan..." : "Simpan Pengaturan"}
        </Button>
      </div>

      {/* Info Banner */}
      <div className="flex items-start gap-3 p-3 rounded-sm bg-blue-500/10 border border-blue-500/20 text-sm">
        <Info className="w-4 h-4 mt-0.5 text-blue-400 flex-shrink-0" />
        <div className="text-xs text-blue-300">
          <p className="font-semibold mb-1">Cara mendapatkan Fonnte API Token:</p>
          <ol className="list-decimal ml-4 space-y-0.5 text-blue-300/80">
            <li>Daftar di <span className="font-mono text-blue-300">fonnte.com</span></li>
            <li>Hubungkan nomor WhatsApp Anda ke Fonnte (scan QR)</li>
            <li>Salin API Token dari dashboard Fonnte</li>
            <li>Tempel token di field di bawah</li>
          </ol>
        </div>
      </div>

      {/* Enable Toggle */}
      <div className="bg-card border border-border rounded-sm p-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-sm bg-primary/10 flex items-center justify-center">
              <Bell className="w-5 h-5 text-primary" />
            </div>
            <div>
              <p className="text-sm font-semibold">Aktifkan Notifikasi</p>
              <p className="text-xs text-muted-foreground">Kirim alert ke WhatsApp saat kondisi kritis</p>
            </div>
          </div>
          <button
            onClick={() => setSettings(s => ({ ...s, enabled: !s.enabled }))}
            className={`relative w-12 h-6 rounded-full transition-colors ${settings.enabled ? "bg-green-500" : "bg-secondary"}`}
          >
            <div className={`absolute top-1 w-4 h-4 rounded-full bg-white shadow transition-all ${settings.enabled ? "left-7" : "left-1"}`} />
          </button>
        </div>
      </div>

      {/* Fonnte Token */}
      <div className="bg-card border border-border rounded-sm p-4 space-y-4">
        <h2 className="text-base font-semibold flex items-center gap-2">
          <Settings2 className="w-4 h-4 text-primary" /> Konfigurasi Fonnte API
        </h2>
        <div className="space-y-1.5">
          <Label className="text-xs text-muted-foreground">Fonnte API Token</Label>
          <Input
            type="password"
            value={settings.fonnte_token}
            onChange={e => setSettings(s => ({ ...s, fonnte_token: e.target.value }))}
            className="rounded-sm bg-background font-mono text-xs"
            placeholder="Masukkan token dari dashboard Fonnte"
          />
          <p className="text-[10px] text-muted-foreground/70">Token bersifat rahasia. Jangan bagikan ke siapapun.</p>
        </div>

        {/* Test Message */}
        <div className="pt-2 border-t border-border/50 space-y-2">
          <Label className="text-xs text-muted-foreground">Test Kirim Pesan</Label>
          <div className="flex gap-2">
            <Input
              value={testPhone}
              onChange={e => setTestPhone(e.target.value)}
              placeholder="628xxxxxxxxxx"
              className="rounded-sm bg-background font-mono text-xs flex-1"
            />
            <Button onClick={handleTest} disabled={sendingTest || !settings.fonnte_token} size="sm" variant="outline" className="rounded-sm gap-2 flex-shrink-0">
              <Send className="w-3.5 h-3.5" /> {sendingTest ? "..." : "Test"}
            </Button>
          </div>
          <p className="text-[10px] text-muted-foreground/70">Format nomor: 628xxxxxxxxxx (tanpa tanda + dan spasi)</p>
        </div>
      </div>

      {/* Recipients */}
      <div className="bg-card border border-border rounded-sm p-4 space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-base font-semibold flex items-center gap-2">
            <Phone className="w-4 h-4 text-primary" /> Nomor Penerima Alert
          </h2>
          <Button onClick={addRecipient} size="sm" variant="outline" className="rounded-sm gap-1 text-xs">
            <Plus className="w-3.5 h-3.5" /> Tambah
          </Button>
        </div>
        {settings.recipients.length === 0 ? (
          <p className="text-sm text-muted-foreground text-center py-4">Belum ada nomor penerima. Klik "Tambah" untuk menambahkan.</p>
        ) : (
          <div className="space-y-2">
            {settings.recipients.map((r, i) => (
              <PhoneRow key={i} r={r} idx={i} onChange={updateRecipient} onRemove={removeRecipient} />
            ))}
          </div>
        )}
      </div>

      {/* Alert Types & Thresholds */}
      <div className="bg-card border border-border rounded-sm p-4 space-y-4">
        <h2 className="text-base font-semibold flex items-center gap-2">
          <AlertTriangle className="w-4 h-4 text-yellow-500" /> Jenis Alert &amp; Threshold
        </h2>
        <div className="space-y-3">

          {/* Device Offline */}
          <div className="flex items-center gap-3 p-3 rounded-sm bg-secondary/20 border border-border/50">
            <button
              onClick={() => setSettings(s => ({ ...s, notify_offline: !s.notify_offline }))}
              className={`relative w-10 h-5 rounded-full transition-colors flex-shrink-0 ${settings.notify_offline ? "bg-green-500" : "bg-secondary"}`}
            >
              <div className={`absolute top-0.5 w-4 h-4 rounded-full bg-white shadow transition-all ${settings.notify_offline ? "left-5" : "left-0.5"}`} />
            </button>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium">Device Offline</p>
              <p className="text-[10px] text-muted-foreground">Kirim alert saat router tidak dapat dijangkau</p>
            </div>
          </div>

          {/* CPU Tinggi */}
          <div className="flex items-center gap-3 p-3 rounded-sm bg-secondary/20 border border-border/50">
            <button
              onClick={() => setSettings(s => ({ ...s, notify_cpu: !s.notify_cpu }))}
              className={`relative w-10 h-5 rounded-full transition-colors flex-shrink-0 ${settings.notify_cpu ? "bg-green-500" : "bg-secondary"}`}
            >
              <div className={`absolute top-0.5 w-4 h-4 rounded-full bg-white shadow transition-all ${settings.notify_cpu ? "left-5" : "left-0.5"}`} />
            </button>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium">CPU Tinggi</p>
              <p className="text-[10px] text-muted-foreground">Alert saat CPU melebihi threshold</p>
            </div>
            <div className="flex items-center gap-1.5 flex-shrink-0">
              <Input
                type="number"
                value={settings.thresholds?.cpu ?? 80}
                onChange={e => setSettings(s => ({ ...s, thresholds: { ...s.thresholds, cpu: parseInt(e.target.value) || 80 } }))}
                className="w-16 h-7 rounded-sm bg-background font-mono text-xs text-center"
                min={1} max={100}
              />
              <span className="text-xs text-muted-foreground">%</span>
            </div>
          </div>

          {/* Ping Tinggi */}
          <div className="flex items-center gap-3 p-3 rounded-sm bg-secondary/20 border border-border/50">
            <button
              onClick={() => setSettings(s => ({ ...s, notify_ping_high: !s.notify_ping_high }))}
              className={`relative w-10 h-5 rounded-full transition-colors flex-shrink-0 ${settings.notify_ping_high ? "bg-green-500" : "bg-secondary"}`}
            >
              <div className={`absolute top-0.5 w-4 h-4 rounded-full bg-white shadow transition-all ${settings.notify_ping_high ? "left-5" : "left-0.5"}`} />
            </button>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium flex items-center gap-1.5"><Activity className="w-3.5 h-3.5 text-cyan-500" /> Ping Tinggi</p>
              <p className="text-[10px] text-muted-foreground">Alert saat latensi melebihi threshold</p>
            </div>
            <div className="flex items-center gap-1.5 flex-shrink-0">
              <Input
                type="number"
                value={settings.thresholds?.ping_ms ?? 100}
                onChange={e => setSettings(s => ({ ...s, thresholds: { ...s.thresholds, ping_ms: parseInt(e.target.value) || 100 } }))}
                className="w-20 h-7 rounded-sm bg-background font-mono text-xs text-center"
                min={1} max={5000}
              />
              <span className="text-xs text-muted-foreground">ms</span>
            </div>
          </div>

          {/* Interface Down */}
          <div className="space-y-0">
            <div className="flex items-center gap-3 p-3 rounded-sm bg-secondary/20 border border-border/50">
              <button
                onClick={() => setSettings(s => ({ ...s, notify_interface_down: !s.notify_interface_down }))}
                className={`relative w-10 h-5 rounded-full transition-colors flex-shrink-0 ${settings.notify_interface_down ? "bg-green-500" : "bg-secondary"}`}
              >
                <div className={`absolute top-0.5 w-4 h-4 rounded-full bg-white shadow transition-all ${settings.notify_interface_down ? "left-5" : "left-0.5"}`} />
              </button>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium flex items-center gap-1.5"><Network className="w-3.5 h-3.5 text-orange-500" /> Interface Down</p>
                <p className="text-[10px] text-muted-foreground">
                  Alert saat interface yang dipilih turun
                  {(settings.watched_interfaces?.length ?? 0) > 0 && (
                    <span className="ml-1 text-orange-400 font-medium">({settings.watched_interfaces.length} dipilih)</span>
                  )}
                </p>
              </div>
            </div>

            {/* Interface picker â€“ hanya tampil jika toggle aktif */}
            {settings.notify_interface_down && (
              <div className="border border-t-0 border-border/50 rounded-b-sm p-3 bg-secondary/10 space-y-2">
                <div className="flex items-center gap-2">
                  <Select value={ifaceDevice} onValueChange={v => { setIfaceDevice(v); setInterfaces([]); }}>
                    <SelectTrigger className="rounded-sm bg-background h-8 text-xs flex-1">
                      <SelectValue placeholder="Pilih device..." />
                    </SelectTrigger>
                    <SelectContent>
                      {devices.map(d => (
                        <SelectItem key={d.id} value={d.id}>{d.name}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <Button
                    onClick={() => fetchInterfaces(ifaceDevice)}
                    disabled={!ifaceDevice || loadingIfaces}
                    size="sm" variant="outline"
                    className="rounded-sm text-xs h-8 gap-1 flex-shrink-0"
                  >
                    {loadingIfaces ? "..." : "Ambil Interface"}
                  </Button>
                </div>

                {interfaces.length > 0 && (
                  <div>
                    <p className="text-[10px] text-muted-foreground mb-1.5">Pilih interface yang ingin dimonitor (bisa lebih dari 1):</p>
                    <div className="flex flex-wrap gap-1.5">
                      {interfaces.map(iface => {
                        const isWatched = (settings.watched_interfaces || []).includes(iface);
                        return (
                          <button
                            key={iface}
                            onClick={() => toggleInterface(iface)}
                            className={`px-2.5 py-1 rounded-sm text-xs font-mono border transition-colors ${
                              isWatched
                                ? "bg-orange-500/20 text-orange-400 border-orange-500/40"
                                : "bg-secondary text-muted-foreground border-border hover:border-orange-500/30"
                            }`}
                          >
                            {isWatched && "âœ“ "}{iface}
                          </button>
                        );
                      })}
                    </div>
                  </div>
                )}

                {(settings.watched_interfaces?.length ?? 0) > 0 && (
                  <div className="pt-1">
                    <p className="text-[10px] text-muted-foreground mb-1">Interface yang dimonitor:</p>
                    <div className="flex flex-wrap gap-1">
                      {settings.watched_interfaces.map(i => (
                        <Badge key={i} variant="outline"
                          className="text-[10px] rounded-sm font-mono text-orange-400 border-orange-500/30 cursor-pointer"
                          onClick={() => toggleInterface(i)}
                        >
                          {i} âœ•
                        </Badge>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>

        </div>
        <p className="text-[10px] text-muted-foreground/70 pt-1 border-t border-border/50">
          â„¹ï¸ Alert tidak akan dikirim ulang selama kondisi masih berlanjut. Sistem baru kirim ulang setelah kondisi kembali normal lalu muncul lagi.
        </p>
      </div>

      {/* Telegram Bot Configuration */}
      <TelegramSection settings={settings} setSettings={setSettings} />
    </div>
  );
}

function TelegramSection({ settings, setSettings }) {
  const [testChatId, setTestChatId] = useState("");
  const [sendingTest, setSendingTest] = useState(false);

  const addChatId = () => {
    setSettings(s => ({ ...s, telegram_chat_ids: [...(s.telegram_chat_ids || []), ""] }));
  };
  const removeChatId = (i) => {
    setSettings(s => ({ ...s, telegram_chat_ids: s.telegram_chat_ids.filter((_, idx) => idx !== i) }));
  };
  const updateChatId = (i, val) => {
    const ids = [...(settings.telegram_chat_ids || [])];
    ids[i] = val;
    setSettings(s => ({ ...s, telegram_chat_ids: ids }));
  };

  const handleTestTelegram = async () => {
    if (!testChatId) { toast.error("Masukkan Chat ID tujuan test"); return; }
    setSendingTest(true);
    try {
      const r = await api.post("/notifications/test-telegram", {
        chat_id: testChatId,
        bot_token: settings.telegram_bot_token,
      });
      toast.success(r.data.message || "Test Telegram berhasil dikirim!");
    } catch (e) {
      toast.error(e.response?.data?.detail || "Test gagal. Periksa bot token dan chat ID.");
    }
    setSendingTest(false);
  };

  return (
    <div className="bg-card border border-border rounded-sm p-4 space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-base font-semibold flex items-center gap-2">
          <Bot className="w-4 h-4 text-blue-400" /> Telegram Bot
        </h2>
        <button
          onClick={() => setSettings(s => ({ ...s, telegram_enabled: !s.telegram_enabled }))}
          className={`relative w-12 h-6 rounded-full transition-colors ${settings.telegram_enabled ? "bg-blue-500" : "bg-secondary"}`}
        >
          <div className={`absolute top-1 w-4 h-4 rounded-full bg-white shadow transition-all ${settings.telegram_enabled ? "left-7" : "left-1"}`} />
        </button>
      </div>

      <div className="flex items-start gap-3 p-3 rounded-sm bg-blue-500/10 border border-blue-500/20 text-sm">
        <MessageSquare className="w-4 h-4 mt-0.5 text-blue-400 flex-shrink-0" />
        <div className="text-xs text-blue-300">
          <p className="font-semibold mb-1">Cara setup Telegram Bot:</p>
          <ol className="list-decimal ml-4 space-y-0.5 text-blue-300/80">
            <li>Buat bot baru via <span className="font-mono">@BotFather</span> di Telegram</li>
            <li>Salin token yang diberikan BotFather</li>
            <li>Chat bot Anda, lalu ambil Chat ID dari <span className="font-mono">api.telegram.org/bot&lt;TOKEN&gt;/getUpdates</span></li>
            <li>Untuk grup: tambahkan bot ke grup, ambil Chat ID dari getUpdates (negatif)</li>
          </ol>
        </div>
      </div>

      <div className="space-y-1.5">
        <Label className="text-xs text-muted-foreground">Telegram Bot Token</Label>
        <Input
          type="password"
          value={settings.telegram_bot_token || ""}
          onChange={e => setSettings(s => ({ ...s, telegram_bot_token: e.target.value }))}
          className="rounded-sm bg-background font-mono text-xs"
          placeholder="1234567890:ABCdefGHIjklMNOpqrSTUvwxYZ"
        />
        <p className="text-[10px] text-muted-foreground/70">Token dari @BotFather. Bersifat rahasia.</p>
      </div>

      {/* Chat IDs */}
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <Label className="text-xs text-muted-foreground">Chat ID Penerima</Label>
          <Button onClick={addChatId} size="sm" variant="outline" className="rounded-sm gap-1 text-xs h-7">
            <Plus className="w-3 h-3" /> Tambah
          </Button>
        </div>
        {(settings.telegram_chat_ids || []).length === 0 ? (
          <p className="text-xs text-muted-foreground text-center py-3">Belum ada Chat ID. Klik &quot;Tambah&quot; untuk menambahkan.</p>
        ) : (
          <div className="space-y-2">
            {(settings.telegram_chat_ids || []).map((id, i) => (
              <div key={i} className="flex items-center gap-2">
                <Input
                  value={id}
                  onChange={e => updateChatId(i, e.target.value)}
                  placeholder="-1001234567890 (grup) atau 123456789 (personal)"
                  className="rounded-sm bg-background font-mono text-xs flex-1"
                />
                <Button variant="ghost" size="icon" className="h-8 w-8 text-destructive" onClick={() => removeChatId(i)}>
                  <Trash2 className="w-3.5 h-3.5" />
                </Button>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Test Telegram */}
      <div className="pt-2 border-t border-border/50 space-y-2">
        <Label className="text-xs text-muted-foreground">Test Kirim Telegram</Label>
        <div className="flex gap-2">
          <Input
            value={testChatId}
            onChange={e => setTestChatId(e.target.value)}
            placeholder="Chat ID tujuan test"
            className="rounded-sm bg-background font-mono text-xs flex-1"
          />
          <Button
            onClick={handleTestTelegram}
            disabled={sendingTest || !settings.telegram_bot_token}
            size="sm" variant="outline" className="rounded-sm gap-2 flex-shrink-0"
          >
            <Send className="w-3.5 h-3.5" /> {sendingTest ? "..." : "Test"}
          </Button>
        </div>
        <p className="text-[10px] text-muted-foreground/70">Masukkan Chat ID (bisa beda dari daftar di atas untuk verifikasi)</p>
      </div>
    </div>
  );
}

