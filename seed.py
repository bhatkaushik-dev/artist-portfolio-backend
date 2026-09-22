"""Seed the database with realistic initial artist data.

Idempotent: re-running updates the singleton and upserts content by its natural
key (page slug, YouTube id, FAQ question) rather than duplicating rows.

    python seed.py                 # schema + content
    python seed.py --reset         # DROP and recreate every table first
    python seed.py --with-photos   # also push ./seed_assets/* through the
                                   # real Pillow + Supabase upload pipeline

Photos are only seeded from real files, because ``width``/``height`` must come
from the image bytes — inventing them would defeat the whole pipeline.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select

from app.db.base import Base
from app.db.session import SessionFactory, dispose_engine, engine
from app.models import FAQ, PageContent, Photo, SiteProfile, Video
from app.models.enums import PhotoRole
from app.models.site_profile import SITE_PROFILE_ID
from app.services.storage_service import storage_service

logging.basicConfig(level=logging.INFO, format="%(levelname)-8s %(message)s")
logger = logging.getLogger("seed")

SEED_ASSETS_DIR = Path(__file__).parent / "seed_assets"
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff"}


# ---------------------------------------------------------------------------
# Content
# ---------------------------------------------------------------------------

SITE_PROFILE: dict = {
    "name": "Kaushik Bhat",
    "short_name": "Kaushik Bhat Tabla",
    "role": "Tabla Artist & Teacher",
    "tagline": "Tabla artist & teacher, Bangalore",
    "locale": "en_IN",
    "email": "kaushikgb99@gmail.com",
    "phone": "+919110691605",
    "phone_display": "+91 91106 91605",
    "website_url": "https://kaushikbhat.in",
    "address": {
        "street_address": "JP Nagar",
        "locality": "Bengaluru",
        "region": "Karnataka",
        "postal_code": "560078",
        "country": "IN",
    },
    "geo_lat": 12.9063,
    "geo_lng": 77.5857,
    "area_served": [
        "JP Nagar",
        "Jayanagar",
        "Bannerghatta Road",
        "Banashankari",
        "BTM Layout",
        "Bengaluru",
    ],
    "social_links": [
        {
            "platform": "YouTube",
            "url": "https://www.youtube.com/@KaushikBhatTabla",
            "handle": "@KaushikBhatTabla",
        },
        {
            "platform": "Instagram",
            "url": "https://www.instagram.com/kaushik_bhat",
            "handle": "@kaushik_bhat",
        },
        {
            "platform": "Facebook",
            "url": "https://www.facebook.com/kaushik.bhat.94/",
            "handle": None,
        },
    ],
    "training": [
        {
            "institution": "Family tradition",
            "teacher": "Shri Ganesh Bhat (father)",
            "gharana": None,
            "years": "Started at age 10",
        },
        {
            "institution": "Guru-shishya parampara",
            "teacher": "Pt Gurumurthy Vaidya",
            "gharana": None,
            "years": "14 years",
        },
    ],
    "alternate_names": ["Kaushik Bhat Tabla", "Kaushik G Bhat"],
    "knows_about": [
        "Tabla",
        "Hindustani classical music",
        "Indian classical percussion",
        "Kathak accompaniment",
        "Bhajan and Abhang accompaniment",
        "Taal and laya",
    ],
    "knows_language": ["kn", "hi", "en"],
    "awards": [
        {
            "title": "B-High Graded Artist",
            "awarded_by": "All India Radio",
            "year": None,
        }
    ],
    "opening_hours": [
        {
            "days": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"],
            "opens": "17:00",
            "closes": "21:00",
        },
        {"days": ["Saturday", "Sunday"], "opens": "09:00", "closes": "19:00"},
    ],
    "price_range": "₹₹",
    "currencies_accepted": ["INR"],
    "image_license_url": None,
    "default_image_url": None,
    "logo_url": None,
    "bio_summary": (
        "Kaushik Bhat is a B-High graded tabla artist of All India Radio, "
        "performing Hindustani classical music and teaching tabla in JP "
        "Nagar, Bangalore."
    ),
}


PAGES: list[dict] = [
    {
        "slug": "about",
        "title": "About",
        "subtitle": "A Journey of Dedication",
        "intro": (
            "A tabla artist from Bangalore whose training began at home and "
            "has carried him to concert stages across India."
        ),
        "blocks": {
            # Paragraph blocks stay in JSONB so the artist can restructure the
            # bio without a migration.
            "bio_paragraphs": [
                "Kaushik Bhat's journey into the world of tabla began at the "
                "age of 10. His initial foundation was laid by his father, "
                "Shri Ganesh Bhat, an international artist, who taught him "
                "that every stroke is a sculpture in time.",
                "Today, after 14 years of immersive study, he continues to "
                "evolve under the guidance of the legendary Pt Gurumurthy "
                "Vaidya. He is a B-High graded tabla artist of All India "
                "Radio.",
                "Kaushik has shared the stage with masters of the craft, "
                "including Pt Parameshwar Hegde, Ustaad Shafique Khan, "
                "Dr Ravindra Katoti, Vid Poornima Bhat Kulkarni, Padmashri "
                "Kanyakumari Avasarala, Pt Dhananjay Hegde, Pt Himanshu "
                "Nanda and Shri Koushik Aithal.",
                "Beyond performance, Kaushik is passionate about passing on "
                "the tradition. He conducts tabla classes in JP Nagar, "
                "Bangalore, for students from complete beginner to advanced, "
                "blending traditional training with a modern understanding "
                "of rhythm.",
            ],
            "repertoire": [
                "Hindustani classical",
                "Tabla solo",
                "Kathak",
                "Bhajans",
                "Abhangs",
                "Devotional",
                "Film scores",
            ],
            "collaborators": [
                "Pt Parameshwar Hegde",
                "Ustaad Shafique Khan",
                "Dr Ravindra Katoti",
                "Vid Poornima Bhat Kulkarni",
                "Padmashri Kanyakumari Avasarala",
                "Pt Dhananjay Hegde",
                "Pt Himanshu Nanda",
                "Shri Koushik Aithal",
            ],
        },
        "body": None,
        "seo_title": "About Kaushik Bhat — Tabla Artist, Bangalore",
        "seo_description": (
            "The biography of Kaushik Bhat: fourteen years of tabla under "
            "Pt Gurumurthy Vaidya, a B-High grading from All India Radio, "
            "and performances with Pt Parameshwar Hegde, Ustaad Shafique "
            "Khan and Padmashri Kanyakumari Avasarala."
        ),
        "seo_keywords": [],
        "canonical_path": "/about",
    },
    {
        "slug": "classes",
        "title": "Classes",
        "subtitle": "Tabla Classes in JP Nagar",
        "intro": (
            "Learn from Kaushik Bhat, a B-High graded artist of All India "
            "Radio — in person in Bangalore, or online. Complete beginners "
            "welcome."
        ),
        "blocks": {
            "levels": [
                {
                    "name": "Beginner",
                    "duration": None,
                    "covers": [
                        "Posture, hand position, tuning and the basic bols",
                        "Theka in teentaal, dadra and keherwa",
                    ],
                    "who": "No background needed",
                },
                {
                    "name": "Intermediate",
                    "duration": None,
                    "covers": [
                        "Kaida, peshkar, rela, tukda and chakradhar",
                        "Accompanying vocal and instrumental music",
                    ],
                    "who": "Building repertoire",
                },
                {
                    "name": "Advanced",
                    "duration": None,
                    "covers": [
                        "Full solo repertoire, laykari and improvisation",
                        "Kathak accompaniment, exams and stage performance",
                    ],
                    "who": "Solo and stage",
                },
            ],
            "formats": [
                {
                    "mode": "In person — JP Nagar",
                    "cadence": "Weekday evenings and weekend mornings",
                    "batch_size": "One-to-one or small batch",
                },
                {
                    "mode": "Online — anywhere",
                    "cadence": "Live video lessons, same syllabus",
                    "batch_size": "One-to-one",
                },
            ],
            "requirements": [
                "An instrument is available to practise on during the first "
                "few lessons",
                "Guidance given on buying and tuning a student-grade tabla "
                "once you continue",
            ],
        },
        "body": None,
        "seo_title": "Tabla Classes in JP Nagar, Bangalore | Kaushik Bhat",
        "seo_description": (
            "Learn tabla in JP Nagar, Bangalore with Kaushik Bhat, a B-High "
            "graded artist of All India Radio. Beginner to advanced, "
            "in-person and online classes, weekday evening and weekend "
            "slots."
        ),
        "seo_keywords": [
            "tabla classes in JP Nagar",
            "tabla classes in Bangalore",
            "tabla teacher JP Nagar",
            "tabla lessons Bangalore",
            "learn tabla in Bangalore",
            "tabla class near me Bangalore",
            "online tabla classes",
            "tabla classes Jayanagar",
            "tabla classes Bannerghatta Road",
        ],
        "canonical_path": "/classes",
    },
    {
        "slug": "contact",
        "title": "Contact",
        "subtitle": "Say Hello",
        "intro": (
            "Class enrolment, concert bookings and accompaniment. WhatsApp "
            "gets the quickest reply."
        ),
        "blocks": {
            "enquiry_types": [
                "Tabla classes (in person, JP Nagar)",
                "Tabla classes (online)",
                "Concert booking",
                "Accompaniment / studio session",
                "Something else",
            ],
            "response_note": (
                "This opens WhatsApp with your message ready to send to "
                "+91 91106 91605. Prefer email? kaushikgb99@gmail.com"
            ),
        },
        "body": None,
        "seo_title": "Contact | Kaushik Bhat, Tabla Artist Bangalore",
        "seo_description": (
            "Contact tabla artist Kaushik Bhat in JP Nagar, Bangalore for "
            "class enrolment, concert bookings and accompaniment enquiries. "
            "WhatsApp, phone and email."
        ),
        "seo_keywords": [],
        "canonical_path": "/contact",
    },
]


VIDEOS: list[dict] = [
    {
        "youtube_id": "4MCrgpkslww",
        "title": "Tabla Solo in Drut Teentaal",
        "description": (
            "A tabla solo in drut teentaal by Kaushik Bhat, accompanied on "
            "harmonium by Hari Krishna Purohit — traditional compositions of "
            "the Benares and Farukhabad gharanas played at speed."
        ),
        "upload_date": datetime(2023, 1, 1, tzinfo=UTC),
        "duration": None,
        "sort_order": 0,
        "featured": True,
    },
    {
        "youtube_id": "5086-Z-tDx0",
        "title": "Raag Multani — with Shri Aniruddh Aithal",
        "description": (
            "Kaushik Bhat accompanies vocalist Shri Aniruddh Aithal on tabla "
            "in a Hindustani classical rendition of Raag Multani."
        ),
        "upload_date": datetime(2023, 1, 1, tzinfo=UTC),
        "duration": None,
        "sort_order": 1,
        "featured": True,
    },
    {
        "youtube_id": "D9hymyGA8ng",
        "title": "Raag Hamsadhwani — with Samarth Hegde",
        "description": (
            "Raag Hamsadhwani performed by Samarth Hegde with Kaushik Bhat "
            "on tabla, blending Hindustani classical melody with intricate "
            "rhythmic accompaniment."
        ),
        "upload_date": datetime(2023, 1, 1, tzinfo=UTC),
        "duration": None,
        "sort_order": 2,
        "featured": False,
    },
]


FAQS: list[dict] = [
    {
        "question": "Where are the tabla classes held in Bangalore?",
        "answer": (
            "Classes are held in JP Nagar, Bangalore. The location is "
            "convenient for students from JP Nagar, Jayanagar, Banashankari, "
            "BTM Layout and Bannerghatta Road. Exact directions are shared "
            "once a slot is confirmed."
        ),
        "page_slug": "classes",
        "sort_order": 0,
    },
    {
        "question": "Do you teach complete beginners?",
        "answer": (
            "Yes. Most students start with no background in music at all. "
            "The beginner course starts from how to sit, how to strike each "
            "bol, and basic theka in teentaal, and builds from there at a "
            "pace that suits you."
        ),
        "page_slug": "classes",
        "sort_order": 1,
    },
    {
        "question": "What is the minimum age to learn tabla?",
        "answer": (
            "Children from about seven years of age can start, once their "
            "hands are large enough to hold the bols comfortably. There is "
            "no upper age limit — adult beginners are welcome and form a "
            "good part of the current batch."
        ),
        "page_slug": "classes",
        "sort_order": 2,
    },
    {
        "question": "Are online tabla classes available?",
        "answer": (
            "Yes. Online classes over video call are available for students "
            "outside Bangalore and for anyone who prefers to learn from "
            "home. The syllabus is the same as the in-person course."
        ),
        "page_slug": "classes",
        "sort_order": 3,
    },
    {
        "question": "How long is each class and how often do they run?",
        "answer": (
            "Classes typically run once or twice a week for about an hour, "
            "in small batches or one-to-one. Weekday evening and weekend "
            "morning slots are available."
        ),
        "page_slug": "classes",
        "sort_order": 4,
    },
    {
        "question": "Do I need my own tabla to begin?",
        "answer": (
            "Not for the first few classes — an instrument is available to "
            "practise on during the lesson. Once you decide to continue, "
            "guidance is given on buying a good student-grade set and on "
            "tuning and maintaining it."
        ),
        "page_slug": "classes",
        "sort_order": 5,
    },
    {
        "question": "Will I be prepared for exams or stage performance?",
        "answer": (
            "Yes. Students are prepared for graded music examinations where "
            "they want to take them, and get regular opportunities to "
            "perform — both solo and as accompaniment for vocal, "
            "instrumental and Kathak recitals."
        ),
        "page_slug": "classes",
        "sort_order": 6,
    },
    {
        "question": "What does Kaushik Bhat's own training background cover?",
        "answer": (
            "Kaushik Bhat is a B-High graded tabla artist of All India "
            "Radio. He began under his father Shri Ganesh Bhat and has "
            "trained for over fourteen years under Pt Gurumurthy Vaidya, "
            "performing with artists including Pt Parameshwar Hegde, "
            "Ustaad Shafique Khan and Padmashri Kanyakumari Avasarala."
        ),
        "page_slug": "about",
        "sort_order": 7,
    },
]


# ---------------------------------------------------------------------------
# Upserts
# ---------------------------------------------------------------------------


async def seed_site_profile(session) -> None:
    profile = await session.get(SiteProfile, SITE_PROFILE_ID)
    if profile is None:
        profile = SiteProfile(id=SITE_PROFILE_ID, **SITE_PROFILE)
        session.add(profile)
        logger.info("Created site profile: %s", SITE_PROFILE["name"])
    else:
        for field, value in SITE_PROFILE.items():
            setattr(profile, field, value)
        logger.info("Updated site profile: %s", SITE_PROFILE["name"])


async def seed_pages(session) -> None:
    for data in PAGES:
        existing = await session.scalar(
            select(PageContent).where(PageContent.slug == data["slug"])
        )
        if existing is None:
            session.add(PageContent(**data))
            logger.info("Created page: /%s", data["slug"])
        else:
            for field, value in data.items():
                setattr(existing, field, value)
            logger.info("Updated page: /%s", data["slug"])


async def seed_videos(session) -> None:
    for data in VIDEOS:
        existing = await session.scalar(
            select(Video).where(Video.youtube_id == data["youtube_id"])
        )
        thumbnail = f"https://i.ytimg.com/vi/{data['youtube_id']}/maxresdefault.jpg"
        if existing is None:
            session.add(Video(thumbnail_url=thumbnail, **data))
            logger.info("Created video: %s", data["title"][:60])
        else:
            for field, value in data.items():
                setattr(existing, field, value)
            logger.info("Updated video: %s", data["title"][:60])


async def seed_faqs(session) -> None:
    for data in FAQS:
        existing = await session.scalar(
            select(FAQ).where(FAQ.question == data["question"])
        )
        if existing is None:
            session.add(FAQ(**data))
            logger.info("Created FAQ: %s", data["question"][:60])
        else:
            for field, value in data.items():
                setattr(existing, field, value)
            logger.info("Updated FAQ: %s", data["question"][:60])


async def seed_photos(session) -> None:
    """Push every image in ./seed_assets through the real upload pipeline.

    Role is taken from the filename prefix (``hero-``, ``about-``, ``classes-``);
    anything else lands in the gallery. Alt text comes from the rest of the
    filename, so ``hero-aditya-at-chowdiah-hall.jpg`` reads sensibly.
    """
    if not SEED_ASSETS_DIR.is_dir():
        logger.warning(
            "No %s directory — skipping photos. Drop images there and re-run "
            "with --with-photos.",
            SEED_ASSETS_DIR.name,
        )
        return

    files = sorted(
        p for p in SEED_ASSETS_DIR.iterdir() if p.suffix.lower() in IMAGE_SUFFIXES
    )
    if not files:
        logger.warning("%s is empty — skipping photos", SEED_ASSETS_DIR.name)
        return

    await storage_service.ensure_bucket()
    role_counters: dict[PhotoRole, int] = {}

    for path in files:
        stem = path.stem
        role = PhotoRole.GALLERY
        for candidate in (PhotoRole.HERO, PhotoRole.ABOUT, PhotoRole.CLASSES):
            if stem.startswith(f"{candidate.value}-"):
                role = candidate
                stem = stem[len(candidate.value) + 1 :]
                break

        alt = stem.replace("-", " ").replace("_", " ").strip().capitalize()

        existing = await session.scalar(select(Photo).where(Photo.alt == alt))
        if existing is not None:
            logger.info("Photo already seeded, skipping: %s", alt)
            continue

        stored = await storage_service.process_and_store(
            path.read_bytes(), role=role.value, alt=alt
        )
        order = role_counters.get(role, 0)
        role_counters[role] = order + 1

        session.add(
            Photo(
                role=role,
                src=stored.webp_url,
                download_url=stored.jpeg_url,
                storage_path_webp=stored.webp_path,
                storage_path_jpeg=stored.jpeg_path,
                width=stored.width,
                height=stored.height,
                alt=alt,
                caption=None,
                sort_order=order,
                byte_size_webp=stored.webp_size,
                byte_size_jpeg=stored.jpeg_size,
            )
        )
        logger.info(
            "Uploaded photo: %s (%dx%d, role=%s)",
            alt,
            stored.width,
            stored.height,
            role.value,
        )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


async def run(*, reset: bool, with_photos: bool) -> None:
    async with engine.begin() as conn:
        if reset:
            logger.warning("Dropping all tables")
            await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Schema ready")

    async with SessionFactory() as session:
        await seed_site_profile(session)
        await seed_pages(session)
        await seed_videos(session)
        await seed_faqs(session)
        if with_photos:
            await seed_photos(session)
        await session.commit()

    await storage_service.shutdown()
    await dispose_engine()
    logger.info("Seed complete")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Drop and recreate every table before seeding (destructive)",
    )
    parser.add_argument(
        "--with-photos",
        action="store_true",
        help="Upload images from ./seed_assets via the Pillow + Supabase pipeline",
    )
    args = parser.parse_args()

    if args.reset:
        confirm = input("This DROPS all portfolio tables. Type 'yes' to continue: ")
        if confirm.strip().lower() != "yes":
            logger.info("Aborted")
            return

    asyncio.run(run(reset=args.reset, with_photos=args.with_photos))


if __name__ == "__main__":
    main()
