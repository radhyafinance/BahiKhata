import { Outlet, NavLink, useNavigate } from "react-router-dom";
import { useAuth } from "./AuthContext";
import { useIllaka } from "./IllakaContext";
import { LayoutDashboard, UserPlus, FileText, LogOut, Menu, X, Users, MapPin, TrendingUp, ClipboardList, Globe, ChevronDown, BookOpen, Crown, Upload } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

const ROLE_LABELS = {
  admin: "Administrator",
  maalik: "Maalik",
  muneem: "Muneem",
  sipahi: "Sipahi",
};

const ROLE_COLOR = {
  admin: "bg-purple-100 text-purple-800",
  maalik: "bg-amber-100 text-amber-800",
  muneem: "bg-blue-100 text-blue-800",
  sipahi: "bg-green-100 text-green-800",
};

function getNavItems(role) {
  const base = [{ to: "/", icon: LayoutDashboard, label: "Dashboard", labelHi: "डैशबोर्ड" }];
  if (role === "muneem" || role === "sipahi") {
    base.push({ to: "/kyc/new", icon: UserPlus, label: "New KYC", labelHi: "नया KYC" });
  }
  base.push({ to: "/clients", icon: FileText, label: "Clients", labelHi: "ग्राहक" });
  base.push({ to: "/loans", icon: TrendingUp, label: "Loans", labelHi: "कर्ज" });
  base.push({ to: "/collections", icon: ClipboardList, label: "Vasuli", labelHi: "वसूली" });
  if (role !== "sipahi") {
    base.push({ to: "/accounts", icon: BookOpen, label: "Accounts", labelHi: "खाता" });
  }
  if (role === "admin" || role === "maalik") {
    base.push({ to: "/illakas", icon: MapPin, label: "Illakas", labelHi: "इलाके / मिसाल" });
    base.push({ to: "/users", icon: Users, label: "Team", labelHi: "टीम" });
    base.push({ to: "/import", icon: Upload, label: "Import", labelHi: "डेटा आयात" });
  }
  return base;
}

