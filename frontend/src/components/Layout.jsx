import { useState, useEffect } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useAuth, useEdition } from "@/App";
import {
  LayoutDashboard, Users, Wifi, WifiOff, FileText, Server, Shield, LogOut, Menu, ChevronLeft, Settings, Bell, HardDrive, Terminal,
  GitBranch, Route, Cable, ShieldAlert, Cpu, Monitor, BarChart2, AlertTriangle, ClipboardList, Download, CalendarClock, Radar, Zap, PieChart, TrendingUp, MessageCircle, Activity, Radio, Search
} from "lucide-react";

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
  { to: "/pppoe",          icon: Users,           label: "PPPoE Users",            serviceKey: "pppoe" },
  { to: "/hotspot",        icon: Wifi,            label: "Hotspot Users",          serviceKey: "hotspot" },
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
  { separator: true, label: "NOC Infrastructure", nocOnly: false /* some are visible to helpdesk */ },
  { to: "/devices",        icon: Server,          label: "Devices Hub",            serviceKey: "devices",        nocOnly: true },
  { to: "/topology",       icon: GitBranch,       label: "Network Map",            serviceKey: "topology" },

  { to: "/ping",           icon: Activity,        label: "Network Ping Tool",      serviceKey: "ping" },
  { to: "/sla",            icon: BarChart2,       label: "SLA Monitor",            serviceKey: "sla" },

  { to: "/incidents",      icon: AlertTriangle,   label: "Incidents",              serviceKey: "incidents" },

  // ── ADVANCED ROUTING ──
  { separator: true, label: "Routing & Peering", nocOnly: true },
  { to: "/routing",        icon: Route,           label: "OSPF / Routes",          serviceKey: "routing",        nocOnly: true },
  { to: "/peering-eye",    icon: Radar,           label: "Sentinel Peering-Eye",   serviceKey: "peering_eye" },

  { to: "/sdwan",          icon: Zap,             label: "Load Balance",           serviceKey: "sdwan",          nocOnly: true },

  // ── SYSTEM ADMINISTRATION ──
  { separator: true, label: "Administration", adminOnly: true },
  { to: "/scheduler",      icon: CalendarClock,   label: "Task Scheduler",         serviceKey: "scheduler",      nocOnly: true },
  { to: "/backups",        icon: HardDrive,       label: "Backup Config",          serviceKey: "backups",        nocOnly: true },
  { to: "/syslog",         icon: Terminal,        label: "Syslog",                 serviceKey: "syslog",         nocOnly: true },
  { to: "/audit",          icon: ClipboardList,   label: "Audit Log",              serviceKey: "audit",          nocOnly: true },
  { to: "/notifications",  icon: Bell,            label: "Notifikasi Sistem",      serviceKey: "notifications",  adminOnly: true },
  { to: "/radius-server",  icon: Radio,           label: "RADIUS Server",          serviceKey: "radius_server",  adminOnly: true },
  { to: "/integration-settings", icon: Cable,     label: "Integrasi & Otomasi",    serviceKey: "integration_settings", adminOnly: true },
  { to: "/settings",       icon: Settings,        label: "Pengaturan Platform",    serviceKey: "settings",       adminOnly: true },
  { to: "/admin",          icon: Shield,          label: "User Management",        serviceKey: "settings",       adminOnly: true },
  { to: "/update",         icon: Download,        label: "Update Aplikasi",        serviceKey: "update",         adminOnly: true },
  { to: "/admin/license",  icon: ShieldAlert,     label: "Lisensi Sistem",         serviceKey: "license",        adminOnly: true },
];

