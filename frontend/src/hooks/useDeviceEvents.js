/**
 * useDeviceEvents — SSE hook untuk real-time device status dari backend
 * EventSource ke /api/events/devices, auto-reconnect tanpa batas jika disconnect.
 *
 * Perbaikan:
 *  - Unlimited reconnect (tidak ada MAX_RECONNECT_ATTEMPTS cap)
 *  - Exponential backoff: 3s → 6s → 12s → ... → max 60s
 *  - Reset backoff ke 3s segera saat koneksi berhasil
 *  - Page Visibility API: reconnect segera saat tab aktif kembali
 *
 * Returns:
 *   devices     : array device terbaru
 *   summary     : { total, online, offline }
 *   connected   : boolean
 *   lastUpdate  : ISO string timestamp update terakhir
 */
import { useState, useEffect, useRef, useCallback } from "react";

const SSE_URL = "/api/events/devices";
const BASE_DELAY_MS = 3000;
const MAX_DELAY_MS  = 60_000;

export default function useDeviceEvents() {
  const [devices, setDevices]     = useState([]);
  const [summary, setSummary]     = useState({ total: 0, online: 0, offline: 0 });
  const [connected, setConnected] = useState(false);
  const [lastUpdate, setLastUpdate] = useState(null);

  const esRef           = useRef(null);
  const reconnectTimer  = useRef(null);
  const attemptRef      = useRef(0);
  const mountedRef      = useRef(true);
  // connectRef agar Page Visibility bisa memanggil connect() terbaru
  const connectRef      = useRef(null);

  const connect = useCallback(() => {
    if (!mountedRef.current) return;

    // Tutup koneksi lama jika ada
    if (esRef.current) {
      esRef.current.close();
      esRef.current = null;
    }
    clearTimeout(reconnectTimer.current);

    const token = localStorage.getItem("noc_token");
    if (!token) return;

    const url = `${SSE_URL}?token=${encodeURIComponent(token)}`;
    const es  = new EventSource(url);
    esRef.current = es;

    es.addEventListener("device_status", (ev) => {
      if (!mountedRef.current) return;
      try {
        const data = JSON.parse(ev.data);
        setDevices(data.devices || []);
        setSummary(data.summary || { total: 0, online: 0, offline: 0 });
        setLastUpdate(data.timestamp || new Date().toISOString());
        // Reset backoff setelah menerima data sukses
        attemptRef.current = 0;
      } catch (err) {
        console.warn("[SSE] parse error:", err);
      }
    });

    es.addEventListener("heartbeat", () => {
      if (!mountedRef.current) return;
      setConnected(true);
    });

    es.onopen = () => {
      if (!mountedRef.current) return;
      setConnected(true);
      attemptRef.current = 0; // reset backoff
    };

    es.onerror = () => {
      if (!mountedRef.current) return;
      setConnected(false);
      es.close();
      esRef.current = null;

      // Exponential backoff tanpa batas maksimum percobaan
      const delay = Math.min(BASE_DELAY_MS * Math.pow(1.5, attemptRef.current), MAX_DELAY_MS);
      attemptRef.current += 1;
      console.info(`[SSE] Disconnected. Reconnecting in ${(delay / 1000).toFixed(1)}s (attempt #${attemptRef.current})`);

      reconnectTimer.current = setTimeout(() => {
        if (mountedRef.current) connect();
      }, delay);
    };
  }, []);

  // Simpan referensi terbaru dari connect() agar bisa dipanggil dari event listener
  useEffect(() => {
    connectRef.current = connect;
  }, [connect]);

  useEffect(() => {
    mountedRef.current = true;
    connect();

    // Page Visibility API: reconnect segera saat tab aktif kembali setelah lama di background
    const handleVisibilityChange = () => {
      if (document.visibilityState === "visible" && mountedRef.current) {
        // Jika SSE sedang tidak terhubung, langsung reconnect sekarang
        if (!esRef.current || esRef.current.readyState === EventSource.CLOSED) {
          clearTimeout(reconnectTimer.current);
          attemptRef.current = 0; // reset backoff saat user aktif kembali
          connectRef.current?.();
        }
      }
    };

    document.addEventListener("visibilitychange", handleVisibilityChange);

    return () => {
      mountedRef.current = false;
      clearTimeout(reconnectTimer.current);
      document.removeEventListener("visibilitychange", handleVisibilityChange);
      if (esRef.current) {
        esRef.current.close();
        esRef.current = null;
      }
    };
  }, [connect]);

  return { devices, summary, connected, lastUpdate };
}
