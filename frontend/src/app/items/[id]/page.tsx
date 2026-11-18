"use client";

import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { Suspense, useState, type FormEvent } from "react";

import { ColorDots, holderText } from "@/components/ItemTag";
import { ErrorNote, StatusPill, useLoad } from "@/components/ui";
import { api } from "@/lib/api";
import { typeLabel, when } from "@/lib/format";
import { RequireAuth, useSession } from "@/lib/session";
import type { ClaimReview, FoundItem } from "@/lib/types";

const EVENT_LABEL: Record<string, string> = {
  reported: "Reported found", transferred_to_desk: "Handed in to a desk",
  claim_opened: "Someone claimed it", claim_approved: "Claim approved",
  claim_rejected: "Claim rejected", claim_cancelled: "Claim withdrawn", returned: "Returned to owner",
  expired: "Retention period ended", retention_extended: "Kept for longer", donated: "Donated",
  disposed: "Disposed", removed: "Removed",
};

function ClaimForm({ item, watchId, onDone }: { item: FoundItem; watchId: string | null; onDone: () => void }) {
  const [proof, setProof] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [hint, setHint] = useState<string | null>(null);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (proof.trim().length < 10) return setHint("Add a bit more detail (at least 10 characters).");
    setHint(null); setBusy(true); setError(null);
    try { await api.claims.create(item.id, proof.trim(), watchId); onDone(); }
    catch (err) { setError(err); } finally { setBusy(false); }
  };
  return (
    <form onSubmit={submit} className="panel stack">
      <h2>Is this yours?</h2>
      <label className="field">
        <span>Describe something only the owner would know</span>
        <textarea value={proof} onChange={(e) => { setProof(e.target.value); setHint(null); }} maxLength={1000}
                  placeholder="Marks, stickers, what's inside, lock screen, engraving…" />
        <small>{item.holder_type === "desk" ? "Desk staff" : "The finder"} will compare this with
          what they see before approving.</small>
      </label>
      {hint && <p className="small" style={{ color: "var(--bad)" }}>{hint}</p>}
      <ErrorNote error={error} />
      <button className="btn" disabled={busy}>{busy ? "Sending…" : "Claim this item"}</button>
    </form>
  );
}

function ReviewPanel({ itemId, onChange }: { itemId: string; onChange: () => void }) {
  const { data: claims, reload, error } = useLoad(() => api.claims.review(itemId), [itemId]);
  const [pickup, setPickup] = useState<Record<string, string>>({});
  const [actionError, setActionError] = useState<unknown>(null);
  const run = async (fn: () => Promise<unknown>) => {
    setActionError(null);
    try { await fn(); await reload(); onChange(); } catch (e) { setActionError(e); }
  };
  if (!claims?.length) return null;
  return (
    <section className="panel stack" aria-labelledby="claims">
      <h2 id="claims">Claims to review</h2>
      <ErrorNote error={error ?? actionError} />
      {claims.map((c: ClaimReview) => (
        <div key={c.id} className="stack">
          <div className="spread">
            <b>{c.claimant.display_name ?? "A student"}</b>
            {c.proof_strength && (
              <span className={`pill ${c.proof_strength === "strong" ? "good" : c.proof_strength === "partial" ? "warn" : "bad"}`}>
                {c.proof_strength} match with your private detail
              </span>
            )}
          </div>
          <blockquote className="proof">{c.proof_text}</blockquote>
          {c.private_detail && <p className="small muted">Your private detail: {c.private_detail}</p>}
          {c.status === "pending" ? (
            <>
              <label className="field">
                <span>Pickup instructions (sent to them if you approve)</span>
                <input value={pickup[c.id] ?? ""} maxLength={500}
                       onChange={(e) => setPickup({ ...pickup, [c.id]: e.target.value })}
                       placeholder="Library front steps, Thursday 2pm" />
              </label>
              <div className="row">
                <button className="btn good" onClick={() => void run(() => api.claims.approve(c.id, pickup[c.id]))}>Approve</button>
                <button className="btn danger" onClick={() => void run(() => api.claims.reject(c.id))}>Reject</button>
              </div>
            </>
          ) : (
            <div className="row">
              <span className="muted small">Approved: {c.pickup_instructions}</span>
              <button className="btn" onClick={() => void run(() => api.claims.complete(c.id))}>I handed it over</button>
            </div>
          )}
        </div>
      ))}
    </section>
  );
}

