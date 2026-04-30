import React, { useState, useEffect, useCallback } from 'react';
import { MapPin, Plus, Link2, Trash2, Edit2, RefreshCw, Download, Upload, ChevronRight, Activity, BarChart2, Layers } from 'lucide-react';
import { NODE_TYPES, LINK_TYPES } from './networkmap/constants';
import { NodeModal, LinkModal } from './networkmap/Modals';
import MapView from './networkmap/MapView';

const API = import.meta.env.VITE_API_URL || '';
const h = () => ({ Authorization: `Bearer ${localStorage.getItem('token')}` });

/* ─── Stat Card ──────────────────────────────────────────────────── */
function StatCard({ icon: Icon, label, value, color = 'blue' }) {
  const colors = { blue:'text-blue-400 bg-blue-500/10', purple:'text-purple-400 bg-purple-500/10', amber:'text-amber-400 bg-amber-500/10', emerald:'text-emerald-400 bg-emerald-500/10', cyan:'text-cyan-400 bg-cyan-500/10' };
  return (
    <div className="bg-slate-800/60 border border-slate-700/50 rounded-xl p-4 flex items-center gap-3">
      <div className={`p-2 rounded-lg ${colors[color]}`}><Icon className="w-5 h-5" /></div>
      <div><div className="text-xl font-bold text-white">{value}</div><div className="text-xs text-slate-500">{label}</div></div>
    </div>
  );
}

/* ─── Tree Node (Sidebar) ────────────────────────────────────────── */
function TreeItem({ node, depth = 0, selected, onClick }) {
  const [open, setOpen] = useState(depth < 2);
  const cfg = NODE_TYPES[node.type] || { emoji: '📍', label: node.type };
  const hasChildren = node.children?.length > 0;
  return (
    <div>
      <button
        onClick={() => { onClick(node); if (hasChildren) setOpen(o => !o); }}
        className={`w-full flex items-center gap-2 px-3 py-1.5 rounded-lg text-left text-sm transition ${selected?.id === node.id ? 'bg-blue-600/20 text-blue-300' : 'text-slate-400 hover:text-white hover:bg-slate-700/50'}`}
        style={{ paddingLeft: `${12 + depth * 16}px` }}
      >
        {hasChildren && <ChevronRight className={`w-3 h-3 flex-shrink-0 transition-transform ${open ? 'rotate-90' : ''}`} />}
        {!hasChildren && <span className="w-3 h-3 flex-shrink-0" />}
        <span>{cfg.emoji}</span>
        <span className="truncate">{node.name}</span>
      </button>
      {open && hasChildren && node.children.map(c => (
        <TreeItem key={c.id} node={c} depth={depth + 1} selected={selected} onClick={onClick} />
      ))}
    </div>
  );
}

