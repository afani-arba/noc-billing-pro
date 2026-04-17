import { useState, useEffect, useCallback } from "react";
import api from "@/lib/api";
import { useAuth } from "@/App";
import {
  Plus, Pencil, Trash2, RefreshCw, Shield, Eye, User, Server, Check,
  Activity, Wifi, WifiOff, Clock, MapPin, Bell, LogOut, ToggleLeft,
  ToggleRight, Zap, Bot, Settings, Users, ShieldCheck, ShieldAlert,
  MonitorDot, CreditCard, Headphones
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Switch } from "@/components/ui/switch";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription,
} from "@/components/ui/dialog";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import {
  Tabs, TabsContent, TabsList, TabsTrigger
} from "@/components/ui/tabs";
import {
  Tooltip, TooltipContent, TooltipProvider, TooltipTrigger
} from "@/components/ui/tooltip";
import { toast } from "sonner";

// ── Role Configuration ──────────────────────────────────────────────────────
const roleConfig = {
  super_admin:   { icon: ShieldCheck, color: "text-red-500",    bg: "bg-red-500/10 border-red-500/20",     label: "Super Admin",   desc: "Akses penuh ke semua fitur, lisensi & sistem" },
  administrator: { icon: Shield,      color: "text-red-400",    bg: "bg-red-400/10 border-red-400/20",     label: "Administrator", desc: "Akses penuh + User Management" },
  admin:         { icon: ShieldAlert, color: "text-orange-500", bg: "bg-orange-500/10 border-orange-500/20", label: "Admin",       desc: "Akses semua service — tidak bisa kelola User Management" },
  branch_admin:  { icon: MonitorDot,  color: "text-purple-400", bg: "bg-purple-400/10 border-purple-400/20", label: "Branch Admin",  desc: "Akses cabang (billing & router) tanpa setting sistem" },
  noc_engineer:  { icon: MonitorDot,  color: "text-orange-400", bg: "bg-orange-400/10 border-orange-400/20", label: "NOC Engineer",  desc: "Full monitoring & routing — tidak ada akses Billing" },
  billing_staff: { icon: CreditCard,  color: "text-green-400",  bg: "bg-green-400/10 border-green-400/20",  label: "Billing Staff", desc: "Full billing & keuangan — tidak ada routing" },
  helpdesk:      { icon: Headphones,  color: "text-blue-400",   bg: "bg-blue-400/10 border-blue-400/20",   label: "Helpdesk / CS", desc: "Read-only monitoring & daftar pelanggan" },
  viewer:        { icon: Eye,         color: "text-gray-400",   bg: "bg-gray-400/10 border-gray-400/20",   label: "Viewer (Legacy)", desc: "Read-only semua halaman monitoring" },
};

// Service categories for the checkbox panel
const SERVICE_CATEGORIES = [
  {
    label: "🖥️ Monitoring Utama",
    services: ["dashboard", "wallboard"],
  },
  {
    label: "📡 Pelanggan & Jaringan",
    services: ["reports", "devices", "genieacs"],
  },
  {
    label: "🔀 Routing & Security",
    services: ["bgp_steering", "peering_eye"],
  },
  {
    label: "💳 Keuangan & Billing",
    services: ["billing", "hotspot_billing", "finance_report"],
  },
  {
    label: "🤖 Support & CS",
    services: ["wa_customer_service"],
  },
  {
    label: "⚙️ Admin & Sistem",
    services: ["notifications", "backups", "settings", "integration_settings", "radius_server", "update", "license"],
  },
];

const SERVICE_LABELS = {
  dashboard: "Dashboard", wallboard: "Wall Display",
  reports: "Reports", devices: "Devices", genieacs: "GenieACS / TR-069",
  bgp_steering: "App Traffic & BGP", peering_eye: "Sentinel Peering-Eye",
  billing: "Billing PPPoE", hotspot_billing: "Billing Hotspot",
  finance_report: "Laporan Keuangan",
  wa_customer_service: "CS Command Center",
  notifications: "Notifikasi", backups: "Backup Config",
  settings: "Pengaturan Platform", integration_settings: "Integrasi & Otomasi",
  update: "Update Aplikasi", radius_server: "Radius Server", license: "Lisensi & Add-ons"
};

