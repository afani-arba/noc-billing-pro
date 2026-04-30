import { useMemo } from 'react';
import { MapContainer, TileLayer, Marker, Popup, Polyline, useMapEvents } from 'react-leaflet';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { NODE_TYPES, LINK_TYPES } from './constants';

// Fix default Leaflet marker icons
delete L.Icon.Default.prototype._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png',
  iconUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png',
  shadowUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png',
});

// Custom icon per node type
function makeIcon(type, selected = false) {
  const cfg = NODE_TYPES[type] || { emoji: '📍', color: '#6b7280' };
  const size = selected ? 48 : 38;
  const border = selected ? '3px solid #fff' : '2px solid rgba(255,255,255,0.6)';
  const html = `
    <div style="
      width:${size}px;height:${size}px;
      background:${cfg.color};
      border-radius:50%;
      display:flex;align-items:center;justify-content:center;
      font-size:${selected ? 22 : 18}px;
      border:${border};
      box-shadow:0 2px 8px rgba(0,0,0,0.5);
      transition:all 0.2s;
    ">${cfg.emoji}</div>`;
  return L.divIcon({ html, className: '', iconSize: [size, size], iconAnchor: [size/2, size/2] });
}

// Click-to-place handler
function MapClickHandler({ onMapClick }) {
  useMapEvents({ click: e => onMapClick && onMapClick(e.latlng) });
  return null;
}

export default function NetworkMapLeaflet({
  nodes, links, selectedNode, onSelectNode, onMapClick, onMoveNode
}) {
  // Default center: Indonesia
  const center = useMemo(() => {
    const geoNodes = nodes.filter(n => n.lat && n.lng);
    if (!geoNodes.length) return [-2.5, 118.0];
    const lat = geoNodes.reduce((s, n) => s + n.lat, 0) / geoNodes.length;
    const lng = geoNodes.reduce((s, n) => s + n.lng, 0) / geoNodes.length;
    return [lat, lng];
  }, [nodes]);

  // Build node lookup for lines
  const nodeMap = useMemo(() => Object.fromEntries(nodes.map(n => [n.id, n])), [nodes]);

  // Polylines for links between placed nodes
  const polylines = useMemo(() => links
    .map(lnk => {
      const src = nodeMap[lnk.source_id];
      const tgt = nodeMap[lnk.target_id];
      if (!src?.lat || !src?.lng || !tgt?.lat || !tgt?.lng) return null;
      return { ...lnk, positions: [[src.lat, src.lng], [tgt.lat, tgt.lng]] };
    })
    .filter(Boolean), [links, nodeMap]);

  const geoNodes = nodes.filter(n => n.lat && n.lng);

  return (
    <MapContainer
      center={center}
      zoom={geoNodes.length ? 13 : 5}
      className="w-full h-full rounded-xl"
      style={{ background: '#1e293b' }}
    >
      <TileLayer
        url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
        attribution='&copy; <a href="https://carto.com/">CARTO</a>'
      />
      <MapClickHandler onMapClick={onMapClick} />

      {/* Polylines (cables) */}
      {polylines.map(lnk => {
        const cfg = LINK_TYPES[lnk.link_type] || LINK_TYPES.fo_core;
        const dashArr = cfg.dash || undefined;
        return (
          <Polyline
            key={lnk.id}
            positions={lnk.positions}
            pathOptions={{ color: cfg.color, weight: 3, dashArray: dashArr, opacity: 0.85 }}
          >
            <Popup>
              <div className="text-xs space-y-1">
                <p className="font-bold">{cfg.label}</p>
                {lnk.label && <p>{lnk.label}</p>}
                {lnk.meta?.core_count > 0 && <p>Core: {lnk.meta.core_count}F</p>}
                {lnk.meta?.distance_m > 0 && <p>Panjang: {lnk.meta.distance_m}m</p>}
                {lnk.meta?.loss_db > 0 && <p>Loss: {lnk.meta.loss_db} dB</p>}
              </div>
            </Popup>
          </Polyline>
        );
      })}

      {/* Node markers */}
      {geoNodes.map(node => (
        <Marker
          key={node.id}
          position={[node.lat, node.lng]}
          icon={makeIcon(node.type, selectedNode?.id === node.id)}
          draggable
          eventHandlers={{
            click: () => onSelectNode(node),
            dragend: e => onMoveNode(node.id, e.target.getLatLng()),
          }}
        >
          <Popup>
            <div className="text-xs space-y-1 min-w-[160px]">
              <p className="font-bold text-sm">{NODE_TYPES[node.type]?.emoji} {node.name}</p>
              {node.label && <p className="text-gray-500">{node.label}</p>}
              {node.address && <p>📍 {node.address}</p>}
              {node.type === 'ont' && node.meta?.customer_name && <p>👤 {node.meta.customer_name}</p>}
              {node.type === 'ont' && node.meta?.pppoe_username && <p>🔑 {node.meta.pppoe_username}</p>}
              {node.type === 'ont' && node.meta?.rx_power && (
                <p className={`font-mono ${node.meta.rx_power < -27 ? 'text-red-600' : node.meta.rx_power < -24 ? 'text-orange-500' : 'text-green-600'}`}>
                  📶 {node.meta.rx_power} dBm
                </p>
              )}
              {(node.type === 'odc' || node.type === 'odp') && node.meta?.capacity > 0 && (
                <p>📊 {node.meta.used || 0}/{node.meta.capacity} port terpakai</p>
              )}
              {node.type === 'olt' && node.meta?.brand && <p>🏭 {node.meta.brand} {node.meta.model}</p>}
              {node.notes && <p className="text-gray-400 italic">{node.notes}</p>}
            </div>
          </Popup>
        </Marker>
      ))}
    </MapContainer>
  );
}
