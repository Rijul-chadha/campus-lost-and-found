"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-11-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql as pg

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DIM = 384

ENUMS: dict[str, list[str]] = {
    "user_role": ["member", "desk", "admin"],
    "holder_type": ["finder", "desk"],
    "item_status": ["reported", "available", "claimed", "returned", "expired", "donated",
                    "disposed", "removed"],
    "custody_event_type": ["reported", "transferred_to_desk", "claim_opened", "claim_approved",
                           "claim_rejected", "claim_cancelled", "returned", "expired",
                           "retention_extended", "donated", "disposed", "removed"],
    "lost_report_status": ["open", "resolved", "expired", "cancelled"],
    "match_status": ["suggested", "notified", "dismissed", "claimed"],
    "claim_status": ["pending", "approved", "rejected", "completed", "cancelled"],
    "notification_kind": ["possible_match", "claim_received", "claim_approved", "claim_rejected",
                          "item_returned", "watch_expiring", "items_expired"],
}


def E(name: str) -> pg.ENUM:  # noqa: N802
    return pg.ENUM(*ENUMS[name], name=name, create_type=False)


def ts(name: str, nullable: bool = False, default: bool = False) -> sa.Column:
    return sa.Column(name, sa.DateTime(timezone=True), nullable=nullable,
                     server_default=sa.func.now() if default else None)


def uid(name: str = "id", *constraints: object, **kw: object) -> sa.Column:
    return sa.Column(name, pg.UUID(as_uuid=True), *constraints, **kw)


