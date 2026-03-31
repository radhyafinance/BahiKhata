import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "./AuthContext";
import { toast } from "sonner";
import { Eye, EyeOff, Loader2, Fingerprint, CheckCircle2, X } from "lucide-react";

const webAuthnSupported =
  typeof window !== "undefined" &&
  !!window.PublicKeyCredential &&
  typeof navigator.credentials?.get === "function";

export default function Login() {
  const { login, passkeyLogin, registerPasskey } = useAuth();
  const navigate = useNavigate();

  const [phone, setPhone] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [passkeyLoading, setPasskeyLoading] = useState(false);
  const [error, setError] = useState("");

  // After password-login: ask user to register a passkey
  const [showPasskeyPrompt, setShowPasskeyPrompt] = useState(false);
  const [registerLoading, setRegisterLoading] = useState(false);
  const [loggedInUser, setLoggedInUser] = useState(null);

  // Shake animation for errors
  const [shake, setShake] = useState(false);

  const triggerShake = () => {
    setShake(true);
    setTimeout(() => setShake(false), 500);
  };

  // ── Passkey login ─────────────────────────────────────────────────────────
  const handlePasskeyLogin = async () => {
    setError("");
    setPasskeyLoading(true);
    try {
      await passkeyLogin();
      toast.success("Welcome back! Signed in with passkey.");
      navigate("/");
    } catch (err) {
      const msg = err.message || "Passkey login failed";
      setError(msg);
      triggerShake();
      toast.error(msg);
    } finally {
      setPasskeyLoading(false);
    }
  };

  // ── Password login ────────────────────────────────────────────────────────
  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const data = await login(phone, password);
      // If device supports WebAuthn and user has no passkey yet → offer registration
      if (webAuthnSupported && !data.has_passkeys) {
        setLoggedInUser(data);
        setShowPasskeyPrompt(true);
      } else {
        toast.success("Welcome to Bahi Khata!");
        navigate("/");
      }
    } catch (err) {
      const detail = err.response?.data?.detail;
      const msg = typeof detail === "string" ? detail : "Invalid credentials";
      setError(msg);
      triggerShake();
      toast.error(msg);
    } finally {
      setLoading(false);
    }
  };

  // ── Passkey registration (after password login) ───────────────────────────
  const handleRegisterPasskey = async () => {
    setRegisterLoading(true);
    try {
      await registerPasskey("Bahi Khata Passkey");
      toast.success("Passkey registered! You can now log in with biometrics.");
      navigate("/");
    } catch (err) {
      const msg = err.message || "Passkey registration failed";
      toast.error(msg);
      // Still proceed to app even if registration fails
      navigate("/");
    } finally {
      setRegisterLoading(false);
    }
  };

  const skipPasskeyRegistration = () => {
    toast.success("Welcome to Bahi Khata!");
    navigate("/");
  };

  // ── Passkey prompt UI ─────────────────────────────────────────────────────
  if (showPasskeyPrompt) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center p-6">
        <div className="w-full max-w-sm text-center">
          {/* Icon */}
          <div
            className="w-20 h-20 rounded-full flex items-center justify-center mx-auto mb-6"
            style={{ background: "hsl(156, 72%, 25%)" }}
          >
            <Fingerprint size={40} className="text-white" />
          </div>

          <h2 className="text-2xl font-bold text-foreground font-['Outfit'] mb-2">
            Enable Faster Login
          </h2>
          <p className="text-muted-foreground text-sm mb-2">
            Register this device for fingerprint / Face ID login.
          </p>
          <p className="text-muted-foreground text-xs mb-8">
            No password needed next time — just one tap.
          </p>

          <button
            onClick={handleRegisterPasskey}
            disabled={registerLoading}
            data-testid="register-passkey-btn"
            className="w-full flex items-center justify-center gap-2 rounded-xl py-3 px-4 text-white font-semibold text-sm mb-3 transition-all hover:opacity-90 active:scale-95"
            style={{ background: "hsl(156, 72%, 25%)" }}
          >
            {registerLoading ? (
              <>
                <Loader2 size={18} className="animate-spin" />
                Setting up…
              </>
            ) : (
              <>
                <Fingerprint size={18} />
                Register Passkey
              </>
            )}
          </button>

          <button
            onClick={skipPasskeyRegistration}
            disabled={registerLoading}
            data-testid="skip-passkey-btn"
            className="w-full py-3 px-4 text-muted-foreground text-sm hover:text-foreground transition-colors"
          >
            Skip for now
          </button>
        </div>
      </div>
    );
  }

  // ── Main login UI ─────────────────────────────────────────────────────────
  return (
    <div className="min-h-screen bg-background flex">
      {/* Left Panel — Hero */}
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

        <div className="absolute top-0 right-0 w-64 h-64 bg-white/5 rounded-full -translate-y-1/2 translate-x-1/2" />
        <div className="absolute bottom-0 left-0 w-48 h-48 bg-white/5 rounded-full translate-y-1/3 -translate-x-1/3" />
      </div>

      {/* Right Panel — Login Form */}
      <div className="flex-1 flex items-center justify-center p-6 lg:p-12">
        <div className={`w-full max-w-md ${shake ? "animate-[shake_0.5s_ease-in-out]" : ""}`}>
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
              Sign in to your account{" "}
              <span className="text-xs">/ अपने खाते में साइन इन करें</span>
            </p>
          </div>

          {/* ── Passkey one-tap button ── */}
          {webAuthnSupported && (
            <div className="mb-6">
              <button
                type="button"
                onClick={handlePasskeyLogin}
                disabled={passkeyLoading}
                data-testid="passkey-login-btn"
                className="w-full flex items-center justify-center gap-3 rounded-xl border-2 py-3 px-4 text-sm font-semibold transition-all hover:shadow-md active:scale-[0.98] disabled:opacity-60"
                style={{
                  borderColor: "hsl(156, 72%, 25%)",
                  color: "hsl(156, 72%, 25%)",
                  background: "hsl(156, 72%, 97%)",
                }}
              >
                {passkeyLoading ? (
                  <>
                    <Loader2 size={18} className="animate-spin" />
                    Verifying…
                  </>
                ) : (
                  <>
                    <Fingerprint size={20} />
                    Sign in with Passkey
                  </>
                )}
              </button>
              <p className="text-center text-xs text-muted-foreground mt-2">
                Use fingerprint, Face ID, or PIN
              </p>
            </div>
          )}

          {/* ── Divider ── */}
          {webAuthnSupported && (
            <div className="flex items-center gap-3 mb-6">
              <div className="flex-1 h-px bg-border" />
              <span className="text-xs text-muted-foreground">or sign in with password</span>
              <div className="flex-1 h-px bg-border" />
            </div>
          )}

          {/* ── Error ── */}
          {error && (
            <div
              className="mb-4 p-4 rounded-lg bg-destructive/10 border border-destructive/20 text-destructive text-sm"
              data-testid="login-error"
            >
              {error}
            </div>
          )}

          {/* ── Password form ── */}
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
                  <span>Signing in…</span>
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
