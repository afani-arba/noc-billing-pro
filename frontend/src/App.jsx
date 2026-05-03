/**
 * App.jsx — NOC-Billing-Pro Frontend Root
 *
 * Provides:
 *   AuthContext  → useAuth()    — token, user, login(), logout()
 *   EditionContext → useEdition() — edition, edition_name, features, billing_enabled
 *
 * Both hooks are exported so any child can import them directly from "@/App".
 */
import React, {
  createContext,
  useContext,
  useState,
  useEffect,
  lazy,
  Suspense,
} from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { Toaster } from "sonner";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import ErrorBoundary from "@/components/ErrorBoundary";
import Layout from "@/components/Layout";
import api from "@/lib/api";
import { ThemeProvider } from "@/context/ThemeContext";

// ─── React Query Client (singleton) ───────────────────────────────────────────
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      staleTime: 30000,
      refetchOnWindowFocus: false,
    },
  },
});

// ─── Lazy-loaded pages ────────────────────────────────────────────────────────
const LoginPage               = lazy(() => import("@/pages/LoginPage"));
const DashboardPage           = lazy(() => import("@/pages/DashboardPage"));
const DevicesPage             = lazy(() => import("@/pages/DevicesPage"));
const BillingPage             = lazy(() => import("@/pages/BillingPage"));
const HotspotBillingPage      = lazy(() => import("@/pages/HotspotBillingPage"));
const FinanceReportPage       = lazy(() => import("@/pages/FinanceReportPage"));
const GenieACSPage            = lazy(() => import("@/pages/GenieACSPage"));
const PeeringEyePage          = lazy(() => import("@/pages/PeeringEyePage"));
const ReportsPage             = lazy(() => import("@/pages/ReportsPage"));
const WACustomerServicePage   = lazy(() => import("@/pages/WACustomerServicePage"));
const SettingsPage            = lazy(() => import("@/pages/SettingsPage"));
const AdminPage               = lazy(() => import("@/pages/AdminPage"));
const BgpSteeringPage         = lazy(() => import("@/pages/BgpSteeringPage"));
const ZapretPage              = lazy(() => import("@/pages/ZapretPage"));
const NetworkTuningPage       = lazy(() => import("@/pages/NetworkTuningPage"));
const NetworkMapPage          = lazy(() => import("@/pages/NetworkMapPage"));
const NotificationsPage       = lazy(() => import("@/pages/NotificationsPage"));
const BackupsPage             = lazy(() => import("@/pages/BackupsPage"));
const UpdatePage              = lazy(() => import("@/pages/UpdatePage"));
const LicensePage             = lazy(() => import("@/pages/LicensePage"));
const WallDisplayPage         = lazy(() => import("@/pages/WallDisplayPage"));
const RadiusSettingsPage      = lazy(() => import("@/pages/RadiusSettingsPage"));
const IntegrationSettingsPage = lazy(() => import("@/pages/IntegrationSettingsPage"));
const ClientLogin             = lazy(() => import("@/pages/ClientPortal/ClientLogin"));
const ClientDashboard         = lazy(() => import("@/pages/ClientPortal/ClientDashboard"));
const ServerSetup             = lazy(() => import("@/pages/ClientPortal/ServerSetup"));
const TechnicianPortal        = lazy(() => import("@/pages/TechnicianPortal"));
const CollectorPortal         = lazy(() => import("@/pages/CollectorPortal"));

// ─── Auth Context ─────────────────────────────────────────────────────────────
const AuthContext = createContext(null);
export const useAuth = () => useContext(AuthContext);

// ─── Edition Context ──────────────────────────────────────────────────────────
const EditionContext = createContext({
  edition: "billing_pro",
  edition_name: "NOC-Billing-Pro",
  features: {
    billing: true,
    customers: true,
    genieacs: true,
    peering_eye: true,
    bgp_steering: true,
    finance_report: true,
    cs_command_center: true,
    client_portal: true,
    n8n_integration: true,
    radius: true,
  },
  is_enterprise: true,
  billing_enabled: true,
});
export const useEdition = () => useContext(EditionContext);

