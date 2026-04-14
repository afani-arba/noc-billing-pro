import React, { useMemo, useState } from "react";
import { Info } from "lucide-react";

/**
 * Custom Heatmap Component for Latency (Ping/Jitter) based on Grafana style.
 * Maps linear traffic_history (array of { time, ping, jitter }) into a 2D histogram array.
 */

// Y-Axis Buckets (from top to bottom visually)
// Y-Axis Buckets for Ping (from top to bottom visually)
const PING_BUCKETS = [
  { label: "1 min",  min: 20000, max: Infinity },
  { label: "20 s",   min: 5000,  max: 20000 },
  { label: "5 s",    min: 1000,  max: 5000 },
  { label: "1 s",    min: 250,   max: 1000 },
  { label: "250 ms", min: 50,    max: 250 },
  { label: "50 ms",  min: 10,    max: 50 },
  { label: "10 ms",  min: 0,     max: 10 },
];

// Y-Axis Buckets for Jitter (smaller scale)
const JITTER_BUCKETS = [
  { label: "1 s",    min: 1000, max: Infinity },
  { label: "250 ms", min: 250,  max: 1000 },
  { label: "50 ms",  min: 50,   max: 250 },
  { label: "20 ms",  min: 20,   max: 50 },
  { label: "10 ms",  min: 10,   max: 20 },
  { label: "5 ms",   min: 2,    max: 10 },
  { label: "1 ms",   min: 0,    max: 2 },
];

// Number of X-Axis Time columns (Visual Grid Width)
const X_COLUMNS = 45;

/**
 * Returns a color based on count intensity [0..1]
 * Uses a spectrum similar to Grafana: Low(Blue) -> Cyan -> Green -> Yellow -> Orange -> Red(High)
 */
function getHeatColor(intensity) {
  if (intensity === 0) return "transparent"; // Or a very dark baseline color like #1e1e1e if border is needed
  if (intensity < 0.1) return "#1e3a8a"; // Deep Blue
  if (intensity < 0.25) return "#0284c7"; // Blue/Cyan
  if (intensity < 0.4) return "#10b981"; // Green
  if (intensity < 0.6) return "#84cc16"; // Yellow-Green
  if (intensity < 0.75) return "#eab308"; // Yellow
  if (intensity < 0.9) return "#ea580c"; // Orange
  return "#dc2626"; // Red
}

