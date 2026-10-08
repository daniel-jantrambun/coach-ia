import { createContext, type ReactNode, useCallback, useContext, useEffect, useState } from "react";
import { ApiError, api, type NewUser, setUnauthorizedHandler, type User } from "./api";

type AuthState = {
  user: User | null;
  loading: boolean;
  /** Aucun compte n'existe encore : l'app propose de créer le compte administrateur. */
  needsSetup: boolean;
  setup: (account: NewUser) => Promise<void>;
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  setUser: (user: User) => void;
};

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUserState] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [needsSetup, setNeedsSetup] = useState(false);

  useEffect(() => {
    // Session expirée ou fermée ailleurs : on revient à l'écran de connexion.
    setUnauthorizedHandler(() => setUserState(null));
    api
      .me()
      .then(setUserState)
      .catch(async (e) => {
        if (!(e instanceof ApiError && e.status === 401)) console.error(e);
        // Pas connecté : est-ce une installation toute neuve ?
        setNeedsSetup((await api.setupStatus().catch(() => ({ needs_setup: false }))).needs_setup);
      })
      .finally(() => setLoading(false));
  }, []);

  const setup = useCallback(async (account: NewUser) => {
    setUserState(await api.setup(account));
    setNeedsSetup(false);
  }, []);

  const login = useCallback(async (username: string, password: string) => {
    setUserState(await api.login(username, password));
  }, []);

  const logout = useCallback(async () => {
    await api.logout().catch(() => {});
    setUserState(null);
  }, []);

  return (
    <AuthContext.Provider value={{ user, loading, needsSetup, setup, login, logout, setUser: setUserState }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth hors de AuthProvider");
  return ctx;
}

/** Utilisateur connecté (les pages protégées ne sont rendues que si `user` existe). */
export function useUser(): User {
  const { user } = useAuth();
  if (!user) throw new Error("Aucun utilisateur connecté");
  return user;
}
