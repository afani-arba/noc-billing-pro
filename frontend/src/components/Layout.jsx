import { useState, useEffect } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useAuth, useEdition } from "@/App";
import {
  LayoutDashboard, Users, Wifi, WifiOff, FileText, Server, Shield, LogOut, Menu, ChevronLeft, Settings, Bell, HardDrive, Terminal,
  GitBranch, Route, Cable, ShieldAlert, Cpu, Monitor, BarChart2, AlertTriangle, Download, Radar, Zap, PieChart, TrendingUp, MessageCircle, Activity, Radio, Search
} from "lucide-react";
import { useTheme } from "@/context/ThemeContext";

const RpIcon = ({ className = "w-5 h-5" }) => (
  <div className={`${className} flex items-center justify-center font-bold text-[9px] border-[1.5px] border-current rounded-[3px] leading-none select-none pt-[1px] px-[0.5px]`} style={{ fontFamily: 'Inter, sans-serif' }}>
    Rp
  </div>
);

import { Button } from "@/components/ui/button";
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger, DropdownMenuSeparator
} from "@/components/ui/dropdown-menu";

// serviceKey maps each nav route to the service name used in allowed_services
const navItems = [
  // ── GENERAL & MONITORING ──
  { separator: true, label: "Overview" },
  { to: "/",               icon: LayoutDashboard, label: "Dashboard",              end: true,  serviceKey: "dashboard" },
  { to: "/wall-display",   icon: Monitor,         label: "Wall Display",           serviceKey: "wallboard" },

  // ── CUSTOMER & SERVICES ──
  { separator: true, label: "Customer Services" },
  { to: "/genieacs",       icon: Cpu,             label: "GenieACS / TR-069",      serviceKey: "genieacs",       nocOnly: true },

  // ── HELPDESK & BILLING ──
  { separator: true, label: "Support & CRM" },
  { to: "/wa-customer-service", icon: MessageCircle, label: "CS Command Center",    serviceKey: "wa_customer_service", adminOnly: false },
  { to: "/reports",        icon: FileText,        label: "Data Reports",           serviceKey: "reports" },

  { separator: true, label: "Keuangan & Penagihan", billingOnly: true, enterpriseOnly: true },
  { to: "/billing",        icon: RpIcon,          label: "Billing PPPoE",          serviceKey: "billing",        billingOnly: true, enterpriseOnly: true },
  { to: "/hotspot-billing",icon: RpIcon,          label: "Billing Hotspot",        serviceKey: "hotspot_billing", billingOnly: true, enterpriseOnly: true },
  { to: "/finance-report", icon: TrendingUp,      label: "Laporan Keuangan",       serviceKey: "finance_report", billingOnly: true, enterpriseOnly: true },

  // ── NOC & INFRASTRUCTURE ──
  { separator: true, label: "NOC Infrastructure", nocOnly: false },
  { to: "/devices",        icon: Server,          label: "Devices Hub",            serviceKey: "devices",        nocOnly: true },
  { to: "/network-map",    icon: GitBranch,       label: "Network Map FTTH",       serviceKey: "network_map" },
  { to: "/ping",           icon: Activity,        label: "Network Ping Tool",      serviceKey: "ping",           billingProHide: true },
  { to: "/sla",            icon: BarChart2,       label: "SLA Monitor",            serviceKey: "sla",            billingProHide: true },
  { to: "/incidents",      icon: AlertTriangle,   label: "Incidents",              serviceKey: "incidents",      billingProHide: true },

  // ── ADVANCED ROUTING ──
  { separator: true, label: "Routing & Peering", nocOnly: true },
  { to: "/routing",        icon: Route,           label: "OSPF / Routes",          serviceKey: "routing",        nocOnly: true, billingProHide: true },
  { to: "/peering-eye",    icon: Radar,           label: "Sentinel Peering-Eye",   serviceKey: "peering_eye" },
  { to: "/bgp-steering",   icon: GitBranch,       label: "App Traffic & Steering", serviceKey: "bgp_steering" },
  { to: "/zapret",         icon: Shield,          label: "Zapret DPI Bypass",      serviceKey: "zapret" },
  { to: "/network-tuning", icon: Activity,        label: "Network Tuning",         serviceKey: "network_tuning" },
  { to: "/sdwan",          icon: Zap,             label: "Load Balance",           serviceKey: "sdwan",          nocOnly: true, billingProHide: true },

  // ── SYSTEM ADMINISTRATION ──
  { separator: true, label: "Administration", adminOnly: true },
  { to: "/backups",        icon: HardDrive,       label: "Backup Config",          serviceKey: "backups",        nocOnly: true },
  { to: "/notifications",  icon: Bell,            label: "Notifikasi Sistem",      serviceKey: "notifications",  adminOnly: true },
  { to: "/radius-server",  icon: Radio,           label: "RADIUS Server",          serviceKey: "radius_server",  adminOnly: true },
  { to: "/integration-settings", icon: Cable,     label: "Integrasi & Otomasi",    serviceKey: "integration_settings", adminOnly: true },
  { to: "/settings",       icon: Settings,        label: "Pengaturan Platform",    serviceKey: "settings",       adminOnly: true },
  { to: "/admin",          icon: Shield,          label: "User Management",        serviceKey: "settings",       superAdminOnly: true },
  { to: "/update",         icon: Download,        label: "Update Aplikasi",        serviceKey: "update",         adminOnly: true },
  { to: "/admin/license",  icon: ShieldAlert,     label: "Lisensi Sistem",         serviceKey: "license",        adminOnly: true },
];

