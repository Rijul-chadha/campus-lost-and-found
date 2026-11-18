"use client";

import Link from "next/link";

import { Empty, ErrorNote, useLoad } from "@/components/ui";
import { api } from "@/lib/api";
import { ago } from "@/lib/format";
import { RequireAuth } from "@/lib/session";

function Inbox() {
  const { data, error, reload } = useLoad(() => api.notifications.list());
  const markAll = async () => { await api.notifications.read([], true); await reload(); };
  const open = (id: string) => void api.notifications.read([id]);

  if (error) return <ErrorNote error={error} />;
  if (!data) return <p className="muted">Loading…</p>;
  return (
    <div className="stack">
      <div className="spread">
        <h1>Alerts</h1>
        {data.items.some((n) => !n.read_at) && (
          <button className="btn secondary" onClick={() => void markAll()}>Mark all read</button>
        )}
      </div>
      {data.items.length === 0 ? (
        <Empty title="No alerts yet">
          <p>Matches for your lost items and claims on items you found appear here and by email.</p>
        </Empty>
      ) : (
        <ul className="list panel">
          {data.items.map((n) => (
            <li key={n.id} className={n.read_at ? "" : "unread"}>
              <div className="spread">
                <b>{n.link ? <Link href={n.link} onClick={() => open(n.id)}>{n.title}</Link> : n.title}</b>
                <span className="small muted">{ago(n.created_at)}</span>
              </div>
              <p className="muted" style={{ margin: 0 }}>{n.body}</p>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default function Page() {
  return <RequireAuth><div className="pad"><Inbox /></div></RequireAuth>;
}
