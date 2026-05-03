import { useState } from 'react';
import { X, Save, AlertCircle } from 'lucide-react';
import { NODE_TYPES, LINK_TYPES, SPLITTER_RATIOS } from './constants';

const API = import.meta.env.VITE_API_URL || '';
const h = () => ({ Authorization: `Bearer ${localStorage.getItem('token')}`, 'Content-Type': 'application/json' });

/* ─── Inline Error Banner ────────────────────────────────────────── */
function ErrorBanner({ message, onDismiss }) {
  if (!message) return null;
  return (
    <div className="flex items-start gap-2 bg-red-500/15 border border-red-500/40 text-red-400 rounded-lg px-3 py-2 text-sm">
      <AlertCircle className="w-4 h-4 flex-shrink-0 mt-0.5" />
      <span className="flex-1">{message}</span>
      {onDismiss && (
        <button onClick={onDismiss} className="text-red-400 hover:text-red-200 flex-shrink-0">
          <X className="w-3 h-3" />
        </button>
      )}
    </div>
  );
}

/* ─── Helper: parse API error ───────────────────────────────────── */
async function parseApiError(response) {
  try {
    const data = await response.json();
    if (response.status === 401) {
      return 'Sesi telah berakhir. Silakan login ulang.';
    }
    return data?.detail || data?.message || `Error ${response.status}`;
  } catch {
    return `Error ${response.status}`;
  }
}

