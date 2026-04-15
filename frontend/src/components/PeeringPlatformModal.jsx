/**
 * PeeringPlatformModal.jsx
 * Modal untuk manajemen platform Peering Eye (CRUD platform pattern & icon).
 * Props:
 *   onClose  - callback saat modal ditutup
 *   onChange - callback saat ada perubahan data (untuk trigger refresh)
 */
import { useState, useEffect } from "react";
import { X, Plus, Trash2, Save, RefreshCw, Edit2 } from "lucide-react";
import { toast } from "sonner";
import api from "@/lib/api";

export default function PeeringPlatformModal({ onClose, onChange }) {
  const [platforms, setPlatforms] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [editId, setEditId] = useState(null);
  const [showAdd, setShowAdd] = useState(false);
  const [form, setForm] = useState({
    name: "",
    regex_pattern: "",
    icon: "🌐",
    color: "#6366f1",
  });

  const load = async () => {
    setLoading(true);
    try {
      const r = await api.get("/peering-eye/platforms");
      setPlatforms(r.data || []);
    } catch {
      toast.error("Gagal memuat platform");
    }
    setLoading(false);
  };

  useEffect(() => { load(); }, []);

  const resetForm = () =>
    setForm({ name: "", regex_pattern: "", icon: "🌐", color: "#6366f1" });

  const startEdit = (p) => {
    setEditId(p.id);
    setForm({ name: p.name, regex_pattern: p.regex_pattern, icon: p.icon || "🌐", color: p.color || "#6366f1" });
    setShowAdd(false);
  };

  const cancelEdit = () => {
    setEditId(null);
    setShowAdd(false);
    resetForm();
  };

  const handleSave = async () => {
    if (!form.name || !form.regex_pattern) {
      toast.error("Nama dan Regex Pattern wajib diisi");
      return;
    }
    setSaving(true);
    try {
      if (editId) {
        await api.put(`/peering-eye/platforms/${editId}`, form);
        toast.success("Platform diperbarui");
      } else {
        await api.post("/peering-eye/platforms", form);
        toast.success("Platform ditambahkan");
      }
      cancelEdit();
      await load();
      onChange?.();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Gagal menyimpan");
    }
    setSaving(false);
  };

  const handleDelete = async (p) => {
    if (!window.confirm(`Hapus platform "${p.name}"?`)) return;
    try {
      await api.delete(`/peering-eye/platforms/${p.id}`);
      toast.success("Platform dihapus");
      await load();
      onChange?.();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Gagal menghapus");
    }
  };

  const isFormMode = showAdd || editId !== null;

  return (
    <div className="fixed inset-0 z-50 bg-black/70 flex items-center justify-center p-4">
      <div className="bg-card border border-border rounded-lg w-full max-w-2xl shadow-2xl flex flex-col max-h-[90vh]">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-border shrink-0">
          <div>
            <h2 className="text-sm font-bold">Manajemen Platform Peering Eye</h2>
            <p className="text-xs text-muted-foreground mt-0.5">
              Kelola regex pattern platform — digunakan untuk klasifikasi DNS traffic
            </p>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-md hover:bg-secondary transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto p-4 space-y-3">
          {/* Add / Edit Form */}
          {isFormMode && (
            <div className="bg-secondary/20 border border-border/60 rounded-lg p-4 space-y-3">
              <h3 className="text-xs font-bold text-muted-foreground uppercase tracking-wider">
                {editId ? "Edit Platform" : "Tambah Platform Baru"}
              </h3>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div className="space-y-1">
                  <label className="text-xs font-medium">Nama Platform *</label>
                  <input
                    value={form.name}
                    onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
                    placeholder="Contoh: YouTube"
                    className="w-full h-8 px-2.5 text-xs rounded-sm border border-border bg-background text-foreground focus:outline-none focus:border-primary/50"
                  />
                </div>
                <div className="space-y-1">
                  <label className="text-xs font-medium flex items-center gap-1">
                    Icon <span className="text-muted-foreground">(emoji)</span>
                  </label>
                  <div className="flex gap-2">
                    <input
                      value={form.icon}
                      onChange={e => setForm(f => ({ ...f, icon: e.target.value }))}
                      placeholder="🌐"
                      className="w-16 h-8 px-2 text-sm rounded-sm border border-border bg-background text-center focus:outline-none focus:border-primary/50"
                    />
                    <input
                      type="color"
                      value={form.color}
                      onChange={e => setForm(f => ({ ...f, color: e.target.value }))}
                      className="h-8 w-12 rounded-sm border border-border bg-background cursor-pointer p-0.5"
                      title="Pilih warna"
                    />
                    <span className="text-xs text-muted-foreground self-center">{form.color}</span>
                  </div>
                </div>
              </div>
              <div className="space-y-1">
                <label className="text-xs font-medium">Regex Pattern *</label>
                <input
                  value={form.regex_pattern}
                  onChange={e => setForm(f => ({ ...f, regex_pattern: e.target.value }))}
                  placeholder="(youtube\.com|googlevideo\.com|ytimg\.com)"
                  className="w-full h-8 px-2.5 text-xs rounded-sm border border-border bg-background text-foreground font-mono focus:outline-none focus:border-primary/50"
                />
                <p className="text-[10px] text-muted-foreground">
                  Pattern regex Python — akan dicocokkan terhadap domain DNS query dari MikroTik
                </p>
              </div>
              <div className="flex gap-2 justify-end">
                <button
                  onClick={cancelEdit}
                  className="px-3 h-7 text-xs rounded-sm border border-border hover:bg-secondary transition-colors"
                >
                  Batal
                </button>
                <button
                  onClick={handleSave}
                  disabled={saving}
                  className="px-3 h-7 text-xs rounded-sm bg-primary text-primary-foreground hover:bg-primary/90 transition-colors flex items-center gap-1.5 disabled:opacity-50"
                >
                  {saving ? <RefreshCw className="w-3 h-3 animate-spin" /> : <Save className="w-3 h-3" />}
                  {saving ? "Menyimpan..." : editId ? "Update" : "Tambahkan"}
                </button>
              </div>
            </div>
          )}

          {/* Add Button */}
          {!isFormMode && (
            <button
              onClick={() => { setShowAdd(true); resetForm(); }}
              className="w-full h-9 border border-dashed border-border/60 rounded-lg text-xs text-muted-foreground hover:text-foreground hover:border-primary/30 hover:bg-primary/5 transition-all flex items-center justify-center gap-2"
            >
              <Plus className="w-3.5 h-3.5" /> Tambah Platform Baru
            </button>
          )}

          {/* Platform List */}
          {loading ? (
            <div className="flex items-center justify-center py-10 gap-2 text-muted-foreground">
              <RefreshCw className="w-4 h-4 animate-spin" />
              <span className="text-xs">Memuat platform...</span>
            </div>
          ) : platforms.length === 0 ? (
            <div className="text-center py-10 text-muted-foreground">
              <p className="text-sm">Belum ada platform terdaftar</p>
              <p className="text-xs mt-1">Klik "Tambah Platform Baru" untuk mulai</p>
            </div>
          ) : (
            <div className="space-y-1.5">
              {platforms.map(p => (
                <div
                  key={p.id}
                  className={`flex items-center gap-3 px-3 py-2.5 rounded-lg border transition-colors ${
                    editId === p.id
                      ? "border-primary/30 bg-primary/5"
                      : "border-border/40 hover:border-border/80 hover:bg-secondary/20"
                  }`}
                >
                  {/* Icon + Color Dot */}
                  <div className="flex items-center gap-2 shrink-0">
                    <span className="text-base leading-none">{p.icon || "🌐"}</span>
                    <span
                      className="w-2 h-2 rounded-full shrink-0"
                      style={{ backgroundColor: p.color || "#6366f1" }}
                    />
                  </div>

                  {/* Info */}
                  <div className="flex-1 min-w-0">
                    <p className="text-xs font-semibold truncate">{p.name}</p>
                    <p className="text-[10px] text-muted-foreground font-mono truncate">
                      {p.regex_pattern}
                    </p>
                  </div>

                  {/* Actions */}
                  <div className="flex gap-1 shrink-0">
                    <button
                      onClick={() => startEdit(p)}
                      className="p-1.5 rounded-md text-muted-foreground hover:text-foreground hover:bg-secondary transition-colors"
                      title="Edit"
                    >
                      <Edit2 className="w-3 h-3" />
                    </button>
                    <button
                      onClick={() => handleDelete(p)}
                      className="p-1.5 rounded-md text-muted-foreground hover:text-red-400 hover:bg-red-500/10 transition-colors"
                      title="Hapus"
                    >
                      <Trash2 className="w-3 h-3" />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between p-3 border-t border-border bg-secondary/10 shrink-0">
          <p className="text-[10px] text-muted-foreground">
            {platforms.length} platform terdaftar
          </p>
          <button
            onClick={onClose}
            className="px-4 h-7 text-xs rounded-sm border border-border hover:bg-secondary transition-colors"
          >
            Tutup
          </button>
        </div>
      </div>
    </div>
  );
}
