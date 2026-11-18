"use client";

import { useParams } from "next/navigation";
import { useState } from "react";

import { ColorDots, ItemTag } from "@/components/ItemTag";
import { Empty, ErrorNote, useLoad } from "@/components/ui";
import { api } from "@/lib/api";
import { when } from "@/lib/format";
import { RequireAuth } from "@/lib/session";

function WatchPage() {
  const { id } = useParams<{ id: string }>();
  const { data: w, error, reload, setData } = useLoad(() => api.watches.get(id), [id]);
  const [actionError, setActionError] = useState<unknown>(null);

  const act = async (action: "cancel" | "renew" | "resolve") => {
    setActionError(null);
    try { setData(await api.watches.act(id, action)); } catch (e) { setActionError(e); }
  };
  const dismiss = async (matchId: string) => {
    await api.watches.dismiss(id, matchId);
    await reload();
  };

  if (error) return <div className="pad"><ErrorNote error={error} /></div>;
  if (!w) return <p className="pad muted">Loading…</p>;
  const open = w.status === "open";
  return (
    <div className="pad stack">
      <h1>{w.title}</h1>
      <ColorDots colors={w.colors} />
      <p className="muted">{w.description}</p>
      <p className="small muted">
        Lost {w.location ? `near ${w.location.name}` : "somewhere on campus"} between {when(w.lost_from)} and {when(w.lost_to)}.{" "}
        {open ? `Watching until ${when(w.expires_at)}.` : `This watch is ${w.status}.`}
      </p>
      <div className="row">
        {open && <button className="btn secondary" onClick={() => void act("resolve")}>I found it</button>}
        {open && <button className="btn quiet" onClick={() => void act("cancel")}>Stop watching</button>}
        {w.status === "expired" && <button className="btn" onClick={() => void act("renew")}>Keep watching</button>}
      </div>
      <ErrorNote error={actionError} />

      <h2>Possible matches</h2>
      {w.matches.length === 0 ? (
        <Empty title="No matches yet">
          <p>Every newly reported item is checked against your description. You&apos;ll get a
            notification as soon as something similar is handed in.</p>
        </Empty>
      ) : (
        <div className="tags">
          {w.matches.map((m) => (
            <div key={m.id} className="stack">
              <ItemTag item={m.item} score={m.score} reasons={m.reasons} href={`/items/${m.item.id}?watch=${w.id}`} />
              {m.status !== "claimed" && (
                <button className="btn quiet small" onClick={() => void dismiss(m.id)}>Not mine</button>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default function Page() {
  return <RequireAuth><WatchPage /></RequireAuth>;
}
