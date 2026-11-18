"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState, type FormEvent } from "react";

import { ErrorNote } from "@/components/ui";
import { api } from "@/lib/api";
import { useSession } from "@/lib/session";

function Login() {
  const router = useRouter();
  const params = useSearchParams();
  const next = params.get("next") || "/";
  const { refresh } = useSession();
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [sent, setSent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  const send = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true); setError(null);
    try {
      await api.auth.requestCode(email.trim());
      setSent(true);
    } catch (err) { setError(err); } finally { setBusy(false); }
  };

  const verify = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true); setError(null);
    try {
      await api.auth.verify(email.trim(), code.trim());
      await refresh();
      // Only follow same-site relative paths (open-redirect guard).
      router.replace(next.startsWith("/") && !next.startsWith("//") ? next : "/");
    } catch (err) { setError(err); } finally { setBusy(false); }
  };

  return (
    <section className="pad" style={{ maxWidth: 460 }}>
      <h1>Sign in</h1>
      {!sent ? (
        <form onSubmit={send} className="stack">
          <p className="muted">Use your campus email. We&apos;ll send you a 6-digit code — no password needed.</p>
          <label className="field">
            <span>Campus email</span>
            <input type="email" required autoComplete="email" value={email}
                   onChange={(e) => setEmail(e.target.value)} placeholder="you@campus.ca" />
          </label>
          <ErrorNote error={error} />
          <button className="btn" disabled={busy}>{busy ? "Sending…" : "Send code"}</button>
        </form>
      ) : (
        <form onSubmit={verify} className="stack">
          <p className="muted">We sent a code to <b>{email}</b>. It expires in 10 minutes.</p>
          <label className="field">
            <span>6-digit code</span>
            <input inputMode="numeric" pattern="\d{6}" maxLength={6} required autoFocus
                   autoComplete="one-time-code" value={code}
                   onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))} />
          </label>
          <ErrorNote error={error} />
          <div className="row">
            <button className="btn" disabled={busy || code.length !== 6}>
              {busy ? "Signing in…" : "Sign in"}
            </button>
            <button type="button" className="btn quiet" onClick={() => { setSent(false); setCode(""); }}>
              Use a different email
            </button>
          </div>
        </form>
      )}
    </section>
  );
}

export default function LoginPage() {
  return <Suspense><Login /></Suspense>;
}