const EMPTY_FORM = {
  username: "", password: "", full_name: "", role: "noc_engineer",
  allowed_devices: [], allowed_services: null, telegram_chat_id: "", is_active: true,
};

export default function AdminPage() {
  const { user: currentUser } = useAuth();
  const [users, setUsers] = useState([]);
  const [devices, setDevices] = useState([]);
  const [sessions, setSessions] = useState([]);
  const [rolesConfig, setRolesConfig] = useState(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState("users");

  // Dialog state
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(EMPTY_FORM);
  const [submitting, setSubmitting] = useState(false);

  // Activity drawer
  const [activityUser, setActivityUser] = useState(null);
  const [activityLogs, setActivityLogs] = useState([]);
  const [activityOpen, setActivityOpen] = useState(false);

  // ── Fetchers ──────────────────────────────────────────────────────────────
  const fetchUsers = useCallback(async () => {
    try {
      const res = await api.get("/admin/users");
      setUsers(res.data);
    } catch {
      toast.error("Gagal memuat daftar user");
    }
    setLoading(false);
  }, []);

  const fetchDevices = useCallback(async () => {
    try {
      const res = await api.get("/devices/all");
      setDevices(res.data);
    } catch {
      console.error("Gagal load devices");
    }
  }, []);

  const fetchSessions = useCallback(async () => {
    try {
      const res = await api.get("/admin/active-sessions");
      setSessions(res.data);
    } catch {
      console.error("Gagal load sessions");
    }
  }, []);

  const fetchRolesConfig = useCallback(async () => {
    try {
      const res = await api.get("/admin/roles-config");
      setRolesConfig(res.data);
    } catch {}
  }, []);

  useEffect(() => {
    fetchUsers();
    fetchDevices();
    fetchSessions();
    fetchRolesConfig();
  }, [fetchUsers, fetchDevices, fetchSessions, fetchRolesConfig]);

  // ── Form helpers ──────────────────────────────────────────────────────────
  const openAdd = () => {
    setEditing(null);
    setForm({ ...EMPTY_FORM });
    setDialogOpen(true);
  };

  const openEdit = (u) => {
    setEditing(u);
    setForm({
      username: u.username,
      password: "",
      full_name: u.full_name || "",
      role: u.role || "noc_engineer",
      allowed_devices: u.allowed_devices || [],
      allowed_services: u.allowed_services || null,
      telegram_chat_id: u.telegram_chat_id || "",
      is_active: u.is_active !== false,
    });
    setDialogOpen(true);
  };

  const toggleDevice = (deviceId) => {
    setForm(prev => ({
      ...prev,
      allowed_devices: prev.allowed_devices.includes(deviceId)
        ? prev.allowed_devices.filter(id => id !== deviceId)
        : [...prev.allowed_devices, deviceId]
    }));
  };

  const toggleService = (svc) => {
    setForm(prev => {
      const current = prev.allowed_services || getDefaultServicesForRole(prev.role);
      const updated = current.includes(svc)
        ? current.filter(s => s !== svc)
        : [...current, svc];
      return { ...prev, allowed_services: updated };
    });
  };

  const getDefaultServicesForRole = (role) => {
    return rolesConfig?.role_defaults?.[role] || [];
  };

  const getEffectiveServices = () => {
    if (form.allowed_services !== null) return form.allowed_services;
    return getDefaultServicesForRole(form.role);
  };

  const onRoleChange = (role) => {
    // Reset services to role defaults when role changes
    setForm(prev => ({ ...prev, role, allowed_services: null }));
  };

  // ── Save ──────────────────────────────────────────────────────────────────
  const handleSave = async () => {
    setSubmitting(true);
    try {
      if (editing) {
        const data = {
          full_name: form.full_name,
          role: form.role,
          allowed_devices: form.role === "super_admin" || form.role === "administrator" ? [] : form.allowed_devices,
          allowed_services: form.allowed_services,
          telegram_chat_id: form.telegram_chat_id || null,
          is_active: form.is_active,
        };
        if (form.password) data.password = form.password;
        await api.put(`/admin/users/${editing.id}`, data);
        toast.success("User berhasil diupdate");
      } else {
        if (!form.username || !form.password || !form.full_name) {
          toast.error("Username, nama lengkap, dan password wajib diisi");
          return;
        }
        const data = {
          ...form,
          telegram_chat_id: form.telegram_chat_id || null,
          allowed_devices: form.role === "super_admin" || form.role === "administrator" ? [] : form.allowed_devices,
        };
        await api.post("/admin/users", data);
        toast.success("User berhasil dibuat");
      }
      setDialogOpen(false);
      fetchUsers();
    } catch (err) {
      toast.error(err.response?.data?.detail || "Operasi gagal");
    } finally {
      setSubmitting(false);
    }
  };

  const handleDelete = async (id) => {
    if (!window.confirm("Hapus user ini secara permanen?")) return;
    try {
      await api.delete(`/admin/users/${id}`);
      toast.success("User dihapus");
      fetchUsers();
    } catch (err) {
      toast.error(err.response?.data?.detail || "Gagal menghapus");
    }
  };

  const handleToggleActive = async (u) => {
    try {
      const res = await api.post(`/admin/users/${u.id}/toggle-active`);
      toast.success(res.data.message);
      fetchUsers();
    } catch (err) {
      toast.error(err.response?.data?.detail || "Gagal mengubah status");
    }
  };

  const handleKick = async (u) => {
    if (!window.confirm(`Kick / force logout user '${u.username}'? Mereka akan otomatis logout.`)) return;
    try {
      const res = await api.post(`/admin/users/${u.id}/revoke-sessions`);
      toast.success(res.data.message);
      fetchSessions();
    } catch (err) {
      toast.error(err.response?.data?.detail || "Gagal kick user");
    }
  };

  const openActivity = async (u) => {
    setActivityUser(u);
    setActivityOpen(true);
    try {
      const res = await api.get(`/admin/users/${u.id}/activity`);
      setActivityLogs(res.data.logs || []);
    } catch {
      setActivityLogs([]);
    }
  };

  const getDeviceNames = (ids) => {
    if (!ids?.length) return "-";
    return devices.filter(d => ids.includes(d.id)).map(d => d.name).join(", ") || "-";
  };

  const formatTime = (ts) => {
    if (!ts) return "-";
    try {
      return new Date(ts).toLocaleString("id-ID", { day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });
    } catch { return ts; }
  };

  // ── Role Summary ──────────────────────────────────────────────────────────
  const roleSummary = Object.keys(roleConfig).map(role => ({
    role,
    count: users.filter(u => u.role === role).length,
    ...roleConfig[role],
  })).filter(r => r.count > 0 || ["super_admin", "administrator", "noc_engineer", "billing_staff"].includes(r.role));

  return (
    <TooltipProvider>
      <div className="space-y-6" data-testid="admin-page">
        {/* Header */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <h1 className="text-2xl sm:text-3xl font-bold tracking-tight flex items-center gap-2">
              <Users className="w-7 h-7 text-primary" />
              User Management
            </h1>
            <p className="text-xs sm:text-sm text-muted-foreground mt-1">
              Kelola akun staf, role akses, device & service yang diizinkan
            </p>
          </div>
          <div className="flex gap-2">
            <Button variant="outline" size="icon" onClick={() => { fetchUsers(); fetchSessions(); }} className="rounded-sm">
              <RefreshCw className="w-4 h-4" />
            </Button>
            <Button onClick={openAdd} className="rounded-sm gap-2" data-testid="add-admin-user-btn">
              <Plus className="w-4 h-4" /> <span className="hidden sm:inline">Tambah User</span>
            </Button>
          </div>
        </div>

        {/* Role Summary Cards */}
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2">
          {Object.entries(roleConfig).map(([role, cfg]) => {
            const count = users.filter(u => u.role === role).length;
            return (
              <div key={role} className={`bg-card border rounded-sm p-3 ${cfg.bg}`}>
                <div className="flex items-center gap-2 mb-1.5">
                  <cfg.icon className={`w-4 h-4 ${cfg.color}`} />
                  <span className="text-[10px] text-muted-foreground truncate">{cfg.label}</span>
                </div>
                <p className={`text-2xl font-bold ${cfg.color}`}>{count}</p>
              </div>
            );
          })}
        </div>

        {/* Main Tabs */}
        <Tabs value={activeTab} onValueChange={setActiveTab}>
          <TabsList className="rounded-sm">
            <TabsTrigger value="users" className="rounded-sm gap-1.5 text-xs">
              <Users className="w-3.5 h-3.5" /> Pengguna ({users.length})
            </TabsTrigger>
            <TabsTrigger value="sessions" className="rounded-sm gap-1.5 text-xs">
              <Activity className="w-3.5 h-3.5" /> Sesi Aktif ({sessions.filter(s => !s.is_revoked).length})
            </TabsTrigger>
          </TabsList>

          {/* ── Users Tab ─────────────────────────────────────────────────── */}
          <TabsContent value="users">
            <div className="bg-card border border-border rounded-sm overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow className="hover:bg-transparent">
                    <TableHead className="text-xs">Nama / Username</TableHead>
                    <TableHead className="text-xs">Role</TableHead>
                    <TableHead className="text-xs hidden lg:table-cell">Device Akses</TableHead>
                    <TableHead className="text-xs hidden lg:table-cell">Services</TableHead>
                    <TableHead className="text-xs hidden md:table-cell">Telegram</TableHead>
                    <TableHead className="text-xs hidden md:table-cell">Login Terakhir</TableHead>
                    <TableHead className="text-xs">Status</TableHead>
                    <TableHead className="text-xs text-right">Aksi</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {loading ? (
                    <TableRow><TableCell colSpan={8} className="text-center text-muted-foreground py-8">Memuat...</TableCell></TableRow>
                  ) : users.length === 0 ? (
                    <TableRow><TableCell colSpan={8} className="text-center text-muted-foreground py-8">Belum ada user</TableCell></TableRow>
                  ) : users.map(u => {
                    const cfg = roleConfig[u.role] || roleConfig.viewer;
                    const isMe = u.id === currentUser?.id;
                    const isActive = u.is_active !== false;
                    return (
                      <TableRow key={u.id} data-testid={`admin-row-${u.username}`} className={!isActive ? "opacity-50" : ""}>
                        <TableCell className="font-medium text-xs sm:text-sm">
                          <div className="font-semibold">{u.full_name}</div>
                          <div className="font-mono text-[10px] text-muted-foreground">{u.username}{isMe && <span className="ml-1 text-primary">(saya)</span>}</div>
                        </TableCell>
                        <TableCell>
                          <Badge className={`rounded-sm text-[10px] border capitalize ${cfg.bg} ${cfg.color}`}>
                            <cfg.icon className="w-3 h-3 mr-1" />{cfg.label}
                          </Badge>
                        </TableCell>
                        <TableCell className="hidden lg:table-cell text-xs text-muted-foreground max-w-[150px] truncate">
                          {["super_admin", "administrator"].includes(u.role) ? (
                            <span className="text-primary text-[10px]">All Devices</span>
                          ) : (
                            <span title={getDeviceNames(u.allowed_devices)}>
                              {(u.allowed_devices?.length || 0)} device
                            </span>
                          )}
                        </TableCell>
                        <TableCell className="hidden lg:table-cell text-xs text-muted-foreground">
                          {["super_admin", "administrator"].includes(u.role) ? (
                            <span className="text-primary text-[10px]">All Services</span>
                          ) : (
                            <span>{(u.allowed_services?.length || 0)} service</span>
                          )}
                        </TableCell>
                        <TableCell className="hidden md:table-cell">
                          {u.telegram_chat_id ? (
                            <Badge className="rounded-sm text-[10px] bg-blue-500/10 text-blue-400 border-blue-500/20">
                              <Bot className="w-3 h-3 mr-1" /> Terhubung
                            </Badge>
                          ) : (
                            <span className="text-[10px] text-muted-foreground">-</span>
                          )}
                        </TableCell>
                        <TableCell className="hidden md:table-cell text-[10px] text-muted-foreground">
                          <div className="flex flex-col gap-0.5">
                            <span>{formatTime(u.last_login)}</span>
                            {u.last_login_ip && <span className="font-mono text-[9px]">{u.last_login_ip}</span>}
                          </div>
                        </TableCell>
                        <TableCell>
                          <Badge className={`rounded-sm text-[10px] border ${isActive ? "bg-green-500/10 text-green-400 border-green-500/20" : "bg-red-500/10 text-red-400 border-red-500/20"}`}>
                            {isActive ? <Wifi className="w-3 h-3 mr-1" /> : <WifiOff className="w-3 h-3 mr-1" />}
                            {isActive ? "Aktif" : "Nonaktif"}
                          </Badge>
                        </TableCell>
                        <TableCell className="text-right">
                          <div className="flex items-center justify-end gap-1">
                            <Tooltip>
                              <TooltipTrigger asChild>
                                <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => openActivity(u)}>
                                  <Clock className="w-3.5 h-3.5" />
                                </Button>
                              </TooltipTrigger>
                              <TooltipContent>Riwayat Aktivitas</TooltipContent>
                            </Tooltip>
                            <Tooltip>
                              <TooltipTrigger asChild>
                                <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => openEdit(u)} data-testid={`admin-edit-${u.username}`}>
                                  <Pencil className="w-3.5 h-3.5" />
                                </Button>
                              </TooltipTrigger>
                              <TooltipContent>Edit User</TooltipContent>
                            </Tooltip>
                            {!isMe && (
                              <>
                                <Tooltip>
                                  <TooltipTrigger asChild>
                                    <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => handleToggleActive(u)}>
                                      {isActive ? <ToggleRight className="w-3.5 h-3.5 text-orange-400" /> : <ToggleLeft className="w-3.5 h-3.5 text-green-400" />}
                                    </Button>
                                  </TooltipTrigger>
                                  <TooltipContent>{isActive ? "Nonaktifkan Akun" : "Aktifkan Akun"}</TooltipContent>
                                </Tooltip>
                                <Tooltip>
                                  <TooltipTrigger asChild>
                                    <Button variant="ghost" size="icon" className="h-7 w-7 text-yellow-400" onClick={() => handleKick(u)}>
                                      <LogOut className="w-3.5 h-3.5" />
                                    </Button>
                                  </TooltipTrigger>
                                  <TooltipContent>Force Logout (Kick Session)</TooltipContent>
                                </Tooltip>
                                <Tooltip>
                                  <TooltipTrigger asChild>
                                    <Button variant="ghost" size="icon" className="h-7 w-7 text-destructive" onClick={() => handleDelete(u.id)} data-testid={`admin-delete-${u.username}`}>
                                      <Trash2 className="w-3.5 h-3.5" />
                                    </Button>
                                  </TooltipTrigger>
                                  <TooltipContent>Hapus User</TooltipContent>
                                </Tooltip>
                              </>
                            )}
                          </div>
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            </div>
            <p className="text-xs text-muted-foreground mt-2">Total: {users.length} user terdaftar</p>
          </TabsContent>

          {/* ── Sessions Tab ──────────────────────────────────────────────── */}
          <TabsContent value="sessions">
            <div className="bg-card border border-border rounded-sm overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow className="hover:bg-transparent">
                    <TableHead className="text-xs">User</TableHead>
                    <TableHead className="text-xs">Role</TableHead>
                    <TableHead className="text-xs">Login Terakhir</TableHead>
                    <TableHead className="text-xs">IP Address</TableHead>
                    <TableHead className="text-xs">Status Sesi</TableHead>
                    <TableHead className="text-xs text-right">Aksi</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {sessions.length === 0 ? (
                    <TableRow><TableCell colSpan={6} className="text-center text-muted-foreground py-8">Tidak ada sesi aktif dalam 24 jam terakhir</TableCell></TableRow>
                  ) : sessions.map(s => {
                    const cfg = roleConfig[s.role] || roleConfig.viewer;
                    return (
                      <TableRow key={s.user_id}>
                        <TableCell className="text-xs font-medium">
                          <div>{s.full_name}</div>
                          <div className="font-mono text-[10px] text-muted-foreground">{s.username}</div>
                        </TableCell>
                        <TableCell>
                          <Badge className={`rounded-sm text-[10px] border ${cfg.bg} ${cfg.color}`}>
                            {cfg.label}
                          </Badge>
                        </TableCell>
                        <TableCell className="text-[10px] text-muted-foreground">{formatTime(s.last_login)}</TableCell>
                        <TableCell className="font-mono text-[10px] text-muted-foreground">{s.last_login_ip || "-"}</TableCell>
                        <TableCell>
                          <Badge className={`rounded-sm text-[10px] border ${s.is_revoked ? "bg-red-500/10 text-red-400 border-red-500/20" : "bg-green-500/10 text-green-400 border-green-500/20"}`}>
                            {s.is_revoked ? "Session Dicabut" : "Aktif"}
                          </Badge>
                        </TableCell>
                        <TableCell className="text-right">
                          {s.user_id !== currentUser?.id && !s.is_revoked && (
                            <Tooltip>
                              <TooltipTrigger asChild>
                                <Button variant="ghost" size="icon" className="h-7 w-7 text-yellow-400"
                                  onClick={() => handleKick({ id: s.user_id, username: s.username })}>
                                  <LogOut className="w-3.5 h-3.5" />
                                </Button>
                              </TooltipTrigger>
                              <TooltipContent>Force Logout</TooltipContent>
                            </Tooltip>
                          )}
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            </div>
          </TabsContent>
        </Tabs>

        {/* ── Add/Edit Dialog ─────────────────────────────────────────────── */}
        <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
          <DialogContent className="rounded-sm bg-card border-border max-w-2xl max-h-[90vh] overflow-y-auto" data-testid="admin-user-dialog">
            <DialogHeader>
              <DialogTitle className="text-xl">{editing ? "Edit User" : "Tambah User Baru"}</DialogTitle>
              <DialogDescription>
                {editing ? "Perbarui detail, role, dan akses device/service." : "Buat akun staf baru dengan role dan izin akses yang sesuai."}
              </DialogDescription>
            </DialogHeader>

            <div className="space-y-5">
              {/* Basic Info */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                {!editing && (
                  <div className="space-y-1.5">
                    <Label className="text-xs text-muted-foreground">Username *</Label>
                    <Input value={form.username} onChange={e => setForm({ ...form, username: e.target.value })}
                      className="rounded-sm bg-background font-mono" placeholder="budi_noc" data-testid="admin-form-username" />
                  </div>
                )}
                <div className="space-y-1.5">
                  <Label className="text-xs text-muted-foreground">Nama Lengkap *</Label>
                  <Input value={form.full_name} onChange={e => setForm({ ...form, full_name: e.target.value })}
                    className="rounded-sm bg-background" placeholder="Budi Santoso" data-testid="admin-form-fullname" />
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs text-muted-foreground">{editing ? "Password Baru (kosong = tidak berubah)" : "Password *"}</Label>
                  <Input type="password" value={form.password} onChange={e => setForm({ ...form, password: e.target.value })}
                    className="rounded-sm bg-background" placeholder={editing ? "(tidak berubah)" : "••••••••"} data-testid="admin-form-password" />
                </div>
              </div>

              {/* Role Selection */}
              <div className="space-y-2">
                <Label className="text-xs text-muted-foreground">Role</Label>
                <Select value={form.role} onValueChange={onRoleChange}>
                  <SelectTrigger className="rounded-sm bg-background" data-testid="admin-form-role">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {Object.entries(roleConfig).map(([role, cfg]) => (
                      <SelectItem key={role} value={role}>
                        <div className="flex items-center gap-2">
                          <cfg.icon className={`w-3.5 h-3.5 ${cfg.color}`} />
                          <span className="font-medium">{cfg.label}</span>
                          <span className="text-[10px] text-muted-foreground hidden sm:inline">— {cfg.desc}</span>
                        </div>
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                {roleConfig[form.role] && (
                  <p className="text-[10px] text-muted-foreground pl-1">{roleConfig[form.role].desc}</p>
                )}
              </div>

              {/* Telegram Chat ID */}
              <div className="space-y-1.5">
                <Label className="text-xs text-muted-foreground flex items-center gap-1.5">
                  <Bot className="w-3.5 h-3.5 text-blue-400" /> Telegram Chat ID (opsional)
                </Label>
                <Input value={form.telegram_chat_id} onChange={e => setForm({ ...form, telegram_chat_id: e.target.value })}
                  className="rounded-sm bg-background font-mono" placeholder="123456789" />
                <p className="text-[10px] text-muted-foreground">Notifikasi insiden akan dikirim langsung ke Telegram user ini (jika ada device yang di-assign)</p>
              </div>

              {/* is_active toggle */}
              {editing && (
                <div className="flex items-center justify-between p-3 bg-muted/30 rounded-sm border border-border">
                  <div>
                    <p className="text-sm font-medium">Status Akun</p>
                    <p className="text-[10px] text-muted-foreground">Nonaktifkan untuk memblokir login tanpa menghapus data</p>
                  </div>
                  <Switch checked={form.is_active} onCheckedChange={v => setForm({ ...form, is_active: v })} />
                </div>
              )}

              {/* Device Access — hide for super_admin / administrator */}
              {!["super_admin", "administrator"].includes(form.role) && (
                <div className="space-y-2">
                  <div className="flex items-center justify-between">
                    <Label className="text-xs text-muted-foreground flex items-center gap-1.5">
                      <Server className="w-3.5 h-3.5" /> Device yang Diizinkan
                    </Label>
                    <div className="flex gap-2">
                      <Button type="button" variant="ghost" size="sm" className="h-6 text-[10px]"
                        onClick={() => setForm(prev => ({ ...prev, allowed_devices: devices.map(d => d.id) }))}>
                        Semua
                      </Button>
                      <Button type="button" variant="ghost" size="sm" className="h-6 text-[10px]"
                        onClick={() => setForm(prev => ({ ...prev, allowed_devices: [] }))}>
                        Kosongkan
                      </Button>
                    </div>
                  </div>
                  <div className="border border-border rounded-sm p-3 max-h-40 overflow-y-auto bg-background/50 space-y-1.5">
                    {devices.length === 0 ? (
                      <p className="text-xs text-muted-foreground text-center py-2">Belum ada device</p>
                    ) : devices.map(device => (
                      <div key={device.id}
                        className={`flex items-center gap-3 p-2 rounded-sm cursor-pointer transition-colors ${
                          form.allowed_devices.includes(device.id)
                            ? "bg-primary/10 border border-primary/30"
                            : "hover:bg-secondary/50"
                        }`}
                        onClick={() => toggleDevice(device.id)}>
                        <div className={`w-4 h-4 rounded-sm border flex items-center justify-center flex-shrink-0 ${
                          form.allowed_devices.includes(device.id) ? "bg-primary border-primary" : "border-border"
                        }`}>
                          {form.allowed_devices.includes(device.id) && <Check className="w-3 h-3 text-primary-foreground" />}
                        </div>
                        <Server className="w-3.5 h-3.5 text-muted-foreground flex-shrink-0" />
                        <div className="flex-1 min-w-0">
                          <p className="text-xs font-medium truncate">{device.name}</p>
                          <p className="text-[10px] text-muted-foreground font-mono">{device.ip_address}</p>
                        </div>
                      </div>
                    ))}
                  </div>
                  <p className="text-[10px] text-muted-foreground">Dipilih: {form.allowed_devices.length} dari {devices.length} device</p>
                </div>
              )}

              {/* Services Access */}
              {!["super_admin", "administrator"].includes(form.role) && (
                <div className="space-y-2">
                  <div className="flex items-center justify-between">
                    <Label className="text-xs text-muted-foreground flex items-center gap-1.5">
                      <Settings className="w-3.5 h-3.5" /> Service / Menu yang Diizinkan
                    </Label>
                    <Button type="button" variant="ghost" size="sm" className="h-6 text-[10px]"
                      onClick={() => setForm(prev => ({ ...prev, allowed_services: null }))}>
                      Reset ke Default Role
                    </Button>
                  </div>
                  <div className="border border-border rounded-sm p-3 max-h-64 overflow-y-auto bg-background/50 space-y-4">
                    {SERVICE_CATEGORIES.map(cat => (
                      <div key={cat.label}>
                        <p className="text-[10px] font-semibold text-muted-foreground mb-2">{cat.label}</p>
                        <div className="grid grid-cols-2 gap-1.5">
                          {cat.services.map(svc => {
                            const effectiveServices = getEffectiveServices();
                            const isChecked = effectiveServices.includes(svc);
                            return (
                              <div key={svc}
                                className={`flex items-center gap-2 p-1.5 rounded-sm cursor-pointer text-xs transition-colors ${
                                  isChecked ? "bg-primary/10 text-primary" : "text-muted-foreground hover:bg-secondary/50"
                                }`}
                                onClick={() => toggleService(svc)}>
                                <div className={`w-3.5 h-3.5 rounded border flex items-center justify-center flex-shrink-0 ${
                                  isChecked ? "bg-primary border-primary" : "border-border"
                                }`}>
                                  {isChecked && <Check className="w-2.5 h-2.5 text-primary-foreground" />}
                                </div>
                                {SERVICE_LABELS[svc] || svc}
                              </div>
                            );
                          })}
                        </div>
                      </div>
                    ))}
                  </div>
                  {form.allowed_services === null && (
                    <p className="text-[10px] text-muted-foreground">Menggunakan default role. Klik service untuk kustomisasi.</p>
                  )}
                </div>
              )}
            </div>

            <DialogFooter>
              <Button variant="outline" onClick={() => setDialogOpen(false)} className="rounded-sm" data-testid="admin-form-cancel">Batal</Button>
              <Button onClick={handleSave} className="rounded-sm" disabled={submitting} data-testid="admin-form-save">
                {submitting ? "Menyimpan..." : (editing ? "Update" : "Buat User")}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>

        {/* ── Activity Log Dialog ──────────────────────────────────────────── */}
        <Dialog open={activityOpen} onOpenChange={setActivityOpen}>
          <DialogContent className="rounded-sm bg-card border-border max-w-xl max-h-[80vh] overflow-y-auto">
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                <Clock className="w-4 h-4" /> Riwayat Aktivitas: {activityUser?.full_name}
              </DialogTitle>
              <DialogDescription className="font-mono text-xs">{activityUser?.username}</DialogDescription>
            </DialogHeader>
            {activityLogs.length === 0 ? (
              <p className="text-center text-muted-foreground py-6 text-sm">Tidak ada aktivitas tercatat</p>
            ) : (
              <div className="space-y-2 mt-2">
                {activityLogs.map(log => (
                  <div key={log.id} className="p-3 bg-muted/30 rounded-sm border border-border/50">
                    <div className="flex items-center justify-between mb-1">
                      <Badge className={`rounded-sm text-[10px] ${
                        log.action === "DELETE" ? "bg-red-500/10 text-red-400 border-red-500/20" :
                        log.action === "CREATE" ? "bg-green-500/10 text-green-400 border-green-500/20" :
                        log.action === "LOGIN"  ? "bg-blue-500/10 text-blue-400 border-blue-500/20" :
                        "bg-orange-500/10 text-orange-400 border-orange-500/20"
                      } border`}>
                        {log.action}
                      </Badge>
                      <span className="text-[10px] text-muted-foreground">{formatTime(log.timestamp)}</span>
                    </div>
                    <p className="text-xs text-foreground">{log.details}</p>
                    <p className="text-[10px] text-muted-foreground mt-0.5">Resource: {log.resource} {log.resource_id ? `(${log.resource_id.substring(0, 8)}...)` : ""}</p>
                  </div>
                ))}
              </div>
            )}
          </DialogContent>
        </Dialog>
      </div>
    </TooltipProvider>
  );
}
