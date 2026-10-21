import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import * as authService from '../services/authService';
import { getToken, setToken } from '../services/apiClient';
import { OFBIZ_VIEWER } from '../lib/target';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  // The OFBiz viewer is read-only and has no server: nobody signs in there.
  const [checking, setChecking] = useState(() => !OFBIZ_VIEWER && Boolean(getToken()));

  useEffect(() => {
    if (OFBIZ_VIEWER || !getToken()) {
      return;
    }
    authService
      .getCurrentUser()
      .then(setUser)
      .catch(() => setToken(null))
      .finally(() => setChecking(false));
  }, []);

  const startSession = useCallback(({ token, user: signedIn }) => {
    setToken(token);
    setUser(signedIn);
    return signedIn;
  }, []);

  const value = useMemo(
    () => ({
      user,
      checking,
      login: (email, password) => authService.login(email, password).then(startSession),
      register: (email, password, displayName) =>
        authService.register(email, password, displayName).then(startSession),
      resetPassword: (token, password) => authService.resetPassword(token, password).then(startSession),
      logout: () => {
        authService.logout();
        setToken(null);
        setUser(null);
      },
      // Signs out every device; this one only once the server has confirmed it.
      logoutEverywhere: () =>
        authService.logoutEverywhere().then(() => {
          setToken(null);
          setUser(null);
        }),
    }),
    [user, checking, startSession]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

// eslint-disable-next-line react-refresh/only-export-components
export function useAuth() {
  return useContext(AuthContext);
}
