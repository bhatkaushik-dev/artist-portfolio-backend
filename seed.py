"""Seed one tenant's content.

Idempotent: re-running updates that tenant's profile and upserts content by its
natural key (page slug, YouTube id, FAQ question, photo alt) rather than
duplicating rows. Every lookup is scoped to the tenant, so seeding artist B
never overwrites A.

    python seed.py                        # the only tenant, if there is one
    python seed.py --tenant kaushik-bhat  # pick one explicitly
    python seed.py --list-tenants         # show available slugs
    python seed.py --reset                # DROP and recreate every table first
    python seed.py --with-photos          # also push ./seed_assets/* through
                                          # the Pillow + Supabase pipeline
    python seed.py --with-photos --assets-dir ../tabla-portfolio/public/photos/originals

Photos are only seeded from real files, because ``width``/``height`` must come
from the image bytes — inventing them would defeat the whole pipeline. Pages
reference photos by id, so seed with ``--with-photos`` (or upload first) for the
headers and story chapters to have pictures; references to photos that do not
exist yet are left empty and can be picked in the admin.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select

from app.db.base import Base
from app.db.session import SessionFactory, dispose_engine, engine
from app.models import FAQ, PageContent, Photo, SiteProfile, Tenant, Video
from app.models.enums import PhotoRole
from app.schemas.page_blocks import validate_blocks
from app.services.storage_service import storage_service

logging.basicConfig(level=logging.INFO, format="%(levelname)-8s %(message)s")
logger = logging.getLogger("seed")

SEED_ASSETS_DIR = Path(__file__).parent / "seed_assets"
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff"}


# ---------------------------------------------------------------------------
# Photos
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PhotoSpec:
    role: PhotoRole
    alt: str
    caption: str
    order: int = 0


# Keyed by the source file's stem, exactly as the portfolio names them in
# public/photos/originals. ``alt`` is the natural key on re-runs, and doubles
# as how pages below find the uploaded photo's id.
#
# The studio shoot is the gallery, in display order. The three family-album
# scans are ``about`` — shown in the /about story, kept out of the gallery.
PHOTO_MANIFEST: dict[str, PhotoSpec] = {
    "kaushik-bhat-tabla-hero-wide": PhotoSpec(
        PhotoRole.GALLERY,
        "Kaushik Bhat, B-High graded tabla artist, smiling among his tabla set in the studio",
        "Among the drums",
        0,
    ),
    "kaushik-bhat-with-tabla-portrait": PhotoSpec(
        PhotoRole.GALLERY,
        "Kaushik Bhat standing with his tabla pair, in a cream kurta and red shawl",
        "With the tabla pair",
        1,
    ),
    "kaushik-bhat-tabla-teacher-jp-nagar-studio": PhotoSpec(
        PhotoRole.GALLERY,
        "Tabla teacher Kaushik Bhat smiling as he plays, JP Nagar, Bangalore",
        "At the tabla",
        2,
    ),
    "kaushik-bhat-tabla-playing-studio": PhotoSpec(
        PhotoRole.GALLERY,
        "Kaushik Bhat playing tabla, surrounded by a set of tuned dayans",
        "Mid-stroke",
        3,
    ),
    "kaushik-bhat-standing-portrait": PhotoSpec(
        PhotoRole.GALLERY,
        "Portrait of tabla artist Kaushik Bhat standing in a maroon kurta, holding a dayan",
        "Portrait",
        4,
    ),
    "kaushik-bhat-tabla-studio-cream-kurta": PhotoSpec(
        PhotoRole.GALLERY,
        "Kaushik Bhat playing tabla in a cream kurta and red shawl",
        "In the studio",
        5,
    ),
    "kaushik-bhat-tabla-tuning": PhotoSpec(
        PhotoRole.GALLERY,
        "Kaushik Bhat tuning his tabla with a hammer before playing",
        "Tuning",
        6,
    ),
    "kaushik-bhat-tabla-cream-kurta-playing": PhotoSpec(
        PhotoRole.GALLERY,
        "Kaushik Bhat playing tabla and gesturing mid-phrase, in a cream kurta and red shawl",
        "Mid-phrase",
        7,
    ),
    "kaushik-bhat-tabla-full-set": PhotoSpec(
        PhotoRole.GALLERY,
        "Kaushik Bhat seated behind a set of four tabla drums in the studio",
        "The full set",
        8,
    ),
    "kaushik-bhat-tabla-hero-portrait": PhotoSpec(
        PhotoRole.GALLERY,
        "Kaushik Bhat, tabla artist and teacher in Bangalore, seated with his tabla",
        "With the dayan",
        9,
    ),
    "kaushik-bhat-parents-ganesh-sunanda-bhat": PhotoSpec(
        PhotoRole.ABOUT,
        "Stone sculptor Shri Ganesh Bhat and Smt. Sunanda Bhat, parents of tabla artist "
        "Kaushik Bhat",
        "With his parents",
        0,
    ),
    "kaushik-bhat-tabla-childhood-concert": PhotoSpec(
        PhotoRole.ABOUT,
        "A young Kaushik Bhat performing tabla on stage in a white kurta",
        "An early concert",
        1,
    ),
    "kaushik-bhat-with-guru-pt-gurumurthy-vaidya": PhotoSpec(
        PhotoRole.ABOUT,
        "Kaushik Bhat with his guru, tabla maestro Pt. Gurumurthy Vaidya",
        "With Pt. Gurumurthy Vaidya",
        2,
    ),
}


@dataclass(frozen=True)
class PhotoRef:
    """A photo named by manifest key, swapped for its id once it exists."""

    key: str


HERO_PORTRAIT = PhotoRef("kaushik-bhat-tabla-hero-portrait")
HERO_WIDE = PhotoRef("kaushik-bhat-tabla-hero-wide")
WITH_TABLA = PhotoRef("kaushik-bhat-with-tabla-portrait")
PLAYING = PhotoRef("kaushik-bhat-tabla-playing-studio")
TEACHING = PhotoRef("kaushik-bhat-tabla-teacher-jp-nagar-studio")
GESTURE = PhotoRef("kaushik-bhat-tabla-cream-kurta-playing")
PARENTS = PhotoRef("kaushik-bhat-parents-ganesh-sunanda-bhat")
CHILDHOOD = PhotoRef("kaushik-bhat-tabla-childhood-concert")
GURU = PhotoRef("kaushik-bhat-with-guru-pt-gurumurthy-vaidya")


# ---------------------------------------------------------------------------
# Content
# ---------------------------------------------------------------------------

SITE_PROFILE: dict = {
    "name": "Kaushik Bhat",
    "short_name": "Kaushik Bhat Tabla",
    "role": "Tabla Artist & Teacher",
    "tagline": "Tabla instructor, JP Nagar, Bengaluru",
    "locale": "en_IN",
    "email": "kaushikgb99@gmail.com",
    "phone": "+919110691605",
    "phone_display": "+91 91106 91605",
    "website_url": "https://kaushikbhat.in",
    # Classes are held inside Swara Hindustani Classical Music School, so this
    # is the school's address exactly as it publishes it on its own website.
    "address": {
        "venue": "Swara Hindustani Classical Music School",
        "street_address": "#38, 3rd Main, Sarakki",
        "locality": "JP Nagar 1st Phase",
        "area": "JP Nagar",
        "city": "Bengaluru",
        "region": "Karnataka",
        "postal_code": "560078",
        "country": "IN",
    },
    # TODO: still the approximate JP Nagar centre, not the building.
    "geo_lat": 12.9063,
    "geo_lng": 77.5857,
    "area_served": [
        "JP Nagar",
        "Jayanagar",
        "Banashankari",
        "BTM Layout",
        "Bannerghatta Road",
        "South Bengaluru",
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
    "training": {
        "start_age": 10,
        "years": 14,
        "teacher": "Pt Gurumurthy Vaidya",
        "father": "Shri Ganesh Bhat",
        "grade": "B-High",
        "grading_body": "All India Radio",
    },
    "alternate_names": ["Kaushik Bhat Tabla", "Kaushik G Bhat"],
    "knows_about": [
        "Tabla",
        "Hindustani classical music",
        "Indian classical percussion",
        "Kathak accompaniment",
        "Bhajan and Abhang accompaniment",
        "Taal and laya",
    ],
    "knows_language": ["Kannada", "Hindi", "English"],
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
    "school": {
        "name": "Kaushik Bhat Tabla Classes",
        "alternate_name": "Tabla Classes in JP Nagar",
        "description": (
            "Tabla classes in JP Nagar, South Bengaluru, for beginners to advanced "
            "students, taught by Kaushik Bhat, a B-High graded tabla artist of All "
            "India Radio. Classes are held inside the Swara Hindustani Classical "
            "Music School; online lessons are also available."
        ),
        # Filled from the teaching photo once photos are seeded.
        "image_url": None,
        "offer_catalog_name": "Tabla courses",
        "offerings": [
            "Beginner tabla course",
            "Intermediate tabla course",
            "Advanced tabla and solo repertoire",
            "Online tabla classes",
        ],
    },
    "image_credit_text": "Kaushik Bhat",
    "image_copyright_notice": "© Kaushik Bhat",
    "image_license_url": "/gallery#licence",
    "image_acquire_license_url": "/contact",
    # Filled from the hero portrait once photos are seeded.
    "default_image_url": None,
    "logo_url": None,
    "bio_summary": (
        "Expert tabla instructor in Bangalore and B-High graded tabla artist of All "
        "India Radio, teaching tabla classes in JP Nagar, South Bengaluru."
    ),
}


PAGES: list[dict] = [
    {
        "slug": "home",
        "title": "Home",
        "subtitle": None,
        "eyebrow": None,
        "heading": "Kaushik",
        "highlight": "Bhat",
        "intro": None,
        "header_photo_id": HERO_PORTRAIT,
        "body": None,
        "blocks": {
            "hero": {"tagline": "Tabla Artist | Percussionist"},
            "about_band": {
                "eyebrow": "About",
                "heading": "Rooted in\nrhythm,",
                "highlight": "shaped by tradition.",
                "body": (
                    "Kaushik Bhat is an accomplished tabla player and a "
                    "**B-High graded artist with All India Radio**."
                ),
                "link": {"label": "Read his story", "href": "/about"},
                "photo_id": HERO_WIDE,
            },
        },
        "seo_title": "Kaushik Bhat | Expert Tabla Instructor in Bangalore",
        "seo_description": (
            "Learn tabla in South Bengaluru with Kaushik Bhat, a B-High graded All "
            "India Radio artist. Tabla classes in JP Nagar for all levels, in person "
            "or online."
        ),
        "og_title": None,
        "og_description": (
            "Tabla classes in JP Nagar, South Bengaluru, with B-High graded All India "
            "Radio artist Kaushik Bhat."
        ),
        "seo_keywords": [
            "Kaushik Bhat",
            "Kaushik Bhat Tabla",
            "Kaushik G Bhat",
            "Tabla classes in JP Nagar",
            "Tabla classes near me",
            "Learn tabla in South Bengaluru",
            "Expert tabla instructor in Bangalore",
            "Tabla teacher JP Nagar",
            "Tabla classes in Bangalore",
            "Tabla artist Bangalore",
            "Online tabla classes",
            "Indian classical music",
            "Hindustani classical tabla",
            "AIR B-High artist",
            "Tabla solo",
        ],
        "canonical_path": "/",
    },
    {
        "slug": "about",
        "title": "About",
        "subtitle": None,
        "eyebrow": "About",
        "heading": "Kaushik",
        "highlight": "Bhat",
        "intro": None,
        # A 325px scan, so the site frames it as a small print, not full-bleed.
        "header_photo_id": CHILDHOOD,
        "body": None,
        "blocks": {
            # Kaushik's own biography, word for word and in his order — do not
            # reword it. One chapter per family-album photograph.
            "chapters": [
                {
                    "id": "early-years",
                    "title": "Early Years",
                    "photo_id": PARENTS,
                    "caption": "With his parents, Smt. Sunanda Bhat & Shri Ganesh Bhat",
                    "paragraphs": [
                        "Kaushik Bhat is an accomplished tabla player and a "
                        "**B-High graded artist with All India Radio**.",
                        "Hailing from a traditional priest family rooted in the "
                        "village of **Idagunji in Uttara Kannada**, Kaushik was born "
                        "to **Smt. Sunanda Bhat** and the renowned stone sculptor "
                        "**Shri Ganesh Bhat**. His musical journey began at age 10 "
                        "under his father’s initial guidance.",
                    ],
                },
                {
                    "id": "training",
                    "title": "Training",
                    "photo_id": GURU,
                    "caption": "With his guru, Pt. Gurumurthy Vaidya",
                    "paragraphs": [
                        "For the past 14 years, he has rigorously honed his craft "
                        "under the esteemed tutelage of **Pt. Gurumurthy Vaidya**. An "
                        "outstanding academic musician, Kaushik is a recipient of the "
                        "prestigious **CCRT Scholarship**, has completed his "
                        "**Visharada and Vidwath** exams with distinction, and has won "
                        "numerous state and national-level competitions. He has also "
                        "been awarded dedicated scholarships by Sapthak Bengaluru and "
                        "Shree Rama Kalavedike.",
                        "Known for his versatility, Kaushik excels in **tabla solo "
                        "recitals** as well as accompaniment for Hindustani classical "
                        "vocals, instrumental performances, and Kathak dance. His "
                        "rhythmic expertise extends into the studio, where he "
                        "regularly records for devotional albums, Abhangs, Bhajans, "
                        "and feature film soundtracks.",
                    ],
                },
                {
                    "id": "career",
                    "title": None,
                    "photo_id": None,
                    "caption": None,
                    "paragraphs": [
                        "Throughout his career, Kaushik has had the privilege of "
                        "accompanying eminent artists, including **Pt. Vinayak "
                        "Torvi**, **Pt. Parameshwar Hegde**, **Ustad Shafique Khan**, "
                        "**Dr. Ashok Hugganavar**, **Vidushi Poornima Bhat Kulkarni**, "
                        "and **Ustad Shakir Khan**. He has showcased his art at major "
                        "cultural organizations and prestigious venues across the "
                        "country, with notable performances at the Bengaluru Ganesh "
                        "Utsava, SPIC MACAY, Shri Rama Kalavedike, Sapthak Bengaluru, "
                        "and the Bijapure Harmonium Foundation.",
                        "Alongside his deep commitment to Hindustani classical music, "
                        "Kaushik successfully balances his passion for the tabla with "
                        "a career as a **Software Engineer**. With the continued "
                        "blessings of his gurus and elders, a bright and promising "
                        "career awaits this talented musician.",
                    ],
                },
            ],
            "print_photo_id": WITH_TABLA,
        },
        "seo_title": "About Kaushik Bhat — Tabla Artist, Bangalore",
        "seo_description": (
            "The biography of Kaushik Bhat: fourteen years of tabla under Pt "
            "Gurumurthy Vaidya, a B-High grading from All India Radio, a CCRT "
            "scholarship, and performances with Pt Vinayak Torvi, Pt Parameshwar "
            "Hegde and Ustad Shafique Khan."
        ),
        "og_title": "About Kaushik Bhat — Tabla Artist",
        "og_description": (
            "Fourteen years under Pt Gurumurthy Vaidya, B-High graded artist of All "
            "India Radio, performing Hindustani classical music across India."
        ),
        "seo_keywords": [],
        "canonical_path": "/about",
    },
    {
        "slug": "performances",
        "title": "Performances",
        "subtitle": None,
        "eyebrow": "Artistry in motion",
        "heading": "Watch &",
        "highlight": "Experience",
        "intro": "Tabla solo and classical accompaniment, recorded live.",
        "header_photo_id": PLAYING,
        "body": None,
        "blocks": {
            "channel_button_label": "YouTube channel",
            "closing": {
                "heading": "More on the YouTube channel",
                "button_label": "Visit @KaushikBhatTabla",
            },
        },
        "seo_title": "Tabla Performances & Videos | Kaushik Bhat",
        "seo_description": (
            "Watch Kaushik Bhat perform tabla: a solo in drut teentaal, Raag Multani "
            "with Shri Aniruddh Aithal and Raag Hamsadhwani with Samarth Hegde."
        ),
        "og_title": "Tabla Performances & Videos — Kaushik Bhat",
        "og_description": (
            "Tabla solo in drut teentaal, Raag Multani and Raag Hamsadhwani — "
            "Hindustani classical performances by Kaushik Bhat."
        ),
        "seo_keywords": [],
        "canonical_path": "/performances",
    },
    {
        "slug": "gallery",
        "title": "Gallery",
        "subtitle": None,
        "eyebrow": "Gallery",
        "heading": "Moments in",
        "highlight": "Rhythm",
        "intro": None,
        "header_photo_id": None,
        "body": None,
        "blocks": {
            "count_note": "Free to download",
            # The target of ImageObject.license — the terms live at a real URL.
            "licence_note": (
                "Photographs may be used for event promotion with credit to Kaushik "
                "Bhat. For other uses, please [get in touch](/contact)."
            ),
        },
        "seo_title": "Photo Gallery | Kaushik Bhat, Tabla Artist",
        "seo_description": (
            "Studio photographs of tabla artist Kaushik Bhat, free to download in full "
            "resolution for press, posters and event listings."
        ),
        "og_title": "Photo Gallery — Kaushik Bhat, Tabla Artist",
        "og_description": (
            "Studio photographs of Kaushik Bhat, downloadable in full resolution."
        ),
        "seo_keywords": [],
        "canonical_path": "/gallery",
    },
    {
        "slug": "classes",
        "title": "Tabla Classes",
        "subtitle": None,
        "eyebrow": "Learn tabla",
        "heading": "Tabla Classes in",
        "highlight": "JP Nagar",
        "intro": (
            "Learn tabla in South Bengaluru from a B-High graded All India Radio "
            "artist — in person in JP Nagar 1st Phase, or online. Complete beginners "
            "welcome."
        ),
        "header_photo_id": GESTURE,
        "body": None,
        "blocks": {
            "formats": [
                {
                    "icon": "map-pin",
                    "title": "In person, JP Nagar 1st Phase",
                    "body": (
                        "Inside Swara Hindustani Classical Music School — near "
                        "Jayanagar, Banashankari and BTM Layout."
                    ),
                },
                {
                    "icon": "monitor",
                    "title": "Online, anywhere",
                    "body": "Live video lessons on the same syllabus.",
                },
                {
                    "icon": "users",
                    "title": "One-to-one or small batch",
                    "body": "Weekday evenings and weekend slots available.",
                },
            ],
            "faq_heading": {
                "eyebrow": "Questions",
                "heading": "Frequently",
                "highlight": "asked",
            },
            "cta": {
                "eyebrow": "Enrolment",
                "heading": "Start learning",
                "highlight": "this month",
                "body": (
                    "Tell Kaushik about your experience and when you're free, and "
                    "he'll suggest a batch or one-to-one slot."
                ),
                "primary": {"label": "Enquire about classes", "href": "/contact"},
                "secondary": {"label": "Hear him play", "href": "/performances"},
                "photo_id": None,
            },
        },
        "seo_title": "Tabla Classes in JP Nagar, South Bengaluru | Kaushik Bhat",
        "seo_description": (
            "Tabla classes in JP Nagar with Kaushik Bhat, a B-High graded All India "
            "Radio artist. Learn tabla in South Bengaluru, beginner to advanced, in "
            "person or online."
        ),
        "og_title": "Tabla Classes in JP Nagar, South Bengaluru | Kaushik Bhat",
        "og_description": (
            "Learn tabla in South Bengaluru — beginner to advanced tabla classes in "
            "JP Nagar, in person or online, with B-High graded All India Radio "
            "artist Kaushik Bhat."
        ),
        "seo_keywords": [
            "tabla classes in JP Nagar",
            "tabla classes near me",
            "learn tabla in South Bengaluru",
            "expert tabla instructor in Bangalore",
            "tabla teacher JP Nagar",
            "tabla classes JP Nagar 1st Phase",
            "tabla classes in Bangalore",
            "online tabla classes",
            "tabla classes Jayanagar",
            "tabla classes Banashankari",
        ],
        "canonical_path": "/classes",
    },
    {
        "slug": "contact",
        "title": "Contact",
        "subtitle": None,
        "eyebrow": "Get in touch",
        "heading": "Say",
        "highlight": "Hello",
        "intro": None,
        "header_photo_id": WITH_TABLA,
        "body": None,
        "blocks": {
            "enquiry_types": [
                "Tabla classes (in person, JP Nagar)",
                "Tabla classes (online)",
                "Concert booking",
                "Accompaniment / studio session",
                "Something else",
            ],
            "location": {
                "heading": "Where classes are held",
                "note": "Classes are held inside the Swara Hindustani Classical Music School.",
            },
        },
        "seo_title": "Contact | Tabla Classes in JP Nagar, Bengaluru — Kaushik Bhat",
        "seo_description": (
            "Enquire about tabla classes in JP Nagar, South Bengaluru. Classes are "
            "held inside Swara Hindustani Classical Music School, JP Nagar 1st Phase. "
            "WhatsApp, phone or email."
        ),
        "og_title": "Contact Kaushik Bhat — Tabla Classes in JP Nagar, Bengaluru",
        "og_description": (
            "Class enrolment, concert bookings and accompaniment — Swara Hindustani "
            "Classical Music School, JP Nagar 1st Phase, Bengaluru."
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


# Rendered on /classes as an accordion and mirrored into FAQPage JSON-LD.
FAQS: list[dict] = [
    {
        "question": "Where are the tabla classes held in Bangalore?",
        "answer": (
            "Classes are held inside the Swara Hindustani Classical Music School, "
            "#38, 3rd Main, Sarakki, JP Nagar 1st Phase, Bengaluru 560078. It is "
            "convenient for students across South Bengaluru — JP Nagar, Jayanagar, "
            "Banashankari, BTM Layout and Bannerghatta Road."
        ),
        "page_slug": "classes",
        "sort_order": 0,
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
        "sort_order": 1,
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
        "sort_order": 2,
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
        "sort_order": 3,
    },
    {
        "question": "Are online tabla classes available?",
        "answer": (
            "Yes. Online classes over video call are available for students "
            "outside Bangalore and for anyone who prefers to learn from "
            "home. The syllabus is the same as the in-person course."
        ),
        "page_slug": "classes",
        "sort_order": 4,
    },
    {
        "question": "How long is each class and how often do they run?",
        "answer": (
            "Classes typically run once or twice a week for about an hour, "
            "in small batches or one-to-one. Weekday (evening) and weekend "
            "(morning/afternoon) slots are available."
        ),
        "page_slug": "classes",
        "sort_order": 5,
    },
]

# Dropped from the site in the redesign. Hidden rather than deleted, so a
# re-seed never destroys an FAQ someone may have edited in the admin.
RETIRED_FAQ_QUESTIONS: tuple[str, ...] = (
    "Will I be prepared for exams or stage performance?",
    "What does Kaushik Bhat's own training background cover?",
)


# ---------------------------------------------------------------------------
# Upserts
# ---------------------------------------------------------------------------


async def seed_site_profile(session, tenant: Tenant) -> SiteProfile:
    profile = await session.scalar(
        select(SiteProfile).where(SiteProfile.tenant_id == tenant.id)
    )
    if profile is None:
        profile = SiteProfile(tenant_id=tenant.id, **SITE_PROFILE)
        session.add(profile)
        logger.info("Created site profile: %s", SITE_PROFILE["name"])
    else:
        for field, value in SITE_PROFILE.items():
            setattr(profile, field, value)
        logger.info("Updated site profile: %s", SITE_PROFILE["name"])
    return profile


async def photo_ids_by_key(session, tenant: Tenant) -> dict[str, Photo]:
    """Manifest key -> the tenant's uploaded photo, matched on alt text."""
    alts = {spec.alt: key for key, spec in PHOTO_MANIFEST.items()}
    rows = (
        await session.execute(
            select(Photo).where(Photo.tenant_id == tenant.id, Photo.alt.in_(list(alts)))
        )
    ).scalars()
    return {alts[photo.alt]: photo for photo in rows}


