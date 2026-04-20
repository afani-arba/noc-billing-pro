// ── Glassmorphism Class Helpers ──────────────────────────────────────────────
// Gunakan helper ini secara konsisten di semua halaman agar mudah di-update.
// Tinggal pass isCyber=true/false berdasarkan useTheme().

/**
 * Mengembalikan class name untuk card / panel utama
 * @param {boolean} isCyber
 * @param {string} [extra] - class tambahan (separator, spacing, dll)
 */
export function cardClass(isCyber, extra = "") {
  const base = isCyber
    ? "glass-card"
    : "bg-card border border-border rounded-sm";
  return `${base} ${extra}`.trim();
}

/**
 * Class untuk section header text (nama halaman, judul card)
 * @param {boolean} isCyber
 */
export function headingClass(isCyber) {
  return isCyber ? "gradient-text font-mono" : "";
}

/**
 * Class untuk muted/secondary text  
 * @param {boolean} isCyber
 */
export function mutedClass(isCyber) {
  return isCyber ? "text-[hsl(185,100%,35%)] font-mono" : "text-muted-foreground";
}

/**
 * Class untuk label kecil di atas input/field
 * @param {boolean} isCyber
 */
export function labelClass(isCyber) {
  return isCyber
    ? "text-[10px] font-mono uppercase tracking-widest text-[hsl(162,100%,40%)]"
    : "text-xs text-muted-foreground uppercase tracking-wider";
}

/**
 * Tooltip style untuk recharts
 * @param {boolean} isCyber
 */
export function chartTooltipStyle(isCyber) {
  return isCyber
    ? { contentStyle: { backgroundColor: "rgba(0,8,6,0.95)", borderColor: "rgba(0,230,118,0.25)", borderRadius: "6px", color: "hsl(162,100%,75%)", fontSize: "11px", fontFamily: "'JetBrains Mono', monospace" } }
    : { contentStyle: { backgroundColor: "#121214", borderColor: "#27272a", borderRadius: "4px", color: "#fafafa", fontSize: "12px", fontFamily: "'JetBrains Mono', monospace" } };
}

/**
 * CartesianGrid color
 * @param {boolean} isCyber
 */
export function gridColor(isCyber) {
  return isCyber ? "rgba(0,230,118,0.07)" : "#27272a";
}

/**
 * Axis tick config
 * @param {boolean} isCyber
 */
export function axisTick(isCyber) {
  return { fill: isCyber ? "rgba(0,230,118,0.5)" : "#a1a1aa", fontSize: 10 };
}

/**
 * Class untuk badge/chip status
 * @param {boolean} isCyber
 * @param {"green"|"cyan"|"amber"|"red"|"purple"|"blue"} color
 */
export function badgeClass(isCyber, color = "green") {
  if (!isCyber) {
    const map = {
      green: "bg-green-500/10 text-green-400 border-green-500/20",
      cyan: "bg-cyan-500/10 text-cyan-400 border-cyan-500/20",
      amber: "bg-amber-500/10 text-amber-400 border-amber-500/20",
      red: "bg-red-500/10 text-red-400 border-red-500/20",
      purple: "bg-purple-500/10 text-purple-400 border-purple-500/20",
      blue: "bg-blue-500/10 text-blue-400 border-blue-500/20",
    };
    return `px-2 py-0.5 rounded-sm text-xs font-medium border ${map[color] || map.green}`;
  }
  const cyberMap = {
    green: "text-[hsl(162,100%,50%)] border-[rgba(0,230,118,0.25)] bg-[rgba(0,230,118,0.06)]",
    cyan: "text-[hsl(185,100%,55%)] border-[rgba(0,229,255,0.25)] bg-[rgba(0,229,255,0.06)]",
    amber: "text-amber-400 border-amber-500/25 bg-amber-500/05",
    red: "text-red-400 border-red-500/25 bg-red-500/05",
    purple: "text-purple-400 border-purple-500/25 bg-purple-500/05",
    blue: "text-[hsl(185,100%,55%)] border-[rgba(0,229,255,0.25)] bg-[rgba(0,229,255,0.06)]",
  };
  return `px-2 py-0.5 rounded text-[10px] font-mono font-medium border ${cyberMap[color] || cyberMap.green}`;
}

/**
 * Modal/Dialog container class
 * @param {boolean} isCyber
 */
export function modalClass(isCyber) {
  return isCyber ? "glass-modal" : "bg-card border border-border rounded-sm";
}
