import { createContext, useContext, useState, useEffect } from "react";
import axios from "axios";
import { useAuth } from "./AuthContext";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const STORAGE_KEY = "bk_illaka_sel";

const IllakaContext = createContext(null);

export function IllakaProvider({ children }) {
  const { user, loading } = useAuth();
  // undefined = not selected yet, null = "All Illakas", {id,name} = specific
  const [selectedIllaka, setSelectedIllakaState] = useState(undefined);
  const [eligibleIllakas, setEligibleIllakas] = useState([]);

  useEffect(() => {
    // Wait for auth to finish loading before touching sessionStorage
    if (loading) return;
    if (!user) {
      sessionStorage.removeItem(STORAGE_KEY);
      setSelectedIllakaState(undefined);
      setEligibleIllakas([]);
      return;
    }
    // Restore from sessionStorage if same user
    try {
      const raw = sessionStorage.getItem(STORAGE_KEY);
      if (raw) {
        const parsed = JSON.parse(raw);
        if (parsed.userId === user.id) {
          setSelectedIllakaState(parsed.illaka);
        } else {
          sessionStorage.removeItem(STORAGE_KEY);
          setSelectedIllakaState(undefined);
        }
      } else {
        setSelectedIllakaState(undefined);
      }
    } catch {
      setSelectedIllakaState(undefined);
    }
    // Fetch eligible illakas
    axios
      .get(`${API}/illakas`, { withCredentials: true })
      .then((r) => setEligibleIllakas(r.data || []))
      .catch(() => {});
  }, [user?.id, loading]);

  const setSelectedIllaka = (illaka) => {
    setSelectedIllakaState(illaka);
    if (user) {
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify({ userId: user.id, illaka }));
    }
  };

  const resetIllaka = () => {
    sessionStorage.removeItem(STORAGE_KEY);
    setSelectedIllakaState(undefined);
  };

  return (
    <IllakaContext.Provider
      value={{
        eligibleIllakas,
        selectedIllaka,
        setSelectedIllaka,
        resetIllaka,
        illakaReady: selectedIllaka !== undefined,
      }}
    >
      {children}
    </IllakaContext.Provider>
  );
}

export function useIllaka() {
  return useContext(IllakaContext);
}
