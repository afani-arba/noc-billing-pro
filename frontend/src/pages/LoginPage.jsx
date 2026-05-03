import { useState } from "react";
import { useNavigate, Navigate } from "react-router-dom";
import { useAuth } from "@/App";
import { useTheme } from "@/context/ThemeContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Server, Eye, EyeOff, Lock, User, Activity, Wifi, Shield } from "lucide-react";
import api from "@/lib/api";
import { toast } from "sonner";

export default function LoginPage() {
  const { user, login } = useAuth();
  const { theme } = useTheme();
  const navigate = useNavigate();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);

  const isCyber = theme === "cyber";

  if (user) return <Navigate to="/" />;

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!username || !password) {
      toast.error("Please fill in all fields");
      return;
    }
    setLoading(true);
    try {
      const res = await api.post("/auth/login", { username, password });
      const user = res.data.user;
      login(res.data.token, user);
      toast.success("Login successful");
      if (user.role === 'teknisi') {
        navigate("/teknisi");
      } else if (user.role === 'kolektor') {
        navigate("/kolektor");
      } else {
        navigate("/");
      }
    } catch (err) {
      toast.error(err.response?.data?.detail || "Invalid credentials");
    }
    setLoading(false);
  };

  // ── CYBER THEME ──────────────────────────────────────────────────────────────
  if (isCyber) {
    return (
      <div className="min-h-screen flex" data-testid="login-page" style={{
        background: "hsl(210,20%,5%)",
        backgroundImage: `
          linear-gradient(rgba(0,230,118,0.04) 1px, transparent 1px),
          linear-gradient(90deg, rgba(0,230,118,0.04) 1px, transparent 1px),
          radial-gradient(ellipse at 15% 30%, rgba(0,230,118,0.10) 0%, transparent 55%),
          radial-gradient(ellipse at 85% 70%, rgba(0,229,255,0.08) 0%, transparent 55%),
          radial-gradient(ellipse at 50% 50%, rgba(0,100,80,0.03) 0%, transparent 70%)
        `,
        backgroundSize: "40px 40px, 40px 40px, 100% 100%, 100% 100%, 100% 100%",
      }}>
        {/* ── Left Panel ─────────────────────────────────────────────────────── */}
        <div className="hidden lg:flex lg:w-1/2 relative overflow-hidden flex-col justify-center px-14 py-16">
          {/* Floating glass orbs */}
          <div className="absolute top-1/4 left-1/4 w-64 h-64 rounded-full opacity-10 animate-float"
            style={{ background: "radial-gradient(circle, rgba(0,230,118,0.4) 0%, transparent 70%)" }}
          />
          <div className="absolute bottom-1/4 right-1/4 w-48 h-48 rounded-full opacity-8 animate-float animation-delay-2000"
            style={{ background: "radial-gradient(circle, rgba(0,229,255,0.4) 0%, transparent 70%)" }}
          />

          {/* Brand */}
          <div className="relative z-10 max-w-lg">
            <div className="flex items-center gap-3 mb-10">
              <div className="w-12 h-12 rounded flex items-center justify-center"
                style={{
                  background: "rgba(0,230,118,0.08)",
                  border: "1px solid rgba(0,230,118,0.3)",
                  boxShadow: "0 0 20px rgba(0,230,118,0.2)",
                  backdropFilter: "blur(12px)",
                }}>
                <Server className="w-6 h-6" style={{ color: "hsl(162,100%,50%)" }} />
              </div>
              <div>
                <h1 className="text-2xl font-bold tracking-tight gradient-text font-mono">ARBA</h1>
                <p className="text-[10px] font-mono uppercase tracking-[0.4em]"
                  style={{ color: "hsl(185,100%,40%)" }}>
                  NOC // Billing Pro
                </p>
              </div>
            </div>

            <h2 className="text-4xl font-bold leading-tight mb-3">
              <span className="gradient-text font-mono">Network</span>
              <span className="text-white block">Operations</span>
              <span className="font-mono text-3xl" style={{ color: "hsl(185,100%,55%)" }}>
                Command Center
              </span>
            </h2>

            <p className="text-sm leading-relaxed mb-10" style={{ color: "rgba(255,255,255,0.4)" }}>
              Sistem manajemen MikroTik profesional untuk NOC Engineers.<br />
              Monitor PPPoE, Hotspot, Bandwidth, dan Device Health secara realtime.
            </p>

            <div className="space-y-4">
              {[
                { icon: Activity, label: "Real-time Monitoring",   desc: "Live bandwidth, latency & packet tracking" },
                { icon: Wifi,     label: "Multi-Device Support",   desc: "Kelola ratusan MikroTik sekaligus" },
                { icon: Shield,   label: "Advanced RBAC & Audit",  desc: "Access control granular per engineer" },
              ].map((feat, i) => (
                <div
                  key={i}
                  className="flex items-start gap-4 p-3 rounded opacity-0 animate-slide-up"
                  style={{
                    animationDelay: `${i * 0.12}s`,
                    animationFillMode: "forwards",
                    background: "rgba(0,230,118,0.04)",
                    border: "1px solid rgba(0,230,118,0.12)",
                    backdropFilter: "blur(8px)",
                  }}
                >
                  <div className="w-8 h-8 rounded flex items-center justify-center flex-shrink-0"
                    style={{ background: "rgba(0,230,118,0.1)", border: "1px solid rgba(0,230,118,0.2)" }}>
                    <feat.icon className="w-4 h-4" style={{ color: "hsl(162,100%,50%)" }} />
                  </div>
                  <div>
                    <p className="text-sm font-semibold font-mono" style={{ color: "hsl(162,100%,70%)" }}>
                      {feat.label}
                    </p>
                    <p className="text-xs" style={{ color: "rgba(255,255,255,0.4)" }}>{feat.desc}</p>
                  </div>
                </div>
              ))}
            </div>

            {/* Version badge */}
            <div className="mt-10 flex items-center gap-3">
              <div className="glow-dot-green" />
              <span className="text-[10px] font-mono uppercase tracking-widest"
                style={{ color: "hsl(185,100%,35%)" }}>
                System Status :: Online · v3.0.0-pro
              </span>
            </div>
          </div>
        </div>

        {/* ── Right Panel — Login Form ─────────────────────────────────────── */}
        <div className="flex-1 flex items-center justify-center p-6">
          {/* Glass card */}
          <div className="w-full max-w-sm p-8 rounded-xl"
            style={{
              background: "rgba(8,14,22,0.85)",
              border: "1px solid rgba(0,230,118,0.15)",
              backdropFilter: "blur(24px)",
              boxShadow: "0 0 40px rgba(0,230,118,0.08), 0 25px 50px rgba(0,0,0,0.8)",
            }}>

            {/* Mobile logo */}
            <div className="flex items-center gap-3 mb-8 lg:hidden">
              <div className="w-9 h-9 rounded flex items-center justify-center"
                style={{ background: "rgba(0,230,118,0.08)", border: "1px solid rgba(0,230,118,0.25)" }}>
                <Server className="w-5 h-5" style={{ color: "hsl(162,100%,50%)" }} />
              </div>
              <div>
                <h1 className="text-lg font-bold gradient-text font-mono">ARBA</h1>
                <p className="text-[10px] font-mono" style={{ color: "hsl(185,100%,40%)" }}>NOC // Billing Pro</p>
              </div>
            </div>

            {/* Form header */}
            <div className="mb-8">
              <div className="flex items-center gap-2 mb-1">
                <div className="glow-dot-green flex-shrink-0" />
                <p className="text-[10px] font-mono uppercase tracking-widest"
                  style={{ color: "hsl(162,100%,45%)" }}>
                  Authenticated Access
                </p>
              </div>
              <h3 className="text-2xl font-bold font-mono" style={{ color: "hsl(162,100%,75%)" }}>
                SIGN_IN
              </h3>
              <p className="text-xs mt-1 font-mono" style={{ color: "rgba(255,255,255,0.35)" }}>
                &gt; Enter credentials to access NOC dashboard
              </p>
            </div>

            <form onSubmit={handleSubmit} className="space-y-5">
              <div className="space-y-1.5">
                <Label htmlFor="username" className="text-[10px] font-mono uppercase tracking-widest"
                  style={{ color: "hsl(162,100%,45%)" }}>
                  &gt; Username
                </Label>
                <div className="relative">
                  <User className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4"
                    style={{ color: "hsl(162,100%,35%)" }} />
                  <input
                    id="username"
                    type="text"
                    placeholder="noc_engineer"
                    value={username}
                    onChange={(e) => setUsername(e.target.value)}
                    className="w-full h-10 pl-10 pr-4 rounded font-mono text-sm outline-none transition-all"
                    style={{
                      background: "rgba(0,230,118,0.04)",
                      border: "1px solid rgba(0,230,118,0.15)",
                      color: "hsl(162,100%,75%)",
                    }}
                    onFocus={e => {
                      e.target.style.borderColor = "rgba(0,230,118,0.5)";
                      e.target.style.boxShadow = "0 0 0 2px rgba(0,230,118,0.1), 0 0 12px rgba(0,230,118,0.15)";
                    }}
                    onBlur={e => {
                      e.target.style.borderColor = "rgba(0,230,118,0.15)";
                      e.target.style.boxShadow = "none";
                    }}
                    data-testid="login-username-input"
                  />
                </div>
              </div>

              <div className="space-y-1.5">
                <Label htmlFor="password" className="text-[10px] font-mono uppercase tracking-widest"
                  style={{ color: "hsl(162,100%,45%)" }}>
                  &gt; Password
                </Label>
                <div className="relative">
                  <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4"
                    style={{ color: "hsl(162,100%,35%)" }} />
                  <input
                    id="password"
                    type={showPassword ? "text" : "password"}
                    placeholder="••••••••"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    className="w-full h-10 pl-10 pr-10 rounded font-mono text-sm outline-none transition-all"
                    style={{
                      background: "rgba(0,230,118,0.04)",
                      border: "1px solid rgba(0,230,118,0.15)",
                      color: "hsl(162,100%,75%)",
                    }}
                    onFocus={e => {
                      e.target.style.borderColor = "rgba(0,230,118,0.5)";
                      e.target.style.boxShadow = "0 0 0 2px rgba(0,230,118,0.1), 0 0 12px rgba(0,230,118,0.15)";
                    }}
                    onBlur={e => {
                      e.target.style.borderColor = "rgba(0,230,118,0.15)";
                      e.target.style.boxShadow = "none";
                    }}
                    data-testid="login-password-input"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword(!showPassword)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 transition-colors"
                    style={{ color: "hsl(162,100%,35%)" }}
                    data-testid="toggle-password-btn"
                  >
                    {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                  </button>
                </div>
              </div>

              {/* Submit button */}
              <button
                type="submit"
                disabled={loading}
                className="w-full h-10 rounded font-mono font-bold text-sm uppercase tracking-widest transition-all active:scale-[0.98] disabled:opacity-50"
                style={{
                  background: "linear-gradient(135deg, hsl(162,100%,40%), hsl(185,100%,38%))",
                  color: "hsl(210,20%,5%)",
                  border: "1px solid rgba(0,230,118,0.4)",
                  boxShadow: "0 0 20px rgba(0,230,118,0.25), 0 0 4px rgba(0,230,118,0.15) inset",
                }}
                onMouseEnter={e => { e.target.style.boxShadow = "0 0 32px rgba(0,230,118,0.5), 0 0 8px rgba(0,230,118,0.2) inset"; }}
                onMouseLeave={e => { e.target.style.boxShadow = "0 0 20px rgba(0,230,118,0.25), 0 0 4px rgba(0,230,118,0.15) inset"; }}
                data-testid="login-submit-btn"
              >
                {loading ? "AUTHENTICATING..." : "SIGN_IN >>"}
              </button>
            </form>

            {/* Footer */}
            <div className="mt-8 pt-4" style={{ borderTop: "1px solid rgba(0,230,118,0.08)" }}>
              <p className="text-[10px] font-mono text-center" style={{ color: "rgba(255,255,255,0.2)" }}>
                POWERED BY
              </p>
              <p className="text-xs font-mono text-center mt-0.5" style={{ color: "hsl(185,100%,35%)" }}>
                PT Arsya Barokah Abadi
              </p>
              <a href="https://www.arbatraining.com" target="_blank" rel="noopener noreferrer"
                className="block text-[10px] font-mono text-center mt-0.5 transition-colors"
                style={{ color: "hsl(162,100%,30%)" }}
                onMouseEnter={e => e.target.style.color = "hsl(162,100%,50%)"}
                onMouseLeave={e => e.target.style.color = "hsl(162,100%,30%)"}>
                www.arbatraining.com
              </a>
            </div>
          </div>
        </div>
      </div>
    );
  }

  // ── CLASSIC THEME (unchanged) ─────────────────────────────────────────────
  return (
    <div className="min-h-screen flex" data-testid="login-page">
      {/* Left Panel - Brand (Corporate Navy) */}
      <div className="hidden lg:flex lg:w-1/2 relative overflow-hidden" style={{ background: "linear-gradient(135deg, hsl(220, 40%, 10%) 0%, hsl(217, 50%, 14%) 50%, hsl(215, 55%, 18%) 100%)" }}>
        <div className="absolute inset-0" style={{ backgroundImage: "linear-gradient(hsl(220,40%,18%,.25) 1px, transparent 1px), linear-gradient(90deg, hsl(220,40%,18%,.25) 1px, transparent 1px)", backgroundSize: "48px 48px" }} />
        <div className="relative z-10 flex flex-col justify-center px-14 py-16 max-w-xl">
          <div className="flex items-center gap-3 mb-12">
            <div className="w-11 h-11 rounded bg-primary flex items-center justify-center shadow-lg">
              <Server className="w-5 h-5 text-white" />
            </div>
            <div>
              <h1 className="text-xl font-bold text-white tracking-tight">ARBA</h1>
              <p className="text-[11px] text-blue-300/70 uppercase tracking-[0.3em]">Monitoring System</p>
            </div>
          </div>
          <h2 className="text-3xl font-bold text-white leading-snug mb-4">
            Network Operations<br />
            <span className="text-blue-400">Command Center</span>
          </h2>
          <p className="text-blue-200/60 text-sm leading-relaxed mb-10">
            Professional MikroTik monitoring and management platform.
            Monitor PPPoE users, hotspot sessions, bandwidth, and device health in real-time.
          </p>
          <div className="space-y-3">
            {[
              { label: "Real-time Monitoring", desc: "Live bandwidth and user tracking" },
              { label: "Multi-Device Support", desc: "Manage multiple MikroTik routers" },
              { label: "Advanced Reports", desc: "Export detailed analytics" },
            ].map((feat, i) => (
              <div key={i} className="flex items-start gap-3 opacity-0 animate-slide-up" style={{ animationDelay: `${i * 0.12}s`, animationFillMode: 'forwards' }}>
                <div className="w-0.5 h-8 rounded-full bg-primary mt-0.5 flex-shrink-0" />
                <div>
                  <p className="text-sm font-semibold text-white">{feat.label}</p>
                  <p className="text-xs text-blue-300/60">{feat.desc}</p>
                </div>
              </div>
            ))}
          </div>
          <div className="mt-16 flex items-center gap-2">
            <div className="flex gap-1">
              <div className="w-1.5 h-1.5 rounded-full bg-primary" />
              <div className="w-1.5 h-1.5 rounded-full bg-primary/50" />
              <div className="w-1.5 h-1.5 rounded-full bg-primary/25" />
            </div>
            <span className="text-[11px] text-blue-300/40 uppercase tracking-wider">Enterprise Network Management</span>
          </div>
        </div>
      </div>

      {/* Right Panel - Login Form */}
      <div className="flex-1 flex items-center justify-center p-6 bg-background">
        <div className="w-full max-w-sm">
          <div className="flex items-center gap-3 mb-10 lg:hidden">
            <div className="w-10 h-10 rounded bg-primary flex items-center justify-center">
              <Server className="w-5 h-5 text-white" />
            </div>
            <div>
              <h1 className="text-xl font-bold text-foreground">ARBA</h1>
              <p className="text-[10px] text-muted-foreground uppercase tracking-[0.2em]">Monitoring System</p>
            </div>
          </div>
          <div className="mb-8">
            <h3 className="text-2xl font-bold text-foreground">Sign In</h3>
            <p className="text-sm text-muted-foreground mt-1">Access your monitoring dashboard</p>
          </div>
          <form onSubmit={handleSubmit} className="space-y-5">
            <div className="space-y-2">
              <Label htmlFor="username" className="text-xs text-muted-foreground uppercase tracking-wider">Username</Label>
              <div className="relative">
                <User className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                <Input
                  id="username"
                  type="text"
                  placeholder="Enter username"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  className="pl-10 h-10 rounded-sm bg-card border-border focus:ring-1 focus:ring-primary"
                  data-testid="login-username-input"
                />
              </div>
            </div>
            <div className="space-y-2">
              <Label htmlFor="password" className="text-xs text-muted-foreground uppercase tracking-wider">Password</Label>
              <div className="relative">
                <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                <Input
                  id="password"
                  type={showPassword ? "text" : "password"}
                  placeholder="Enter password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="pl-10 pr-10 h-10 rounded-sm bg-card border-border focus:ring-1 focus:ring-primary"
                  data-testid="login-password-input"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors"
                  data-testid="toggle-password-btn"
                >
                  {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
            </div>
            <Button
              type="submit"
              disabled={loading}
              className="w-full h-10 rounded-sm bg-primary hover:bg-primary/90 text-white font-medium transition-all active:scale-[0.98]"
              data-testid="login-submit-btn"
            >
              {loading ? "Signing in..." : "Sign In"}
            </Button>
          </form>
          <div className="text-center mt-8 space-y-2">
            <div className="pt-4 border-t border-border/50">
              <p className="text-[10px] text-muted-foreground/70">Powered By</p>
              <p className="text-xs text-muted-foreground font-medium">PT Arsya Barokah Abadi</p>
              <a href="https://www.arbatraining.com" target="_blank" rel="noopener noreferrer" className="text-xs text-primary hover:underline">www.arbatraining.com</a>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
