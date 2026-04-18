import { useState, useEffect, useCallback } from "react";
import api from "@/lib/api";
import { toast } from "sonner";
import { useAuth } from "@/App";
import { 
  Plus, RefreshCw, Edit2, Trash2, X, Package, Save, Router
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

const Rp = (n) => `Rp ${(Number(n) || 0).toLocaleString("id-ID")}`;

// ── PackageForm ────────────────────────────────────────────────────────────────
export function PackageForm({ initial, onClose, onSaved, defaultServiceType = "pppoe" }) {
  const [formTab, setFormTab] = useState("basic");
  const [form, setForm] = useState({
    name:               initial?.name || "",
    price:              initial?.price ?? "",
    speed_up:           initial?.speed_up || "",
    speed_down:         initial?.speed_down || "",
    service_type:       initial?.service_type || initial?.type || defaultServiceType,
    uptime_limit:       initial?.uptime_limit || "",
    validity:           initial?.validity || "",
    billing_cycle:      initial?.billing_cycle || 30,
    active:             initial?.active ?? true,
    device_id:          initial?.source_device_id || initial?.device_id || "",
    fup_enabled:        initial?.fup_enabled ?? false,
    fup_limit_gb:       initial?.fup_limit_gb || "",
    fup_rate_limit:     initial?.fup_rate_limit || "",
    day_night_enabled:  initial?.day_night_enabled ?? false,
    night_rate_limit:   initial?.night_rate_limit || "",
    night_start:        initial?.night_start || "22:00",
    night_end:          initial?.night_end   || "06:00",
    enable_early_promo:   initial?.enable_early_promo ?? false,
    promo_amount:         initial?.promo_amount || 0,
  });
  const [saving, setSaving] = useState(false);
  const [devices, setDevices] = useState([]);
  const set = (k, v) => setForm(f => ({ ...f, [k]: v }));
  const isEdit = !!initial?.id;

  useEffect(() => {
    api.get("/devices").then(r => setDevices(r.data || [])).catch(() => {});
  }, []);

  const submit = async () => {
    if (!form.name || form.price === "" || form.price === null) { toast.error("Nama dan harga wajib"); return; }
    if (form.fup_enabled && (!form.fup_limit_gb || !form.fup_rate_limit)) {
      toast.error("FUP aktif: isi Kuota (GB) dan Speed setelah FUP"); return;
    }
    if (form.day_night_enabled && !form.night_rate_limit) {
      toast.error("Night Mode aktif: isi Speed Malam"); return;
    }
    setSaving(true);
    try {
      const payload = {
        ...form,
        price:                Number(form.price),
        billing_cycle:        Number(form.billing_cycle),
        device_id:            form.device_id || null,
        fup_limit_gb:         form.fup_limit_gb ? Number(form.fup_limit_gb) : 0,
        enable_early_promo:   form.enable_early_promo,
        promo_amount:         Number(form.promo_amount) || 0,
      };
      if (isEdit) await api.put(`/billing/packages/${initial.id}`, payload);
      else        await api.post("/billing/packages", payload);
      toast.success(isEdit ? "Paket diupdate" : form.device_id ? "Paket dibuat di MikroTik..." : "Paket ditambahkan");
      onSaved();
    } catch (e) { toast.error(e.response?.data?.detail || "Gagal menyimpan"); }
    setSaving(false);
  };

  const FORM_TABS = [
    { id: "basic",   label: "Dasar"       },
    { id: "fup",     label: "FUP",        badge: form.fup_enabled       },
    { id: "night",   label: "Night Mode", badge: form.day_night_enabled },
    { id: "booster", label: "Booster",    badge: form.booster_enabled },
    { id: "promo",   label: "Promo",      badge: form.enable_early_promo },
  ].filter(tab => {
    if (defaultServiceType === "hotspot" && tab.id !== "basic") return false;
    return true;
  });

  return (
    <div className="fixed inset-0 z-50 bg-black/70 flex items-center justify-center p-4">
      <div className="bg-card border border-border rounded-sm w-full max-w-md shadow-2xl flex flex-col max-h-[92vh]">
        <div className="flex items-center justify-between p-4 border-b border-border flex-shrink-0">
          <h3 className="font-semibold">{isEdit ? "Edit Paket" : "Tambah Paket"}</h3>
          <Button size="icon" variant="ghost" className="h-7 w-7" onClick={onClose}>
            <X className="w-4 h-4" />
          </Button>
        </div>

        <div className="flex border-b border-border flex-shrink-0 bg-secondary/20">
          {FORM_TABS.map(t => (
            <button key={t.id} onClick={() => setFormTab(t.id)}
              className={`relative flex-1 py-2.5 text-xs font-medium transition-colors ${
                formTab === t.id
                  ? "border-b-2 border-primary text-primary bg-card"
                  : "text-muted-foreground hover:text-foreground"
              }`}>
              {t.label}
              {t.badge && (
                <span className="absolute top-1.5 right-2 w-1.5 h-1.5 rounded-full bg-primary animate-pulse" />
              )}
            </button>
          ))}
        </div>

        <div className="p-4 space-y-3 overflow-y-auto flex-1">
          {/* ── TAB DASAR ─────────────────────────────── */}
          {formTab === "basic" && (
            <>
              <div className="space-y-1.5">
                <Label className="text-xs text-muted-foreground">Nama Paket *</Label>
                <Input value={form.name} onChange={e => set("name", e.target.value)}
                  className="h-8 rounded-sm text-xs" placeholder="Paket 20Mbps" />
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs text-muted-foreground">Harga (Rp) *</Label>
                <Input
                  value={form.price === 0 ? "" : String(form.price)}
                  onChange={e => set("price", e.target.value)}
                  type="text"
                  inputMode="numeric"
                  pattern="[0-9]*"
                  placeholder="0"
                  className="h-8 rounded-sm text-xs font-mono"
                />
              </div>
              {defaultServiceType === "hotspot" && (
                <div className="grid grid-cols-2 gap-2">
                  <div className="space-y-1.5">
                    <Label className="text-xs text-muted-foreground">Waktu Pakai</Label>
                    <Input value={form.uptime_limit} onChange={e => set("uptime_limit", e.target.value)}
                      className="h-8 rounded-sm text-xs" placeholder="1h 30m" />
                    <p className="text-[10px] text-muted-foreground italic">d=Hari, h=Jam, m=Menit</p>
                  </div>
                  <div className="space-y-1.5">
                    <Label className="text-xs text-muted-foreground">Masa Berlaku</Label>
                    <Input value={form.validity} onChange={e => set("validity", e.target.value)}
                      className="h-8 rounded-sm text-xs" placeholder="30d" />
                    <p className="text-[10px] text-muted-foreground italic">d=Hari, h=Jam</p>
                  </div>
                </div>
              )}
              <div className="grid grid-cols-2 gap-2">
                <div className="space-y-1.5">
                  <Label className="text-xs text-muted-foreground">
                    {defaultServiceType === "hotspot" ? "Upload Speed" : "Upload Speed (Siang)"}
                  </Label>
                  <Input value={form.speed_up} onChange={e => set("speed_up", e.target.value)}
                    className="h-8 rounded-sm text-xs font-mono" placeholder="20M" />
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs text-muted-foreground">
                    {defaultServiceType === "hotspot" ? "Download Speed" : "Download Speed (Siang)"}
                  </Label>
                  <Input value={form.speed_down} onChange={e => set("speed_down", e.target.value)}
                    className="h-8 rounded-sm text-xs font-mono" placeholder="20M" />
                </div>
              </div>
              {!isEdit && form.service_type !== "hotspot" && (
                <div className="space-y-1.5">
                  <Label className="text-xs text-muted-foreground flex items-center gap-1.5">
                    <Router className="w-3 h-3 text-blue-400" />
                    Target Router MikroTik
                    <span className="text-[10px] text-muted-foreground/60">(opsional)</span>
                  </Label>
                  <select value={form.device_id} onChange={e => set("device_id", e.target.value)}
                    className="w-full h-8 text-xs rounded-sm border border-border bg-secondary px-2 text-foreground">
                    <option value="">— Simpan hanya di database —</option>
                    {devices.map(d => (
                      <option key={d.id} value={d.id}>{d.name} ({d.ip_address})</option>
                    ))}
                  </select>
                  {form.device_id && (
                    <p className="text-[10px] text-blue-400/80 italic flex items-center gap-1">
                      ✓ Profile PPPoE akan dibuat otomatis di router yang dipilih
                    </p>
                  )}
                </div>
              )}
              {isEdit && (
                <label className="flex items-center gap-2 cursor-pointer">
                  <input type="checkbox" checked={form.active}
                    onChange={e => set("active", e.target.checked)} />
                  <span className="text-xs text-muted-foreground">Paket aktif</span>
                </label>
              )}
            </>
          )}

          {/* ── TAB FUP ───────────────────────────────── */}
          {formTab === "fup" && (
            <div className="space-y-4">
              <div className="flex items-center justify-between p-3 bg-secondary/30 rounded-sm border border-border">
                <div>
                  <p className="text-xs font-semibold">Fair Usage Policy (FUP)</p>
                  <p className="text-[10px] text-muted-foreground mt-0.5">
                    Turunkan kecepatan otomatis jika kuota habis. Tanpa disconnect.
                  </p>
                </div>
                <button onClick={() => set("fup_enabled", !form.fup_enabled)}
                  className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors flex-shrink-0 ml-3 ${
                    form.fup_enabled ? "bg-primary" : "bg-muted"
                  }`}>
                  <span className={`inline-block h-3.5 w-3.5 rounded-full bg-white shadow transition-transform ${
                    form.fup_enabled ? "translate-x-4" : "translate-x-0.5"
                  }`} />
                </button>
              </div>
              {form.fup_enabled ? (
                <div className="space-y-3 animate-in fade-in duration-200">
                  <div className="space-y-1.5">
                    <Label className="text-xs text-muted-foreground">Batas Kuota Bulanan</Label>
                    <div className="flex items-center gap-2">
                      <Input value={form.fup_limit_gb}
                        onChange={e => set("fup_limit_gb", e.target.value)}
                        type="text" inputMode="numeric" pattern="[0-9]*"
                        className="h-8 rounded-sm text-xs flex-1 font-mono"
                        placeholder="Contoh: 2000" />
                      <span className="text-xs text-muted-foreground font-mono bg-secondary px-2 py-1 rounded-sm border border-border whitespace-nowrap">GB</span>
                    </div>
                  </div>
                  <div className="space-y-1.5">
                    <Label className="text-xs text-muted-foreground">Speed Setelah FUP Habis</Label>
                    <Input value={form.fup_rate_limit}
                      onChange={e => set("fup_rate_limit", e.target.value)}
                      className="h-8 rounded-sm text-xs font-mono"
                      placeholder="Contoh: 5M/5M atau 512k/1M" />
                  </div>
                  {form.fup_limit_gb && form.fup_rate_limit && (
                    <div className="p-3 bg-amber-500/10 border border-amber-500/20 rounded-sm text-[10px] text-amber-300 space-y-1">
                      <p className="font-semibold text-xs">Preview Kebijakan FUP:</p>
                      <div className="flex items-center gap-2">
                        <span className="w-2 h-2 rounded-full bg-green-400 flex-shrink-0" />
                        <span>Normal: <span className="font-mono">{form.speed_up||"?"}/{form.speed_down||"?"}</span> hingga {Number(form.fup_limit_gb||0).toLocaleString()} GB</span>
                      </div>
                      <div className="flex items-center gap-2">
                        <span className="w-2 h-2 rounded-full bg-red-400 flex-shrink-0" />
                        <span>Setelah FUP: <span className="font-mono text-red-300">{form.fup_rate_limit}</span> — reset tiap awal bulan</span>
                      </div>
                    </div>
                  )}
                </div>
              ) : (
                <div className="text-center py-8 text-muted-foreground space-y-1">
                  <p className="text-3xl">♾️</p>
                  <p className="text-xs font-medium">FUP Nonaktif</p>
                  <p className="text-[10px]">Pelanggan mendapatkan bandwidth unlimited</p>
                </div>
              )}
            </div>
          )}

          {/* ── TAB NIGHT MODE ────────────────────────── */}
          {formTab === "night" && (
            <div className="space-y-4">
              <div className="flex items-center justify-between p-3 bg-secondary/30 rounded-sm border border-border">
                <div>
                  <p className="text-xs font-semibold">Night Mode Bandwidth</p>
                  <p className="text-[10px] text-muted-foreground mt-0.5">
                    Atur kecepatan berbeda di jam malam. Tanpa disconnect pelanggan.
                  </p>
                </div>
                <button onClick={() => set("day_night_enabled", !form.day_night_enabled)}
                  className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors flex-shrink-0 ml-3 ${
                    form.day_night_enabled ? "bg-primary" : "bg-muted"
                  }`}>
                  <span className={`inline-block h-3.5 w-3.5 rounded-full bg-white shadow transition-transform ${
                    form.day_night_enabled ? "translate-x-4" : "translate-x-0.5"
                  }`} />
                </button>
              </div>
              {form.day_night_enabled ? (
                <div className="space-y-3 animate-in fade-in duration-200">
                  <div className="space-y-1.5">
                    <Label className="text-xs text-muted-foreground">Speed Malam (Night Rate Limit)</Label>
                    <Input value={form.night_rate_limit}
                      onChange={e => set("night_rate_limit", e.target.value)}
                      className="h-8 rounded-sm text-xs font-mono"
                      placeholder="Contoh: 50M/50M atau 100M/100M" />
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <div className="space-y-1.5">
                      <Label className="text-xs text-muted-foreground">🌙 Mulai Malam</Label>
                      <Input type="time" value={form.night_start}
                        onChange={e => set("night_start", e.target.value)}
                        className="h-8 rounded-sm text-xs font-mono" />
                    </div>
                    <div className="space-y-1.5">
                      <Label className="text-xs text-muted-foreground">☀️ Berakhir (Mulai Siang)</Label>
                      <Input type="time" value={form.night_end}
                        onChange={e => set("night_end", e.target.value)}
                        className="h-8 rounded-sm text-xs font-mono" />
                    </div>
                  </div>
                  <div className="p-3 bg-blue-950/40 border border-blue-500/20 rounded-sm space-y-2">
                    <p className="text-[10px] font-semibold text-blue-300">Jadwal Bandwidth Otomatis:</p>
                    <div className="space-y-1.5">
                      <div className="flex items-center justify-between text-[10px]">
                        <span className="flex items-center gap-1.5 text-muted-foreground">
                          <span className="w-5 h-5 rounded bg-amber-500/20 flex items-center justify-center text-[8px]">☀️</span>
                          Siang ({form.night_end} — {form.night_start})
                        </span>
                        <span className="font-mono px-2 py-0.5 bg-secondary rounded">
                          {form.speed_up||"?"}/{form.speed_down||"?"}
                        </span>
                      </div>
                      <div className="flex items-center justify-between text-[10px]">
                        <span className="flex items-center gap-1.5 text-muted-foreground">
                          <span className="w-5 h-5 rounded bg-blue-500/20 flex items-center justify-center text-[8px]">🌙</span>
                          Malam ({form.night_start} — {form.night_end})
                        </span>
                        <span className="font-mono px-2 py-0.5 bg-blue-500/20 rounded text-blue-300">
                          {form.night_rate_limit||"?"}
                        </span>
                      </div>
                    </div>
                    <p className="text-[9px] text-muted-foreground/60 border-t border-border/30 pt-1.5">
                      ⚡ Perubahan via Queue MikroTik (non-RADIUS) atau CoA (RADIUS) — tanpa disconnect
                    </p>
                  </div>
                </div>
              ) : (
                <div className="text-center py-8 text-muted-foreground space-y-1">
                  <p className="text-3xl">🕐</p>
                  <p className="text-xs font-medium">Night Mode Nonaktif</p>
                  <p className="text-[10px]">Kecepatan sama selama 24 jam penuh</p>
                </div>
              )}
            </div>
          )}


          {/* ── TAB PROMO ───────────────────────────── */}
          {formTab === "promo" && (
            <div className="space-y-4">
              <div className="flex items-center justify-between p-3 bg-secondary/30 rounded-sm border border-border">
                <div>
                  <p className="text-xs font-semibold">Promo Diskon "Early Bird"</p>
                  <p className="text-[10px] text-muted-foreground mt-0.5">
                    Syarat: Pelanggan tidak boleh telat bayar dalam 3 bulan berturut-turut.
                  </p>
                </div>
                <button onClick={() => set("enable_early_promo", !form.enable_early_promo)}
                  className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors flex-shrink-0 ml-3 ${
                    form.enable_early_promo ? "bg-primary" : "bg-muted"
                  }`}>
                  <span className={`inline-block h-3.5 w-3.5 rounded-full bg-white shadow transition-transform ${
                    form.enable_early_promo ? "translate-x-4" : "translate-x-0.5"
                  }`} />
                </button>
              </div>
              {form.enable_early_promo ? (
                <div className="space-y-3 animate-in fade-in duration-200">
                  <div className="space-y-1.5">
                    <Label className="text-xs text-muted-foreground">Potongan / Diskon Tepat Waktu (Rp)</Label>
                    <Input value={form.promo_amount === 0 ? "" : String(form.promo_amount)}
                      onChange={e => set("promo_amount", e.target.value)}
                      type="text" inputMode="numeric" pattern="[0-9]*"
                      className="h-8 rounded-sm text-xs font-mono"
                      placeholder="Contoh: 5000" />
                  </div>
                  <div className="p-3 bg-green-950/40 border border-green-500/20 rounded-sm space-y-2">
                    <p className="text-[10px] font-semibold text-green-300">Simulasi Tagihan:</p>
                    <div className="text-[10px] text-muted-foreground space-y-1">
                       <p>Harga Normal: <span className="font-mono">{Rp(form.price)}</span></p>
                       <p className="text-green-300">Potongan: <span className="font-mono">-{Rp(form.promo_amount)}</span></p>
                       <p className="font-bold border-t border-border/50 pt-1">
                          Total Dibayar: <span className="font-mono text-white">{Rp(Number(form.price) - Number(form.promo_amount))}</span>
                       </p>
                    </div>
                  </div>
                </div>
              ) : (
                <div className="text-center py-8 text-muted-foreground space-y-1">
                  <p className="text-3xl">💸</p>
                  <p className="text-xs font-medium">Promo Nonaktif</p>
                  <p className="text-[10px]">Pelanggan selalu membayar tagihan penuh.</p>
                </div>
              )}
            </div>
          )}
        </div>

        <div className="flex gap-2 p-4 border-t border-border flex-shrink-0">
          <Button variant="outline" className="flex-1 rounded-sm text-xs" onClick={onClose}>Batal</Button>
          <Button className="flex-1 rounded-sm text-xs" onClick={submit} disabled={saving}>
            {saving ? "Menyimpan..." : isEdit ? "Update Paket" : "Tambah Paket"}
          </Button>
        </div>
      </div>
    </div>
  );
}

// ── PackageRow — HARUS di luar PackagesTab agar tidak terjadi re-mount saat state editPrice berubah ──
// Pola anti-pattern: mendefinisikan komponen di dalam fungsi lain menyebabkan React unmount+remount
// setiap render → kursor menghilang dari input. Komponen ini di-level modul = stabil.
function PackageRow({ p, isAdmin, defaultServiceType, editPrice, setEditPrice, savingPrice, savePrice, setEditPkg, setShowForm, deletePkg, toggleActive }) {
  return (
    <tr className={`border-b border-border/40 hover:bg-secondary/20 ${p.price === 0 ? "bg-amber-500/5" : ""}`}>
      <td className="px-3 py-2.5">
        <div className="flex items-center gap-2 flex-wrap">
          <p className="text-xs font-medium">{p.name}</p>
          {p.price === 0 && (
            <span className="text-[9px] px-1 py-0.5 rounded border border-amber-500/40 text-amber-400 bg-amber-500/5 whitespace-nowrap">Belum ada harga</span>
          )}
          {p.fup_enabled && (
            <span className="text-[9px] px-1 py-0.5 rounded border border-orange-500/40 text-orange-400 bg-orange-500/5 whitespace-nowrap font-mono">
              FUP {p.fup_limit_gb}GB
            </span>
          )}
          {p.day_night_enabled && (
            <span className="text-[9px] px-1 py-0.5 rounded border border-blue-500/40 text-blue-400 bg-blue-500/5 whitespace-nowrap">
              🌙 Night
            </span>
          )}
        </div>
      </td>
      {defaultServiceType === "hotspot" && (
        <>
          <td className="px-3 py-2.5 text-[10px] text-muted-foreground font-mono">{p.uptime_limit || "—"}</td>
          <td className="px-3 py-2.5 text-[10px] text-muted-foreground font-mono">{p.validity || "—"}</td>
        </>
      )}
      <td className="px-3 py-2.5 text-[10px] text-muted-foreground font-mono text-center">
        {(p.speed_down || p.speed_up) ? (p.speed_down + "/" + p.speed_up) : "—"}
      </td>
      <td className="px-3 py-2.5">
        {isAdmin ? (
          <div className="flex items-center gap-1">
            {/* type="text" inputMode="numeric" mencegah cursor jumping di Chrome */}
            <Input
              type="text"
              inputMode="numeric"
              pattern="[0-9]*"
              placeholder="0"
              value={editPrice[p.id] !== undefined ? editPrice[p.id] : (p.price === 0 ? "" : String(p.price))}
              onChange={e => setEditPrice(prev => ({ ...prev, [p.id]: e.target.value }))}
              onKeyDown={e => { if (e.key === "Enter") savePrice(p); }}
              className={`h-7 w-28 text-xs rounded-sm font-mono ${p.price === 0 ? "border-amber-500/50 focus:border-amber-500" : ""}`}
            />
            {editPrice[p.id] !== undefined && (
              <Button size="sm" className="h-7 px-2 text-xs rounded-sm"
                onClick={() => savePrice(p)}
                disabled={savingPrice[p.id]}>
                {savingPrice[p.id] ? "..." : "OK"}
              </Button>
            )}
          </div>
        ) : (
          <span className={`font-mono text-xs font-bold ${p.price === 0 ? "text-amber-400" : "text-primary"}`}>
            {p.price === 0 ? "Belum diisi" : Rp(p.price)}
          </span>
        )}
      </td>
      <td className="px-3 py-2.5">
        <button onClick={() => isAdmin && toggleActive(p)} disabled={!isAdmin}
          className={`text-[10px] px-1.5 py-0.5 rounded-sm border transition-colors ${p.active ? "border-green-500/30 text-green-400 hover:bg-green-500/10" : "border-red-500/30 text-red-400 hover:bg-red-500/10"}`}>
          {p.active ? "Aktif" : "Non-aktif"}
        </button>
      </td>
      <td className="px-3 py-2.5">
        {isAdmin && (
          <div className="flex gap-1">
            <Button size="icon" variant="ghost" className="h-6 w-6"
              onClick={() => { setEditPkg(p); setShowForm(true); }}>
              <Edit2 className="w-3 h-3" />
            </Button>
            <Button size="icon" variant="ghost" className="h-6 w-6"
              onClick={() => deletePkg(p.id)}>
              <Trash2 className="w-3 h-3 text-destructive" />
            </Button>
          </div>
        )}
      </td>
    </tr>
  );
}

// ── TableHeader — juga di luar untuk konsistensi ──────────────────────────────
function TableHeader({ defaultServiceType }) {
  return (
    <thead>
      <tr className="border-b border-border">
        <th className="px-3 py-2 text-left text-[10px] font-semibold text-muted-foreground uppercase tracking-wider">Nama Paket</th>
        {defaultServiceType === "hotspot" && (
          <>
            <th className="px-3 py-2 text-left text-[10px] font-semibold text-muted-foreground uppercase tracking-wider">Waktu Pakai</th>
            <th className="px-3 py-2 text-left text-[10px] font-semibold text-muted-foreground uppercase tracking-wider">Masa Berlaku</th>
          </>
        )}
        <th className="px-3 py-2 text-left text-[10px] font-semibold text-muted-foreground uppercase tracking-wider">Speed</th>
        <th className="px-3 py-2 text-left text-[10px] font-semibold text-muted-foreground uppercase tracking-wider">Harga</th>
        <th className="px-3 py-2 text-left text-[10px] font-semibold text-muted-foreground uppercase tracking-wider">Status</th>
        <th className="px-3 py-2 text-left text-[10px] font-semibold text-muted-foreground uppercase tracking-wider"></th>
      </tr>
    </thead>
  );
}

// ── PackagesTab ───────────────────────────────────────────────────────────────
export function PackagesTab({ packages, onRefresh, deviceId, defaultServiceType = "pppoe" }) {
  const [showForm, setShowForm] = useState(false);
  const [editPkg, setEditPkg] = useState(null);
  const [devices, setDevices] = useState([]);
  const [syncDevice, setSyncDevice] = useState("");
  const [syncing, setSyncing] = useState(false);
  const [editPrice, setEditPrice] = useState({});
  const [savingPrice, setSavingPrice] = useState({});
  const { user } = useAuth();
  const READONLY_ROLES = ["viewer", "helpdesk"];
  const isAdmin = !READONLY_ROLES.includes(user?.role);

  // ── Filter berdasarkan jenis layanan ──
  let filteredPackages = packages;
  if (defaultServiceType === "hotspot") {
    filteredPackages = packages.filter(p => (p.service_type || p.type) === "hotspot" || (p.service_type || p.type) === "both");
  } else {
    filteredPackages = packages.filter(p => (p.service_type || p.type) === "pppoe" || (p.service_type || p.type) === "both");
    if (deviceId) {
      filteredPackages = filteredPackages.filter(p => p.source_device_id === deviceId);
    }
  }

  // ── Grouping per device ──
  const isGrouped = !deviceId && defaultServiceType !== "hotspot";
  const deviceGroups = isGrouped
    ? filteredPackages.reduce((acc, p) => {
        const key = p.source_device_id || "__manual__";
        const label = p.source_device_name || (p.source_device_id ? p.source_device_id : "Paket Manual (Tanpa Router)");
        if (!acc[key]) acc[key] = { label, packages: [] };
        acc[key].packages.push(p);
        return acc;
      }, {})
    : null;

  useEffect(() => {
    api.get("/devices").then(r => setDevices(r.data)).catch(() => {});
  }, []);

  const deletePkg = useCallback(async (id) => {
    if (!window.confirm("Hapus paket ini?")) return;
    try { await api.delete(`/billing/packages/${id}`); toast.success("Paket dihapus"); onRefresh(); }
    catch (e) { toast.error(e.response?.data?.detail || "Gagal"); }
  }, [onRefresh]);

  const syncFromMikroTik = async () => {
    if (!syncDevice) { toast.error("Pilih device dulu"); return; }
    setSyncing(true);
    try {
      const r = await api.post("/billing/packages/sync-from-mikrotik", null, { params: { device_id: syncDevice } });
      toast.success(r.data.message);
      onRefresh();
    } catch (e) { toast.error(e.response?.data?.detail || "Gagal sync"); }
    setSyncing(false);
  };

  const savePrice = useCallback(async (pkg) => {
    const price = editPrice[pkg.id];
    if (price === undefined) return;
    setSavingPrice(s => ({ ...s, [pkg.id]: true }));
    try {
      await api.patch(`/billing/packages/${pkg.id}/price`, { price: Number(price) });
      toast.success(`Harga ${pkg.name} disimpan`);
      setEditPrice(p => { const n = { ...p }; delete n[pkg.id]; return n; });
      onRefresh();
    } catch (e) { toast.error(e.response?.data?.detail || "Gagal"); }
    setSavingPrice(s => ({ ...s, [pkg.id]: false }));
  }, [editPrice, onRefresh]);

  const toggleActive = useCallback(async (pkg) => {
    try {
      await api.patch(`/billing/packages/${pkg.id}/price`, { active: !pkg.active });
      toast.success(`Paket ${pkg.active ? "dinonaktifkan" : "diaktifkan"}`);
      onRefresh();
    } catch (e) { toast.error(e.response?.data?.detail || "Gagal"); }
  }, [onRefresh]);

  return (
    <div className="space-y-3">
      {isAdmin && (
        <div className="flex flex-wrap gap-2 items-center">
          {defaultServiceType !== "hotspot" && (
            <div className="flex items-center gap-1 flex-1 min-w-[200px]">
              <select value={syncDevice} onChange={e => setSyncDevice(e.target.value)}
                className="flex-1 h-8 text-xs rounded-sm border border-border bg-secondary px-2 text-foreground">
                <option value="">Sync Profile dari Router...</option>
                {devices.map(d => <option key={d.id} value={d.id}>{d.name} ({d.host})</option>)}
              </select>
              <Button size="sm" variant="outline"
                className="rounded-sm h-8 gap-1 text-xs border-blue-500/40 text-blue-400 hover:bg-blue-500/10 whitespace-nowrap"
                onClick={syncFromMikroTik} disabled={syncing || !syncDevice}>
                <RefreshCw className={`w-3.5 h-3.5 ${syncing ? "animate-spin" : ""}`} />
                {syncing ? "Sync..." : "Sync Profile"}
              </Button>
            </div>
          )}
          <Button size="sm" variant="outline" className="rounded-sm h-8 gap-1 text-xs whitespace-nowrap"
            onClick={() => { setEditPkg(null); setShowForm(true); }}>
            <Plus className="w-3.5 h-3.5" /> {defaultServiceType === "hotspot" ? "Tambah Paket" : "Tambah Manual"}
          </Button>
        </div>
      )}

      {filteredPackages.length === 0 ? (
        <div className="text-center py-10">
          <Package className="w-10 h-10 text-muted-foreground/30 mx-auto mb-2" />
          <p className="text-muted-foreground text-sm mb-1">Belum ada paket {defaultServiceType === "hotspot" ? "Hotspot" : "layanan"}</p>
          <p className="text-[11px] text-muted-foreground/60">Gunakan tombol "Sync Profile" untuk mengambil daftar paket dari MikroTik</p>
        </div>
      ) : isGrouped ? (
        <div className="space-y-4 pb-4">
          {Object.entries(deviceGroups).map(([devId, group]) => {
            const zeroPriceCount = group.packages.filter(p => !p.price || p.price === 0).length;
            return (
              <div key={devId} className="border border-border rounded-sm overflow-hidden">
                <div className={`flex items-center justify-between px-3 py-2 border-b ${zeroPriceCount > 0 ? "bg-amber-500/10 border-amber-500/20" : "bg-secondary/40 border-border"}`}>
                  <div className="flex items-center gap-2">
                    <div className={`w-1.5 h-1.5 rounded-full ${zeroPriceCount > 0 ? "bg-amber-400" : "bg-blue-400"}`} />
                    <span className="text-xs font-bold text-foreground">{group.label}</span>
                    <span className="text-[10px] text-muted-foreground font-mono bg-secondary px-1.5 py-0.5 rounded-sm">
                      {group.packages.length} paket
                    </span>
                    {zeroPriceCount > 0 && (
                      <span className="text-[10px] text-amber-400 flex items-center gap-1">
                        ⚠ {zeroPriceCount} belum ada harga
                      </span>
                    )}
                  </div>
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <TableHeader defaultServiceType={defaultServiceType} />
                    <tbody>
                      {group.packages.map(p => (
                        <PackageRow key={p.id} p={p}
                          isAdmin={isAdmin} defaultServiceType={defaultServiceType}
                          editPrice={editPrice} setEditPrice={setEditPrice}
                          savingPrice={savingPrice} savePrice={savePrice}
                          setEditPkg={setEditPkg} setShowForm={setShowForm}
                          deletePkg={deletePkg} toggleActive={toggleActive}
                        />
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            );
          })}
          <p className="text-[10px] text-muted-foreground text-right font-mono">{filteredPackages.length} paket total</p>
        </div>
      ) : (
        <div className="overflow-x-auto pb-4">
          <table className="w-full text-sm">
            <TableHeader defaultServiceType={defaultServiceType} />
            <tbody>
              {filteredPackages.map(p => (
                <PackageRow key={p.id} p={p}
                  isAdmin={isAdmin} defaultServiceType={defaultServiceType}
                  editPrice={editPrice} setEditPrice={setEditPrice}
                  savingPrice={savingPrice} savePrice={savePrice}
                  setEditPkg={setEditPkg} setShowForm={setShowForm}
                  deletePkg={deletePkg} toggleActive={toggleActive}
                />
              ))}
            </tbody>
          </table>
          <p className="text-[10px] text-muted-foreground mt-2 text-right font-mono">{filteredPackages.length} paket</p>
        </div>
      )}

      {showForm && (
        <PackageForm
          initial={editPkg || (deviceId ? { source_device_id: deviceId } : null)}
          defaultServiceType={defaultServiceType}
          onClose={() => setShowForm(false)}
          onSaved={() => { setShowForm(false); onRefresh(); }}
        />
      )}
    </div>
  );
}
