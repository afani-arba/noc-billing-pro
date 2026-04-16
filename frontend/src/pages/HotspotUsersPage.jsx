import { useState, useEffect, useCallback } from "react";
import api from "@/lib/api";
import { useAuth } from "@/App";
import { Search, Plus, Pencil, Trash2, RefreshCw, Wifi, WifiOff, Server, Eye, EyeOff, ChevronDown, ChevronUp, ChevronLeft, ChevronRight, FileDown, Printer } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { toast } from "sonner";

const PAGE_SIZE = 50;

function HotspotUserCard({ u, isViewer, userRole, onEdit, onDelete }) {
  const [showPwd, setShowPwd] = useState(false);
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="bg-card border border-border rounded-sm p-3 hover:border-primary/30 transition-all" data-testid={`hotspot-row-${u.name}`}>
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <div className={`w-2 h-2 rounded-full flex-shrink-0 ${u.is_online ? "bg-green-500 animate-pulse" : "bg-muted-foreground/30"}`} />
          <span className="font-mono text-sm font-semibold truncate">{u.name}</span>
        </div>
        <div className="flex items-center gap-1 flex-shrink-0">
          <Badge className={`rounded-sm text-[10px] border ${u.disabled === "true" ? "bg-red-500/10 text-red-500 border-red-500/20" : "bg-green-500/10 text-green-500 border-green-500/20"}`}>
            {u.disabled === "true" ? "off" : "on"}
          </Badge>
          <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => setExpanded(!expanded)}>
            {expanded ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
          </Button>
        </div>
      </div>

      {/* Password row - always visible */}
      <div className="mt-2 flex items-center gap-2">
        <span className="text-[10px] text-muted-foreground w-16 flex-shrink-0">Password</span>
        <span className="font-mono text-xs text-muted-foreground flex-1 truncate">
          {showPwd ? (u.password || "-") : (u.password ? "********" : "-")}
        </span>
        {u.password && (
          <Button variant="ghost" size="icon" className="h-6 w-6 flex-shrink-0" onClick={() => setShowPwd(!showPwd)}>
            {showPwd ? <EyeOff className="w-3 h-3" /> : <Eye className="w-3 h-3" />}
          </Button>
        )}
      </div>

      {/* Expanded details */}
      {expanded && (
        <div className="mt-2 pt-2 border-t border-border/50 space-y-1.5">
          <div className="flex items-center gap-2">
            <span className="text-[10px] text-muted-foreground w-16 flex-shrink-0">Profile</span>
            <Badge variant="outline" className="rounded-sm text-[10px]">{u.profile || "default"}</Badge>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-[10px] text-muted-foreground w-16 flex-shrink-0">Server</span>
            <span className="text-xs font-mono">{u.server || "all"}</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-[10px] text-muted-foreground w-16 flex-shrink-0">Online</span>
            {u.is_online
              ? <Badge className="rounded-sm text-[10px] border bg-green-500/10 text-green-500 border-green-500/20 gap-1"><Wifi className="w-3 h-3" />Online</Badge>
              : <span className="text-xs text-muted-foreground">Offline</span>}
          </div>
          {u.comment && (
            <div className="flex items-start gap-2">
              <span className="text-[10px] text-muted-foreground w-16 flex-shrink-0">Comment</span>
              <span className="text-xs text-muted-foreground">{u.comment}</span>
            </div>
          )}
        </div>
      )}

      {/* Actions */}
      {!isViewer && (
        <div className="mt-2 pt-2 border-t border-border/50 flex gap-1 justify-end">
          <Button variant="ghost" size="sm" className="h-7 px-2 text-[10px] gap-1 rounded-sm" onClick={() => onEdit(u)} data-testid={`hotspot-edit-${u.name}`}>
            <Pencil className="w-3 h-3" /> Edit
          </Button>
          {userRole === "administrator" && (
            <Button variant="ghost" size="sm" className="h-7 px-2 text-[10px] gap-1 rounded-sm text-destructive" onClick={() => onDelete(u[".id"], u.name)} data-testid={`hotspot-delete-${u.name}`}>
              <Trash2 className="w-3 h-3" /> Hapus
            </Button>
          )}
        </div>
      )}
    </div>
  );
}

