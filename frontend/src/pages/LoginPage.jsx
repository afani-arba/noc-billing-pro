import { useState } from "react";
import { useNavigate, Navigate } from "react-router-dom";
import { useAuth } from "@/App";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Server, Eye, EyeOff, Lock, User } from "lucide-react";
import api from "@/lib/api";
import { toast } from "sonner";

export default function LoginPage() {
  const { user, login } = useAuth();
  const navigate = useNavigate();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);

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
      login(res.data.token, res.data.user);
      toast.success("Login successful");
      navigate("/");
    } catch (err) {
      toast.error(err.response?.data?.detail || "Invalid credentials");
    }
    setLoading(false);
  };

  return (
    <div className="min-h-screen flex" data-testid="login-page">
      {/* Left Panel - Brand (Corporate Navy) */}
      <div className="hidden lg:flex lg:w-1/2 relative overflow-hidden" style={{ background: "linear-gradient(135deg, hsl(220, 40%, 10%) 0%, hsl(217, 50%, 14%) 50%, hsl(215, 55%, 18%) 100%)" }}>
        {/* Subtle grid overlay */}
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

          {/* Corporate footer badge */}
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
          {/* Mobile logo */}
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
            <h3 className="text-2xl font-bold text-foreground ">Sign In</h3>
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