def campus_fk() -> sa.Column:
    return uid("campus_id", sa.ForeignKey("campuses.id", ondelete="CASCADE"), nullable=False,
               index=True)


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    bind = op.get_bind()
    for name, values in ENUMS.items():
        pg.ENUM(*values, name=name).create(bind, checkfirst=True)

    op.create_table(
        "campuses",
        uid(primary_key=True),
        sa.Column("slug", sa.String(64), nullable=False, unique=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("email_domains", pg.ARRAY(sa.String(253)), nullable=False),
        sa.Column("timezone", sa.String(64), nullable=False),
        ts("created_at", default=True), ts("updated_at", default=True),
    )
    op.create_index("ix_campuses_email_domains", "campuses", ["email_domains"],
                    postgresql_using="gin")

    op.create_table(
        "locations",
        uid(primary_key=True), campus_fk(),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("aliases", pg.ARRAY(sa.String(100)), nullable=False, server_default="{}"),
        sa.Column("lat", sa.Float), sa.Column("lng", sa.Float),
        sa.UniqueConstraint("campus_id", "name", name="uq_locations_campus_id"),
    )

    op.create_table(
        "desks",
        uid(primary_key=True), campus_fk(),
        sa.Column("name", sa.String(200), nullable=False),
        uid("location_id", sa.ForeignKey("locations.id", ondelete="SET NULL")),
        sa.Column("hours", sa.Text), sa.Column("contact_email", sa.String(320)),
        sa.UniqueConstraint("campus_id", "name", name="uq_desks_campus_id"),
    )

    op.create_table(
        "users",
        uid(primary_key=True), campus_fk(),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("display_name", sa.String(120)),
        sa.Column("role", E("user_role"), nullable=False, server_default="member"),
        uid("desk_id", sa.ForeignKey("desks.id", ondelete="SET NULL")),
        ts("last_login_at", nullable=True),
        ts("created_at", default=True), ts("updated_at", default=True),
    )
    op.execute("CREATE UNIQUE INDEX uq_users_campus_email ON users (campus_id, lower(email))")

    op.create_table(
        "found_items",
        uid(primary_key=True), campus_fk(),
        uid("reporter_id", sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("title", sa.String(140), nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("public_title", sa.String(140), nullable=False),
        sa.Column("public_description", sa.Text),
        sa.Column("category", sa.String(40), index=True),
        sa.Column("item_type", sa.String(40)),
        sa.Column("colors", pg.ARRAY(sa.String(30)), nullable=False, server_default="{}"),
        sa.Column("brand", sa.String(60)),
        sa.Column("is_sensitive", sa.Boolean, nullable=False, server_default=sa.false()),
        uid("found_location_id", sa.ForeignKey("locations.id", ondelete="SET NULL")),
        sa.Column("found_location_detail", sa.String(200)),
        ts("found_at"),
        sa.Column("holder_type", E("holder_type"), nullable=False),
        uid("holder_desk_id", sa.ForeignKey("desks.id", ondelete="SET NULL")),
        sa.Column("status", E("item_status"), nullable=False, server_default="reported"),
        sa.Column("upload_keys", pg.ARRAY(sa.String(300)), nullable=False, server_default="{}"),
        sa.Column("photo_keys", pg.ARRAY(sa.String(300)), nullable=False, server_default="{}"),
        sa.Column("private_detail", sa.Text),
        sa.Column("embedding", Vector(DIM)),
        sa.Column("embedding_model", sa.String(80)),
        ts("expires_at"),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        ts("created_at", default=True), ts("updated_at", default=True),
    )
    op.execute("CREATE INDEX ix_found_items_campus_status_found_at "
               "ON found_items (campus_id, status, found_at DESC)")
    op.execute("CREATE INDEX ix_found_items_embedding_hnsw ON found_items "
               "USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64)")
    op.execute("CREATE INDEX ix_found_items_expiry ON found_items (expires_at) "
               "WHERE status = 'available'")
    op.execute("CREATE INDEX ix_found_items_reporter ON found_items (reporter_id, created_at DESC)")

    op.create_table(
        "custody_events",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True), campus_fk(),
        uid("found_item_id", sa.ForeignKey("found_items.id", ondelete="CASCADE"), nullable=False),
        sa.Column("event_type", E("custody_event_type"), nullable=False),
        uid("actor_id", sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("from_holder", sa.String(80)), sa.Column("to_holder", sa.String(80)),
        sa.Column("note", sa.Text),
        ts("created_at", default=True),
    )
    op.create_index("ix_custody_events_item", "custody_events", ["found_item_id", "id"])
    # Append-only audit log: history can be added to, never rewritten. UPDATE is always
    # blocked; a direct DELETE is blocked, but a cascaded delete (an FK action firing from
    # inside the RI trigger, so pg_trigger_depth() > 1) is allowed, e.g. erasing a campus.
    op.execute("""
        CREATE FUNCTION custody_events_append_only() RETURNS trigger AS $$
        BEGIN
          IF TG_OP = 'UPDATE' OR pg_trigger_depth() = 1 THEN
            RAISE EXCEPTION 'custody_events is append-only (% blocked)', TG_OP;
          END IF;
          RETURN OLD;
        END $$ LANGUAGE plpgsql;
    """)
    # asyncpg runs one statement per call, so the trigger is its own execute.
    op.execute("""
        CREATE TRIGGER custody_events_append_only BEFORE UPDATE OR DELETE ON custody_events
          FOR EACH ROW EXECUTE FUNCTION custody_events_append_only()
    """)

    op.create_table(
        "lost_reports",
        uid(primary_key=True), campus_fk(),
        uid("owner_id", sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(140), nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("category", sa.String(40)), sa.Column("item_type", sa.String(40)),
        sa.Column("colors", pg.ARRAY(sa.String(30)), nullable=False, server_default="{}"),
        sa.Column("brand", sa.String(60)),
        uid("location_id", sa.ForeignKey("locations.id", ondelete="SET NULL")),
        sa.Column("location_detail", sa.String(200)),
        ts("lost_from"), ts("lost_to"),
        sa.Column("status", E("lost_report_status"), nullable=False, server_default="open"),
        sa.Column("embedding", Vector(DIM)),
        sa.Column("embedding_model", sa.String(80)),
        ts("expires_at"), ts("last_matched_at", nullable=True),
        ts("created_at", default=True), ts("updated_at", default=True),
    )
    op.execute("CREATE INDEX ix_lost_reports_open ON lost_reports (campus_id, category, lost_from) "
               "WHERE status = 'open'")
    op.execute("CREATE INDEX ix_lost_reports_embedding_hnsw ON lost_reports "
               "USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64)")
    op.execute("CREATE INDEX ix_lost_reports_owner ON lost_reports (owner_id, created_at DESC)")

    op.create_table(
        "matches",
        uid(primary_key=True), campus_fk(),
        uid("lost_report_id", sa.ForeignKey("lost_reports.id", ondelete="CASCADE"),
            nullable=False, index=True),
        uid("found_item_id", sa.ForeignKey("found_items.id", ondelete="CASCADE"), nullable=False),
        sa.Column("score", sa.Float, nullable=False),
        sa.Column("components", pg.JSONB, nullable=False),
        sa.Column("reasons", pg.ARRAY(sa.String(200)), nullable=False, server_default="{}"),
        sa.Column("status", E("match_status"), nullable=False, server_default="suggested"),
        ts("created_at", default=True), ts("updated_at", default=True),
        sa.UniqueConstraint("lost_report_id", "found_item_id", name="uq_matches_pair"),
    )
    op.create_index("ix_matches_found_item", "matches", ["found_item_id"])

    op.create_table(
        "claims",
        uid(primary_key=True), campus_fk(),
        uid("found_item_id", sa.ForeignKey("found_items.id", ondelete="CASCADE"), nullable=False),
        uid("claimant_id", sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        uid("lost_report_id", sa.ForeignKey("lost_reports.id", ondelete="SET NULL")),
        sa.Column("proof_text", sa.Text, nullable=False),
        sa.Column("proof_score", sa.Float), sa.Column("proof_strength", sa.String(16)),
        sa.Column("status", E("claim_status"), nullable=False, server_default="pending"),
        uid("decided_by_id", sa.ForeignKey("users.id", ondelete="SET NULL")),
        ts("decided_at", nullable=True),
        sa.Column("decision_note", sa.Text), sa.Column("pickup_instructions", sa.Text),
        ts("created_at", default=True), ts("updated_at", default=True),
    )
    op.execute("CREATE UNIQUE INDEX uq_claims_active_per_claimant ON claims "
               "(found_item_id, claimant_id) WHERE status IN ('pending', 'approved')")
    op.execute("CREATE UNIQUE INDEX uq_claims_one_approved_per_item ON claims (found_item_id) "
               "WHERE status = 'approved'")
    op.create_index("ix_claims_item_status", "claims", ["found_item_id", "status"])
    op.execute("CREATE INDEX ix_claims_claimant ON claims (claimant_id, created_at DESC)")

    op.create_table(
        "notifications",
        uid(primary_key=True), campus_fk(),
        uid("user_id", sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", E("notification_kind"), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column("link", sa.String(300)),
        sa.Column("payload", pg.JSONB, nullable=False, server_default="{}"),
        sa.Column("dedupe_key", sa.String(200), nullable=False, unique=True),
        ts("read_at", nullable=True), ts("emailed_at", nullable=True),
        ts("created_at", default=True), ts("updated_at", default=True),
    )
    op.execute("CREATE INDEX ix_notifications_inbox ON notifications (user_id, created_at DESC)")
    op.execute("CREATE INDEX ix_notifications_unread ON notifications (user_id) "
               "WHERE read_at IS NULL")

    op.create_table(
        "outbox_events",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("event_type", sa.String(80), nullable=False),
        sa.Column("aggregate_id", sa.String(64), nullable=False),
        sa.Column("payload", pg.JSONB, nullable=False),
        ts("created_at", default=True), ts("published_at", nullable=True),
        sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text),
    )
    op.execute("CREATE INDEX ix_outbox_unpublished ON outbox_events (id) "
               "WHERE published_at IS NULL")


def downgrade() -> None:
    for t in ("outbox_events", "notifications", "claims", "matches", "lost_reports",
              "custody_events", "found_items", "users", "desks", "locations", "campuses"):
        op.drop_table(t)
    op.execute("DROP FUNCTION IF EXISTS custody_events_append_only() CASCADE")
    bind = op.get_bind()
    for name in ENUMS:
        pg.ENUM(name=name).drop(bind, checkfirst=True)
