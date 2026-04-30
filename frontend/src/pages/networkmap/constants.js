// Network Map — Node constants & helpers
export const NODE_TYPES = {
  mikrotik:      { label: 'MikroTik',     color: '#3b82f6', emoji: '🖥️' },
  olt:           { label: 'OLT',          color: '#8b5cf6', emoji: '📡' },
  odc:           { label: 'ODC',          color: '#f59e0b', emoji: '🏢' },
  odp:           { label: 'ODP',          color: '#10b981', emoji: '📦' },
  splitter:      { label: 'Splitter',     color: '#6366f1', emoji: '🔀' },
  ont:           { label: 'ONT',          color: '#06b6d4', emoji: '🏠' },
  fat:           { label: 'FAT',          color: '#ec4899', emoji: '📍' },
  joint_closure: { label: 'Joint',        color: '#ef4444', emoji: '⚡' },
};

export const LINK_TYPES = {
  fo_core:         { label: 'FO Core',        color: '#f59e0b', dash: '' },
  fo_distribution: { label: 'FO Distribution',color: '#3b82f6', dash: '8,4' },
  fo_drop:         { label: 'FO Drop',        color: '#10b981', dash: '4,4' },
  ethernet:        { label: 'Ethernet',       color: '#6b7280', dash: '2,4' },
  pon:             { label: 'PON',            color: '#8b5cf6', dash: '' },
};

export const SPLITTER_RATIOS = ['1:2','1:4','1:8','1:16','1:32'];
