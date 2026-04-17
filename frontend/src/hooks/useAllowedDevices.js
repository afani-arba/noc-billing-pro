/**
 * useAllowedDevices
 *
 * Custom hook yang mengembalikan daftar device yang sudah difilter
 * berdasarkan user.allowed_devices (RBAC multi-tenant).
 *
 * - Super Admin / Administrator: melihat semua device
 * - Branch Admin / NOC / Billing Staff / dll: hanya melihat device yang diizinkan
 *
 * Jika user hanya memiliki 1 device yang diizinkan → isLocked = true
 * dan defaultDeviceId akan otomatis dikembalikan.
 *
 * FIX: fetchDevices hanya dipanggil sekali on-mount menggunakan ref untuk
 * menghindari cascade re-render / page refresh.
 */
import { useState, useEffect, useCallback, useRef } from "react";
import { useAuth } from "@/App";
import api from "@/lib/api";

const ADMIN_ROLES = ["super_admin", "administrator"];

export function useAllowedDevices(autoSelectFirst = true) {
  const { user } = useAuth();
  const [allDevices, setAllDevices] = useState([]);
  const [loading, setLoading] = useState(true);

  // Gunakan ref agar hasFetched tidak trigger re-render
  const hasFetched = useRef(false);

  const fetchDevices = useCallback(async () => {
    setLoading(true);
    try {
      const r = await api.get("/devices");
      setAllDevices(r.data || []);
    } catch {
      setAllDevices([]);
    } finally {
      setLoading(false);
    }
  }, []); // dependency kosong — tidak perlu bergantung pada user karena backend sudah filter

  // Hanya fetch sekali saat mount, gunakan ref untuk guard
  useEffect(() => {
    if (!hasFetched.current) {
      hasFetched.current = true;
      fetchDevices();
    }
  }, [fetchDevices]);

  // Apakah user adalah admin penuh (bisa lihat semua)
  const isAdmin = ADMIN_ROLES.includes(user?.role);

  // Device yang diizinkan untuk user ini
  // - Admin: semua device
  // - Non-admin dengan allowed_devices: filter sesuai list
  // - Non-admin tanpa allowed_devices: semua device yang dikembalikan backend
  const allowedDeviceIds = user?.allowed_devices;
  const filteredDevices =
    isAdmin || !allowedDeviceIds || allowedDeviceIds.length === 0
      ? allDevices
      : allDevices.filter((d) => allowedDeviceIds.includes(d.id));

  // Apakah dropdown harus dikunci (hanya 1 device)
  const isLocked = !isAdmin && filteredDevices.length === 1;

  // Default device ID (pertama jika locked, atau kosong jika admin)
  const defaultDeviceId = isLocked ? filteredDevices[0]?.id : "";

  return {
    devices: filteredDevices,
    allDevices,
    loading,
    isAdmin,
    isLocked,
    defaultDeviceId,
    refetch: fetchDevices,
  };
}
