import { Outlet, NavLink, useNavigate } from "react-router-dom";
import { useAuth } from "./AuthContext";
import {
  LayoutDashboard, UserPlus, Users, Settings, LogOut, Menu, X, FileText
} from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

const NAV_ITEMS = [
  { to: "/", icon: LayoutDashboard, label: "Dashboard", labelHi: "डैशबोर्ड" },
  { to: "/kyc/new", icon: UserPlus, label: "New KYC", labelHi: "नया KYC" },
  { to: "/clients", icon: FileText, label: "Clients", labelHi: "ग्राहक" },
];

const ADMIN_ITEMS = [
  { to: "/users", icon: Users, label: "Users", labelHi: "उपयोगकर्ता" },
];

export default function Layout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [sidebarOpen, setSidebarOpen] = useState(false);

  const handleLogout = async () => {
    await logout();
    toast.success("Logged out successfully");
    navigate("/login");
  };

  const navItems = [
    ...NAV_ITEMS,
    ...(user?.role === "admin" ? ADMIN_ITEMS : []),
  ];

  const roleLabel = {
    admin: "Administrator",
    branch_manager: "Branch Manager",
    field_officer: "Field Officer",
  }[user?.role] || user?.role;

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
            <p className="text-xs text-muted-foreground">NBFC-MFI Platform</p>
          </div>
        </div>
      </div>

      {/* Nav */}
      <nav className="flex-1 p-4 space-y-1" data-testid="sidebar-nav">
        {navItems.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.to === "/"}
            onClick={() => setSidebarOpen(false)}
            className={({ isActive }) =>
              `flex items-center gap-3 px-4 py-3 rounded-lg transition-all duration-200 group ${
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
        <div className="flex items-center gap-3 px-2 py-2 mb-2">
          <div className="w-9 h-9 bg-primary/15 rounded-full flex items-center justify-center">
            <span className="text-primary font-bold text-sm">
              {user?.name?.charAt(0)?.toUpperCase()}
            </span>
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-semibold text-foreground truncate">{user?.name}</p>
            <p className="text-xs text-muted-foreground">{roleLabel}</p>
          </div>
        </div>
        <button
          onClick={handleLogout}
          data-testid="logout-btn"
          className="flex items-center gap-3 w-full px-4 py-3 rounded-lg text-destructive hover:bg-destructive/10 transition-colors duration-200"
        >
          <LogOut size={18} />
          <span className="text-sm font-semibold">Logout / लॉगआउट</span>
        </button>
      </div>
    </div>
  );

  return (
    <div className="flex h-screen bg-background overflow-hidden">
      {/* Desktop Sidebar */}
      <aside className="hidden lg:flex flex-col w-64 border-r border-border bg-card flex-shrink-0">
        <SidebarContent />
      </aside>

      {/* Mobile Sidebar Overlay */}
      {sidebarOpen && (
        <div className="fixed inset-0 z-50 lg:hidden">
          <div
            className="absolute inset-0 bg-black/40"
            onClick={() => setSidebarOpen(false)}
          />
          <aside className="absolute left-0 top-0 h-full w-72 bg-card border-r border-border shadow-xl z-10">
            <div className="absolute top-4 right-4">
              <button onClick={() => setSidebarOpen(false)} className="p-2 rounded-lg hover:bg-muted">
                <X size={20} />
              </button>
            </div>
            <SidebarContent />
          </aside>
        </div>
      )}

      {/* Main Content */}
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
          <div className="w-9 h-9 bg-primary/15 rounded-full flex items-center justify-center">
            <span className="text-primary font-bold text-xs">
              {user?.name?.charAt(0)?.toUpperCase()}
            </span>
          </div>
        </header>

        {/* Page Content */}
        <main className="flex-1 overflow-auto">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