// â”€â”€â”€ SidebarContent sebagai komponen TERPISAH di luar Layout â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
// PENTING: jangan definisikan komponen di dalam komponen lain —
// setiap render akan dianggap komponen baru → remount → scroll reset
function SidebarContent({ collapsed, filteredNav, user, onNavClick, edition }) {
  return (
    <div className="flex flex-col h-full">
      {/* Logo */}
      <NavLink to="/" onClick={onNavClick} className="flex items-center gap-3 px-4 h-14 border-b border-border flex-shrink-0 hover:bg-secondary/50 transition-colors">
        <div className="w-7 h-7 rounded bg-primary flex items-center justify-center flex-shrink-0">
          <Server className="w-4 h-4 text-primary-foreground" />
        </div>
        {!collapsed && (
          <div className="overflow-hidden">
            <h1 className="text-sm font-bold tracking-tight text-foreground">ARBA</h1>
            <p className="text-[10px] text-muted-foreground uppercase tracking-widest">Monitoring System</p>
          </div>
        )}
      </NavLink>

      {/* Nav — scrollable */}
      <nav className="flex-1 min-h-0 px-2 py-4 space-y-1 overflow-y-auto">
        {filteredNav.map((item, idx) => {
          if (item.separator) {
            return (
              <div key={`sep-${idx}`} className="px-3 pt-3 pb-1">
                {!collapsed && (
                  <p className="text-[9px] text-muted-foreground/50 uppercase tracking-widest font-semibold">{item.label}</p>
                )}
                {collapsed && <div className="border-t border-border/30 my-1" />}
              </div>
            );
          }
          return (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              onClick={onNavClick}
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-2.5 rounded-sm text-sm transition-all duration-200 group ${
                  isActive
                    ? "bg-primary/10 text-primary border-l-2 border-primary"
                    : "text-muted-foreground hover:text-foreground hover:bg-secondary/50"
                }`
              }
            >
              <item.icon className="w-4 h-4 flex-shrink-0" />
              {!collapsed && <span>{item.label}</span>}
            </NavLink>
          );
        })}
      </nav>

      {/* Edition Badge + User info */}
      <div className="p-3 border-t border-border/50 flex-shrink-0">
        {/* Edition Badge */}
        {!collapsed && (
          <div className={`mb-2 px-2 py-1 rounded text-[9px] font-bold uppercase tracking-widest text-center ${
            edition === "enterprise"
              ? "bg-cyan-500/10 text-cyan-400 border border-cyan-500/20"
              : "bg-primary/10 text-primary border border-primary/20"
          }`}>
            {edition === "enterprise" ? "⚡ Enterprise" : "🔵 Pro"}
          </div>
        )}
        {/* Role badge */}
        {!collapsed && user?.role && !(["administrator", "super_admin"]).includes(user.role) && (
          <div className={`mb-2 px-2 py-1 rounded text-[9px] font-semibold text-center border ${
            user.role === "noc_engineer"  ? "bg-orange-500/10 text-orange-400 border-orange-500/20" :
            user.role === "billing_staff" ? "bg-green-500/10 text-green-400 border-green-500/20" :
            "bg-blue-500/10 text-blue-400 border-blue-500/20"
          }`}>
            {user.role === "noc_engineer" ? "🟠 NOC Engineer" :
             user.role === "billing_staff" ? "🟢 Billing Staff" :
             "🔵 Helpdesk"}
          </div>
        )}
        {!collapsed ? (
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-sm bg-secondary flex items-center justify-center text-xs font-semibold text-foreground">
              {user?.full_name?.charAt(0)?.toUpperCase() || "A"}
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-xs font-medium text-foreground truncate">{user?.full_name}</p>
              <p className="text-[10px] text-muted-foreground capitalize">{user?.role}</p>
            </div>
          </div>
        ) : (
          <div className="w-8 h-8 rounded-sm bg-secondary flex items-center justify-center text-xs font-semibold text-foreground mx-auto">
            {user?.full_name?.charAt(0)?.toUpperCase() || "A"}
          </div>
        )}
      </div>
    </div>
  );
}

// â”€â”€â”€ Layout â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
export default function Layout() {
  const { user, logout } = useAuth();
  const { edition, edition_name, features } = useEdition();
  const navigate = useNavigate();
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [now, setNow] = useState(new Date());

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

  const ADMIN_ROLES = ["super_admin", "administrator"];
  const NOC_ROLES   = ["super_admin", "administrator", "noc_engineer"];
  const BILLING_ROLES = ["super_admin", "administrator", "billing_staff"];

  const isAdmin         = ADMIN_ROLES.includes(user?.role);
  const isNOC           = NOC_ROLES.includes(user?.role);
  const isBillingRole   = BILLING_ROLES.includes(user?.role);
  const isBillingEnabled = features?.billing === true;

  // Get user's allowed services (null/undefined = use role defaults)
  const userServices = user?.allowed_services || [];

  const canSeeService = (serviceKey) => {
    if (!serviceKey) return true;  // separators/generic items
    if (isAdmin) return true;      // admin sees everything
    if (serviceKey === "dashboard") return true; // dashboard is always available
    // If user has explicit allowed_services list, check it
    if (user && Array.isArray(user.allowed_services)) {
      return user.allowed_services.includes(serviceKey);
    }
    return null; // indicates we should use legacy role fallback
  };

  const filteredNav = navItems.filter((item) => {
    // enterpriseOnly: hide if billing feature not available
    if (item.enterpriseOnly && !isBillingEnabled) return false;
    
    // Check explicit RBAC
    const customAccess = item.serviceKey ? canSeeService(item.serviceKey) : true;
    if (customAccess === true) return true;
    if (customAccess === false) return false;

    // customAccess === null means no explicit allowed_services defined (legacy user),
    // so we fallback to the old role checks
    if (item.adminOnly && !isAdmin) return false;
    if (item.nocOnly && !isNOC) return false;
    if (item.billingOnly && !isBillingRole) return false;

    return true;
  });
  const closeMobile = () => setMobileOpen(false);

  return (
    <div className="flex h-screen overflow-hidden bg-background" data-testid="app-layout">
      {/* Mobile overlay */}
      {mobileOpen && (
        <div className="fixed inset-0 bg-black/60 z-40 lg:hidden" onClick={closeMobile} />
      )}

      {/* Sidebar — Mobile */}
      <aside
        className={`fixed inset-y-0 left-0 z-50 w-60 bg-card border-r border-border transform transition-transform duration-300 lg:hidden ${
          mobileOpen ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        <SidebarContent
          collapsed={false}
          filteredNav={filteredNav}
          user={user}
          edition={edition}
          onNavClick={closeMobile}
        />
      </aside>

      {/* Sidebar — Desktop */}
      <aside
        className={`hidden lg:flex flex-col border-r border-border bg-card transition-all duration-300 ${
          collapsed ? "w-14" : "w-60"
        }`}
      >
        <SidebarContent
          collapsed={collapsed}
          filteredNav={filteredNav}
          user={user}
          edition={edition}
          onNavClick={() => {}}
        />
      </aside>

      {/* Main */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* Header */}
        <header className="h-14 flex items-center justify-between px-4 lg:px-6 border-b border-border bg-card sticky top-0 z-30">
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
              <span className="text-sm font-mono font-semibold text-foreground tabular-nums">{timeStr}</span>
              <span className="text-[10px] text-muted-foreground">{dateStr}</span>
            </div>

            <div className="hidden sm:flex items-center gap-2 px-2.5 py-1 rounded border border-border bg-secondary text-xs">
              <div className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
              <span className="text-muted-foreground font-mono text-[11px]">System Online</span>
            </div>

            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="ghost" size="sm" className="gap-2" data-testid="user-menu-btn">
                  <div className="w-6 h-6 rounded-sm bg-primary/20 flex items-center justify-center text-xs font-semibold text-primary">
                    {user?.full_name?.charAt(0)?.toUpperCase() || "A"}
                  </div>
                  <span className="hidden sm:inline text-sm">{user?.full_name}</span>
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-48">
                <div className="px-2 py-1.5">
                  <p className="text-sm font-medium">{user?.full_name}</p>
                  <p className="text-xs text-muted-foreground capitalize">{user?.role}</p>
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