export default function Layout() {
  const { user, logout } = useAuth();
  const { selectedIllaka, resetIllaka, maaliks, selectedMaalik, setSelectedMaalik } = useIllaka();
  const navigate = useNavigate();
  const [sidebarOpen, setSidebarOpen] = useState(false);

  const handleLogout = async () => {
    await logout();
    toast.success("Logged out");
    navigate("/login");
  };

  const navItems = getNavItems(user?.role);
  const illakaLabel = selectedIllaka ? selectedIllaka.name : "All Illakas";

  const IllakaSwitcher = ({ compact = false }) => (
    <button
      onClick={resetIllaka}
      data-testid="illaka-switcher-btn"
      title="Change Illaka"
      className={`flex items-center gap-2 rounded-lg border border-primary/30 bg-primary/10 text-primary hover:bg-primary/20 transition-colors ${
        compact ? "px-2 py-1.5 text-xs" : "px-3 py-2 text-xs font-medium"
      }`}
    >
      {selectedIllaka ? <MapPin size={13} /> : <Globe size={13} />}
      <span className="truncate max-w-[120px] font-semibold">{illakaLabel}</span>
      <ChevronDown size={11} className="flex-shrink-0 opacity-70" />
    </button>
  );

  const SidebarContent = () => (
    <div className="flex flex-col h-full">
      {/* Logo */}
      <div className="p-6 border-b border-border">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 bg-primary rounded-xl flex items-center justify-center">
            <span className="text-white font-bold text-lg font-['Outfit']">B</span>
          </div>
          <div>
            <h1 className="font-bold text-xl text-foreground font-['Outfit']">Bahi Khata</h1>
            <p className="text-xs text-muted-foreground">Sahukar Platform</p>
          </div>
        </div>
      </div>

      {/* Nav */}
      <nav className="flex-1 p-4 space-y-1 overflow-y-auto" data-testid="sidebar-nav">
        {navItems.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.to === "/"}
            onClick={() => setSidebarOpen(false)}
            className={({ isActive }) =>
              `flex items-center gap-3 px-4 py-3 rounded-lg transition-all duration-200 ${
                isActive
                  ? "bg-primary text-primary-foreground shadow-sm"
                  : "text-foreground hover:bg-muted"
              }`
            }
          >
            <item.icon size={20} strokeWidth={1.8} />
            <div>
              <div className="text-sm font-semibold">{item.label}</div>
              <div className="text-xs opacity-70">{item.labelHi}</div>
            </div>
          </NavLink>
        ))}
      </nav>

      {/* User + Logout */}
      <div className="p-4 border-t border-border">
        {/* Maalik Filter — Admin only */}
        {user?.role === "admin" && maaliks.length > 0 && (
          <div className="mb-3 px-1">
            <p className="text-xs text-muted-foreground mb-1.5 font-medium flex items-center gap-1">
              <Crown size={11} /> Maalik Filter
            </p>
            <select
              value={selectedMaalik?.id || ""}
              onChange={e => {
                const m = maaliks.find(m => m.id === e.target.value);
                setSelectedMaalik(m ? { id: m.id, name: m.name, illaka_ids: m.assigned_illaka_ids || [] } : null);
              }}
              className="w-full text-xs px-2 py-1.5 rounded-lg border border-border bg-background text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
              data-testid="maalik-filter-select"
            >
              <option value="">All Maaliks</option>
              {maaliks.map(m => <option key={m.id} value={m.id}>{m.name}</option>)}
            </select>
          </div>
        )}
        {/* Illaka Switcher */}
        <div className="mb-3 px-1">
          <p className="text-xs text-muted-foreground mb-1.5 font-medium">Working Illaka / कार्यक्षेत्र</p>
          <IllakaSwitcher />
        </div>
        <div className="flex items-center gap-3 px-2 py-2 mb-2">
          <div className="w-9 h-9 bg-primary/15 rounded-full flex items-center justify-center flex-shrink-0">
            <span className="text-primary font-bold text-sm">
              {user?.name?.charAt(0)?.toUpperCase()}
            </span>
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-semibold text-foreground truncate">{user?.name}</p>
            <span className={`text-xs px-2 py-0.5 rounded-full font-semibold ${ROLE_COLOR[user?.role] || ""}`}>
              {ROLE_LABELS[user?.role] || user?.role}
            </span>
          </div>
        </div>
        <button
          onClick={handleLogout}
          data-testid="logout-btn"
          className="flex items-center gap-3 w-full px-4 py-3 rounded-lg text-destructive hover:bg-destructive/10 transition-colors"
        >
          <LogOut size={18} />
          <span className="text-sm font-semibold">Logout / लॉगआउट</span>
        </button>
      </div>
    </div>
  );

  return (
    <div
      className="flex bg-background overflow-hidden"
      style={{
        height: "100dvh",
        paddingTop: "env(safe-area-inset-top)",
        paddingBottom: "env(safe-area-inset-bottom)",
        paddingLeft: "env(safe-area-inset-left)",
        paddingRight: "env(safe-area-inset-right)",
      }}
    >
      {/* Desktop Sidebar */}
      <aside className="hidden lg:flex flex-col w-64 border-r border-border bg-card flex-shrink-0">
        <SidebarContent />
      </aside>

      {/* Mobile overlay */}
      {sidebarOpen && (
        <div className="fixed inset-0 z-50 lg:hidden">
          <div className="absolute inset-0 bg-black/40" onClick={() => setSidebarOpen(false)} />
          <aside
            className="absolute left-0 top-0 h-full w-72 bg-card border-r border-border shadow-xl z-10"
            style={{ paddingTop: "env(safe-area-inset-top)" }}
          >
            <div className="absolute top-4 right-4">
              <button onClick={() => setSidebarOpen(false)} className="p-2 rounded-lg hover:bg-muted">
                <X size={20} />
              </button>
            </div>
            <SidebarContent />
          </aside>
        </div>
      )}

      {/* Main */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* Mobile Header */}
        <header className="lg:hidden flex items-center justify-between px-4 py-3 border-b border-border bg-card">
          <button onClick={() => setSidebarOpen(true)} className="p-2 rounded-lg hover:bg-muted" data-testid="mobile-menu-btn">
            <Menu size={22} />
          </button>
          <div className="flex items-center gap-2">
            <div className="w-7 h-7 bg-primary rounded-lg flex items-center justify-center">
              <span className="text-white font-bold text-xs">B</span>
            </div>
            <span className="font-bold text-foreground font-['Outfit']">Bahi Khata</span>
          </div>
          <IllakaSwitcher compact />
        </header>
        {/* Desktop Top-Right Bar */}
        <div className="hidden lg:flex items-center justify-end px-6 py-2.5 border-b border-border bg-card/60 backdrop-blur-sm">
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <span>Working Illaka:</span>
            <IllakaSwitcher />
          </div>
        </div>
        <main className="flex-1 overflow-auto pb-16">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