def resolve_refs(value: Any, photos: dict[str, Photo], *, as_str: bool) -> Any:
    """Swap every ``PhotoRef`` for the photo's id, or None if not uploaded."""
    if isinstance(value, PhotoRef):
        photo = photos.get(value.key)
        if photo is None:
            logger.warning("  photo %s not uploaded yet — left empty", value.key)
            return None
        return str(photo.id) if as_str else photo.id
    if isinstance(value, dict):
        return {k: resolve_refs(v, photos, as_str=as_str) for k, v in value.items()}
    if isinstance(value, list):
        return [resolve_refs(v, photos, as_str=as_str) for v in value]
    return value


async def seed_pages(session, tenant: Tenant, photos: dict[str, Photo]) -> None:
    for spec in PAGES:
        data = dict(spec)
        # Columns take a UUID; JSONB blocks take its string form.
        data["header_photo_id"] = resolve_refs(data["header_photo_id"], photos, as_str=False)
        data["blocks"] = resolve_refs(data["blocks"], photos, as_str=True)
        # The same contract the API enforces on PUT.
        validate_blocks(data["slug"], data["blocks"])

        existing = await session.scalar(
            select(PageContent).where(
                PageContent.tenant_id == tenant.id,
                PageContent.slug == data["slug"],
            )
        )
        if existing is None:
            session.add(PageContent(tenant_id=tenant.id, **data))
            logger.info("Created page: /%s", data["slug"])
        else:
            for field, value in data.items():
                setattr(existing, field, value)
            logger.info("Updated page: /%s", data["slug"])


