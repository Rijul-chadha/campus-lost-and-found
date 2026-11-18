"use client";

import Link from "next/link";
import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";

import { ColorDots, ItemTag } from "@/components/ItemTag";
import { ErrorNote } from "@/components/ui";
import { api } from "@/lib/api";
import { typeLabel, when } from "@/lib/format";
import { RequireAuth } from "@/lib/session";
import type { ChatMessage, ChatOut, WatchDetail } from "@/lib/types";

const GREETING: ChatMessage = {
  role: "assistant",
  content: "What did you lose? Say what it looks like, and where and when you last had it.",
};

function Assistant() {
  const [messages, setMessages] = useState<ChatMessage[]>([GREETING]);
  const [draft, setDraft] = useState("");
  const [result, setResult] = useState<ChatOut | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [inputError, setInputError] = useState<string | null>(null);
  const [watch, setWatch] = useState<WatchDetail | null>(null);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => { endRef.current?.scrollIntoView({ block: "nearest" }); }, [messages, busy]);

  const send = async (e?: FormEvent) => {
    e?.preventDefault();
    const text = draft.trim();
    if (!text) return setInputError("Type a description first.");
    setInputError(null); setError(null);
    // The greeting is UI copy, not conversation: don't send it to the API.
    const convo = [...messages.filter((m) => m !== GREETING), { role: "user" as const, content: text }];
    setMessages([GREETING, ...convo]);
    setDraft("");
    setBusy(true);
    try {
      const out = await api.assistant.chat(convo.slice(-20));
      setResult(out);
      setMessages((m) => [...m, { role: "assistant", content: out.reply }]);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  };

  const onKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); void send(); }
  };

  const saveWatch = async () => {
    if (!result?.watch_draft) return;
    setBusy(true); setError(null);
    try { setWatch(await api.watches.create(result.watch_draft)); }
    catch (err) { setError(err); } finally { setBusy(false); }
  };

  const ex = result?.extracted;
  return (
    <div className="pad">
      <h1>Find my item</h1>
      <div className="chat">
        <div>
          <div className="thread" aria-live="polite">
            {messages.map((m, i) => (
              <div key={i} className={`bubble ${m.role}`}>{m.content}</div>
            ))}
            {busy && <div className="bubble assistant muted">Searching…</div>}
            <div ref={endRef} />
          </div>

          {result && result.matches.length > 0 && (
            <section className="stack" style={{ marginTop: "1.5rem" }} aria-labelledby="matches">
              <h2 id="matches">Possible matches</h2>
              <div className="tags">
                {result.matches.map((m) => (
                  <ItemTag key={m.item.id} item={m.item} score={m.score} reasons={m.reasons}
                           href={`/items/${m.item.id}${watch ? `?watch=${watch.id}` : ""}`} />
                ))}
              </div>
            </section>
          )}

          <form className="composer" onSubmit={send}>
            <label className="sr-only" htmlFor="msg">Describe your item</label>
            <textarea id="msg" value={draft} onChange={(e) => { setDraft(e.target.value); setInputError(null); }}
                      onKeyDown={onKey} maxLength={1000} disabled={busy}
                      placeholder="e.g. black Herschel backpack, left it in the library yesterday afternoon" />
            <button className="btn" disabled={busy}>Send</button>
          </form>
          {inputError && <p className="small" style={{ color: "var(--bad)" }}>{inputError}</p>}
          <ErrorNote error={error} />
        </div>

        <aside className="panel stack" aria-labelledby="understood">
          <h3 id="understood">Your description</h3>
          {!ex ? <p className="muted small">Fills in as you describe it.</p> : (
            <dl className="understood">
              <dt>Item</dt>
              <dd className={ex.item_type ? "" : "unknown"}>{ex.item_type ? typeLabel(ex.item_type) : "Not sure yet"}</dd>
              <dt>Colour</dt>
              <dd className={ex.colors.length ? "" : "unknown"}>
                {ex.colors.length ? <span className="row"><ColorDots colors={ex.colors} />{ex.colors.join(", ")}</span> : "Not mentioned"}
              </dd>
              {ex.brand && (<><dt>Brand</dt><dd>{ex.brand}</dd></>)}
              <dt>Where</dt>
              <dd className={ex.location_name ? "" : "unknown"}>{ex.location_name ?? "Anywhere on campus"}</dd>
              <dt>When</dt>
              <dd className={ex.time_is_guess ? "unknown" : ""}>
                {ex.time_is_guess ? "In the last week" : `${when(ex.lost_from)} – ${when(ex.lost_to)}`}
              </dd>
            </dl>
          )}

          {watch ? (
            <div className="notice good">
              <b>Saved.</b> We&apos;ll alert you when a similar item is reported.{" "}
              <Link href={`/me/watches/${watch.id}`}>View</Link>
            </div>
          ) : result?.watch_draft ? (
            <div className="stack">
              <p className="small muted">Not here yet? We&apos;ll check every new item for 60 days
                and alert you.</p>
              <button className="btn" onClick={() => void saveWatch()} disabled={busy}>
                Notify me if it turns up
              </button>
            </div>
          ) : null}
          {result && !result.used_llm && (
            <p className="small muted">Basic search is on; the AI assistant is unavailable.</p>
          )}
        </aside>
      </div>
    </div>
  );
}

export default function Page() {
  return <RequireAuth><Assistant /></RequireAuth>;
}
