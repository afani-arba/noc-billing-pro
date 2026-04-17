/**
 * useAllowedDevices
 * 
 * Custom hook yang mengembalikan daftar device yang sudah difilter
 * berdasarkan user.allowed_devices (RBAC multi-tenant).
 * 
 * - Super Admin / Administrator: melihat semua device
 * - Branch Admin / NOC / Billing Staff / dll: hanya melihat device yang diizinkan
 * 
 * Jika user hanya memiliki 1 device yang diizinkan → selectedDevice
 * akan otomatis dikunci ke device tersebut (tidak bisa diubah).
 */
import { useState, useEffect, useCallback } from "react";
import { useAuth } from "@/App";
import api from "@/lib/api";

const ADMIN_ROLES = ["super_admin", "administrator"];

export function useAllowedDevices(autoSelectFirst = true) {
  const { user } = useAuth();
  const [allDevices, setAllDevices] = useState([]);
  const [loading, setLoading] = useState(true);

  // Fetch semua device yang diizinkan untuk user ini
  // Backend sudah memfilter via filter_devices_for_user()
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
  }, []);

  useEffect(() => {
    fetchDevices();
  }, [fetchDevices]);

  // Apakah user adalah admin penuh (bisa lihat semua)
  const isAdmin = ADMIN_ROLES.includes(user?.role);

  // Device yang diizinkan untuk user ini
  // - Admin: semua device
  // - Non-admin dengan allowed_devices: filter sesuai list
  // - Non-admin tanpa allowed_devices: semua device yang dikembalikan backend
  const allowedDeviceIds = user?.allowed_devices;
  const filteredDevices = (isAdmin || !allowedDeviceIds || allowedDeviceIds.length === 0)
    ? allDevices
    : allDevices.filter(d => allowedDeviceIds.includes(d.id));

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