def link_profile_images(profile: SiteProfile, photos: dict[str, Photo]) -> None:
    """Point the Person and MusicSchool images at the uploaded photos."""
    portrait, teaching = photos.get(HERO_PORTRAIT.key), photos.get(TEACHING.key)
    if portrait is not None:
        profile.default_image_url = portrait.src
    if teaching is not None:
        # Reassign rather than mutate: JSONB columns don't track in-place edits.
        profile.school = {**profile.school, "image_url": teaching.src}


async def seed_videos(session, tenant: Tenant) -> None:
    for data in VIDEOS:
        existing = await session.scalar(
            select(Video).where(
                Video.tenant_id == tenant.id,
                Video.youtube_id == data["youtube_id"],
            )
        )
        thumbnail = f"https://i.ytimg.com/vi/{data['youtube_id']}/maxresdefault.jpg"
        if existing is None:
            session.add(Video(tenant_id=tenant.id, thumbnail_url=thumbnail, **data))
            logger.info("Created video: %s", data["title"][:60])
        else:
            for field, value in data.items():
                setattr(existing, field, value)
            logger.info("Updated video: %s", data["title"][:60])


async def seed_faqs(session, tenant: Tenant) -> None:
    for data in FAQS:
        existing = await session.scalar(
            select(FAQ).where(
                FAQ.tenant_id == tenant.id, FAQ.question == data["question"]
            )
        )
        if existing is None:
            session.add(FAQ(tenant_id=tenant.id, **data))
            logger.info("Created FAQ: %s", data["question"][:60])
        else:
            for field, value in data.items():
                setattr(existing, field, value)
            existing.is_active = True
            logger.info("Updated FAQ: %s", data["question"][:60])

    retired = (
        await session.execute(
            select(FAQ).where(
                FAQ.tenant_id == tenant.id,
                FAQ.question.in_(RETIRED_FAQ_QUESTIONS),
                FAQ.is_active.is_(True),
            )
        )
    ).scalars()
    for faq in retired:
        faq.is_active = False
        logger.info("Hid retired FAQ: %s", faq.question[:60])


