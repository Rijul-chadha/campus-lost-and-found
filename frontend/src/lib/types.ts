// Mirrors the FastAPI schemas. Regenerate a full client with `npm run gen:api`.

export type Role = "member" | "desk" | "admin";
export type HolderType = "finder" | "desk";
export type ItemStatus =
  | "reported" | "available" | "claimed" | "returned"
  | "expired" | "donated" | "disposed" | "removed";
export type ClaimStatus = "pending" | "approved" | "rejected" | "completed" | "cancelled";
export type WatchStatus = "open" | "resolved" | "expired" | "cancelled";
export type MatchStatus = "suggested" | "notified" | "dismissed" | "claimed";

export interface Page<T> { items: T[]; next_cursor: string | null }

export interface User {
  id: string; campus_id: string; email: string; display_name: string | null;
  role: Role; desk_id: string | null;
}

export interface Location { id: string; name: string; lat: number | null; lng: number | null }
export interface Desk { id: string; name: string; location_id: string | null; hours: string | null }
export interface Campus {
  id: string; slug: string; name: string; timezone: string;
  locations: Location[]; desks: Desk[];
}

export interface Photo { url: string; thumb_url: string }

export interface CustodyEvent {
  id: number; event_type: string; actor_id: string | null; from_holder: string | null;
  to_holder: string | null; note: string | null; created_at: string;
}

export interface FoundItem {
  id: string; title: string; description: string | null; category: string | null;
  item_type: string | null; colors: string[]; brand: string | null; is_sensitive: boolean;
  location: Location | null; location_detail: string | null; found_at: string;
  status: ItemStatus; holder_type: HolderType; holder_desk: Desk | null;
  photos: Photo[]; photos_hidden: boolean; created_at: string; expires_at: string;
  viewer: { is_reporter: boolean; can_view_private: boolean; can_claim: boolean;
            has_active_claim: boolean };
  // present on the private view only
  private_detail?: string | null;
  reporter?: { id: string; display_name: string | null };
  custody?: CustodyEvent[];
}

export interface FoundItemCreate {
  title: string; description?: string | null; category?: string | null;
  item_type?: string | null; colors?: string[]; brand?: string | null;
  found_location_id?: string | null; found_location_detail?: string | null;
  found_at: string; holder_type: HolderType; holder_desk_id?: string | null;
  private_detail?: string | null; upload_keys: string[];
}

export interface LostReportCreate {
  title: string; description: string; category?: string | null; item_type?: string | null;
  colors?: string[]; brand?: string | null; location_id?: string | null;
  location_detail?: string | null; lost_from: string; lost_to: string;
}

export interface Watch {
  id: string; title: string; description: string; category: string | null;
  item_type: string | null; colors: string[]; brand: string | null;
  location: Location | null; location_detail: string | null; lost_from: string;
  lost_to: string; status: WatchStatus; expires_at: string; created_at: string;
  match_count: number;
}
export interface Match { id: string; score: number; reasons: string[]; status: MatchStatus;
                         item: FoundItem }
export interface WatchDetail extends Watch { matches: Match[] }

export interface ChatMessage { role: "user" | "assistant"; content: string }
export interface ChatOut {
  reply: string;
  extracted: {
    category: string | null; item_type: string | null; colors: string[]; brand: string | null;
    location_id: string | null; location_name: string | null; lost_from: string;
    lost_to: string; time_is_guess: boolean;
  };
  missing: string[];
  matches: { score: number; reasons: string[]; item: FoundItem }[];
  watch_draft: LostReportCreate | null;
  used_llm: boolean;
}

export interface Claim {
  id: string; found_item_id: string; item_title: string; status: ClaimStatus;
  created_at: string; decided_at: string | null; decision_note: string | null;
  pickup_instructions: string | null;
}
export interface ClaimReview extends Claim {
  proof_text: string; proof_strength: "strong" | "partial" | "weak" | null;
  proof_score: number | null; private_detail: string | null;
  claimant: { id: string; display_name: string | null };
}

export interface Notification {
  id: string; kind: string; title: string; body: string; link: string | null;
  payload: Record<string, unknown>; read_at: string | null; created_at: string;
}

export interface DeskOverview {
  by_status: Record<string, number>; pending_claims: number; held_by_finders: number;
  expiring_within_7d: number; awaiting_decision: number; returned_last_30d: number;
  reported_last_30d: number; return_rate_last_30d: number; open_watches: number;
}