function Pagination({ page, totalPages, onPage }) {
  if (totalPages <= 1) return null;
  return (
    <div className="flex items-center justify-center gap-2 py-2">
      <Button variant="outline" size="icon" className="h-7 w-7 rounded-sm" disabled={page === 0} onClick={() => onPage(page - 1)}>
        <ChevronLeft className="w-4 h-4" />
      </Button>
      <span className="text-xs text-muted-foreground">
        Halaman <span className="text-foreground font-mono">{page + 1}</span> / <span className="font-mono">{totalPages}</span>
      </span>
      <Button variant="outline" size="icon" className="h-7 w-7 rounded-sm" disabled={page >= totalPages - 1} onClick={() => onPage(page + 1)}>
        <ChevronRight className="w-4 h-4" />
      </Button>
    </div>
  );
}

export default function HotspotUsersPage() {
  const { user } = useAuth();
  const isViewer = user?.role === "viewer";
  const [devices, setDevices] = useState([]);
  const [selectedDevice, setSelectedDevice] = useState("");
  const [users, setUsers] = useState([]);
  const [vouchers, setVouchers] = useState([]);
  const [tabMode, setTabMode] = useState("users"); // "users" or "vouchers"
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [showFormPwd, setShowFormPwd] = useState(false);
  const [form, setForm] = useState({ name: "", password: "", profile: "default", server: "all", comment: "" });
  const [page, setPage] = useState(0);
  const [profiles, setProfiles] = useState([]);
  const [servers, setServers] = useState([]);
  const [profilesLoading, setProfilesLoading] = useState(false);

  useEffect(() => {
    api.get("/devices").then(r => {
      setDevices(r.data);
      if (r.data.length === 1) setSelectedDevice(r.data[0].id);
    }).catch(() => {});
  }, []);

  // Fetch Hotspot profiles + servers from MikroTik when device changes
  useEffect(() => {
    if (!selectedDevice) { setProfiles([]); setServers([]); return; }
    setProfilesLoading(true);
    Promise.all([
      api.get("/hotspot-profiles", { params: { device_id: selectedDevice } }).then(r => r.data).catch(() => []),
      api.get("/hotspot-servers", { params: { device_id: selectedDevice } }).then(r => r.data).catch(() => []),
    ]).then(([prof, srv]) => {
      setProfiles(prof || []);
      setServers(srv || []);
    }).finally(() => setProfilesLoading(false));
  }, [selectedDevice]);

  const fetchUsers = useCallback(async () => {
    if (!selectedDevice) return;
    setLoading(true);
    setError("");
    setPage(0);
    try {
      const params = { device_id: selectedDevice };
      if (search) params.search = search;
      
      const [rUsers, rVouchers] = await Promise.all([
         api.get("/hotspot-users", { params }),
         api.get("/hotspot-vouchers", { params })
      ]);
      setUsers(rUsers.data);
      setVouchers(rVouchers.data);
    } catch (e) {
      const msg = e.response?.data?.detail || "Failed to connect to MikroTik or DB";
      setError(msg);
      setUsers([]);
      setVouchers([]);
    }
    setLoading(false);
  }, [selectedDevice, search]);

  useEffect(() => { fetchUsers(); }, [fetchUsers]);
  useEffect(() => { setPage(0); }, [search]);

  const openAdd = () => {
    setEditing(null);
    setShowFormPwd(false);
    setForm({ name: "", password: "", profile: "default", server: "all", comment: "" });
    setDialogOpen(true);
  };

  const openEdit = (u) => {
    setEditing(u);
    setShowFormPwd(false);
    setForm({ name: u.name || "", password: "", profile: u.profile || "default", server: u.server || "all", comment: u.comment || "", disabled: u.disabled || "false" });
    setDialogOpen(true);
  };

  const handleSave = async () => {
    try {
      if (editing) {
        const data = { ...form };
        if (!data.password) delete data.password;
        await api.put(`/hotspot-users/${editing[".id"]}?device_id=${selectedDevice}`, data);
        toast.success("Hotspot user updated on MikroTik");
      } else {
        await api.post(`/hotspot-users?device_id=${selectedDevice}`, form);
        toast.success("Hotspot user created on MikroTik");
      }
      setDialogOpen(false);
      fetchUsers();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Operation failed");
    }
  };

  const handleDelete = async (mtId, name) => {
    if (!window.confirm(`Delete Hotspot user "${name}" from MikroTik?`)) return;
    try {
      await api.delete(`/hotspot-users/${mtId}?device_id=${selectedDevice}`);
      toast.success("Hotspot user deleted");
      fetchUsers();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Delete failed");
    }
  };

  const [showVoucherPdf, setShowVoucherPdf] = useState(false);
  const [pdfLoading, setPdfLoading] = useState(false);
  const [pdfOpts, setPdfOpts] = useState({ layout: "8x", template: "branded", device_id: "" });

  const downloadVoucherPdf = async () => {
    if (!selectedDevice) return toast.error("Pilih device terlebih dahulu");
    setPdfLoading(true);
    try {
      const token = localStorage.getItem("access_token") || sessionStorage.getItem("access_token") || "";
      const params = new URLSearchParams({
        device_id: selectedDevice,
        layout: pdfOpts.layout,
        template: pdfOpts.template,
      });
      const resp = await fetch(`/api/vouchers/pdf?${params}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({ detail: "Gagal generate PDF" }));
        throw new Error(err.detail || "Gagal generate PDF");
      }
      const blob = await resp.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `voucher-hotspot-${selectedDevice}.pdf`;
      a.click();
      URL.revokeObjectURL(url);
      toast.success("PDF Voucher berhasil diunduh!");
      setShowVoucherPdf(false);
    } catch (e) {
      toast.error(e.message || "Gagal generate PDF voucher");
    }
    setPdfLoading(false);
  };

  const currentDev = devices.find(d => d.id === selectedDevice);
  const activeData = tabMode === "users" ? users : vouchers;
  const onlineCount = users.filter(u => u.is_online).length;
  const totalPages = Math.ceil(activeData.length / PAGE_SIZE);
  const pagedData = activeData.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);

  const deleteVoucher = async (id, name) => {
    if (!window.confirm(`Hapus voucher ${name}?`)) return;
    try {
      await api.delete(`/hotspot-vouchers/${id}?device_id=${selectedDevice}`);
      toast.success("Voucher dihapus");
      fetchUsers();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Delete failed");
    }
  };

  return (
    <div className="space-y-3 pb-16" data-testid="hotspot-users-page">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <h1 className="text-xl sm:text-2xl md:text-3xl font-bold tracking-tight">Hotspot Users &amp; Vouchers</h1>
          <p className="text-xs sm:text-sm text-muted-foreground">Manage Hotspot users (MikroTik) &amp; Vouchers (NOC Sentinel RADIUS)</p>
        </div>
        <div className="flex gap-2 flex-wrap justify-end">
          {selectedDevice && tabMode === "vouchers" && (
            <Button onClick={() => setShowVoucherPdf(true)} size="sm" variant="outline" className="rounded-sm gap-2 border-purple-500/30 text-purple-400 hover:bg-purple-500/10">
              <Printer className="w-4 h-4" /> Cetak Voucher PDF
            </Button>
          )}
          {!isViewer && selectedDevice && tabMode === "users" && (
            <Button onClick={openAdd} size="sm" className="rounded-sm gap-2 w-full sm:w-auto" data-testid="add-hotspot-user-btn">
              <Plus className="w-4 h-4" /> Add User
            </Button>
          )}
        </div>
      </div>

      <div className="flex border-b border-border text-sm mb-4">
        <button className={`px-4 py-2 font-semibold -mb-[1px] ${tabMode === "users" ? "border-b-2 border-primary text-primary" : "text-muted-foreground"}`} onClick={() => {setTabMode("users"); setPage(0);}}>Local Users (MikroTik)</button>
        <button className={`px-4 py-2 font-semibold -mb-[1px] ${tabMode === "vouchers" ? "border-b-2 border-primary text-primary" : "text-muted-foreground"}`} onClick={() => {setTabMode("vouchers"); setPage(0);}}>Vouchers (RADIUS)</button>
      </div>

      {/* Controls */}
      <div className="flex flex-col gap-2">
        <div className="flex flex-col sm:flex-row gap-2">
          <div className="flex flex-col gap-1 sm:flex-none">
            <label className="text-[10px] text-muted-foreground uppercase tracking-widest">Select Device</label>
            <Select value={selectedDevice} onValueChange={v => { setSelectedDevice(v); setPage(0); }}>
              <SelectTrigger className="w-full sm:w-52 rounded-sm bg-card text-xs h-9" data-testid="hotspot-device-select">
                <SelectValue placeholder="Select device..." />
              </SelectTrigger>
              <SelectContent>
                {devices.map(d => (
                  <SelectItem key={d.id} value={d.id}>
                    <span className="flex items-center gap-2">
                      <div className={`w-1.5 h-1.5 rounded-full ${d.status === "online" ? "bg-green-500" : "bg-red-500"}`} />
                      {d.name}
                    </span>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="flex gap-2 flex-1 sm:self-end">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
              <Input placeholder="Cari username..." value={search} onChange={e => { setSearch(e.target.value); setPage(0); }}
                className="pl-9 rounded-sm bg-card h-9 text-xs" data-testid="hotspot-search-input" />
            </div>
            <Button variant="outline" size="icon" onClick={fetchUsers} className="rounded-sm h-9 w-9 flex-shrink-0" data-testid="hotspot-refresh-btn">
              <RefreshCw className="w-4 h-4" />
            </Button>
          </div>
        </div>
      </div>

      {/* Stats bar */}
      {selectedDevice && !error && activeData.length > 0 && user?.role === "administrator" && (
        <div className="flex items-center gap-3 text-xs text-muted-foreground px-1">
          <span>Total: <span className="text-foreground font-mono">{activeData.length}</span> {tabMode}</span>
          {tabMode === "users" && <span className="text-green-500">Online: <span className="font-mono">{onlineCount}</span></span>}
          {totalPages > 1 && (
            <span className="text-muted-foreground/60 ml-2">
              Tampil: <span className="font-mono">{page * PAGE_SIZE + 1}–{Math.min((page + 1) * PAGE_SIZE, activeData.length)}</span>
            </span>
          )}
          {currentDev && <span className="ml-auto font-mono text-[10px]">{currentDev.name}</span>}
        </div>
      )}

      {/* Content */}
      {!selectedDevice ? (
        <div className="bg-card border border-border rounded-sm p-8 sm:p-12 text-center">
          <Server className="w-10 h-10 sm:w-12 sm:h-12 mx-auto mb-3 text-muted-foreground/30" />
          <p className="text-sm text-muted-foreground">Select a MikroTik device to view Hotspot users & vouchers</p>
        </div>
      ) : error ? (
        <div className="bg-card border border-red-500/30 rounded-sm p-6 sm:p-8 text-center">
          <WifiOff className="w-8 h-8 sm:w-10 sm:h-10 mx-auto mb-3 text-red-500/50" />
          <p className="text-red-400 text-xs sm:text-sm">{error}</p>
        </div>
      ) : loading ? (
        <div className="bg-card border border-border rounded-sm p-8 text-center">
          <RefreshCw className="w-6 h-6 mx-auto mb-2 text-muted-foreground animate-spin" />
          <p className="text-sm text-muted-foreground">Connecting to databases...</p>
        </div>
      ) : activeData.length === 0 ? (
        <div className="bg-card border border-border rounded-sm p-8 text-center">
          <p className="text-sm text-muted-foreground">No data found</p>
        </div>
      ) : (
        <>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2 sm:gap-3">
            {tabMode === "users" && pagedData.map(u => (
              <HotspotUserCard
                key={u[".id"]}
                u={u}
                isViewer={isViewer}
                userRole={user?.role}
                onEdit={openEdit}
                onDelete={handleDelete}
              />
            ))}
            {tabMode === "vouchers" && pagedData.map(v => (
               <div key={v.id} className="bg-card border border-border rounded-sm p-3 hover:border-primary/30 transition-all flex flex-col">
                  <div className="flex justify-between items-center bg-muted/30 -m-3 mb-3 p-2 px-3 border-b border-border">
                     <span className="font-mono font-bold">{v.username}</span>
                     <Badge className={`rounded-sm text-[10px] ${v.status === 'active' ? 'bg-green-500/10 text-green-500' : 'bg-primary/10 text-primary'}`}>{v.status.toUpperCase()}</Badge>
                  </div>
                  <div className="flex-1 space-y-1 text-sm mt-1">
                     <div className="flex justify-between text-xs"><span className="text-muted-foreground">Password:</span> <span className="font-mono">{v.password}</span></div>
                     <div className="flex justify-between text-xs"><span className="text-muted-foreground">Profile:</span> <span>{v.profile || "default"}</span></div>
                     <div className="flex justify-between text-xs"><span className="text-muted-foreground">Sales Value:</span> <span className="font-mono text-green-500">Rp {parseInt(v.price||0).toLocaleString('id-ID')}</span></div>
                     <div className="flex justify-between text-xs"><span className="text-muted-foreground">Validity:</span> <span>{v.validity || "-"}</span></div>
                  </div>
                  {!isViewer && user?.role === "administrator" && (
                    <div className="mt-3 pt-2 border-t border-border flex justify-end">
                      <Button variant="ghost" size="sm" className="h-7 px-2 text-[10px] gap-1 rounded-sm text-destructive" onClick={() => deleteVoucher(v.id, v.username)}>
                        <Trash2 className="w-3 h-3" /> Hapus
                      </Button>
                    </div>
                  )}
               </div>
            ))}
          </div>
          <Pagination page={page} totalPages={totalPages} onPage={setPage} />
        </>
      )}

      {/* Dialog */}
      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent className="rounded-sm bg-card border-border max-w-md" data-testid="hotspot-user-dialog">
          <DialogHeader>
            <DialogTitle className="text-xl">{editing ? "Edit Hotspot User" : "Add Hotspot User"}</DialogTitle>
            <DialogDescription>{editing ? "Update Hotspot user on MikroTik." : "Create a new Hotspot user on MikroTik."}</DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label className="text-xs text-muted-foreground">Username</Label>
                <Input value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} className="rounded-sm bg-background" data-testid="hotspot-form-username" />
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs text-muted-foreground">Password</Label>
                <div className="relative">
                  <Input
                    type={showFormPwd ? "text" : "password"}
                    value={form.password}
                    onChange={e => setForm({ ...form, password: e.target.value })}
                    className="rounded-sm bg-background pr-9"
                    placeholder={editing ? "(unchanged)" : ""}
                    data-testid="hotspot-form-password"
                  />
                  <Button type="button" variant="ghost" size="icon" className="absolute right-1 top-1/2 -translate-y-1/2 h-7 w-7" onClick={() => setShowFormPwd(!showFormPwd)}>
                    {showFormPwd ? <EyeOff className="w-3.5 h-3.5" /> : <Eye className="w-3.5 h-3.5" />}
                  </Button>
                </div>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label className="text-xs text-muted-foreground">
                  Profile {profilesLoading && <span className="text-[10px] text-muted-foreground/60"> (loading...)</span>}
                </Label>
                {profiles.length > 0 ? (
                  <Select value={form.profile} onValueChange={v => setForm({ ...form, profile: v })}>
                    <SelectTrigger className="rounded-sm bg-background" data-testid="hotspot-form-profile">
                      <SelectValue placeholder="Pilih profile..." />
                    </SelectTrigger>
                    <SelectContent>
                      {profiles.map(p => (
                        <SelectItem key={p.name} value={p.name}>
                          <div className="flex flex-col items-start">
                            <span>{p.name}</span>
                            {p.rate_limit && <span className="text-[10px] text-muted-foreground">{p.rate_limit}</span>}
                          </div>
                        </SelectItem>
                      ))}
                      {!profiles.find(p => p.name === form.profile) && form.profile && (
                         <SelectItem value={form.profile}>
                            <div className="flex flex-col items-start">
                              <span>{form.profile}</span>
                            </div>
                         </SelectItem>
                      )}
                    </SelectContent>
                  </Select>
                ) : (
                  <Input
                    value={form.profile}
                    onChange={e => setForm({ ...form, profile: e.target.value })}
                    className="rounded-sm bg-background"
                    placeholder={profilesLoading ? "Loading..." : "default"}
                    data-testid="hotspot-form-profile"
                  />
                )}
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs text-muted-foreground">Server</Label>
                {servers.length > 0 ? (
                  <Select value={form.server} onValueChange={v => setForm({ ...form, server: v })}>
                    <SelectTrigger className="rounded-sm bg-background" data-testid="hotspot-form-server">
                      <SelectValue placeholder="Pilih server..." />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">all</SelectItem>
                      {servers.map(s => (
                        <SelectItem key={s.name} value={s.name}>
                          <div className="flex flex-col items-start">
                            <span>{s.name}</span>
                            {s.interface && <span className="text-[10px] text-muted-foreground">{s.interface}</span>}
                          </div>
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                ) : (
                  <Input
                    value={form.server}
                    onChange={e => setForm({ ...form, server: e.target.value })}
                    className="rounded-sm bg-background"
                    placeholder="all"
                    data-testid="hotspot-form-server"
                  />
                )}
              </div>
            </div>
            {editing && (
              <div className="space-y-1.5">
                <Label className="text-xs text-muted-foreground">Status</Label>
                <Select value={form.disabled} onValueChange={v => setForm({ ...form, disabled: v })}>
                  <SelectTrigger className="rounded-sm bg-background" data-testid="hotspot-form-status"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="false">Enabled</SelectItem>
                    <SelectItem value="true">Disabled</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            )}
            <div className="space-y-1.5">
              <Label className="text-xs text-muted-foreground">Comment</Label>
              <Input value={form.comment} onChange={e => setForm({ ...form, comment: e.target.value })} className="rounded-sm bg-background" data-testid="hotspot-form-comment" />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDialogOpen(false)} className="rounded-sm" data-testid="hotspot-form-cancel">Cancel</Button>
            <Button onClick={handleSave} className="rounded-sm" data-testid="hotspot-form-save">{editing ? "Update" : "Create"}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Voucher PDF Dialog */}
      <Dialog open={showVoucherPdf} onOpenChange={setShowVoucherPdf}>
        <DialogContent className="rounded-sm bg-card border-border max-w-sm">
          <DialogHeader>
            <DialogTitle>Cetak Voucher PDF</DialogTitle>
            <DialogDescription>
              Generate PDF voucher hotspot untuk dicetak. Semua voucher pada device ini akan disertakan.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-1.5">
              <Label className="text-xs text-muted-foreground">Layout Per Halaman</Label>
              <Select value={pdfOpts.layout} onValueChange={v => setPdfOpts({ ...pdfOpts, layout: v })}>
                <SelectTrigger className="rounded-sm bg-background text-xs h-8">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="4x">4 per halaman (besar)</SelectItem>
                  <SelectItem value="8x">8 per halaman (sedang)</SelectItem>
                  <SelectItem value="16x">16 per halaman (kecil)</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs text-muted-foreground">Template Desain</Label>
              <Select value={pdfOpts.template} onValueChange={v => setPdfOpts({ ...pdfOpts, template: v })}>
                <SelectTrigger className="rounded-sm bg-background text-xs h-8">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="branded">Branded (Logo + Warna)</SelectItem>
                  <SelectItem value="basic">Basic (Hitam Putih)</SelectItem>
                  <SelectItem value="minimal">Minimal (Clean)</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="p-2 bg-secondary/30 rounded-sm text-[10px] text-muted-foreground">
              Device: <span className="text-foreground font-mono">{currentDev?.name || selectedDevice}</span>
              {" | "}Total voucher: <span className="text-foreground font-mono">{vouchers.length}</span>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowVoucherPdf(false)} className="rounded-sm text-xs">Batal</Button>
            <Button onClick={downloadVoucherPdf} disabled={pdfLoading} className="rounded-sm text-xs gap-2">
              <FileDown className="w-3.5 h-3.5" />
              {pdfLoading ? "Generating PDF..." : "Download PDF"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