async def seed_photos(session, tenant: Tenant, assets_dir: Path) -> None:
    """Push every image in ``assets_dir`` through the real upload pipeline.

    Files named in ``PHOTO_MANIFEST`` get its role, alt, caption and order.
    Anything else falls back to the filename: a ``hero-``/``about-``/``classes-``
    prefix picks the role (otherwise gallery) and the rest becomes the alt.
    """
    if not assets_dir.is_dir():
        logger.warning(
            "No %s directory — skipping photos. Drop images there and re-run "
            "with --with-photos.",
            assets_dir,
        )
        return

    files = sorted(
        p for p in assets_dir.iterdir() if p.suffix.lower() in IMAGE_SUFFIXES
    )
    if not files:
        logger.warning("%s is empty — skipping photos", assets_dir)
        return

    await storage_service.ensure_bucket()
    role_counters: dict[PhotoRole, int] = {}

    for path in files:
        spec = PHOTO_MANIFEST.get(path.stem)
        if spec is not None:
            role, alt, caption, order = spec.role, spec.alt, spec.caption, spec.order
        else:
            stem = path.stem
            role = PhotoRole.GALLERY
            for candidate in (PhotoRole.HERO, PhotoRole.ABOUT, PhotoRole.CLASSES):
                if stem.startswith(f"{candidate.value}-"):
                    role = candidate
                    stem = stem[len(candidate.value) + 1 :]
                    break
            alt = stem.replace("-", " ").replace("_", " ").strip().capitalize()
            caption = None
            # After the manifest's own slots, so hand-dropped extras trail them.
            order = len(PHOTO_MANIFEST) + role_counters.get(role, 0)
            role_counters[role] = role_counters.get(role, 0) + 1

        existing = await session.scalar(
            select(Photo).where(Photo.tenant_id == tenant.id, Photo.alt == alt)
        )
        if existing is not None:
            if spec is not None:
                existing.role, existing.caption, existing.sort_order = role, caption, order
            logger.info("Photo already seeded, skipping upload: %s", alt[:60])
            continue

        stored = await storage_service.process_and_store(
            path.read_bytes(), tenant_slug=tenant.slug, role=role.value, alt=alt
        )

        session.add(
            Photo(
                tenant_id=tenant.id,
                role=role,
                src=stored.webp_url,
                download_url=stored.jpeg_url,
                storage_path_webp=stored.webp_path,
                storage_path_jpeg=stored.jpeg_path,
                width=stored.width,
                height=stored.height,
                alt=alt,
                caption=caption,
                sort_order=order,
                byte_size_webp=stored.webp_size,
                byte_size_jpeg=stored.jpeg_size,
            )
        )
        logger.info(
            "Uploaded photo: %s (%dx%d, role=%s)",
            alt[:60],
            stored.width,
            stored.height,
            role.value,
        )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