/* ─── Node Form Modal ────────────────────────────────────────────── */
export function NodeModal({ node, initialData, onClose, onSaved, lockedDeviceId }) {
  const isEdit = !!node?.id;
  const [form, setForm] = useState(node || initialData || {
    type: 'olt', name: '', label: '', lat: '', lng: '', notes: '', meta: {}
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const set = (k, v) => setForm(f => ({ ...f, [k]: v }));
  const setMeta = (k, v) => setForm(f => ({ ...f, meta: { ...f.meta, [k]: v } }));

  const save = async () => {
    if (!form.name.trim()) { setError('Nama wajib diisi'); return; }
    setSaving(true);
    setError('');
    try {
      // Strip address field (removed), inject device_id lock if set
      const { address: _addr, ...rest } = form;
      const body = {
        ...rest,
        lat: form.lat ? Number(form.lat) : null,
        lng: form.lng ? Number(form.lng) : null,
        meta: {
          ...form.meta,
          ...(lockedDeviceId ? { mikrotik_device_id: lockedDeviceId } : {}),
        },
      };
      const url = isEdit
        ? `${API}/api/network-map/nodes/${node.id}`
        : `${API}/api/network-map/nodes`;
      const method = isEdit ? 'PUT' : 'POST';
      const r = await fetch(url, { method, headers: h(), body: JSON.stringify(body) });
      if (!r.ok) {
        const msg = await parseApiError(r);
        setError(msg);
        setSaving(false);
        return;
      }
      onSaved(await r.json());
    } catch (e) {
      setError(e.message || 'Terjadi kesalahan jaringan');
    }
    setSaving(false);
  };

  return (
    <div className="fixed inset-0 bg-black/70 z-[9999] flex items-center justify-center p-4">
      <div className="bg-slate-900 border border-slate-700 rounded-2xl w-full max-w-lg shadow-2xl">
        <div className="flex items-center justify-between p-5 border-b border-slate-700">
          <h2 className="text-white font-bold">{isEdit ? 'Edit' : 'Tambah'} Node</h2>
          <button onClick={onClose}><X className="text-slate-400 hover:text-white w-5 h-5" /></button>
        </div>
        <div className="p-5 space-y-3 max-h-[70vh] overflow-y-auto">
          {/* Error banner — replaces browser alert() */}
          <ErrorBanner message={error} onDismiss={() => setError('')} />

          {!isEdit && (
            <div>
              <label className="text-xs text-slate-400">Tipe Node</label>
              <select value={form.type} onChange={e => set('type', e.target.value)} className="w-full bg-slate-800 border border-slate-700 text-white rounded-lg px-3 py-2 text-sm mt-1">
                {Object.entries(NODE_TYPES).map(([k, v]) => <option key={k} value={k}>{v.emoji} {v.label}</option>)}
              </select>
            </div>
          )}

          {/* Fields: Nama, Label/Keterangan, Catatan — "Alamat Lokasi" dihapus */}
          {[['name', 'Nama *'], ['label', 'Label/Keterangan'], ['notes', 'Catatan']].map(([k, lbl]) => (
            <div key={k}>
              <label className="text-xs text-slate-400">{lbl}</label>
              <input
                value={form[k] || ''}
                onChange={e => set(k, e.target.value)}
                className="w-full bg-slate-800 border border-slate-700 text-white rounded-lg px-3 py-2 text-sm mt-1"
                placeholder={lbl}
              />
            </div>
          ))}

          <div className="grid grid-cols-2 gap-3">
            {[['lat', 'Latitude'], ['lng', 'Longitude']].map(([k, lbl]) => (
              <div key={k}>
                <label className="text-xs text-slate-400">{lbl}</label>
                <input
                  type="number" step="any"
                  value={form[k] || ''}
                  onChange={e => set(k, e.target.value)}
                  className="w-full bg-slate-800 border border-slate-700 text-white rounded-lg px-3 py-2 text-sm mt-1"
                  placeholder={lbl}
                />
              </div>
            ))}
          </div>

          {/* Type-specific meta fields */}
          {form.type === 'olt' && (
            <div className="bg-slate-800/50 rounded-lg p-3 space-y-2">
              <p className="text-xs text-purple-400 font-semibold">Info OLT</p>
              {[['brand', 'Brand (ZTE/Huawei/C-Data)'], ['model', 'Model'], ['management_ip', 'IP Management']].map(([k, lbl]) => (
                <div key={k}>
                  <label className="text-xs text-slate-400">{lbl}</label>
                  <input value={form.meta?.[k] || ''} onChange={e => setMeta(k, e.target.value)} className="w-full bg-slate-900 border border-slate-700 text-white rounded px-2 py-1 text-xs mt-0.5" />
                </div>
              ))}
              <div><label className="text-xs text-slate-400">Total PON Port</label>
                <input type="number" value={form.meta?.total_pon || ''} onChange={e => setMeta('total_pon', Number(e.target.value))} className="w-full bg-slate-900 border border-slate-700 text-white rounded px-2 py-1 text-xs mt-0.5" /></div>
            </div>
          )}
          {(form.type === 'odc' || form.type === 'odp') && (
            <div className="bg-slate-800/50 rounded-lg p-3 space-y-2">
              <p className="text-xs text-amber-400 font-semibold">Info {form.type.toUpperCase()}</p>
              <div className="grid grid-cols-2 gap-2">
                <div><label className="text-xs text-slate-400">Kapasitas</label>
                  <input type="number" value={form.meta?.capacity || ''} onChange={e => setMeta('capacity', Number(e.target.value))} className="w-full bg-slate-900 border border-slate-700 text-white rounded px-2 py-1 text-xs mt-0.5" /></div>
                <div><label className="text-xs text-slate-400">Terpakai</label>
                  <input type="number" value={form.meta?.used || ''} onChange={e => setMeta('used', Number(e.target.value))} className="w-full bg-slate-900 border border-slate-700 text-white rounded px-2 py-1 text-xs mt-0.5" /></div>
              </div>
              {form.type === 'odp' && (
                <div><label className="text-xs text-slate-400">Rasio Splitter</label>
                  <select value={form.meta?.splitter_ratio || '1:8'} onChange={e => setMeta('splitter_ratio', e.target.value)} className="w-full bg-slate-900 border border-slate-700 text-white rounded px-2 py-1 text-xs mt-0.5">
                    {SPLITTER_RATIOS.map(r => <option key={r}>{r}</option>)}
                  </select></div>
              )}
            </div>
          )}
          {form.type === 'ont' && (
            <div className="bg-slate-800/50 rounded-lg p-3 space-y-2">
              <p className="text-xs text-cyan-400 font-semibold">Info ONT</p>
              {[['serial_number', 'Serial Number'], ['customer_name', 'Nama Pelanggan'], ['pppoe_username', 'PPPoE Username']].map(([k, lbl]) => (
                <div key={k}>
                  <label className="text-xs text-slate-400">{lbl}</label>
                  <input value={form.meta?.[k] || ''} onChange={e => setMeta(k, e.target.value)} className="w-full bg-slate-900 border border-slate-700 text-white rounded px-2 py-1 text-xs mt-0.5" />
                </div>
              ))}
              <div><label className="text-xs text-slate-400">RX Power (dBm)</label>
                <input type="number" step="0.1" value={form.meta?.rx_power || ''} onChange={e => setMeta('rx_power', Number(e.target.value))} className="w-full bg-slate-900 border border-slate-700 text-white rounded px-2 py-1 text-xs mt-0.5" /></div>
            </div>
          )}
          {form.type === 'splitter' && (
            <div className="bg-slate-800/50 rounded-lg p-3 space-y-2">
              <p className="text-xs text-indigo-400 font-semibold">Info Splitter</p>
              <div><label className="text-xs text-slate-400">Rasio</label>
                <select value={form.meta?.ratio || '1:8'} onChange={e => setMeta('ratio', e.target.value)} className="w-full bg-slate-900 border border-slate-700 text-white rounded px-2 py-1 text-xs mt-0.5">
                  {SPLITTER_RATIOS.map(r => <option key={r}>{r}</option>)}
                </select></div>
            </div>
          )}
        </div>
        <div className="p-4 border-t border-slate-700 flex justify-end gap-3">
          <button onClick={onClose} className="px-4 py-2 text-sm text-slate-400 hover:text-white">Batal</button>
          <button onClick={save} disabled={saving} className="px-5 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-sm flex items-center gap-2 disabled:opacity-50">
            <Save className="w-4 h-4" /> {saving ? 'Menyimpan...' : 'Simpan'}
          </button>
        </div>
      </div>
    </div>
  );
}

/* ─── Link Modal ─────────────────────────────────────────────────── */
export function LinkModal({ sourceNode, nodes: nodesProp, onClose, onSaved }) {
  const [targetId, setTargetId] = useState('');
  const [linkType, setLinkType] = useState('fo_core');
  const [label, setLabel] = useState('');
  const [meta, setMeta] = useState({ cable_type: '', core_count: '', distance_m: '', loss_db: '' });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  // Defensive: ensure nodes is always an array
  const nodes = Array.isArray(nodesProp) ? nodesProp : [];
  const others = nodes.filter(n => n.id !== sourceNode.id);

  const save = async () => {
    if (!targetId) { setError('Pilih node tujuan terlebih dahulu'); return; }
    setSaving(true);
    setError('');
    try {
      const body = {
        source_id: sourceNode.id, target_id: targetId, link_type: linkType, label,
        meta: { ...meta, core_count: Number(meta.core_count) || 0, distance_m: Number(meta.distance_m) || 0, loss_db: Number(meta.loss_db) || 0 }
      };
      const r = await fetch(`${API}/api/network-map/links`, { method: 'POST', headers: h(), body: JSON.stringify(body) });
      if (!r.ok) {
        const msg = await parseApiError(r);
        setError(msg);
        setSaving(false);
        return;
      }
      onSaved(await r.json());
    } catch (e) {
      setError(e.message || 'Terjadi kesalahan jaringan');
    }
    setSaving(false);
  };

  return (
    <div className="fixed inset-0 bg-black/70 z-[9999] flex items-center justify-center p-4">
      <div className="bg-slate-900 border border-slate-700 rounded-2xl w-full max-w-md shadow-2xl">
        <div className="flex items-center justify-between p-5 border-b border-slate-700">
          <h2 className="text-white font-bold">Buat Koneksi dari <span className="text-blue-400">{sourceNode.name}</span></h2>
          <button onClick={onClose}><X className="text-slate-400 hover:text-white w-5 h-5" /></button>
        </div>
        <div className="p-5 space-y-3">
          {/* Error banner */}
          <ErrorBanner message={error} onDismiss={() => setError('')} />

          <div><label className="text-xs text-slate-400">Hubungkan ke Node</label>
            <select value={targetId} onChange={e => setTargetId(e.target.value)} className="w-full bg-slate-800 border border-slate-700 text-white rounded-lg px-3 py-2 text-sm mt-1">
              <option value="">-- Pilih Node --</option>
              {others.map(n => <option key={n.id} value={n.id}>{NODE_TYPES[n.type]?.emoji} {n.name}</option>)}
            </select></div>
          <div><label className="text-xs text-slate-400">Tipe Kabel</label>
            <select value={linkType} onChange={e => setLinkType(e.target.value)} className="w-full bg-slate-800 border border-slate-700 text-white rounded-lg px-3 py-2 text-sm mt-1">
              {Object.entries(LINK_TYPES).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
            </select></div>
          <div><label className="text-xs text-slate-400">Label (opsional)</label>
            <input value={label} onChange={e => setLabel(e.target.value)} placeholder="e.g. FO Core 24F - 500m" className="w-full bg-slate-800 border border-slate-700 text-white rounded-lg px-3 py-2 text-sm mt-1" /></div>
          <div className="grid grid-cols-2 gap-2">
            <div><label className="text-xs text-slate-400">Jumlah Core</label>
              <input type="number" value={meta.core_count} onChange={e => setMeta(m => ({ ...m, core_count: e.target.value }))} className="w-full bg-slate-800 border border-slate-700 text-white rounded px-2 py-1.5 text-sm mt-1" /></div>
            <div><label className="text-xs text-slate-400">Panjang (m)</label>
              <input type="number" value={meta.distance_m} onChange={e => setMeta(m => ({ ...m, distance_m: e.target.value }))} className="w-full bg-slate-800 border border-slate-700 text-white rounded px-2 py-1.5 text-sm mt-1" /></div>
          </div>
        </div>
        <div className="p-4 border-t border-slate-700 flex justify-end gap-3">
          <button onClick={onClose} className="px-4 py-2 text-sm text-slate-400 hover:text-white">Batal</button>
          <button onClick={save} disabled={saving} className="px-5 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-sm disabled:opacity-50">
            {saving ? 'Menghubungkan...' : 'Hubungkan'}
          </button>
        </div>
      </div>
    </div>
  );
}