function Item() {
  const { id } = useParams<{ id: string }>();
  const search = useSearchParams();
  const watchId = search.get("watch");
  const isNew = search.get("new") === "1";
  const { user } = useSession();
  const { data: item, error, reload } = useLoad(() => api.items.get(id), [id]);
  const [claimed, setClaimed] = useState(false);

  if (error) return <div className="pad"><ErrorNote error={error} /></div>;
  if (!item) return <p className="pad muted">Loading…</p>;

  const canReview = item.viewer.is_reporter || user?.role !== "member";
  return (
    <div className="pad detail">
      <div className="stack">
        {isNew && (
          <p className="notice good">
            Reported. Anyone looking for something similar will be alerted.
          </p>
        )}
        <div className="row"><StatusPill status={item.status} />
          <span className="muted small">{typeLabel(item.item_type)}</span></div>
        <h1>{item.title}</h1>
        <ColorDots colors={item.colors} />
        {item.description ? <p>{item.description}</p>
          : item.is_sensitive ? <p className="muted">Details of personal documents are only shown to
            the owner after their claim is approved.</p> : null}
        <dl className="understood">
          <dt>Found</dt>
          <dd>{item.location?.name ?? "On campus"}{item.location_detail ? `, ${item.location_detail}` : ""}, {when(item.found_at)}</dd>
          <dt>Where it is now</dt>
          <dd>{holderText(item)}{item.holder_desk?.hours ? ` (${item.holder_desk.hours})` : ""}</dd>
          {item.brand && (<><dt>Brand</dt><dd>{item.brand}</dd></>)}
        </dl>
        {item.photos.length > 0 && (
          <div className="gallery">
            {item.photos.map((p) => <a key={p.url} href={p.url} target="_blank" rel="noreferrer"><img src={p.thumb_url} alt={`Photo of ${item.title}`} /></a>)}
          </div>
        )}
        {item.photos_hidden && <p className="small muted">Photos are hidden to protect the owner&apos;s privacy.</p>}
        {item.private_detail && (
          <p className="notice">Your private detail for checking claims: <b>{item.private_detail}</b></p>
        )}
      </div>

      <div className="stack">
        {item.viewer.can_claim && !claimed && (
          <ClaimForm item={item} watchId={watchId} onDone={() => { setClaimed(true); void reload(); }} />
        )}
        {(claimed || item.viewer.has_active_claim) && (
          <div className="notice">
            Claim sent. You&apos;ll get an alert once it&apos;s reviewed.{" "}
            <Link href="/me">My claims</Link>
          </div>
        )}
        {canReview && <ReviewPanel itemId={item.id} onChange={() => void reload()} />}
        {item.custody && (
          <section className="panel" aria-labelledby="history">
            <h2 id="history">History</h2>
            <ol className="timeline">
              {item.custody.map((e) => (
                <li key={e.id}>
                  <b>{EVENT_LABEL[e.event_type] ?? e.event_type}</b>
                  <div className="small muted">{when(e.created_at)}{e.note ? ` (${e.note})` : ""}</div>
                </li>
              ))}
            </ol>
          </section>
        )}
        {item.viewer.is_reporter && item.status === "available" && (
          <button className="btn quiet" onClick={async () => {
            if (window.confirm("Withdraw this report? It will disappear from search.")) {
              await api.items.withdraw(item.id); void reload();
            }
          }}>Withdraw this report</button>
        )}
      </div>
    </div>
  );
}

export default function Page() {
  return <RequireAuth><Suspense><Item /></Suspense></RequireAuth>;
}
