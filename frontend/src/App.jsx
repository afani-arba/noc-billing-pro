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
import ErrorBoundary from "@/components/ErrorBoundary";
import Layout from "@/components/Layout";
import api from "@/lib/api";

// ─── Lazy-loaded pages ────────────────────────────────────────────────────────
const LoginPage               = lazy(() => import("@/pages/LoginPage"));
const DashboardPage           = lazy(() => import("@/pages/DashboardPage"));
const DevicesPage             = lazy(() => import("@/pages/DevicesPage"));
const PPPoEUsersPage          = lazy(() => import("@/pages/PPPoEUsersPage"));
const HotspotUsersPage        = lazy(() => import("@/pages/HotspotUsersPage"));
const BillingPage             = lazy(() => import("@/pages/BillingPage"));
const HotspotBillingPage      = lazy(() => import("@/pages/HotspotBillingPage"));
const FinanceReportPage       = lazy(() => import("@/pages/FinanceReportPage"));
const GenieACSPage            = lazy(() => import("@/pages/GenieACSPage"));
const PeeringEyePage          = lazy(() => import("@/pages/PeeringEyePage"));
const ReportsPage             = lazy(() => import("@/pages/ReportsPage"));
const WACustomerServicePage   = lazy(() => import("@/pages/WACustomerServicePage"));
const SettingsPage            = lazy(() => import("@/pages/SettingsPage"));
const AdminPage               = lazy(() => import("@/pages/AdminPage"));
const NotificationsPage       = lazy(() => import("@/pages/NotificationsPage"));
const BackupsPage             = lazy(() => import("@/pages/BackupsPage"));
const AuditLogPage            = lazy(() => import("@/pages/AuditLogPage"));
const SchedulerPage           = lazy(() => import("@/pages/SchedulerPage"));
const UpdatePage              = lazy(() => import("@/pages/UpdatePage"));
const LicensePage             = lazy(() => import("@/pages/LicensePage"));
const WallDisplayPage         = lazy(() => import("@/pages/WallDisplayPage"));
const RadiusSettingsPage      = lazy(() => import("@/pages/RadiusSettingsPage"));
const IntegrationSettingsPage = lazy(() => import("@/pages/IntegrationSettingsPage"));
const ClientLogin             = lazy(() => import("@/pages/ClientPortal/ClientLogin"));
const ClientDashboard         = lazy(() => import("@/pages/ClientPortal/ClientDashboard"));

// ─── Auth Context ─────────────────────────────────────────────────────────────
const AuthContext = createContext(null);
export const useAuth = () => useContext(AuthContext);

// ─── Edition Context ──────────────────────────────────────────────────────────
const EditionContext = createContext({
  edition: "enterprise",
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

// ─── Loading spinner ──────────────────────────────────────────────────────────
function PageFallback() {
  return (
    <div className="flex items-center justify-center h-screen w-full bg-background">
      <div className="animate-spin rounded-full h-8 w-8 border-t-2 border-b-2 border-primary" />
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
    edition: "enterprise",
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
    <AuthContext.Provider value={{ token, user, login, logout }}>
      <EditionContext.Provider value={editionData}>
        <BrowserRouter>
          <ErrorBoundary>
            <Suspense fallback={<PageFallback />}>
              <Routes>
                {/* ── Public routes ─────────────────────────────────────── */}
                <Route path="/login" element={<LoginPage />} />

                {/* ── Client Self-Service Portal (public) ───────────────── */}
                <Route path="/portal/login"     element={<ClientLogin />} />
                <Route path="/portal/dashboard" element={<ClientDashboard />} />
                <Route path="/portal"           element={<Navigate to="/portal/login" replace />} />

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
                  <Route path="wall-display"           element={<WallDisplayPage />} />

                  {/* 2. Device Hub */}
                  <Route path="devices"                element={<DevicesPage />} />

                  {/* 3. GenieACS + ZTP */}
                  <Route path="genieacs"               element={<GenieACSPage />} />

                  {/* 4. RADIUS / Hotspot Users */}
                  <Route path="hotspot"                element={<HotspotUsersPage />} />

                  {/* 5. Billing PPPoE */}
                  <Route path="pppoe"                  element={<PPPoEUsersPage />} />
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
                  <Route path="audit"                  element={<AuditLogPage />} />
                  <Route path="scheduler"              element={<SchedulerPage />} />

                  {/* Disabled features in Billing Pro — redirect to home */}
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
        <Toaster richColors position="top-right" closeButton />
      </EditionContext.Provider>
    </AuthContext.Provider>
  );
}
