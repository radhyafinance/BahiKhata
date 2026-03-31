import { createContext, useContext, useState, useEffect } from "react";
import axios from "axios";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const AuthContext = createContext(null);

// ── base64url helpers (WebAuthn binary ↔ string) ─────────────────────────────
function bufToBase64url(buf) {
  const bytes = new Uint8Array(buf);
  let str = "";
  for (const byte of bytes) str += String.fromCharCode(byte);
  return btoa(str).replace(/\+/g, "-").replace(/\//g, "_").replace(/=/g, "");
}

function base64urlToBuf(b64url) {
  const b64 = b64url.replace(/-/g, "+").replace(/_/g, "/");
  const padded = b64.padEnd(b64.length + ((4 - (b64.length % 4)) % 4), "=");
  const binary = atob(padded);
  const buf = new ArrayBuffer(binary.length);
  const view = new Uint8Array(buf);
  for (let i = 0; i < binary.length; i++) view[i] = binary.charCodeAt(i);
  return buf;
}

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    axios
      .get(`${API}/auth/me`, { withCredentials: true })
      .then((r) => setUser(r.data))
      .catch(() => setUser(null))
      .finally(() => setLoading(false));
  }, []);

  const login = async (phone, password) => {
    const { data } = await axios.post(
      `${API}/auth/login`,
      { phone, password },
      { withCredentials: true }
    );
    setUser(data);
    return data;
  };

  /** One-tap passkey login — no phone/password needed. */
  const passkeyLogin = async () => {
    // 1. Get authentication options (sets wauthn_session cookie)
    const { data: options } = await axios.post(
      `${API}/auth/passkey/auth-options`,
      {},
      { withCredentials: true }
    );

    // 2. Decode binary fields from base64url → ArrayBuffer
    const publicKey = {
      ...options,
      challenge: base64urlToBuf(options.challenge),
      allowCredentials: (options.allowCredentials || []).map((c) => ({
        ...c,
        id: base64urlToBuf(c.id),
      })),
    };

    // 3. Invoke browser authenticator (fingerprint / FaceID)
    let assertion;
    try {
      assertion = await navigator.credentials.get({ publicKey });
    } catch (err) {
      if (err.name === "NotAllowedError") throw new Error("Passkey login was cancelled or timed out.");
      if (err.name === "NotSupportedError" || err.name === "SecurityError")
        throw new Error("Passkey not supported on this device/browser. Please use your password.");
      throw new Error("Passkey login failed. Please use your password instead.");
    }
    if (!assertion) throw new Error("Passkey login cancelled.");

    // 4. Encode response back to base64url for the backend
    const credential = {
      id: assertion.id,
      rawId: bufToBase64url(assertion.rawId),
      type: assertion.type,
      response: {
        clientDataJSON: bufToBase64url(assertion.response.clientDataJSON),
        authenticatorData: bufToBase64url(assertion.response.authenticatorData),
        signature: bufToBase64url(assertion.response.signature),
        userHandle: assertion.response.userHandle
          ? bufToBase64url(assertion.response.userHandle)
          : null,
      },
    };

    // 5. Verify on backend → sets access_token cookie
    const { data } = await axios.post(
      `${API}/auth/passkey/auth-verify`,
      credential,
      { withCredentials: true }
    );
    setUser(data);
    return data;
  };

  /** Register current device as a passkey (must be already logged in). */
  const registerPasskey = async (passkeyName = "Passkey") => {
    // 1. Get registration options
    const { data: options } = await axios.post(
      `${API}/auth/passkey/register-options`,
      {},
      { withCredentials: true }
    );

    // 2. Decode binary fields
    const publicKey = {
      ...options,
      challenge: base64urlToBuf(options.challenge),
      user: {
        ...options.user,
        id: base64urlToBuf(options.user.id),
      },
      excludeCredentials: (options.excludeCredentials || []).map((c) => ({
        ...c,
        id: base64urlToBuf(c.id),
      })),
    };

    // 3. Create credential with browser
    let credential;
    try {
      credential = await navigator.credentials.create({ publicKey });
    } catch (err) {
      if (err.name === "NotAllowedError") throw new Error("Passkey registration was cancelled.");
      throw err;
    }
    if (!credential) throw new Error("Passkey registration cancelled.");

    // 4. Encode for backend
    const attestation = {
      id: credential.id,
      rawId: bufToBase64url(credential.rawId),
      type: credential.type,
      passkeyName,
      response: {
        clientDataJSON: bufToBase64url(credential.response.clientDataJSON),
        attestationObject: bufToBase64url(credential.response.attestationObject),
        transports: credential.response.getTransports
          ? credential.response.getTransports()
          : [],
      },
    };

    // 5. Verify + persist
    const { data } = await axios.post(
      `${API}/auth/passkey/register-verify`,
      attestation,
      { withCredentials: true }
    );

    // Reflect the change locally so Login page updates
    setUser((prev) => (prev ? { ...prev, has_passkeys: true } : prev));
    return data;
  };

  const logout = async () => {
    await axios.post(`${API}/auth/logout`, {}, { withCredentials: true });
    setUser(null);
  };

  return (
    <AuthContext.Provider
      value={{ user, setUser, loading, login, logout, passkeyLogin, registerPasskey }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