/* ─── Node Detail Panel ──────────────────────────────────────────── */
function NodeDetail({ node, onEdit, onConnect, onDelete }) {
  if (!node) return (
    <div className="p-4 text-center text-slate-600 text-sm">
      <MapPin className="w-8 h-8 mx-auto mb-2 opacity-30" />
      Klik node di peta untuk melihat detail
    </div>
  );
  const cfg = NODE_TYPES[node.type] || { emoji: '📍', label: node.type, color: '#6b7280' };
  const cap = node.meta?.capacity > 0 ? Math.round((node.meta.used || 0) / node.meta.capacity * 100) : null;
  return (
    <div className="p-4 space-y-3">
      <div className="flex items-center gap-3">
        <div className="text-3xl">{cfg.emoji}</div>
        <div>
          <div className="text-white font-bold">{node.name}</div>
          <div className="text-xs" style={{ color: cfg.color }}>{cfg.label}</div>
        </div>
      </div>
      {node.label && <p className="text-sm text-slate-400">{node.label}</p>}
      {node.address && <p className="text-xs text-slate-500">📍 {node.address}</p>}
      {(node.lat && node.lng) && <p className="text-xs font-mono text-slate-600">{node.lat.toFixed(6)}, {node.lng.toFixed(6)}</p>}

      {/* Capacity bar */}
      {cap !== null && (
        <div>
          <div className="flex justify-between text-xs text-slate-500 mb-1">
            <span>Kapasitas</span><span>{node.meta.used}/{node.meta.capacity} port ({cap}%)</span>
          </div>
          <div className="w-full bg-slate-700 rounded-full h-2">
            <div className={`h-2 rounded-full ${cap > 90 ? 'bg-red-500' : cap > 70 ? 'bg-amber-500' : 'bg-emerald-500'}`} style={{ width: `${cap}%` }} />
          </div>
        </div>
      )}

      {/* Meta info */}
      {node.type === 'olt' && node.meta?.brand && (
        <div className="text-xs space-y-1 bg-slate-800 rounded-lg p-3">
          <p className="text-slate-400">Brand: <span className="text-white">{node.meta.brand} {node.meta.model}</span></p>
          {node.meta.management_ip && <p className="text-slate-400">IP: <span className="font-mono text-white">{node.meta.management_ip}</span></p>}
          {node.meta.total_pon > 0 && <p className="text-slate-400">PON: <span className="text-white">{node.meta.total_pon} port</span></p>}
        </div>
      )}
      {node.type === 'ont' && (
        <div className="text-xs space-y-1 bg-slate-800 rounded-lg p-3">
          {node.meta?.customer_name && <p className="text-slate-400">Pelanggan: <span className="text-white">{node.meta.customer_name}</span></p>}
          {node.meta?.pppoe_username && <p className="text-slate-400">PPPoE: <span className="font-mono text-white">{node.meta.pppoe_username}</span></p>}
          {node.meta?.serial_number && <p className="text-slate-400">SN: <span className="font-mono text-white">{node.meta.serial_number}</span></p>}
          {node.meta?.rx_power != null && (
            <p className="text-slate-400">RX Power: <span className={`font-mono font-bold ${node.meta.rx_power < -27 ? 'text-red-400' : node.meta.rx_power < -24 ? 'text-amber-400' : 'text-emerald-400'}`}>{node.meta.rx_power} dBm</span></p>
          )}
        </div>
      )}
      {node.notes && <p className="text-xs text-slate-500 italic">{node.notes}</p>}

      <div className="flex gap-2 pt-2">
        <button onClick={() => onEdit(node)} className="flex-1 flex items-center justify-center gap-1 bg-blue-600/20 text-blue-400 hover:bg-blue-600/30 text-xs px-3 py-2 rounded-lg">
          <Edit2 className="w-3 h-3" /> Edit
        </button>
        <button onClick={() => onConnect(node)} className="flex-1 flex items-center justify-center gap-1 bg-emerald-600/20 text-emerald-400 hover:bg-emerald-600/30 text-xs px-3 py-2 rounded-lg">
          <Link2 className="w-3 h-3" /> Sambung
        </button>
        <button onClick={() => onDelete(node)} className="flex items-center justify-center bg-rose-600/20 text-rose-400 hover:bg-rose-600/30 text-xs px-3 py-2 rounded-lg">
          <Trash2 className="w-3 h-3" />
        </button>
      </div>
    </div>
  );
}

