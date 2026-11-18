"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";

import { holderText, ItemTag } from "@/components/ItemTag";
import { Empty, ErrorNote, StatusPill, useLoad } from "@/components/ui";
import { api } from "@/lib/api";
import { ago, when } from "@/lib/format";
import { RequireAuth } from "@/lib/session";
import type { FoundItem } from "@/lib/types";

type Tab = "recent" | "claims" | "finders" | "expired" | "search";

const TABS: [Tab, string][] = [
  ["recent", "Recently handed in"], ["claims", "Claims"], ["finders", "With finders"],
  ["expired", "Unclaimed"], ["search", "Search"],
];

function Stats() {
  const { data } = useLoad(() => api.desk.overview());
  if (!data) return null;
  const stat = (n: number | string, label: string) => (
    <div className="stat"><b>{n}</b><span className="small muted">{label}</span></div>
  );
  return (
    <div className="stats">
      {stat(data.pending_claims, "claims to review")}
      {stat(data.held_by_finders, "items still with finders")}
      {stat(data.awaiting_decision, "unclaimed after 60 days")}
      {stat(`${Math.round(data.return_rate_last_30d * 100)}%`, "returned in the last 30 days")}
    </div>
  );
}

function Recent() {
  const [category, setCategory] = useState("");
  const [extra, setExtra] = useState<FoundItem[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const { data, error } = useLoad(async () => {
    const page = await api.items.browse({ category: category || undefined });
    setExtra([]);
    setCursor(page.next_cursor);
    return page.items;
  }, [category]);
  const more = async () => {
    if (!cursor) return;
    const page = await api.items.browse({ category: category || undefined, cursor });
    setExtra((x) => [...x, ...page.items]);
    setCursor(page.next_cursor);
  };
  const items = [...(data ?? []), ...extra];

  return (
    <div className="stack">
      <label className="row small">
        <span className="muted">Show</span>
        <select value={category} onChange={(e) => setCategory(e.target.value)} style={{ width: "auto" }}>
          <option value="">Everything</option>
          <option value="electronics">Electronics</option>
          <option value="cards">Cards and IDs</option>
          <option value="wallet">Wallets</option>
          <option value="keys">Keys</option>
          <option value="bags">Bags</option>
          <option value="clothing">Clothing</option>
          <option value="bottles">Bottles</option>
          <option value="accessories">Accessories</option>
          <option value="stationery">Books and stationery</option>
        </select>
      </label>
      <ErrorNote error={error} />
      {!data ? <p className="muted">Loading…</p> : items.length === 0 ? (
        <Empty title="Nothing waiting for an owner" />
      ) : (
        <div className="tags">
          {items.map((it) => <ItemTag key={it.id} item={it} href={`/items/${it.id}`} />)}
        </div>
      )}
      {cursor && <button className="btn secondary" onClick={() => void more()}>Show more</button>}
    </div>
  );
}

function Claims() {
  const { data, error } = useLoad(() => api.claims.review());
  if (error) return <ErrorNote error={error} />;
  if (!data) return <p className="muted">Loading…</p>;
  if (!data.length) return <Empty title="No claims to review" />;
  return (
    <ul className="list">
      {data.map((c) => (
        <li key={c.id} className="spread">
          <div>
            <Link href={`/items/${c.found_item_id}`}><b>{c.item_title}</b></Link>
            <div className="small muted">{c.claimant.display_name}, {ago(c.created_at)}</div>
          </div>
          {c.status === "approved" ? <span className="pill good">Awaiting pickup</span> : (
            <span className={`pill ${c.proof_strength === "strong" ? "good" : c.proof_strength === "weak" ? "bad" : "warn"}`}>
              {c.proof_strength ? `${c.proof_strength} proof` : "No private detail"}
            </span>
          )}
        </li>
      ))}
    </ul>
  );
}

function Rows({ items, mode, onAction }: { items: FoundItem[]; mode: Tab; onAction: () => void }) {
  const [error, setError] = useState<unknown>(null);
  const run = async (fn: () => Promise<unknown>) => {
    setError(null);
    try { await fn(); onAction(); } catch (e) { setError(e); }
  };
  if (!items.length) return <Empty title="Nothing here" />;
  return (
    <>
      <ErrorNote error={error} />
      <ul className="list">
        {items.map((i) => (
          <li key={i.id} className="spread">
            <div>
              <Link href={`/items/${i.id}`}><b>{i.title}</b></Link>
              <div className="small muted">
                {i.location?.name ?? "Campus"}, {when(i.found_at)}. {holderText(i)}.
              </div>
            </div>
            <div className="row">
              {mode === "search" && <StatusPill status={i.status} />}
              {mode === "finders" && (
                <button className="btn secondary" onClick={() => void run(() => api.desk.receive(i.id))}>
                  Mark received
                </button>
              )}
              {mode === "expired" && (
                <>
                  <button className="btn secondary" onClick={() => void run(() => api.desk.close(i.id, "donate"))}>Donate</button>
                  <button className="btn secondary" onClick={() => void run(() => api.desk.close(i.id, "dispose"))}>Dispose</button>
                  <button className="btn quiet" onClick={() => void run(() => api.desk.close(i.id, "extend"))}>Keep 30 days</button>
                </>
              )}
            </div>
          </li>
        ))}
      </ul>
    </>
  );
}

function ItemList({ mode }: { mode: "finders" | "expired" | "search" }) {
  const [q, setQ] = useState("");
  const [query, setQuery] = useState("");
  const params = mode === "finders" ? { status: "available", holder_type: "finder" }
    : mode === "expired" ? { status: "expired" } : { q: query };
  const { data, error, reload } = useLoad(() => api.desk.items(params), [mode, query]);
  return (
    <div className="stack">
      {mode === "search" && (
        <form className="row" onSubmit={(e) => { e.preventDefault(); setQuery(q); }}>
          <label className="sr-only" htmlFor="q">Search every item</label>
          <input id="q" value={q} onChange={(e) => setQ(e.target.value)}
                 placeholder="Search every item, including returned" style={{ maxWidth: 380 }} />
          <button className="btn secondary">Search</button>
        </form>
      )}
      {mode === "finders" && <p className="small muted">Mark an item received when its finder drops it off.</p>}
      <ErrorNote error={error} />
      {data ? <Rows items={data.items} mode={mode} onAction={() => void reload()} />
        : <p className="muted">Loading…</p>}
    </div>
  );
}

function Desk() {
  const sp = useSearchParams();
  const initial: Tab = sp.get("status") === "expired" ? "expired" : sp.get("claim") ? "claims" : "recent";
  const [tab, setTab] = useState<Tab>(initial);
  return (
    <div className="pad stack">
      <div className="spread">
        <h1>Desk</h1>
        <Link className="btn" href="/found/new">Log a handed-in item</Link>
      </div>
      <Stats />
      <div className="tabs" role="tablist">
        {TABS.map(([t, label]) => (
          <button key={t} role="tab" aria-selected={tab === t} onClick={() => setTab(t)}>{label}</button>
        ))}
      </div>
      <div role="tabpanel">
        {tab === "recent" ? <Recent /> : tab === "claims" ? <Claims /> : <ItemList key={tab} mode={tab} />}
      </div>
    </div>
  );
}

export default function Page() {
  return <RequireAuth staff><Suspense><Desk /></Suspense></RequireAuth>;
}
