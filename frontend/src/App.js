import "@/App.css";
import "./index.css";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { Toaster } from "sonner";
import { AuthProvider, useAuth } from "./components/AuthContext";
import { IllakaProvider, useIllaka } from "./components/IllakaContext";
import Login from "./components/Login";
import Layout from "./components/Layout";
import Dashboard from "./components/Dashboard";
import KYCForm from "./components/KYCForm";
import ClientList from "./components/ClientList";
import ClientDetail from "./components/ClientDetail";
import UserManagement from "./components/UserManagement";
import IllakaManagement from "./components/IllakaManagement";
import LoanList from "./components/LoanList";
import LoanForm from "./components/LoanForm";
import LoanDetail from "./components/LoanDetail";
import CollectionSheet from "./components/CollectionSheet";
import IllakaSelector from "./components/IllakaSelector";

const ProtectedRoute = ({ children, roles }) => {
  const { user, loading } = useAuth();
  const { illakaReady } = useIllaka();
  if (loading) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <div className="flex flex-col items-center gap-3">
          <div className="w-10 h-10 border-4 border-primary border-t-transparent rounded-full animate-spin" />
          <p className="text-muted-foreground text-sm">Loading...</p>
        </div>
      </div>
    );
  }
  if (!user) return <Navigate to="/login" replace />;
  if (!illakaReady) return <IllakaSelector />;
  if (roles && !roles.includes(user.role)) return <Navigate to="/" replace />;
  return children;
};

function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <IllakaProvider>
          <Toaster position="top-right" richColors />
          <Routes>
            <Route path="/login" element={<Login />} />
            <Route
              path="/"
              element={
                <ProtectedRoute>
                  <Layout />
                </ProtectedRoute>
              }
            >
              <Route index element={<Dashboard />} />
              <Route path="kyc/new" element={<KYCForm />} />
              <Route path="kyc/:id/edit" element={<KYCForm />} />
              <Route path="clients" element={<ClientList />} />
              <Route path="clients/:id" element={<ClientDetail />} />
              <Route
                path="illakas"
                element={
                  <ProtectedRoute roles={["admin", "maalik"]}>
                    <IllakaManagement />
                  </ProtectedRoute>
                }
              />
              <Route
                path="users"
                element={
                  <ProtectedRoute roles={["admin", "maalik"]}>
                    <UserManagement />
                  </ProtectedRoute>
                }
              />
              <Route path="loans" element={<LoanList />} />
              <Route path="loans/new" element={<ProtectedRoute roles={["muneem", "sipahi"]}><LoanForm /></ProtectedRoute>} />
              <Route path="loans/:id" element={<LoanDetail />} />
              <Route path="loans/:id/edit" element={<ProtectedRoute roles={["admin", "maalik", "muneem", "sipahi"]}><LoanForm /></ProtectedRoute>} />
              <Route path="collections" element={<CollectionSheet />} />
            </Route>
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </IllakaProvider>
      </AuthProvider>
    </BrowserRouter>
  );
}

export default App;
