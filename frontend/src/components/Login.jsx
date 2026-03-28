import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "./AuthContext";
import { toast } from "sonner";
import { Eye, EyeOff, Loader2 } from "lucide-react";

export default function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [phone, setPhone] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await login(phone, password);
      toast.success("Welcome to Bahi Khata!");
      navigate("/");
    } catch (err) {
      const detail = err.response?.data?.detail;
      const msg = typeof detail === "string" ? detail : "Invalid credentials";
      setError(msg);
      toast.error(msg);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-background flex">
      {/* Left Panel - Hero */}
      <div
        className="hidden lg:flex flex-col justify-between w-1/2 p-12 relative overflow-hidden"
        style={{ background: "hsl(156, 72%, 25%)" }}
      >
        <div className="relative z-10">
          <div className="flex items-center gap-3 mb-16">
            <div className="w-12 h-12 bg-white/20 rounded-xl flex items-center justify-center">
              <span className="text-white font-bold text-2xl font-['Outfit']">B</span>
            </div>
            <div>
              <h1 className="text-white font-bold text-2xl font-['Outfit']">Bahi Khata</h1>
              <p className="text-white/70 text-sm">NBFC-MFI Management Platform</p>
            </div>
          </div>
          <div className="space-y-6">
            <h2 className="text-white text-4xl font-bold font-['Outfit'] leading-tight">
              Empowering Financial<br />Inclusion
            </h2>
            <p className="text-white/80 text-lg leading-relaxed">
              Streamline KYC collection, manage client records, and grow your microfinance portfolio — all in one place.
            </p>
            <p className="text-white/60 text-base">
              वित्तीय समावेशन को सशक्त बनाना
            </p>
          </div>
        </div>

        <div className="relative z-10">
          <img
            src="https://images.unsplash.com/photo-1766716946030-5869da2a0ead?crop=entropy&cs=srgb&fm=jpg&w=600&q=80"
            alt="Rural business"
            className="rounded-2xl w-full object-cover h-64 opacity-40"
          />
        </div>

        {/* Decorative circles */}
        <div className="absolute top-0 right-0 w-64 h-64 bg-white/5 rounded-full -translate-y-1/2 translate-x-1/2" />
        <div className="absolute bottom-0 left-0 w-48 h-48 bg-white/5 rounded-full translate-y-1/3 -translate-x-1/3" />
      </div>

      {/* Right Panel - Login Form */}
      <div className="flex-1 flex items-center justify-center p-6 lg:p-12">
        <div className="w-full max-w-md">
          {/* Mobile Logo */}
          <div className="flex items-center gap-3 mb-10 lg:hidden">
            <div className="w-10 h-10 bg-primary rounded-xl flex items-center justify-center">
              <span className="text-white font-bold text-lg font-['Outfit']">B</span>
            </div>
            <div>
              <h1 className="font-bold text-xl text-foreground font-['Outfit']">Bahi Khata</h1>
              <p className="text-xs text-muted-foreground">NBFC-MFI Platform</p>
            </div>
          </div>

          <div className="mb-8">
            <h2 className="text-3xl font-bold text-foreground font-['Outfit']">Welcome back</h2>
            <p className="text-muted-foreground mt-1">
              Sign in to your account <span className="text-xs">/ अपने खाते में साइन इन करें</span>
            </p>
          </div>

          {error && (
            <div
              className="mb-4 p-4 rounded-lg bg-destructive/10 border border-destructive/20 text-destructive text-sm"
              data-testid="login-error"
            >
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-5" data-testid="login-form">
            <div>
              <label className="bk-label">
                <span className="bk-label-en">Mobile Number</span>
                <span className="bk-label-hi">मोबाइल नंबर</span>
              </label>
              <input
                type="tel"
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
                className="bk-input"
                placeholder="10-digit mobile number"
                required
                data-testid="login-phone-input"
              />
            </div>

            <div>
              <label className="bk-label">
                <span className="bk-label-en">Password</span>
                <span className="bk-label-hi">पासवर्ड</span>
              </label>
              <div className="relative">
                <input
                  type={showPassword ? "text" : "password"}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="bk-input pr-12"
                  placeholder="••••••••"
                  required
                  data-testid="login-password-input"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-4 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors"
                  data-testid="toggle-password-btn"
                >
                  {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                </button>
              </div>
            </div>

            <button
              type="submit"
              disabled={loading}
              className="bk-btn-primary flex items-center justify-center gap-2 mt-6"
              data-testid="login-submit-btn"
            >
              {loading ? (
                <>
                  <Loader2 size={18} className="animate-spin" />
                  <span>Signing in...</span>
                </>
              ) : (
                "Sign In / साइन इन करें"
              )}
            </button>
          </form>

          <p className="text-center text-xs text-muted-foreground mt-8">
            Bahi Khata &copy; 2025 — Secure NBFC-MFI Platform
          </p>
        </div>
      </div>
    </div>
  );
}