/* ═══ MAIN PAGE ══════════════════════════════════════════════════════ */
export default function NetworkMapPage() {
  const [nodes, setNodes] = useState([]);
  const [links, setLinks] = useState([]);
  const [tree, setTree] = useState([]);
  const [stats, setStats] = useState(null);
  const [selectedNode, setSelectedNode] = useState(null);
  const [nodeModal, setNodeModal] = useState(null);
  const [linkModal, setLinkModal] = useState(null);
  const [placing, setPlacing] = useState(null); // pending node awaiting map click
  const [addType, setAddType] = useState('olt');
  const [loading, setLoading] = useState(false);
  const [tab, setTab] = useState('tree'); // 'tree' | 'stats'
  const [importLoading, setImportLoading] = useState('');

  const fetchAll = useCallback(async () => {
    setLoading(true);
    try {
      const [nRes, lRes, tRes, sRes] = await Promise.all([
        fetch(`${API}/api/network-map/nodes`, { headers: h() }),
        fetch(`${API}/api/network-map/links`, { headers: h() }),
        fetch(`${API}/api/network-map/tree`, { headers: h() }),
        fetch(`${API}/api/network-map/stats`, { headers: h() }),
      ]);
      setNodes(await nRes.json());
      setLinks(await lRes.json());
      setTree(await tRes.json());
      setStats(await sRes.json());
    } catch (e) { console.error(e); }
    setLoading(false);
  }, []);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  const handleMapClick = useCallback(async (latlng) => {
    if (!placing) return;
    // Open node form pre-filled with lat/lng
    setNodeModal({ type: placing.type, name: '', label: '', address: '', lat: latlng.lat.toFixed(6), lng: latlng.lng.toFixed(6), notes: '', meta: {} });
    setPlacing(null);
  }, [placing]);

  const handleNodeSaved = useCallback(async (saved) => {
    setNodeModal(null);
    await fetchAll();
    setSelectedNode(saved);
  }, [fetchAll]);

  const handleLinkSaved = useCallback(async () => {
    setLinkModal(null);
    await fetchAll();
  }, [fetchAll]);

  const handleMoveNode = useCallback(async (nodeId, latlng) => {
    await fetch(`${API}/api/network-map/nodes/${nodeId}/position`, {
      method: 'PATCH', headers: { ...h(), 'Content-Type': 'application/json' },
      body: JSON.stringify({ lat: latlng.lat, lng: latlng.lng }),
    });
    setNodes(prev => prev.map(n => n.id === nodeId ? { ...n, lat: latlng.lat, lng: latlng.lng } : n));
  }, []);

  const handleDelete = useCallback(async (node) => {
    if (!confirm(`Hapus node "${node.name}" dan semua koneksinya?`)) return;
    await fetch(`${API}/api/network-map/nodes/${node.id}`, { method: 'DELETE', headers: h() });
    setSelectedNode(null);
    await fetchAll();
  }, [fetchAll]);

  const doImport = async (type) => {
    setImportLoading(type);
    try {
      const ep = type === 'devices' ? 'import-devices' : 'import-onts';
      const r = await fetch(`${API}/api/network-map/${ep}`, { method: 'POST', headers: h() });
      const d = await r.json();
      alert(d.message);
      await fetchAll();
    } catch (e) { alert(e.message); }
    setImportLoading('');
  };

  const unplacedNodes = nodes.filter(n => !n.lat || !n.lng);

  return (
    <div className="flex h-[calc(100vh-4rem)] bg-slate-950 overflow-hidden">
      {/* ── Sidebar ─────────────────────────────────────────────────── */}
      <div className="w-72 flex-shrink-0 flex flex-col bg-slate-900 border-r border-slate-800 overflow-hidden">
        {/* Header */}
        <div className="p-4 border-b border-slate-800">
          <h1 className="text-white font-bold flex items-center gap-2 text-base">
            <MapPin className="w-5 h-5 text-blue-400" /> Network Map
          </h1>
          <p className="text-slate-500 text-xs mt-1">FTTH Topology Visualizer</p>
        </div>

        {/* Add Node */}
        <div className="p-3 border-b border-slate-800 space-y-2">
          <p className="text-xs text-slate-500 font-semibold uppercase tracking-wide">Tambah Node</p>
          <div className="flex gap-2">
            <select value={addType} onChange={e => setAddType(e.target.value)}
              className="flex-1 bg-slate-800 border border-slate-700 text-white text-xs rounded-lg px-2 py-1.5">
              {Object.entries(NODE_TYPES).map(([k, v]) => <option key={k} value={k}>{v.emoji} {v.label}</option>)}
            </select>
            <button onClick={() => setPlacing({ type: addType })}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium transition ${placing ? 'bg-amber-500 text-black animate-pulse' : 'bg-blue-600 hover:bg-blue-700 text-white'}`}>
              {placing ? '📍 Klik Peta' : <><Plus className="w-3 h-3 inline" /> Tambah</>}
            </button>
          </div>
          {placing && <p className="text-xs text-amber-400 animate-pulse">👆 Klik lokasi di peta untuk menempatkan node</p>}
          <button onClick={() => setNodeModal({ type: addType, name: '', label: '', address: '', lat: '', lng: '', notes: '', meta: {} })}
            className="w-full text-xs text-slate-500 hover:text-white py-1">
            + Tambah tanpa koordinat
          </button>
        </div>

        {/* Import buttons */}
        <div className="p-3 border-b border-slate-800 space-y-2">
          <p className="text-xs text-slate-500 font-semibold uppercase tracking-wide">Auto Import</p>
          <div className="grid grid-cols-2 gap-2">
            <button onClick={() => doImport('devices')} disabled={!!importLoading}
              className="flex items-center justify-center gap-1 bg-blue-600/15 hover:bg-blue-600/25 text-blue-400 text-xs px-2 py-2 rounded-lg disabled:opacity-50">
              <Download className="w-3 h-3" /> {importLoading === 'devices' ? '...' : 'MikroTik'}
            </button>
            <button onClick={() => doImport('onts')} disabled={!!importLoading}
              className="flex items-center justify-center gap-1 bg-cyan-600/15 hover:bg-cyan-600/25 text-cyan-400 text-xs px-2 py-2 rounded-lg disabled:opacity-50">
              <Download className="w-3 h-3" /> {importLoading === 'onts' ? '...' : 'ONT'}
            </button>
          </div>
        </div>

        {/* Unplaced nodes */}
        {unplacedNodes.length > 0 && (
          <div className="p-3 border-b border-slate-800">
            <p className="text-xs text-amber-500 font-semibold mb-2">⚠ Belum di-pin di peta ({unplacedNodes.length})</p>
            <div className="space-y-1 max-h-28 overflow-y-auto">
              {unplacedNodes.slice(0, 10).map(n => (
                <button key={n.id} onClick={() => setSelectedNode(n)}
                  className="w-full text-left text-xs text-slate-400 hover:text-white px-2 py-1 rounded hover:bg-slate-800">
                  {NODE_TYPES[n.type]?.emoji} {n.name}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Tree / Stats tabs */}
        <div className="flex border-b border-slate-800">
          {[['tree', Layers, 'Pohon'], ['stats', BarChart2, 'Statistik']].map(([id, Icon, lbl]) => (
            <button key={id} onClick={() => setTab(id)}
              className={`flex-1 flex items-center justify-center gap-1.5 py-2 text-xs transition ${tab === id ? 'text-blue-400 border-b-2 border-blue-400' : 'text-slate-500 hover:text-white'}`}>
              <Icon className="w-3 h-3" /> {lbl}
            </button>
          ))}
        </div>

        <div className="flex-1 overflow-y-auto">
          {tab === 'tree' && (
            <div className="p-2 space-y-0.5">
              {loading && <p className="text-xs text-slate-600 text-center py-4">Memuat...</p>}
              {!loading && tree.length === 0 && (
                <p className="text-xs text-slate-600 text-center py-6">Belum ada node.<br/>Tambah node atau import dari Device Hub.</p>
              )}
              {tree.map(n => <TreeItem key={n.id} node={n} selected={selectedNode} onClick={setSelectedNode} />)}
            </div>
          )}
          {tab === 'stats' && stats && (
            <div className="p-3 space-y-3">
              <div className="grid grid-cols-2 gap-2">
                <div className="bg-slate-800 rounded-lg p-3 text-center">
                  <div className="text-2xl font-bold text-white">{stats.total_nodes}</div>
                  <div className="text-xs text-slate-500">Total Node</div>
                </div>
                <div className="bg-slate-800 rounded-lg p-3 text-center">
                  <div className="text-2xl font-bold text-white">{stats.total_links}</div>
                  <div className="text-xs text-slate-500">Koneksi</div>
                </div>
              </div>
              {stats.utilization_pct > 0 && (
                <div className="bg-slate-800 rounded-lg p-3">
                  <div className="flex justify-between text-xs text-slate-400 mb-1">
                    <span>Utilisasi Kapasitas</span>
                    <span>{stats.utilization_pct}%</span>
                  </div>
                  <div className="w-full bg-slate-700 rounded-full h-2">
                    <div className={`h-2 rounded-full ${stats.utilization_pct > 90 ? 'bg-red-500' : stats.utilization_pct > 70 ? 'bg-amber-500' : 'bg-emerald-500'}`}
                      style={{ width: `${stats.utilization_pct}%` }} />
                  </div>
                  <div className="text-xs text-slate-500 mt-1">{stats.total_used}/{stats.total_capacity} port</div>
                </div>
              )}
              <div className="space-y-1">
                <p className="text-xs text-slate-500 font-semibold uppercase tracking-wide">Per Tipe</p>
                {Object.entries(stats.by_type || {}).map(([type, count]) => {
                  const cfg = NODE_TYPES[type];
                  return (
                    <div key={type} className="flex items-center justify-between text-xs py-1">
                      <span className="text-slate-400">{cfg?.emoji} {cfg?.label || type}</span>
                      <span className="font-mono text-white bg-slate-800 px-2 py-0.5 rounded">{count}</span>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>

        {/* Refresh */}
        <div className="p-3 border-t border-slate-800">
          <button onClick={fetchAll} disabled={loading} className="w-full flex items-center justify-center gap-2 bg-slate-800 hover:bg-slate-700 text-slate-400 hover:text-white text-xs py-2 rounded-lg transition disabled:opacity-50">
            <RefreshCw className={`w-3 h-3 ${loading ? 'animate-spin' : ''}`} /> Refresh Data
          </button>
        </div>
      </div>

      {/* ── Map ───────────────────────────────────────────────────────── */}
      <div className="flex-1 relative">
        {/* Legend */}
        <div className="absolute top-3 right-3 z-[999] bg-slate-900/95 border border-slate-700 rounded-xl p-3 text-xs space-y-1 backdrop-blur-sm">
          <p className="font-semibold text-slate-400 mb-1">Legend</p>
          {Object.entries(NODE_TYPES).map(([k, v]) => (
            <div key={k} className="flex items-center gap-2">
              <span>{v.emoji}</span>
              <div className="w-2 h-2 rounded-full" style={{ background: v.color }} />
              <span className="text-slate-400">{v.label}</span>
            </div>
          ))}
          <hr className="border-slate-700 my-1" />
          {Object.entries(LINK_TYPES).map(([k, v]) => (
            <div key={k} className="flex items-center gap-2">
              <div className="w-4 h-0.5 rounded" style={{ background: v.color }} />
              <span className="text-slate-500">{v.label}</span>
            </div>
          ))}
        </div>

        {/* Node detail overlay */}
        {selectedNode && (
          <div className="absolute bottom-4 left-4 z-[999] w-72 bg-slate-900/95 border border-slate-700 rounded-xl backdrop-blur-sm shadow-2xl overflow-hidden">
            <NodeDetail
              node={selectedNode}
              onEdit={n => setNodeModal(n)}
              onConnect={n => setLinkModal(n)}
              onDelete={handleDelete}
            />
          </div>
        )}

        {placing && (
          <div className="absolute top-4 left-1/2 -translate-x-1/2 z-[999] bg-amber-500 text-black text-sm font-bold px-5 py-2 rounded-full shadow-lg animate-bounce">
            📍 Klik di peta untuk menempatkan {NODE_TYPES[placing.type]?.label}
          </div>
        )}

        <MapView
          nodes={nodes}
          links={links}
          selectedNode={selectedNode}
          onSelectNode={setSelectedNode}
          onMapClick={handleMapClick}
          onMoveNode={handleMoveNode}
        />
      </div>

      {/* ── Modals ─────────────────────────────────────────────────────── */}
      {nodeModal && (
        <NodeModal
          node={nodeModal.id ? nodeModal : null}
          initialData={nodeModal}
          onClose={() => setNodeModal(null)}
          onSaved={handleNodeSaved}
        />
      )}
      {linkModal && (
        <LinkModal
          sourceNode={linkModal}
          nodes={nodes}
          onClose={() => setLinkModal(null)}
          onSaved={handleLinkSaved}
        />
      )}
    </div>
  );
}
