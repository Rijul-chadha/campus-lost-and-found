"""Idempotent demo data: one campus, locations, two desks, staff accounts, sample items.

    python -m scripts.seed

Sign in with any address @campus.ca (codes appear in Mailpit at :8025 and in API logs).
    lost@campus.ca   -> desk staff at Campus Security (opens the desk dashboard)
    admin@campus.ca  -> admin
    sam@campus.ca    -> member who found the demo items
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update

from app.core.config import get_settings
from app.db.session import get_sessionmaker
from app.domain import privacy
from app.domain.enums import CustodyEventType, HolderType, ItemStatus, Role
from app.domain.extraction import embedding_text, extract_brand, extract_colors, extract_item
from app.integrations.embeddings import get_embedder
from app.modules.auth.models import User
from app.modules.campus.models import Campus, Desk, Location
from app.modules.items.models import CustodyEvent, FoundItem

DOMAIN = "campus.ca"
DESK_EMAIL = f"lost@{DOMAIN}"
OLD_DOMAINS = ("northfield.edu", "mail.northfield.edu", "campus.lost.ca")

LOCATIONS = [
    ("Main Library", ["library", "lib", "stacks"], 43.6644, -79.3995),
    ("Engineering Building", ["engineering", "eng building", "eng"], 43.6597, -79.3972),
    ("Student Centre", ["student centre", "student center", "suc"], 43.6608, -79.3962),
    ("Athletic Centre", ["gym", "athletic centre", "rec centre", "pool"], 43.6626, -79.4005),
    ("Dining Hall", ["cafeteria", "dining hall", "caf"], 43.6650, -79.3960),
    ("Science Complex", ["science building", "chem building", "labs"], 43.6611, -79.3940),
    ("North Residence", ["residence", "rez", "north res", "dorms"], 43.6680, -79.3990),
    ("Bus Loop", ["bus stop", "bus loop", "shuttle"], 43.6590, -79.4010),
    ("Lecture Hall A", ["lecture hall", "hall a", "auditorium"], 43.6620, -79.3980),
]

SAMPLE_ITEMS = [
    ("AirPods Pro case", "White AirPods Pro charging case, small scratch on the lid",
     "Main Library", 5, "Initials JK written inside the lid"),
    ("Black backpack", "Black Herschel backpack with a calculus textbook inside",
     "Engineering Building", 20, "Has a keychain shaped like a cactus"),
    ("Water bottle", "Navy blue Hydro Flask water bottle covered in stickers",
     "Main Library", 30, "One sticker is a pixel-art cat"),
    ("Keys on lanyard", "Set of 3 keys on a red lanyard with a car fob",
     "Dining Hall", 10, "Toyota fob, one key is painted green"),
    ("Grey hoodie", "Grey university hoodie size M", "Lecture Hall A", 48,
     "Small ink stain on the left cuff"),
    ("Student card", "Student ID card found on the floor", "Student Centre", 3,
     "Name starts with A, photo has glasses"),
    ("Umbrella", "Compact black umbrella with wooden handle", "Bus Loop", 26,
     "Handle has a crack near the top"),
    ("Sunglasses", "Ray-Ban sunglasses in a brown case", "Dining Hall", 7,
     "Case has a gold logo"),
]


async def main() -> None:
    settings = get_settings()
    emb = get_embedder(settings.embedding_provider, settings.embedding_model)
    async with get_sessionmaker()() as s:
        existing = (await s.execute(select(Campus).where(Campus.slug == "northfield"))).scalar()
        if existing:
            # Earlier seeds used other domains; move demo data onto the current one.
            existing.email_domains = [DOMAIN]
            for old in OLD_DOMAINS:
                users = (await s.execute(select(User).where(
                    User.campus_id == existing.id, User.email.like(f"%@{old}")))).scalars().all()
                for u in users:
                    local = u.email.split("@")[0]
                    u.email = DESK_EMAIL if local == "desk" else f"{local}@{DOMAIN}"
                await s.execute(update(Desk).where(Desk.campus_id == existing.id,
                                                   Desk.contact_email.like(f"%@{old}"))
                                .values(contact_email=DESK_EMAIL))
            await s.commit()
            print(f"seed: campus present; sign-in domain is now @{DOMAIN}")
            return

        campus = Campus(id=uuid.uuid4(), slug="northfield", name="Northfield University",
                        email_domains=[DOMAIN],
                        timezone="America/Toronto")
        s.add(campus)
        await s.flush()
        locs = {name: Location(id=uuid.uuid4(), campus_id=campus.id, name=name, aliases=al,
                               lat=lat, lng=lng) for name, al, lat, lng in LOCATIONS}
        s.add_all(locs.values())
        await s.flush()
        security = Desk(id=uuid.uuid4(), campus_id=campus.id, name="Campus Security Office",
                        location_id=locs["Student Centre"].id,
                        hours="Open 24/7, ground floor of the Student Centre",
                        contact_email=DESK_EMAIL)
        library = Desk(id=uuid.uuid4(), campus_id=campus.id, name="Library Front Desk",
                       location_id=locs["Main Library"].id, hours="Mon-Fri 8am-10pm")
        s.add_all([security, library])
        await s.flush()

        desk_user = User(id=uuid.uuid4(), campus_id=campus.id, email=DESK_EMAIL,
                         display_name="Lost & Found Desk", role=Role.DESK, desk_id=security.id)
        admin = User(id=uuid.uuid4(), campus_id=campus.id, email=f"admin@{DOMAIN}",
                     display_name="Admin", role=Role.ADMIN)
        finder = User(id=uuid.uuid4(), campus_id=campus.id, email=f"sam@{DOMAIN}",
                      display_name="Sam (demo finder)")
        s.add_all([desk_user, admin, finder])
        await s.flush()

        now = datetime.now(UTC)
        texts = []
        for title, desc, *_ in SAMPLE_ITEMS:
            cat, typ, _ = extract_item(f"{title}. {desc}")
            texts.append(embedding_text(title=title, description=desc, item_type=typ,
                                        category=cat, colors=extract_colors(desc),
                                        brand=extract_brand(desc)))
        vectors = emb.embed(texts)
        for i, ((title, desc, loc, hours_ago, secret), vec) in enumerate(
                zip(SAMPLE_ITEMS, vectors, strict=True)):
            cat, typ, _ = extract_item(f"{title}. {desc}")
            at_desk = i % 2 == 0
            item = FoundItem(
                id=uuid.uuid4(), campus_id=campus.id, reporter_id=finder.id, title=title,
                description=desc, public_title=privacy.public_title(title, typ),
                public_description=privacy.redact(desc), category=cat, item_type=typ,
                colors=extract_colors(desc), brand=extract_brand(desc),
                is_sensitive=privacy.is_sensitive(typ), found_location_id=locs[loc].id,
                found_at=now - timedelta(hours=hours_ago),
                holder_type=HolderType.DESK if at_desk else HolderType.FINDER,
                holder_desk_id=security.id if at_desk else None,
                status=ItemStatus.AVAILABLE, upload_keys=[], photo_keys=[],
                private_detail=secret, embedding=vec, embedding_model=emb.name,
                expires_at=now + timedelta(days=settings.item_retention_days),
            )
            s.add(item)
            await s.flush()
            s.add(CustodyEvent(campus_id=campus.id, found_item_id=item.id,
                               event_type=CustodyEventType.REPORTED, actor_id=finder.id,
                               to_holder="desk" if at_desk else "finder", note="seed"))
        await s.commit()
        print(f"seed: created campus {campus.name} with {len(SAMPLE_ITEMS)} items")


if __name__ == "__main__":
    asyncio.run(main())
