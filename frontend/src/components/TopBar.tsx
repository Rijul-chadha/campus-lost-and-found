"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

import { api } from "@/lib/api";
import { useSession } from "@/lib/session";

export function TopBar() {
  const { user, signOut } = useSession();
  const path = usePathname();
  const [unread, setUnread] = useState(0);

  useEffect(() => {
    if (!user) return;
    let alive = true;
    const tick = () => api.notifications.unread().then((r) => alive && setUnread(r.unread))
      .catch(() => undefined);
    void tick();
    // Polling is fine at campus scale; swap for SSE/WebSocket if traffic grows.
    const id = setInterval(tick, 30_000);
    return () => { alive = false; clearInterval(id); };
  }, [user, path]);

  const link = (href: string, label: string) => (
    <Link href={href} aria-current={path === href ? "page" : undefined}>{label}</Link>
  );

  return (
    <header className="topbar">
      <div className="wrap">
        <Link href="/" className="brand"><span className="brand-mark" aria-hidden />Campus Lost <span className="brand-amp">&amp; Found</span></Link>
        {user ? (
          <nav className="nav" aria-label="Main">
            {link("/found/new", "Report found")}
            {link("/lost", "Find my item")}
            {link("/me", "My items")}
            {user.role !== "member" && link("/desk", "Desk")}
            <Link href="/notifications" className="bell"
                  aria-label={`Notifications${unread ? `, ${unread} unread` : ""}`}>
              Alerts{unread > 0 && <span className="count">{unread > 99 ? "99+" : unread}</span>}
            </Link>
            <button className="btn quiet" onClick={() => void signOut()}>Sign out</button>
          </nav>
        ) : (
          <nav className="nav" aria-label="Main">{link("/login", "Sign in")}</nav>
        )}
      </div>
    </header>
  );
}
