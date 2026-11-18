"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { ColorPicker, ErrorNote } from "@/components/ui";
import { api, uploadPhoto } from "@/lib/api";
import { fromLocalInput, ITEM_TYPES, toLocalInput } from "@/lib/format";
import { RequireAuth, useSession } from "@/lib/session";
import type { HolderType } from "@/lib/types";

const MAX_PHOTOS = 4;

function ReportForm() {
  const router = useRouter();
  const { campus, user } = useSession();
  const isStaff = user?.role !== "member";
  const [title, setTitle] = useState("");
  const [itemType, setItemType] = useState("");
  const [description, setDescription] = useState("");
  const [colors, setColors] = useState<string[]>([]);
  const [brand, setBrand] = useState("");
  const [locationId, setLocationId] = useState("");
  const [locationDetail, setLocationDetail] = useState("");
  const [foundAt, setFoundAt] = useState(toLocalInput(new Date()));
  const [holder, setHolder] = useState<HolderType>(isStaff ? "desk" : "finder");
  const [deskId, setDeskId] = useState(user?.desk_id ?? "");
  const [secret, setSecret] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [fieldError, setFieldError] = useState<string | null>(null);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setFieldError(null); setError(null);
    if (!title.trim()) return setFieldError("Add a short name for the item.");
    if (!locationId) return setFieldError("Choose where you found it.");
    if (holder === "desk" && !deskId) return setFieldError("Choose which desk has it.");
    setBusy(true);
    try {
      const upload_keys = await Promise.all(files.map(uploadPhoto));
      const item = await api.items.create({
        title: title.trim(), description: description.trim() || null,
        item_type: itemType || null, colors, brand: brand.trim() || null,
        found_location_id: locationId, found_location_detail: locationDetail.trim() || null,
        found_at: fromLocalInput(foundAt), holder_type: holder,
        holder_desk_id: holder === "desk" ? deskId : null,
        private_detail: secret.trim() || null, upload_keys,
      });
      router.push(`/items/${item.id}?new=1`);
    } catch (err) {
      setError(err);
      setBusy(false);
    }
  };

  return (
    <form onSubmit={submit} className="form" noValidate>
      <header className="page-head">
        <h1>Report a found item</h1>
        <p className="muted">Your name and contact details stay private.</p>
      </header>

      <section className="form-section">
        <h2>What it is</h2>
        <label className="field">
          <span>Name</span>
          <input value={title} onChange={(e) => setTitle(e.target.value)} maxLength={140}
                 placeholder="Black Nike backpack" />
        </label>
        <div className="grid-2">
          <label className="field">
            <span>Type</span>
            <select value={itemType} onChange={(e) => setItemType(e.target.value)}>
              <option value="">Detect from name</option>
              {ITEM_TYPES.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
            </select>
          </label>
          <label className="field">
            <span>Brand <em>optional</em></span>
            <input value={brand} onChange={(e) => setBrand(e.target.value)} maxLength={60} />
          </label>
        </div>
        <fieldset>
          <legend>Colour</legend>
          <ColorPicker value={colors} onChange={setColors} />
        </fieldset>
        <label className="field">
          <span>Description <em>optional</em></span>
          <textarea value={description} onChange={(e) => setDescription(e.target.value)} maxLength={2000}
                    placeholder="Stickers, size, anything inside" />
        </label>
        <label className="field">
          <span>Photos <em>up to {MAX_PHOTOS}</em></span>
          <input type="file" accept="image/jpeg,image/png,image/webp,image/heic" multiple
                 onChange={(e) => setFiles(Array.from<File>(e.target.files ?? []).slice(0, MAX_PHOTOS))} />
        </label>
      </section>

      <section className="form-section">
        <h2>Where and when</h2>
        <div className="grid-2">
          <label className="field">
            <span>Place</span>
            <select value={locationId} onChange={(e) => setLocationId(e.target.value)}>
              <option value="">Choose a place</option>
              {campus?.locations.map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}
            </select>
          </label>
          <label className="field">
            <span>Time</span>
            <input type="datetime-local" value={foundAt} max={toLocalInput(new Date())}
                   onChange={(e) => setFoundAt(e.target.value)} />
          </label>
        </div>
        <label className="field">
          <span>Exact spot <em>optional</em></span>
          <input value={locationDetail} onChange={(e) => setLocationDetail(e.target.value)}
                 maxLength={200} placeholder="3rd floor study area" />
        </label>
      </section>

      <section className="form-section">
        <h2>Handover</h2>
        {isStaff ? (
          <div className="choice">
            <label>
              <input type="radio" name="holder" checked={holder === "desk"} onChange={() => setHolder("desk")} />
              <span>At a desk</span>
            </label>
            <label>
              <input type="radio" name="holder" checked={holder === "finder"} onChange={() => setHolder("finder")} />
              <span>With me</span>
            </label>
          </div>
        ) : (
          <p className="muted">
            Keep it for now. You&apos;ll approve the owner&apos;s claim and arrange pickup, or drop it
            at {campus?.desks.map((d) => d.name).join(" or ") || "a desk"} anytime.
          </p>
        )}
        {holder === "desk" && (
          <label className="field">
            <span>Desk</span>
            <select value={deskId} onChange={(e) => setDeskId(e.target.value)}>
              <option value="">Choose a desk</option>
              {campus?.desks.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
            </select>
          </label>
        )}
        <label className="field">
          <span>Owner check <em>recommended</em></span>
          <input value={secret} onChange={(e) => setSecret(e.target.value)} maxLength={500}
                 placeholder="Cat sticker inside the lid" />
          <small>A detail only the owner would know. Never shown publicly.</small>
        </label>
      </section>

      {fieldError && <p className="notice bad" role="alert">{fieldError}</p>}
      <ErrorNote error={error} />
      <button className="btn" disabled={busy}>{busy ? "Reporting…" : "Report item"}</button>
    </form>
  );
}

export default function Page() {
  return <RequireAuth><div className="pad"><ReportForm /></div></RequireAuth>;
}