export default function LatencyHeatmap({ data = [], dataKey = "ping" }) {
  const [hoveredCell, setHoveredCell] = useState(null);

  const Y_BUCKETS = dataKey === "jitter" ? JITTER_BUCKETS : PING_BUCKETS;

  const { grid, maxCount, timeLabels } = useMemo(() => {
    if (!data || data.length === 0) {
      return { grid: [], maxCount: 0, timeLabels: [] };
    }

    // Filter out rows where data is totally invalid
    // Jitter can legitimately be 0, and Ping can technically be 0 or very near 0 
    const validData = data.filter((d) => d[dataKey] !== undefined && d[dataKey] !== null);

    if (validData.length === 0) {
      return { grid: [], maxCount: 0, timeLabels: [] };
    }

    // Determine the time span to chunk into X_COLUMNS
    const startTimeStr = validData[0].time;
    const endTimeStr = validData[validData.length - 1].time;

    // Helper to parse time strings "HH:mm:ss" or "HH:mm" to seconds (for rough binning)
    const parseTime = (tStr) => {
      const parts = tStr.split(":");
      let seconds = 0;
      if (parts.length === 3) {
        seconds = (+parts[0]) * 3600 + (+parts[1]) * 60 + (+parts[2]);
      } else if (parts.length === 2) {
        seconds = (+parts[0]) * 3600 + (+parts[1]) * 60;
      }
      return seconds;
    };

    const startSec = parseTime(startTimeStr);
    let endSec = parseTime(endTimeStr);
    
    // Handle overnight wrapping
    if (endSec < startSec) endSec += 24 * 3600; 

    // Total span in seconds
    const totalSpan = endSec - startSec || 1; 
    const bucketDuration = totalSpan / X_COLUMNS;

    // Initialize 2D array [row_y][col_x]
    const matrix = Array(Y_BUCKETS.length)
      .fill(null)
      .map(() => Array(X_COLUMNS).fill(0));

    // Distribution
    let currentMaxCount = 0;

    validData.forEach((d) => {
      let tSec = parseTime(d.time);
      if (tSec < startSec) tSec += 24 * 3600;
      
      const elapsed = tSec - startSec;
      let colIdx = Math.floor(elapsed / bucketDuration);
      if (colIdx >= X_COLUMNS) colIdx = X_COLUMNS - 1;
      if (colIdx < 0) colIdx = 0;

      // Extract raw data points if available, otherwise fallback to the averaged value
      const rawData = d[`${dataKey}_raw`] && Array.isArray(d[`${dataKey}_raw`]) && d[`${dataKey}_raw`].length > 0 
        ? d[`${dataKey}_raw`] 
        : [d[dataKey]];

      rawData.forEach((valStr) => {
        const val = parseFloat(valStr || 0);
        if (val < 0) return; // Ignore negative pings (offline/errors), but allow 0 (e.g. 0.0 Jitter)

        const rowIdx = Y_BUCKETS.findIndex((b) => val >= b.min && val < b.max);
        
        if (rowIdx !== -1) {
          matrix[rowIdx][colIdx] += 1;
          if (matrix[rowIdx][colIdx] > currentMaxCount) {
            currentMaxCount = matrix[rowIdx][colIdx];
          }
        }
      });
    });

    // Generate labels for X axis (approx every 15 columns)
    const labels = [];
    for (let i = 0; i <= X_COLUMNS; i += 15) {
      if (i >= X_COLUMNS) break;
      const targetSec = startSec + i * bucketDuration;
      let hr = Math.floor(targetSec / 3600) % 24;
      let min = Math.floor((targetSec % 3600) / 60);
      labels.push({
        idx: i,
        label: `${hr.toString().padStart(2, "0")}:${min.toString().padStart(2, "0")}`
      });
    }
    // Add endpoint label
    {
       let hr = Math.floor(endSec / 3600) % 24;
       let min = Math.floor((endSec % 3600) / 60);
       labels.push({ idx: X_COLUMNS -1, label: `${hr.toString().padStart(2, "0")}:${min.toString().padStart(2, "0")}`});
    }

    return { grid: matrix, maxCount: currentMaxCount, timeLabels: labels };

  }, [data, dataKey]);

  if (!data || data.length === 0 || maxCount === 0) {
    return (
      <div className="h-48 flex items-center justify-center bg-secondary/10 rounded-sm border border-dashed border-border" data-testid="heatmap-empty">
        <div className="text-center text-muted-foreground/60">
          <Info className="w-8 h-8 mx-auto mb-2 opacity-50" />
          <p className="text-sm">Tidak ada data Heatmap untuk {dataKey === "ping" ? "Ping" : "Jitter"}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col select-none" style={{ background: "#141414", padding: "16px", borderRadius: "4px" }}>
      
      {/* Container for Y-axis + Grid */}
      <div className="flex">
        {/* Y Axis Labels */}
        <div className="flex flex-col justify-between pr-3 py-[2px]" style={{ fontSize: "10px", color: "#a1a1aa", fontFamily: "sans-serif", textAlign: "right", minWidth: "45px" }}>
          {Y_BUCKETS.map((b) => (
            <div key={b.label} className="h-full flex items-center justify-end leading-none">
              {b.label}
            </div>
          ))}
        </div>

        {/* Heatmap Grid */}
        <div className="flex-1 relative flex flex-col gap-[2px]">
          {grid.map((rowArr, rowIndex) => (
            <div key={`row-${rowIndex}`} className="flex flex-1 gap-[2px]">
              {rowArr.map((count, colIndex) => {
                const intensity = maxCount > 0 ? count / maxCount : 0;
                const bgColor = getHeatColor(intensity);
                const isHovered = hoveredCell?.r === rowIndex && hoveredCell?.c === colIndex;

                return (
                  <div
                    key={`cell-${rowIndex}-${colIndex}`}
                    className="flex-1 rounded-[1px] cursor-crosshair transition-all duration-100"
                    style={{
                      backgroundColor: bgColor !== "transparent" ? bgColor : "#1e1e1e",
                      border: "1px solid rgba(0,0,0,0.3)",
                      opacity: isHovered && count > 0 ? 0.8 : 1,
                      transform: isHovered && count > 0 ? "scale(1.1)" : "scale(1)",
                      zIndex: isHovered ? 10 : 1
                    }}
                    onMouseEnter={() => {
                      if (count > 0) setHoveredCell({ r: rowIndex, c: colIndex, count, bucket: Y_BUCKETS[rowIndex].label });
                    }}
                    onMouseLeave={() => setHoveredCell(null)}
                  />
                );
              })}
            </div>
          ))}
          
          {/* Tooltip Popup */}
          {hoveredCell && (
            <div 
              className="absolute pointer-events-none bg-black border border-zinc-700 text-white text-xs px-2 py-1 rounded shadow-lg z-50 whitespace-nowrap"
              style={{
                left: `${(hoveredCell.c / X_COLUMNS) * 100}%`,
                top: `${(hoveredCell.r / Y_BUCKETS.length) * 100}%`,
                transform: "translate(-50%, -120%)"
              }}
            >
              <div className="font-mono">{hoveredCell.count} hits</div>
              <div className="text-[10px] text-zinc-400">Latency: {hoveredCell.bucket}</div>
            </div>
          )}
        </div>
      </div>

      {/* X Axis Time Labels */}
      <div className="flex ml-[45px] mt-2 relative h-4">
        {timeLabels.map((lbl, idx) => (
          <div 
            key={`${lbl.idx}-${idx}`}
            className="absolute text-[10px] text-zinc-400 font-mono -translate-x-1/2" 
            style={{ left: `${(lbl.idx / (X_COLUMNS - 1)) * 100}%` }}
          >
            {lbl.label}
          </div>
        ))}
      </div>

      {/* Legend / Color Scale */}
      <div className="flex items-center gap-2 mt-4 ml-[45px]">
        <span className="text-[10px] text-zinc-500 font-mono">0</span>
        <div 
          className="h-1.5 w-64 rounded-full" 
          style={{ 
            background: `linear-gradient(to right, #1e3a8a, #0284c7, #10b981, #84cc16, #eab308, #ea580c, #dc2626)` 
          }}
        />
        <span className="text-[10px] text-zinc-500 font-mono">{maxCount} hits</span>
      </div>

    </div>
  );
}

