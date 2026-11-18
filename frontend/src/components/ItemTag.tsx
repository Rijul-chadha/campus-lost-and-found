import Link from "next/link";

import { ago, colorHex, STATUS_LABEL, typeLabel } from "@/lib/format";
import type { FoundItem } from "@/lib/types";

export function ColorDots({ colors }: { colors: string[] }) {
  if (!colors.length) return null;
  return (
    <div className="swatches" aria-label={`Colours: ${colors.join(", ")}`}>
      {colors.map((c) => (
        <span key={c} className={`dot${c === "clear" ? " clear" : ""}`} title={c}
              style={{ background: colorHex(c) }} />
      ))}
    </div>
  );
}

export function holderText(item: FoundItem): string {
  if (item.holder_type === "desk") return item.holder_desk ? `At ${item.holder_desk.name}` : "At a desk";
  return "With the finder";
}

/** A found item rendered as a lost-and-found claim tag. */
export function ItemTag({
  item, href, score, reasons,
}: { item: FoundItem; href?: string; score?: number; reasons?: string[] }) {
  const thumb = item.photos[0]?.thumb_url;
  const dim = item.status !== "available" && item.status !== "reported";
  const body = (
    <>
      <div className={`tag-photo${thumb ? "" : " is-empty"}`}>
        {thumb ? <img src={thumb} alt="" loading="lazy" />
          : <span>{item.photos_hidden ? "Photo hidden for privacy" : typeLabel(item.item_type)}</span>}
      </div>
      <h3 className="tag-title">{item.title}</h3>
      <ColorDots colors={item.colors} />
      <p className="tag-meta">
        Found {item.location ? `at ${item.location.name}` : "on campus"}, {ago(item.found_at)}
      </p>
      {reasons && reasons.length > 0 && (
        <ul className="reasons">{reasons.slice(0, 3).map((r) => <li key={r}>{r}</li>)}</ul>
      )}
      <div className="tag-foot">
        <span>{dim ? STATUS_LABEL[item.status] : holderText(item)}</span>
        {score !== undefined && (
          <span className="row" title={`Match score ${Math.round(score * 100)}%`}>
            <span className="meter" aria-hidden><i style={{ width: `${Math.round(score * 100)}%` }} /></span>
            <span className="sr-only">Match strength {Math.round(score * 100)} percent</span>
          </span>
        )}
      </div>
    </>
  );
  const cls = `tag${dim ? " is-dim" : ""}`;
  return href ? <Link href={href} className={cls}>{body}</Link> : <div className={cls}>{body}</div>;
}
