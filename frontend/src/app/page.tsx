"use client";

import Link from "next/link";

import { useSession } from "@/lib/session";

export default function Home() {
  const { user } = useSession();
  const to = (path: string) => (user ? path : `/login?next=${path}`);

  return (
    <section className="hero">
      <h1>Lost something?<br />Found something?</h1>
      <p className="lede">Report what you found, or describe what you lost. We match them up.</p>
      <div className="hero-actions">
        <Link href={to("/found/new")} className="tag hero-tag">
          <h2 className="tag-title">I found something</h2>
          <p>Add a photo and where you found it.</p>
          <span className="btn">Report found item</span>
        </Link>
        <Link href={to("/lost")} className="tag hero-tag lost">
          <h2 className="tag-title">I lost something</h2>
          <p>Describe it. We search now and alert you if it turns up later.</p>
          <span className="btn">Find my item</span>
        </Link>
      </div>
      {!user && <p className="muted small">Sign in with your campus email to continue.</p>}
    </section>
  );
}
