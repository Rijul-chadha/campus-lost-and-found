"use client";

import Link from "next/link";
import { useState } from "react";

import { ColorDots, ItemTag } from "@/components/ItemTag";
import { Empty, ErrorNote, useLoad } from "@/components/ui";
import { api } from "@/lib/api";
import { ago } from "@/lib/format";
import { RequireAuth } from "@/lib/session";

type Tab = "watches" | "found" | "claims";

const CLAIM_LABEL: Record<string, string> = {
  pending: "Waiting for review", approved: "Approved", rejected: "Not approved",
  completed: "Returned to you", cancelled: "Withdrawn",
};

function Watches() {
  const { data, error } = useLoad(() => api.watches.list());
  if (error) return <ErrorNote error={error} />;
  if (!data) return <p className="muted">Loading…</p>;
  if (!data.items.length) return (
    <Empty title="Nothing saved">
      <p>Describe what you lost and we&apos;ll alert you when it turns up.</p>
      <Link className="btn" href="/lost">Find my item</Link>
    </Empty>
  );
  return (
    <ul className="list">
      {data.items.map((w) => (
        <li key={w.id} className="spread">
          <div>
            <Link href={`/me/watches/${w.id}`}><b>{w.title}</b></Link>
            <div className="row small muted"><ColorDots colors={w.colors} />
              {w.location ? w.location.name : "Anywhere on campus"}, saved {ago(w.created_at)}</div>
          </div>
          <span className={`pill ${w.status === "open" ? "" : w.status === "resolved" ? "good" : "warn"}`}>
            {w.status === "open" ? `${w.match_count} possible match${w.match_count === 1 ? "" : "es"}` : w.status}
          </span>
        </li>
      ))}
    </ul>
  );
}

function Found() {
  const { data, error } = useLoad(() => api.items.mine());
  if (error) return <ErrorNote error={error} />;
  if (!data) return <p className="muted">Loading…</p>;
  if (!data.items.length) return (
    <Empty title="Nothing reported yet">
      <Link className="btn" href="/found/new">Report found item</Link>
    </Empty>
  );
  return (
    <>
      <p><Link href="/claims/review">Review claims</Link></p>
      <div className="tags">{data.items.map((i) => <ItemTag key={i.id} item={i} href={`/items/${i.id}`} />)}</div>
    </>
  );
}

function Claims() {
  const { data, error } = useLoad(() => api.claims.mine());
  if (error) return <ErrorNote error={error} />;
  if (!data) return <p className="muted">Loading…</p>;
  if (!data.length) return <Empty title="No claims yet"><p>Items you claim appear here.</p></Empty>;
  return (
    <ul className="list">
      {data.map((c) => (
        <li key={c.id} className="stack">
          <div className="spread">
            <Link href={`/items/${c.found_item_id}`}><b>{c.item_title}</b></Link>
            <span className={`pill ${c.status === "approved" || c.status === "completed" ? "good" : c.status === "rejected" ? "bad" : ""}`}>
              {CLAIM_LABEL[c.status]}
            </span>
          </div>
          {c.pickup_instructions && <p className="notice good">Pickup: {c.pickup_instructions}</p>}
          {c.decision_note && <p className="small muted">{c.decision_note}</p>}
          {(c.status === "pending" || c.status === "approved") && (
            <button className="btn quiet" style={{ alignSelf: "flex-start" }}
                    onClick={() => void api.claims.cancel(c.id).then(() => location.reload())}>
              Withdraw claim
            </button>
          )}
        </li>
      ))}
    </ul>
  );
}

function Me() {
  const [tab, setTab] = useState<Tab>("watches");
  const tabs: [Tab, string][] = [["watches", "Lost"], ["found", "Found"], ["claims", "Claims"]];
  return (
    <div className="pad">
      <h1>My items</h1>
      <div className="tabs" role="tablist">
        {tabs.map(([t, label]) => (
          <button key={t} role="tab" aria-selected={tab === t} onClick={() => setTab(t)}>{label}</button>
        ))}
      </div>
      <div role="tabpanel">
        {tab === "watches" && <Watches />}
        {tab === "found" && <Found />}
        {tab === "claims" && <Claims />}
      </div>
    </div>
  );
}

export default function Page() {
  return <RequireAuth><Me /></RequireAuth>;
}