async def resolve_tenant(session, slug: str | None) -> Tenant | None:
    """Pick the tenant to seed, or explain why the choice is ambiguous."""
    tenants = list((await session.execute(select(Tenant).order_by(Tenant.created_at))).scalars())

    if not tenants:
        logger.error("No tenants exist. Create one with POST /api/tenants first.")
        return None

    if slug is None:
        if len(tenants) == 1:
            return tenants[0]
        logger.error(
            "%d tenants exist — pass --tenant <slug>. Available: %s",
            len(tenants),
            ", ".join(t.slug for t in tenants),
        )
        return None

    for tenant in tenants:
        if tenant.slug == slug:
            return tenant

    logger.error(
        "No tenant with slug %r. Available: %s", slug, ", ".join(t.slug for t in tenants)
    )
    return None


async def list_tenants() -> None:
    async with SessionFactory() as session:
        rows = (await session.execute(select(Tenant).order_by(Tenant.created_at))).scalars()
        for tenant in rows:
            flag = "" if tenant.is_active else "  (inactive)"
            logger.info("%-24s %s%s", tenant.slug, tenant.name, flag)
    await dispose_engine()


async def run(
    *, tenant_slug: str | None, reset: bool, with_photos: bool, assets_dir: Path
) -> None:
    async with engine.begin() as conn:
        if reset:
            logger.warning("Dropping all tables")
            await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Schema ready")

    async with SessionFactory() as session:
        tenant = await resolve_tenant(session, tenant_slug)
        if tenant is None:
            await dispose_engine()
            return

        logger.info("Seeding tenant: %s (%s)", tenant.name, tenant.slug)
        profile = await seed_site_profile(session, tenant)
        # Photos before pages: pages point at them by id.
        if with_photos:
            await seed_photos(session, tenant, assets_dir)
            await session.flush()
        photos = await photo_ids_by_key(session, tenant)
        link_profile_images(profile, photos)
        await seed_pages(session, tenant, photos)
        await seed_videos(session, tenant)
        await seed_faqs(session, tenant)
        await session.commit()

    await storage_service.shutdown()
    await dispose_engine()
    logger.info("Seed complete")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--tenant",
        metavar="SLUG",
        help="Which artist to seed. Optional while only one tenant exists.",
    )
    parser.add_argument(
        "--list-tenants",
        action="store_true",
        help="Print every tenant slug and exit",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Drop and recreate every table before seeding (destructive)",
    )
    parser.add_argument(
        "--with-photos",
        action="store_true",
        help="Upload images via the Pillow + Supabase pipeline",
    )
    parser.add_argument(
        "--assets-dir",
        type=Path,
        default=SEED_ASSETS_DIR,
        metavar="DIR",
        help="Where --with-photos reads images from (default: ./seed_assets)",
    )
    args = parser.parse_args()

    if args.list_tenants:
        asyncio.run(list_tenants())
        return

    if args.reset:
        # --reset drops `tenants` too, taking every artist's keys with it.
        confirm = input(
            "This DROPS all tables, including tenants and their keys. "
            "Type 'yes' to continue: "
        )
        if confirm.strip().lower() != "yes":
            logger.info("Aborted")
            return

    asyncio.run(
        run(
            tenant_slug=args.tenant,
            reset=args.reset,
            with_photos=args.with_photos,
            assets_dir=args.assets_dir,
        )
    )


if __name__ == "__main__":
    main()
