"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense } from "react";

import { Empty, ErrorNote, useLoad } from "@/components/ui";
import { api } from "@/lib/api";
import { ago } from "@/lib/format";
import { RequireAuth } from "@/lib/session";

function Queue() {
  const item = useSearchParams().get("item");
  const { data, error } = useLoad(() => api.claims.review(item), [item]);
  if (error) return <ErrorNote error={error} />;
  if (!data) return <p className="muted">Loading…</p>;
  if (!data.length) return <Empty title="No claims waiting"><p>When someone claims an item you&apos;re holding, it shows up here.</p></Empty>;
  return (
    <ul className="list">
      {data.map((c) => (
        <li key={c.id} className="spread">
          <div>
            <Link href={`/items/${c.found_item_id}`}><b>{c.item_title}</b></Link>
            <div className="small muted">{c.claimant.display_name ?? "A student"} claimed it {ago(c.created_at)}</div>
          </div>
          <span className={`pill ${c.status === "approved" ? "good" : ""}`}>
            {c.status === "approved" ? "Waiting for handover" : "Needs a decision"}
          </span>
        </li>
      ))}
    </ul>
  );
}

export default function Page() {
  return (
    <RequireAuth>
      <div className="pad stack">
        <h1>Claims to review</h1>
        <p className="muted">Open an item to compare the claimant&apos;s description with your private detail.</p>
        <Suspense><Queue /></Suspense>
      </div>
    </RequireAuth>
  );
}
