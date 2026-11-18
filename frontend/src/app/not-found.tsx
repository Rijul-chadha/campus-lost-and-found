import Link from "next/link";

export default function NotFound() {
  return (
    <section className="pad">
      <h1>This page isn&apos;t here</h1>
      <p className="muted">The link may be old, or the item may have been returned or removed.</p>
      <Link className="btn" href="/">Go to the home page</Link>
    </section>
  );
}
