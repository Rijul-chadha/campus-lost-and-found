import type {
  Campus, ChatMessage, ChatOut, Claim, ClaimReview, DeskOverview, FoundItem, FoundItemCreate,
  LostReportCreate, Notification, Page, User, Watch, WatchDetail,
} from "./types";

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public details: Record<string, unknown> = {},
  ) {
    super(message);
  }
}

type Method = "GET" | "POST" | "PATCH" | "DELETE";

async function request<T>(method: Method, path: string, body?: unknown): Promise<T> {
  const res = await fetch(`/api/v1${path}`, {
    method,
    credentials: "same-origin",
    headers: {
      "content-type": "application/json",
      // Required by the API's CSRF guard for cookie-authenticated writes.
      "x-requested-with": "campus-lost",
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (res.status === 204) return undefined as T;
  const data = await res.json().catch(() => null);
  if (!res.ok) {
    let message: string = data?.title ?? `Request failed (${res.status})`;
    const errors = data?.details?.errors as { loc: string[]; msg: string }[] | undefined;
    if (errors?.length) message = errors.map((e) => `${e.loc.at(-1)}: ${e.msg}`).join("; ");
    throw new ApiError(res.status, data?.code ?? "error", message, data?.details ?? {});
  }
  return data as T;
}

const qs = (params: Record<string, string | number | null | undefined>) => {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== null && v !== undefined && v !== "")
    p.set(k, String(v));
  const s = p.toString();
  return s ? `?${s}` : "";
};

export const api = {
  auth: {
    me: () => request<User>("GET", "/auth/me"),
    requestCode: (email: string) => request<void>("POST", "/auth/request-code", { email }),
    verify: (email: string, code: string) => request<User>("POST", "/auth/verify", { email, code }),
    logout: () => request<void>("POST", "/auth/logout"),
    rename: (display_name: string) => request<User>("PATCH", "/auth/me", { display_name }),
  },
  campus: () => request<Campus>("GET", "/campus"),
  items: {
    browse: (p: { category?: string; location_id?: string; cursor?: string | null } = {}) =>
      request<Page<FoundItem>>("GET", `/items${qs(p)}`),
    mine: () => request<Page<FoundItem>>("GET", "/items/mine"),
    get: (id: string) => request<FoundItem>("GET", `/items/${id}`),
    create: (body: FoundItemCreate) => request<FoundItem>("POST", "/items", body),
    withdraw: (id: string) => request<void>("DELETE", `/items/${id}`),
  },
  uploads: {
    intent: (content_type: string) =>
      request<{ key: string; url: string; fields: Record<string, string>; max_bytes: number }>(
        "POST", "/uploads", { content_type }),
  },
  watches: {
    create: (body: LostReportCreate) => request<WatchDetail>("POST", "/lost-reports", body),
    list: () => request<Page<Watch>>("GET", "/lost-reports"),
    get: (id: string) => request<WatchDetail>("GET", `/lost-reports/${id}`),
    act: (id: string, action: "cancel" | "renew" | "resolve") =>
      request<WatchDetail>("POST", `/lost-reports/${id}/${action}`),
    dismiss: (id: string, matchId: string) =>
      request<void>("POST", `/lost-reports/${id}/matches/${matchId}/dismiss`),
  },
  assistant: {
    chat: (messages: ChatMessage[]) => request<ChatOut>("POST", "/assistant/chat", { messages }),
  },
  claims: {
    create: (found_item_id: string, proof_text: string, lost_report_id?: string | null) =>
      request<Claim>("POST", "/claims", { found_item_id, proof_text, lost_report_id }),
    mine: () => request<Claim[]>("GET", "/claims/mine"),
    review: (item?: string | null) => request<ClaimReview[]>("GET", `/claims/review${qs({ item })}`),
    approve: (id: string, pickup_instructions?: string) =>
      request<ClaimReview>("POST", `/claims/${id}/approve`,
        { pickup_instructions: pickup_instructions || null }),
    reject: (id: string, note?: string) =>
      request<ClaimReview>("POST", `/claims/${id}/reject`, { note: note || null }),
    complete: (id: string) => request<ClaimReview>("POST", `/claims/${id}/complete`),
    cancel: (id: string) => request<Claim>("POST", `/claims/${id}/cancel`),
  },
  notifications: {
    list: (cursor?: string | null) =>
      request<Page<Notification>>("GET", `/notifications${qs({ cursor })}`),
    unread: () => request<{ unread: number }>("GET", "/notifications/unread-count"),
    read: (ids: string[], all = false) => request<void>("POST", "/notifications/read", { ids, all }),
  },
  desk: {
    overview: () => request<DeskOverview>("GET", "/desk/overview"),
    items: (p: { status?: string; holder_type?: string; q?: string; cursor?: string | null }) =>
      request<Page<FoundItem>>("GET", `/desk/items${qs(p)}`),
    receive: (id: string, note?: string) =>
      request<FoundItem>("POST", `/desk/items/${id}/receive`, { note: note || null }),
    close: (id: string, action: "donate" | "dispose" | "extend", note?: string) =>
      request<FoundItem>("POST", `/desk/items/${id}/close`, { action, note: note || null }),
  },
};

/** Direct-to-bucket upload with the presigned POST policy from the API. */
export async function uploadPhoto(file: File): Promise<string> {
  const intent = await api.uploads.intent(file.type);
  if (file.size > intent.max_bytes) {
    throw new ApiError(413, "too_large",
      `Photos must be under ${Math.round(intent.max_bytes / 1024 / 1024)} MB`);
  }
  const form = new FormData();
  Object.entries(intent.fields).forEach(([k, v]) => form.append(k, v));
  form.append("file", file);
  const res = await fetch(intent.url, { method: "POST", body: form });
  if (!res.ok) throw new ApiError(res.status, "upload_failed", "Photo upload failed. Try again.");
  return intent.key;
}
