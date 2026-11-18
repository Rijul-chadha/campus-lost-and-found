"use client";

import { useCallback, useEffect, useState, type ReactNode } from "react";

import { ApiError } from "@/lib/api";
import { COLORS, STATUS_LABEL, STATUS_TONE } from "@/lib/format";
import type { ItemStatus } from "@/lib/types";

export function StatusPill({ status }: { status: ItemStatus }) {
  const tone = STATUS_TONE[status];
  return <span className={`pill ${tone === "neutral" ? "" : tone}`}>{STATUS_LABEL[status]}</span>;
}

export function ErrorNote({ error }: { error: unknown }) {
  if (!error) return null;
  const msg = error instanceof ApiError ? error.message
    : error instanceof Error ? error.message : "Something went wrong.";
  return <p className="notice bad" role="alert">{msg}</p>;
}

export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="panel">
      <h3>{title}</h3>
      {children}
    </div>
  );
}

// Common colours only; the full list (navy, olive, tan…) is still recognised in free text.
const PICKER = ["black", "white", "gray", "silver", "red", "orange", "yellow", "gold", "green",
  "teal", "blue", "navy", "purple", "pink", "brown", "beige", "clear", "multicolor"];

export function ColorPicker({ value, onChange, max = 3 }: {
  value: string[]; onChange: (v: string[]) => void; max?: number;
}) {
  const toggle = (c: string) => onChange(
    value.includes(c) ? value.filter((x) => x !== c) : value.length >= max ? value : [...value, c]);
  return (
    <div>
      <div className="swatches" role="group" aria-label={`Colours, up to ${max}`}>
        {COLORS.filter((c) => PICKER.includes(c.name)).map((c) => (
          <button type="button" key={c.name} title={c.name} aria-label={c.name}
                  aria-pressed={value.includes(c.name)} onClick={() => toggle(c.name)}
                  className={`swatch${c.name === "clear" ? " is-clear" : ""}`}
                  style={{ background: c.hex }} />
        ))}
      </div>
      <p className="swatch-names" aria-live="polite">
        {value.length ? value.join(", ") : `Pick up to ${max}`}
      </p>
    </div>
  );
}

/** Small data hook: load on mount, expose reload, keep the last error. */
export function useLoad<T>(fn: () => Promise<T>, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(true);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const load = useCallback(fn, deps);
  const reload = useCallback(async () => {
    setLoading(true);
    try {
      setData(await load());
      setError(null);
    } catch (e) {
      setError(e);
    } finally {
      setLoading(false);
    }
  }, [load]);
  useEffect(() => { void reload(); }, [reload]);
  return { data, error, loading, reload, setData };
}