// ─── SidebarContent ───────────────────────────────────────────────────────────
function SidebarContent({ collapsed, filteredNav, user, onNavClick, edition, isCyber }) {
  return (
    <div className="flex flex-col h-full">
      {/* Logo */}
      <NavLink
        to="/"
        onClick={onNavClick}
        className={`flex items-center gap-3 px-4 h-14 border-b flex-shrink-0 transition-colors ${
          isCyber
            ? "border-[var(--glass-border)] hover:bg-[var(--glass-bg-hover)]"
            : "border-border hover:bg-secondary/50"
        }`}
      >
        {/* Logo Icon */}
        <div className={`w-7 h-7 rounded flex items-center justify-center flex-shrink-0 transition-all ${
          isCyber
            ? "bg-[var(--glass-bg)] border border-[var(--glass-border)] shadow-[0_0_12px_var(--glass-glow)]"
            : "bg-primary"
        }`}>
          {isCyber ? (
            <Server className="w-4 h-4" style={{ color: "hsl(162,100%,50%)" }} />
          ) : (
            <Server className="w-4 h-4 text-primary-foreground" />
          )}
        </div>
        {!collapsed && (
          <div className="overflow-hidden">
            <h1 className={`text-sm font-bold tracking-tight ${isCyber ? "gradient-text" : "text-foreground"}`}>
              ARBA
            </h1>
            <p className={`text-[10px] uppercase tracking-widest ${
              isCyber ? "font-mono" : ""
            } text-muted-foreground`}>
              {isCyber ? "NOC // Billing" : "Billing Pro"}
            </p>
          </div>
        )}
      </NavLink>

      {/* Nav — scrollable */}
      <nav className="flex-1 min-h-0 px-2 py-4 space-y-0.5 overflow-y-auto custom-scrollbar">
        {filteredNav.map((item, idx) => {
          if (item.separator) {
            return (
              <div key={`sep-${idx}`} className={`px-3 pt-4 pb-1.5 ${collapsed ? "py-2" : ""}`}>
                {!collapsed && (
                  <p className={`text-[9px] uppercase tracking-widest font-semibold ${
                    isCyber
                      ? "text-[hsl(162,100%,35%)] font-mono"
                      : "text-muted-foreground/50"
                  }`}>
                    {isCyber ? `> ${item.label}` : item.label}
                  </p>
                )}
                {collapsed && <div className={`border-t my-1 ${isCyber ? "border-[var(--glass-border)]" : "border-border/30"}`} />}
              </div>
            );
          }
          return (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              onClick={onNavClick}
              className={({ isActive }) => {
                if (isCyber) {
                  return `flex items-center gap-3 px-3 py-2 rounded text-sm transition-all duration-200 group ${
                    isActive
                      ? "glass-card nav-active"
                      : "text-muted-foreground hover:text-[hsl(162,100%,50%)] hover:bg-[var(--glass-bg)]"
                  }`;
                }
                return `flex items-center gap-3 px-3 py-2.5 rounded-sm text-sm transition-all duration-200 group ${
                  isActive
                    ? "bg-primary/10 text-primary border-l-2 border-primary"
                    : "text-muted-foreground hover:text-foreground hover:bg-secondary/50"
                }`;
              }}
            >
              <item.icon className={`w-4 h-4 flex-shrink-0 transition-all ${
                isCyber ? "group-hover:drop-shadow-[0_0_4px_rgba(0,230,118,0.8)]" : ""
              }`} />
              {!collapsed && <span className={isCyber ? "font-mono text-xs tracking-wide" : ""}>{item.label}</span>}
            </NavLink>
          );
        })}
      </nav>

      {/* Edition Badge + User info */}
      <div className={`p-3 flex-shrink-0 ${
        isCyber ? "border-t border-[var(--glass-border)]" : "border-t border-border/50"
      }`}>
        {/* Edition Badge */}
        {!collapsed && (
          <div className={`mb-2 px-2 py-1 rounded text-[9px] font-bold uppercase tracking-widest text-center ${
            isCyber
              ? "glass-card border-[var(--glass-border)] text-[hsl(162,100%,50%)] font-mono"
              : edition === "billing_pro"
                ? "bg-primary/10 text-primary border border-primary/20"
                : edition === "enterprise"
                ? "bg-cyan-500/10 text-cyan-400 border border-cyan-500/20"
                : "bg-blue-500/10 text-blue-400 border border-blue-500/20"
          }`}>
            {isCyber
              ? `[[ ${edition === "billing_pro" ? "BILLING PRO" : edition === "enterprise" ? "ENTERPRISE" : "PRO"} ]]`
              : edition === "billing_pro" ? "💼 Billing Pro" : edition === "enterprise" ? "⚡ Enterprise" : "🔵 Pro"
            }
          </div>
        )}
        {/* Role badge */}
        {!collapsed && user?.role && !(["administrator", "super_admin"]).includes(user.role) && (
          <div className={`mb-2 px-2 py-1 rounded text-[9px] font-semibold text-center border ${
            isCyber
              ? "glass-card border-[var(--glass-border)] text-[hsl(185,100%,50%)] font-mono"
              : user.role === "noc_engineer"  ? "bg-orange-500/10 text-orange-400 border-orange-500/20"
              : user.role === "billing_staff" ? "bg-green-500/10 text-green-400 border-green-500/20"
              : "bg-blue-500/10 text-blue-400 border-blue-500/20"
          }`}>
            {isCyber
              ? `> ${user.role.toUpperCase().replace("_", " ")}`
              : user.role === "noc_engineer" ? "🟠 NOC Engineer"
              : user.role === "billing_staff" ? "🟢 Billing Staff"
              : "🔵 Helpdesk"
            }
          </div>
        )}
        {/* User avatar + name */}
        {!collapsed ? (
          <div className="flex items-center gap-3">
            <div className={`w-8 h-8 rounded flex items-center justify-center text-xs font-bold flex-shrink-0 ${
              isCyber
                ? "glass-card border border-[var(--glass-border)] text-[hsl(162,100%,50%)] font-mono shadow-[0_0_8px_var(--glass-glow)]"
                : "rounded-sm bg-secondary text-foreground"
            }`}>
              {user?.full_name?.charAt(0)?.toUpperCase() || "A"}
            </div>
            <div className="flex-1 min-w-0">
              <p className={`text-xs font-medium truncate ${isCyber ? "text-[hsl(162,100%,75%)]" : "text-foreground"}`}>
                {user?.full_name}
              </p>
              <p className={`text-[10px] capitalize ${isCyber ? "text-[hsl(185,100%,40%)] font-mono" : "text-muted-foreground"}`}>
                {user?.role}
              </p>
            </div>
          </div>
        ) : (
          <div className={`w-8 h-8 rounded flex items-center justify-center text-xs font-bold mx-auto ${
            isCyber
              ? "glass-card text-[hsl(162,100%,50%)] font-mono"
              : "rounded-sm bg-secondary text-foreground"
          }`}>
            {user?.full_name?.charAt(0)?.toUpperCase() || "A"}
          </div>
        )}
      </div>
    </div>
  );
}

