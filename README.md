# Artist Portfolio API

FastAPI + SQLAlchemy 2.0 backend over Supabase Postgres. It is the single source
of truth for the Next.js portfolio in [`../tabla-portfolio`](../tabla-portfolio):
the same typed models feed the visible React components and the Google JSON-LD
schema builder, so the two cannot drift apart.

## Layout

```
app/
  core/config.py      Pydantic BaseSettings; normalises Supabase's DATABASE_URL
  db/                 Async engine, session factory, declarative base
  models/             SiteProfile, PageContent, Photo, Video, FAQ, Enquiry
  schemas/            Pydantic v2 request/response contracts
  services/
    storage_service.py  Pillow inspection + WebP/JPEG transcode + bucket I/O
    enquiry_service.py  WhatsApp URL encoding + background email task
    youtube_service.py  YouTube Data API v3 metadata sync
  api/v1/             One router per resource, DI'd sessions
  main.py             App factory, CORS, GZip, lifespan
seed.py               Idempotent seeding with realistic artist data
.github/workflows/    Daily Supabase keep-alive
```

## Setup

```bash
python -m venv .venv
.venv/Scripts/activate        # Windows; use source .venv/bin/activate elsewhere
pip install -r requirements.txt

cp .env.example .env          # then fill in the Supabase values
python seed.py                # creates tables and seeds content
uvicorn app.main:app --reload
```

Interactive docs at <http://localhost:8000/docs> (disabled when
`ENVIRONMENT=production`).

## Endpoints

| Method | Path | Auth | Notes |
| --- | --- | --- | --- |
| `GET` | `/api/bootstrap` | — | **Primary ISR endpoint.** Everything in one payload |
| `GET` | `/api/health` | — | Runs `SELECT 1` + a `site_profile` read; returns DB latency |
| `GET` | `/api/site` | — | Profile + schema metadata |
| `PUT` | `/api/site` | admin | Partial update of the singleton |
| `GET` | `/api/pages` · `/api/pages/{slug}` | — | Copy, JSONB blocks, SEO |
| `PUT` | `/api/pages/{slug}` | admin | |
| `GET` | `/api/photos?role=` | — | `gallery` · `hero` · `about` · `classes` |
| `POST` | `/api/photos/upload` | admin | Multipart; dimensions derived via Pillow |
| `PATCH` | `/api/photos/{id}/order` | admin | Returns the renumbered role bucket |
| `PATCH` | `/api/photos/{id}` | admin | Metadata only — never dimensions |
| `DELETE` | `/api/photos/{id}` | admin | Removes the row and both storage objects |
| `GET` | `/api/videos?featured=` | — | Featured first, then explicit order |
| `POST` | `/api/videos` | admin | By YouTube id; syncs metadata when a key is set |
| `PUT` | `/api/videos/{id}` · `POST /api/videos/{id}/sync` | admin | |
| `DELETE` | `/api/videos/{id}` | admin | |
| `GET` | `/api/faqs` | — | Ordered, active only by default |
| `POST` | `/api/faqs` · `PUT /api/faqs/{id}` · `DELETE /api/faqs/{id}` | admin | |
| `POST` | `/api/enquiries` | — | Persists, queues email, returns `whatsapp_url` |
| `GET` | `/api/enquiries?status=` | admin | Paginated lead list |
| `PATCH` | `/api/enquiries/{id}` | admin | Status / notes |

Write routes require the `X-Admin-Key: <ADMIN_API_KEY>` header.

## Design notes

**`order` vs `sort_order`.** `order` is reserved in SQL, so the column is
`sort_order` while the JSON contract stays `order`. The aliasing lives in
`app/schemas/common.py`.

**Image dimensions are never client-supplied.** `POST /api/photos/upload`
decodes the bytes with Pillow, bakes in EXIF orientation *before* measuring,
downscales past `IMAGE_MAX_EDGE_PX`, and writes both a WebP (display, alpha
preserved) and a progressive JPEG (download, alpha flattened). `width`/`height`
describe the stored assets, so `ImageObject` JSON-LD and `next/image` sizing
always agree. Seeding photos therefore requires real files — see
`seed.py --with-photos`.

**Lead capture ordering.** Persist → commit → queue notification → respond.
A mail outage cannot cost a lead, and the visitor still gets a working
`wa.me` link. Notification outcomes are recorded on the row (`notified`,
`notification_error`) so failures are visible and retryable.

**Supabase pooler.** Transaction-mode pooling (port 6543) cannot hold prepared
statements. `DB_DISABLE_PREPARED_STATEMENTS=true` (the default) disables
asyncpg's statement cache and switches to `NullPool`, since the pooler is
already doing the pooling. Set it to `false` only for a direct 5432 connection,
where `DB_POOL_SIZE`/`DB_MAX_OVERFLOW` then apply.

**Keep-alive.** Supabase pauses free-tier projects after ~7 days of inactivity,
and an HTTP 200 from the app alone does not count — the query has to reach
Postgres, which is why `/api/health` always executes one. Set the repository
variable `API_BASE_URL` and the bundled workflow pings it daily. GitHub only
runs workflows from the *repository root*, so if this backend is a subdirectory
of a larger repo, move `.github/workflows/keep-alive.yml` up to that root.

## Consuming from Next.js

```ts
// One fetch hydrates the whole build/ISR cache.
const res = await fetch(`${process.env.API_BASE_URL}/api/bootstrap`, {
  next: { revalidate: 3600 },
});
const { site, pages, photos_by_role, videos, faqs, content_version } =
  await res.json();
```

`content_version` is the latest `updated_at` across every content table, also
sent as an `ETag`, so a revalidation can cheaply detect that nothing changed.

## Checks

```bash
.venv/Scripts/python -m ruff check app seed.py
```
