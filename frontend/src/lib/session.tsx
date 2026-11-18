"use client";

import { useRouter } from "next/navigation";
import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";

import { api, ApiError } from "./api";
import type { Campus, User } from "./types";

interface Session {
  user: User | null;
  campus: Campus | null;
  loading: boolean;
  refresh: () => Promise<void>;
  signOut: () => Promise<void>;
}

const Ctx = createContext<Session | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [campus, setCampus] = useState<Campus | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      const [me, c] = await Promise.all([api.auth.me(), api.campus()]);
      setUser(me);
      setCampus(c);
    } catch (e) {
      if (!(e instanceof ApiError && e.status === 401)) console.error(e);
      setUser(null);
      setCampus(null);
    } finally {
      setLoading(false);
    }
  }, []);

  const signOut = useCallback(async () => {
    await api.auth.logout();
    setUser(null);
    setCampus(null);
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  return <Ctx.Provider value={{ user, campus, loading, refresh, signOut }}>{children}</Ctx.Provider>;
}

export function useSession(): Session {
  const s = useContext(Ctx);
  if (!s) throw new Error("useSession must be used inside SessionProvider");
  return s;
}

/** Renders children only for signed-in users; sends everyone else to /login. */
export function RequireAuth({ children, staff = false }: { children: ReactNode; staff?: boolean }) {
  const { user, loading } = useSession();
  const router = useRouter();
  useEffect(() => {
    if (!loading && !user) {
      const next = typeof window !== "undefined" ? window.location.pathname + window.location.search : "/";
      router.replace(`/login?next=${encodeURIComponent(next)}`);
    }
  }, [loading, user, router]);
  if (loading || !user) return <p className="muted pad">Loading…</p>;
  if (staff && user.role === "member") {
    return <p className="pad">This page is for lost-and-found desk staff.</p>;
  }
  return <>{children}</>;
}