// ─── Loading spinner (theme-aware) ──────────────────────────────────────────
function PageFallback() {
  return (
    <div className="flex items-center justify-center h-screen w-full bg-background">
      <div className="flex flex-col items-center gap-3">
        {/* Outer glow ring */}
        <div className="relative w-10 h-10">
          <div className="absolute inset-0 rounded-full border-2 border-transparent
            border-t-[hsl(var(--primary))] border-r-[hsl(var(--primary))]
            animate-spin
            shadow-[0_0_12px_rgba(0,230,118,0.4)]
          " />
          <div className="absolute inset-1.5 rounded-full border border-[hsl(var(--primary)/0.2)]" />
        </div>
        <span className="text-[10px] font-mono text-muted-foreground uppercase tracking-widest animate-pulse">
          Loading...
        </span>
      </div>
    </div>
  );
}

// ─── Protected Route ──────────────────────────────────────────────────────────
function ProtectedRoute({ children }) {
  const { token } = useAuth();
  if (!token) return <Navigate to="/login" replace />;
  return children;
}

// ─── App Root ─────────────────────────────────────────────────────────────────
export default function App() {
  // ── Auth state (persisted in localStorage) ──────────────────────────────────
  const [token, setToken] = useState(
    () => localStorage.getItem("noc_token") || null
  );
  const [user, setUser] = useState(() => {
    try {
      return JSON.parse(localStorage.getItem("noc_user") || "null");
    } catch {
      return null;
    }
  });

  // ── Edition state (fetched from backend, default = full billing_pro set) ────
  const [editionData, setEditionData] = useState({
    edition: "billing_pro",
    edition_name: "NOC-Billing-Pro",
    features: {
      billing: true,
      customers: true,
      genieacs: true,
      peering_eye: true,
      bgp_steering: true,
      finance_report: true,
      cs_command_center: true,
      client_portal: true,
      n8n_integration: true,
      radius: true,
    },
    is_enterprise: true,
    billing_enabled: true,
  });

  useEffect(() => {
    if (!token) return;
    api
      .get("/edition")
      .then((res) => setEditionData(res.data))
      .catch(() => {
        // Keep defaults if backend unreachable (license page still reachable)
      });
  }, [token]);

  // ── Auth helpers ────────────────────────────────────────────────────────────
  const login = (newToken, newUser) => {
    localStorage.setItem("noc_token", newToken);
    localStorage.setItem("noc_user", JSON.stringify(newUser));
    setToken(newToken);
    setUser(newUser);
  };

  const logout = () => {
    localStorage.removeItem("noc_token");
    localStorage.removeItem("noc_user");
    setToken(null);
    setUser(null);
  };

  return (
    <QueryClientProvider client={queryClient}>
    <AuthContext.Provider value={{ token, user, login, logout }}>
      <EditionContext.Provider value={editionData}>
        <ThemeProvider>
        <BrowserRouter>
          <ErrorBoundary>
            <Suspense fallback={<PageFallback />}>
              <Routes>
                {/* ── Public routes ─────────────────────────────────────── */}
                <Route path="/login" element={<LoginPage />} />

                {/* ── Client Self-Service Portal (public) ───────────────── */}
                <Route path="/portal/setup"     element={<ServerSetup />} />
                <Route path="/portal/login"     element={<ClientLogin />} />
                <Route path="/portal/dashboard" element={<ClientDashboard />} />
                <Route path="/portal"           element={<Navigate to="/portal/login" replace />} />

                {/* ── Full-Screen TV Dashboards ─────────────────────────── */}
                <Route
                  path="/wall-display"
                  element={
                    <ProtectedRoute>
                      <WallDisplayPage />
                    </ProtectedRoute>
                  }
                />

                {/* ── Field Operations Portals ─────────────────────────── */}
                <Route
                  path="/teknisi"
                  element={
                    <ProtectedRoute>
                      <TechnicianPortal />
                    </ProtectedRoute>
                  }
                />
                <Route
                  path="/kolektor"
                  element={
                    <ProtectedRoute>
                      <CollectorPortal />
                    </ProtectedRoute>
                  }
                />

                {/* ── Authenticated app (all nested under Layout) ────────── */}
                <Route
                  path="/"
                  element={
                    <ProtectedRoute>
                      <Layout />
                    </ProtectedRoute>
                  }
                >
                  {/* 1. Dashboard */}
                  <Route index                         element={<DashboardPage />} />

                  {/* 2. Device Hub */}
                  <Route path="devices"                element={<DevicesPage />} />

                  {/* 3. GenieACS + ZTP */}
                  <Route path="genieacs"               element={<GenieACSPage />} />

                  {/* 4. RADIUS / Hotspot Users */}
                  <Route path="hotspot"                element={<Navigate to="/" replace />} />

                  {/* 5. Billing PPPoE */}
                  <Route path="pppoe"                  element={<Navigate to="/" replace />} />
                  <Route path="billing"                element={<BillingPage />} />

                  {/* 6. Billing Hotspot */}
                  <Route path="hotspot-billing"        element={<HotspotBillingPage />} />

                  {/* 7. Laporan Keuangan */}
                  <Route path="finance-report"         element={<FinanceReportPage />} />
                  <Route path="reports"                element={<ReportsPage />} />

                  {/* 8. CS Command Center */}
                  <Route path="wa-customer-service"    element={<WACustomerServicePage />} />

                  {/* 9. Portal Pelanggan (admin view) */}
                  {/* Client Portal public routes are above */}

                  {/* 10 & 11. Peering Eye + BGP */}
                  <Route path="peering-eye"            element={<PeeringEyePage />} />
                  <Route path="bgp-steering"           element={<BgpSteeringPage />} />
                  <Route path="zapret"                 element={<ZapretPage />} />
                  <Route path="network-tuning"          element={<NetworkTuningPage />} />
                  <Route path="network-map"             element={<NetworkMapPage />} />

                  {/* 12. Pengaturan */}
                  <Route path="settings"               element={<SettingsPage />} />
                  <Route path="notifications"          element={<NotificationsPage />} />
                  <Route path="radius-server"          element={<RadiusSettingsPage />} />

                  {/* 13. Integrasi & Otomasi */}
                  <Route path="integration-settings"   element={<IntegrationSettingsPage />} />

                  {/* 14. User Management */}
                  <Route path="admin"                  element={<AdminPage />} />

                  {/* 15. Update Aplikasi */}
                  <Route path="update"                 element={<UpdatePage />} />

                  {/* 16. Lisensi Sistem */}
                  <Route path="admin/license"          element={<LicensePage />} />

                  {/* System support pages */}
                  <Route path="backups"                element={<BackupsPage />} />

                  {/* Disabled features — redirect to home */}
                  <Route path="scheduler"              element={<Navigate to="/" replace />} />
                  <Route path="syslog"                 element={<Navigate to="/" replace />} />
                  <Route path="audit"                  element={<Navigate to="/" replace />} />
                  <Route path="topology"               element={<Navigate to="/" replace />} />
                  <Route path="sdwan"                  element={<Navigate to="/" replace />} />
                  <Route path="routing"                element={<Navigate to="/" replace />} />
                  <Route path="sla"                    element={<Navigate to="/" replace />} />
                  <Route path="incidents"              element={<Navigate to="/" replace />} />
                  <Route path="ping"                   element={<Navigate to="/" replace />} />

                  {/* Catch-all */}
                  <Route path="*"                      element={<Navigate to="/" replace />} />
                </Route>

                {/* Global catch-all */}
                <Route path="*" element={<Navigate to="/" replace />} />
              </Routes>
            </Suspense>
          </ErrorBoundary>
        </BrowserRouter>

        {/* Global toast notifications */}
        <Toaster richColors position="bottom-right" closeButton theme="dark" />
      </ThemeProvider>
      </EditionContext.Provider>
    </AuthContext.Provider>
    </QueryClientProvider>
  );
}
