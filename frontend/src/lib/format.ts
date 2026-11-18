import type { ItemStatus } from "./types";

export const ITEM_TYPES: { value: string; label: string; category: string }[] = [
  ["phone", "Phone", "electronics"], ["laptop", "Laptop", "electronics"],
  ["earbuds", "Earbuds / AirPods", "electronics"], ["headphones", "Headphones", "electronics"],
  ["charger", "Charger or cable", "electronics"], ["tablet", "Tablet / e-reader", "electronics"],
  ["calculator", "Calculator", "electronics"], ["smartwatch", "Smartwatch", "electronics"],
  ["student_card", "Student / campus card", "cards"], ["drivers_license", "Driver's licence", "cards"],
  ["bank_card", "Bank or transit card", "cards"], ["health_card", "Health card", "cards"],
  ["passport", "Passport", "cards"], ["wallet", "Wallet", "wallet"], ["keys", "Keys", "keys"],
  ["backpack", "Backpack", "bags"], ["bag", "Other bag", "bags"], ["jacket", "Jacket / coat", "clothing"],
  ["hoodie", "Hoodie / sweater", "clothing"], ["hat", "Hat", "clothing"], ["scarf", "Scarf", "clothing"],
  ["gloves", "Gloves", "clothing"], ["shoes", "Shoes", "clothing"],
  ["water_bottle", "Water bottle / mug", "bottles"], ["glasses", "Glasses", "accessories"],
  ["ring", "Ring", "accessories"], ["necklace", "Necklace", "accessories"],
  ["bracelet", "Bracelet", "accessories"], ["earrings", "Earrings", "accessories"],
  ["watch", "Watch", "accessories"], ["umbrella", "Umbrella", "accessories"],
  ["notebook", "Notebook / book", "stationery"], ["pencil_case", "Pencil case", "stationery"],
  ["sports_gear", "Sports gear", "sports"], ["other", "Something else", "other"],
].map(([value, label, category]) => ({ value: value!, label: label!, category: category! }));

export const typeLabel = (t: string | null | undefined) =>
  ITEM_TYPES.find((x) => x.value === t)?.label ?? "Item";

export const COLORS: { name: string; hex: string }[] = [
  ["black", "#1d1d1f"], ["white", "#ffffff"], ["gray", "#8a8f98"], ["silver", "#c4c8cf"],
  ["charcoal", "#41454d"], ["red", "#c8312a"], ["maroon", "#6e1f28"], ["orange", "#e8782d"],
  ["yellow", "#f0c63a"], ["gold", "#c9a23c"], ["green", "#2f8a4c"], ["olive", "#6b7036"],
  ["teal", "#1f8a8a"], ["blue", "#2f64d8"], ["navy", "#1d2c5e"], ["light blue", "#8fb8ea"],
  ["purple", "#7046b8"], ["lavender", "#b9a5e3"], ["pink", "#e483ad"], ["brown", "#7a4f2e"],
  ["tan", "#c19a6b"], ["beige", "#ddc9a3"], ["cream", "#f3ead2"], ["clear", "transparent"],
  ["multicolor", "conic-gradient(#c8312a,#f0c63a,#2f8a4c,#2f64d8,#7046b8,#c8312a)"],
].map(([name, hex]) => ({ name: name!, hex: hex! }));

export const colorHex = (c: string) => COLORS.find((x) => x.name === c)?.hex ?? "#bbb";

const rtf = new Intl.RelativeTimeFormat("en", { numeric: "auto" });

export function ago(iso: string): string {
  const diff = (new Date(iso).getTime() - Date.now()) / 1000;
  const units: [Intl.RelativeTimeFormatUnit, number][] = [
    ["day", 86400], ["hour", 3600], ["minute", 60],
  ];
  for (const [unit, s] of units) if (Math.abs(diff) >= s) return rtf.format(Math.round(diff / s), unit);
  return "just now";
}

export const when = (iso: string) =>
  new Date(iso).toLocaleString("en-CA", {
    weekday: "short", month: "short", day: "numeric", hour: "numeric", minute: "2-digit",
  });

export const STATUS_LABEL: Record<ItemStatus, string> = {
  reported: "Processing", available: "Waiting for owner", claimed: "Claim approved",
  returned: "Returned", expired: "Unclaimed", donated: "Donated", disposed: "Disposed",
  removed: "Removed",
};

export const STATUS_TONE: Record<ItemStatus, "neutral" | "good" | "warn" | "bad"> = {
  reported: "neutral", available: "neutral", claimed: "good", returned: "good",
  expired: "warn", donated: "neutral", disposed: "neutral", removed: "bad",
};

export function toLocalInput(d: Date): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

/** datetime-local value -> ISO with offset (the API requires timezone-aware times). */
export const fromLocalInput = (v: string) => new Date(v).toISOString();