// ─── Layout ───────────────────────────────────────────────────────────────────
export default function Layout() {
  const { user, logout } = useAuth();
  const { edition, edition_name, features } = useEdition();
  const { theme } = useTheme();
  const navigate = useNavigate();
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [now, setNow] = useState(new Date());

  const isCyber = theme === "cyber";

  useEffect(() => {
    const timer = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(timer);
  }, []);

  const timeStr = now.toLocaleTimeString("id-ID", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  const dateStr = now.toLocaleDateString("id-ID", { weekday: "short", day: "2-digit", month: "short", year: "numeric" });

  const handleLogout = () => {
    logout();
    navigate("/login");
  };

  const ADMIN_ROLES   = ["super_admin", "administrator"];
  const SUPER_ADMIN_ROLES = ["super_admin", "administrator"];
  const FULL_ADMIN_ROLES  = ["super_admin", "administrator", "admin"];
  const NOC_ROLES   = ["super_admin", "administrator", "admin", "branch_admin", "noc_engineer"];
  const BILLING_ROLES = ["super_admin", "administrator", "admin", "branch_admin", "billing_staff"];

  const isAdmin         = FULL_ADMIN_ROLES.includes(user?.role);
  const isSuperAdmin    = SUPER_ADMIN_ROLES.includes(user?.role);
  const isNOC           = NOC_ROLES.includes(user?.role);
  const isBillingRole   = BILLING_ROLES.includes(user?.role);
  const isBillingEnabled = features?.billing === true;

  const userServices = user?.allowed_services || [];

  const canSeeService = (serviceKey) => {
    if (!serviceKey) return true;
    if (isAdmin) return true;
    if (serviceKey === "dashboard") return true;
    if (user && Array.isArray(user.allowed_services)) {
      return user.allowed_services.includes(serviceKey);
    }
    return null;
  };

  const filteredNav = navItems.filter((item) => {
    if (item.billingProHide && edition === "billing_pro") return false;
    if (item.enterpriseOnly && !isBillingEnabled) return false;
    if (item.superAdminOnly && !isSuperAdmin) return false;
    const customAccess = item.serviceKey ? canSeeService(item.serviceKey) : true;
    if (customAccess === true) return true;
    if (customAccess === false) return false;
    if (item.adminOnly && !isAdmin) return false;
    if (item.nocOnly && !isNOC) return false;
    if (item.billingOnly && !isBillingRole) return false;
    return true;
  });

  const closeMobile = () => setMobileOpen(false);

  // Sidebar style
  const sidebarClass = isCyber
    ? "glass-panel border-r border-[var(--glass-border)]"
    : "bg-card border-r border-border";

  // Header style
  const headerClass = isCyber
    ? "glass-panel border-b border-[var(--glass-border)] sticky top-0 z-30"
    : "h-14 bg-card border-b border-border sticky top-0 z-30";

  return (
    <div className="flex h-screen overflow-hidden bg-background" data-testid="app-layout">
      {/* Mobile overlay */}
      {mobileOpen && (
        <div
          className={`fixed inset-0 z-40 lg:hidden ${isCyber ? "bg-black/80 backdrop-blur-sm" : "bg-black/60"}`}
          onClick={closeMobile}
        />
      )}

      {/* Sidebar — Mobile */}
      <aside
        className={`fixed inset-y-0 left-0 z-50 w-60 transform transition-transform duration-300 lg:hidden ${sidebarClass} ${
          mobileOpen ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        <SidebarContent
          collapsed={false}
          filteredNav={filteredNav}
          user={user}
          edition={edition}
          onNavClick={closeMobile}
          isCyber={isCyber}
        />
      </aside>

      {/* Sidebar — Desktop */}
      <aside
        className={`hidden lg:flex flex-col transition-all duration-300 ${sidebarClass} ${
          collapsed ? "w-14" : "w-60"
        }`}
      >
        <SidebarContent
          collapsed={collapsed}
          filteredNav={filteredNav}
          user={user}
          edition={edition}
          onNavClick={() => {}}
          isCyber={isCyber}
        />
      </aside>

      {/* Main */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* Header */}
        <header className={`flex items-center justify-between px-4 lg:px-6 h-14 ${headerClass}`}>
          <div className="flex items-center gap-3">
            <Button
              variant="ghost"
              size="icon"
              className="lg:hidden"
              onClick={() => setMobileOpen(true)}
              data-testid="mobile-menu-btn"
            >
              <Menu className="w-5 h-5" />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              className="hidden lg:flex"
              onClick={() => setCollapsed(!collapsed)}
              data-testid="collapse-sidebar-btn"
            >
              <ChevronLeft className={`w-4 h-4 transition-transform ${collapsed ? "rotate-180" : ""}`} />
            </Button>
          </div>

          <div className="flex items-center gap-3">
            {/* Live Clock */}
            <div className="flex flex-col items-end">
              <span className={`text-sm font-semibold tabular-nums ${
                isCyber ? "font-mono text-[hsl(162,100%,60%)] drop-shadow-[0_0_6px_rgba(0,230,118,0.5)]" : "font-mono text-foreground"
              }`}>
                {timeStr}
              </span>
              <span className={`text-[10px] ${isCyber ? "font-mono text-[hsl(185,100%,40%)]" : "text-muted-foreground"}`}>
                {dateStr}
              </span>
            </div>

            {/* System Status */}
            <div className={`hidden sm:flex items-center gap-2 px-2.5 py-1 rounded text-xs ${
              isCyber
                ? "glass-card border border-[var(--glass-border)]"
                : "border border-border bg-secondary"
            }`}>
              <div className={`w-1.5 h-1.5 rounded-full ${isCyber ? "glow-dot-green" : "bg-emerald-500"}`} />
              <span className={`font-mono text-[11px] ${
                isCyber ? "text-[hsl(162,100%,50%)]" : "text-muted-foreground"
              }`}>
                {isCyber ? "SYS::ONLINE" : "System Online"}
              </span>
            </div>

            {/* User Menu */}
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="ghost" size="sm" className="gap-2" data-testid="user-menu-btn">
                  <div className={`w-6 h-6 rounded flex items-center justify-center text-xs font-bold ${
                    isCyber
                      ? "glass-card border border-[var(--glass-border)] text-[hsl(162,100%,50%)] font-mono shadow-[0_0_6px_var(--glass-glow)]"
                      : "rounded-sm bg-primary/20 text-primary"
                  }`}>
                    {user?.full_name?.charAt(0)?.toUpperCase() || "A"}
                  </div>
                  <span className="hidden sm:inline text-sm">{user?.full_name}</span>
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className={`w-48 ${isCyber ? "glass-modal border-[var(--glass-border)]" : ""}`}>
                <div className="px-2 py-1.5">
                  <p className={`text-sm font-medium ${isCyber ? "text-[hsl(162,100%,70%)] font-mono" : ""}`}>
                    {user?.full_name}
                  </p>
                  <p className={`text-xs capitalize ${isCyber ? "text-[hsl(185,100%,40%)] font-mono" : "text-muted-foreground"}`}>
                    {user?.role}
                  </p>
                </div>
                <DropdownMenuSeparator />
                <DropdownMenuItem onClick={handleLogout} data-testid="logout-btn" className="text-destructive">
                  <LogOut className="w-4 h-4 mr-2" />
                  Logout
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </header>

        {/* Content */}
        <main className="flex-1 overflow-y-auto p-4 lg:p-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
