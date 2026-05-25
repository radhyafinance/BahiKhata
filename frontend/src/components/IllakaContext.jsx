import { createContext, useContext, useState, useEffect, useCallback } from "react";
import axios from "axios";
import { useAuth } from "./AuthContext";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const STORAGE_KEY = "bk_illaka_sel";
const MAALIK_KEY  = "bk_maalik_sel";

const IllakaContext = createContext(null);

export function IllakaProvider({ children }) {
  const { user, loading } = useAuth();
  // undefined = not selected yet, null = "All Illakas", {id,name} = specific
  const [selectedIllaka, setSelectedIllakaState] = useState(undefined);
  const [eligibleIllakas, setEligibleIllakas] = useState([]);
  const [maaliks, setMaaliks] = useState([]);
  const [selectedMaalik, setSelectedMaalikState] = useState(null);

  const fetchIllakas = useCallback(() => {
    axios
      .get(`${API}/illakas`, { withCredentials: true })
      .then((r) => setEligibleIllakas(r.data || []))
      .catch(() => {});
  }, []);

  useEffect(() => {
    // Wait for auth to finish loading before touching sessionStorage
    if (loading) return;
    if (!user) {
      sessionStorage.removeItem(STORAGE_KEY);
      sessionStorage.removeItem(MAALIK_KEY);
      setSelectedIllakaState(undefined);
      setSelectedMaalikState(null);
      setEligibleIllakas([]);
      setMaaliks([]);
      return;
    }
    // Restore illaka from sessionStorage if same user
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
    // Restore maalik filter from sessionStorage (admin only)
    if (user.role === "admin") {
      try {
        const rawM = sessionStorage.getItem(MAALIK_KEY);
        if (rawM) {
          const parsedM = JSON.parse(rawM);
          if (parsedM.userId === user.id) setSelectedMaalikState(parsedM.maalik);
        }
      } catch { /* ignore */ }
    }
    // Fetch eligible illakas
    fetchIllakas();
    // Fetch maaliks list for admin
    if (user.role === "admin") {
      axios.get(`${API}/users`, { withCredentials: true })
        .then(r => setMaaliks((r.data || []).filter(u => u.role === "maalik")))
        .catch(() => {});
    }
  }, [user?.id, loading, fetchIllakas]);

  // Illakas filtered by selected Maalik (admin only)
  const filteredIllakas = selectedMaalik
    ? eligibleIllakas.filter(ill =>
        ill.maalik_id === selectedMaalik.id ||
        (selectedMaalik.illaka_ids || []).includes(ill.id)
      )
    : eligibleIllakas;

  const setSelectedIllaka = (illaka) => {
    setSelectedIllakaState(illaka);
    if (user) {
      // Store only essential fields — not the full object — to minimise sessionStorage footprint
      const slim = illaka ? { id: illaka.id, name: illaka.name } : null;
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify({ userId: user.id, illaka: slim }));
    }
  };

  const setSelectedMaalik = (maalik) => {
    setSelectedMaalikState(maalik);
    if (user) {
      // Store only essential fields
      const slim = maalik ? { id: maalik.id, name: maalik.name } : null;
      sessionStorage.setItem(MAALIK_KEY, JSON.stringify({ userId: user.id, maalik: slim }));
    }
    // Reset illaka if it's no longer in the filtered list
    if (maalik && selectedIllaka?.id) {
      const validIds = eligibleIllakas
        .filter(ill => ill.maalik_id === maalik.id || (maalik.illaka_ids || []).includes(ill.id))
        .map(ill => ill.id);
      if (!validIds.includes(selectedIllaka.id)) {
        resetIllaka();
      }
    }
  };

  const resetIllaka = () => {
    sessionStorage.removeItem(STORAGE_KEY);
    setSelectedIllakaState(undefined);
    // Re-fetch the illaka list so any newly created illakas appear
    fetchIllakas();
  };

  return (
    <IllakaContext.Provider
      value={{
        eligibleIllakas,
        filteredIllakas,
        selectedIllaka,
        setSelectedIllaka,
        resetIllaka,
        illakaReady: selectedIllaka !== undefined,
        maaliks,
        selectedMaalik,
        setSelectedMaalik,
      }}
    >
      {children}
    </IllakaContext.Provider>
  );
}

export function useIllaka() {
  return useContext(IllakaContext);
}
