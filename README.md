# LearnWise – AI Tutor with Live Search

An AI tutor that searches live documentation before answering, so you always get accurate, up-to-date answers with sources.

## Trello Board
https://trello.com/b/UqREXgJa/timski-proekt

## Features

-  **Streaming AI chat** — answers appear word by word, with a stop button to cancel generation mid-answer
-  **Live web search** — fetches current docs via the Tavily Search API
-  **Source sidebar** — see exactly where the AI got its info
-  **Subject mode** — focus on Python, FastAPI, React, etc.
-  **Accounts & chat history** — register/login, and every conversation is saved, searchable, renameable, exportable
-  **React frontend** — a proper Vite + TypeScript SPA, editorial paper/ink look, markdown rendered, code highlighted
-  **Course-aware tutoring** — pass a `course_id` to any chat/study-tool call and the tutor folds in that FINKI course's metadata + lecture topics as extra context

## Setup

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Set your API keys
```bash
cp .env.example .env
# Edit .env and add your keys
```

**GROQ_API_KEY** (required)
→ Get from https://console.groq.com/keys

**TAVILY_API_KEY** (optional but recommended)
→ Sign up at https://app.tavily.com/home

**DATABASE_URL** (required)
→ You need a local PostgreSQL server. Create a database (e.g. `learnwise`), then set:
```
DATABASE_URL=postgresql://postgres:YOUR_PASSWORD@localhost:5432/learnwise
```

**JWT_SECRET_KEY** (required)
→ Any long random string, used to sign login tokens. Generate one with:
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

### 3. Set up the database
```bash
alembic upgrade head
```
This creates all tables (`users`, `verification_tokens`, `conversations`, `chat_messages`, `cached_searches`, `courses`, `course_materials`, `recordings`) and enables the `pg_trgm` Postgres extension (used for fuzzy search-cache matching and course-name search). Whenever you pull new migration files from git, re-run this command to apply them to your local database.

### 4. Run the backend
```bash
uvicorn backend.main:app --reload 
```
The API is now at http://localhost:8000 (interactive docs at `/docs`).

### 5. Run the frontend
```bash
cd frontend
npm install
npm run dev
```
Open http://localhost:5173 — Vite's dev server proxies `/api/*` straight to the backend on :8000 (see `frontend/vite.config.ts`), so no CORS setup is needed in development.

For a production build, `cd frontend && npm run build` produces `frontend/dist`, which `backend/main.py` will serve directly at `/` if the directory exists (no separate frontend server needed in that case).

### 6. (Optional) Ingest course data
```bash
source .venv/bin/activate
python -m backend.services.ingestion.cli --source all
```
Pulls course/lecture-recording data from the public finki-hub.com sites into the `courses`/`course_materials`/`recordings` tables — see "Course Data" below before running this at full scale.

## Project Architecture

```
.
├── README.md                    # Project documentation
├── config.py                    # Environment variables & app config
├── requirements.txt             # Python dependencies
├── alembic.ini                  # Alembic config
│
├── alembic/                     # Database migrations
│   └── versions/                # One file per migration - run `alembic upgrade head`
│
├── frontend/                    # React + TypeScript SPA (Vite) - see "Frontend" below
│   └── src/
│       ├── api/                 # apiFetch client, auth/conversations/chatTools calls
│       ├── context/             # AuthContext (user/token/status)
│       ├── hooks/                # useChatStream (SSE), useConversations
│       ├── pages/                # Login/Register/Chat/Courses/CourseDetail/etc.
│       ├── components/          # layout/sidebar/chat/sources/modals
│       └── types/                # TS interfaces mirroring backend/models/*.py
│
└── backend/                     # Main application root
    │
    ├── main.py                  # FastAPI entry point - registers all routes, CORS config
    │
    ├── ai/                      # AI integration layer
    │   └── chat.py              # Groq API calls, streaming, quiz/summary/explore/followups generation
    │
    ├── database/                # Data storage layer
    │   ├── session.py           # SQLAlchemy engine, SessionLocal, get_db dependency
    │   └── models.py            # ORM tables: User, VerificationToken, Conversation, ChatMessage,
    │                            #   CachedSearch, Course, CourseMaterial, Recording
    │
    ├── middleware/               # Request/response processing
    │   ├── auth.py               # get_current_user dependency (JWT auth guard)
    │   └── rate_limit.py         # slowapi Limiter used on auth routes
    │
    ├── models/                  # Pydantic schemas
    │   ├── message.py           # Message schema: {role, content}
    │   ├── chatRequest.py       # Chat request: {messages, subject, search, conversation_id}
    │   ├── searchResult.py      # Search result: {title, url, snippet}
    │   ├── QuizRequest.py       # Quiz generation request
    │   ├── exploreRequest.py    # Topic exploration request
    │   ├── summaryRequest.py    # Summary generation request
    │   ├── askMoreRequest.py    # Follow-up questions request
    │   ├── authRequest.py       # Register/Login/ForgotPassword/ResetPassword schemas
    │   ├── conversationRequest.py # Conversation create/update/list/detail schemas
    │   └── courseResponse.py    # Course/CourseMaterial/Recording response schemas
    │
    ├── routes/                  # API endpoints (controllers)
    │   ├── health.py            # /api/health - Service health check
    │   ├── chatRoute.py         # /api/chat, /api/quiz, /api/summary, /api/explore, /api/ask-more
    │   ├── conversationRoute.py # /api/conversations/* - CRUD + export for chat history
    │   ├── courseRoute.py       # /api/courses/* - public course/material/recording catalog
    │   └── auth/                # /api/auth/* - Register, Login, Logout, Me, verify, reset
    │       └── __init__.py
    │
    ├── services/                # Business logic layer
    │   ├── search_cache.py      # Cache lookup/write in front of Tavily (exact + pg_trgm fuzzy match)
    │   ├── chat_service.py      # Conversation resolve/save helpers used by chatRoute.py
    │   ├── course_context.py    # Formats a Course into a context block for the AI prompt
    │   └── ingestion/           # Standalone scraper/loader for finki-hub.com course data
    │       ├── finki_hub_client.py  # Polite httpx wrapper (UA, rate limit, robots.txt check)
    │       ├── predmeti_scraper.py  # Course metadata from assets.finki-hub.com/courses.json
    │       ├── snimki_scraper.py    # Recording listings from the recordings-listing GitHub repo
    │       ├── upsert.py            # Idempotent ON CONFLICT DO UPDATE helpers
    │       └── cli.py               # `python -m backend.services.ingestion.cli --source all|predmeti|snimki`
    │
    ├── static/                  # Legacy static files, no longer served by main.py (kept for reference)
    │   ├── index.html           # Alternative/older UI
    │   └── learnwise-2.html     # Original vanilla-JS chat UI - superseded by frontend/
    │
    ├── utils/                   # Helper functions
    │   ├── security.py          # Password hashing (bcrypt) + JWT create/decode
    │   └── email.py              # Sends via Resend if configured, else logs to console
    │
    ├── web_search/              # Web search integration
    │   └── search.py            # Tavily API - search, query building
    │
    └── tests/                   # Unit & integration tests
        └── test_search_cache.py # Cache normalize/match/hit tests (needs a real Postgres w/ pg_trgm)
```

## Architecture Layers Explained

| Layer | Directory | Purpose |
|-------|-----------|---------|
| Presentation | routes/ | API endpoints - handles HTTP requests/responses |
| Business Logic | services/ | Search caching, chat/conversation persistence, course context formatting, course-data ingestion |
| Data Access | database/ | Database models and connections |
| AI Integration | ai/ | Groq API calls and prompt engineering |
| Search | web_search/ | Tavily API integration for live documentation |
| Middleware | middleware/ | Request processing - JWT auth guard, rate limiting |
| Models | models/ | Pydantic schemas for request/response validation |
| Utils | utils/ | Helper functions used across the app |
| Static | static/ | Legacy HTML/JS - no longer served, kept for reference only |
| Frontend | frontend/ | React + TypeScript SPA (Vite) - the actual UI now |
| Tests | tests/ | Unit and integration tests |

## Data Flow

```
1. User sends message → routes/chatRoute.py
2. Web search (if enabled) → services/search_cache.py → cache hit, or web_search/search.py → Tavily API on a miss
3. Optional course context (if course_id given) → services/course_context.py → courses/recordings tables
4. Build final prompt context → ai/chat.py
5. AI response → Groq API (streaming)
6. Save to database → database/models.py
7. Return response → routes/chatRoute.py → User
```

## Key Components

### AI Layer (ai/chat.py)
- Handles all Groq API interactions (`llama-3.3-70b-versatile`, called directly via `httpx`, no SDK)
- Manages system prompts and context injection (search results are injected as extra context before the model answers)
- Streams responses back to the client via Server-Sent Events
- Also powers `/api/quiz`, `/api/summary`, `/api/explore`, `/api/ask-more` — these do **not** call Groq's streaming path, they return a single JSON response each

### Web Search (web_search/search.py) + Search Cache (services/search_cache.py)
- `web_search/search.py` integrates with the Tavily Search API, builds queries, and formats results for AI context
- `services/search_cache.py` sits in front of it: `/api/chat` and `/api/explore` now call `get_or_search()`/`get_or_search_many()` instead of hitting Tavily directly. A question is matched against the `cached_searches` table first — exact normalized match, then a Postgres `pg_trgm` fuzzy-similarity fallback for near-duplicate phrasing (scoped per `subject`) — and only falls through to a live Tavily call on a genuine cache miss. Cache entries soft-refresh after 90 days rather than expiring outright, since study-content answers don't go stale on a clock

### Routes (routes/)
- `chatRoute.py`: `/api/chat`, `/api/quiz`, `/api/summary`, `/api/explore`, `/api/ask-more` — **all require auth**
- `health.py`: service health monitoring
- `auth/`: authentication endpoints (register, login, logout, me, verify-email, forgot/reset password)
- `conversationRoute.py`: chat history CRUD + export, **all require auth**
- `courseRoute.py`: `/api/courses/*` - public, read-only course catalog (no auth needed, not user-specific)

### Models (models/)
- Request/response validation using Pydantic
- Type-safe data structures
- Automatic API documentation generation (visit `/docs` while the server is running)

## Auth & Chat History — how it actually works

This was added by a teammate on the `maja` branch and merged via PR #1. Summary for anyone who didn't build it:

- **Passwords**: hashed with bcrypt (`passlib`) in `backend/utils/security.py` before being stored — never stored or logged in plaintext.
- **Login tokens**: a single stateless JWT (HS256, signed with `JWT_SECRET_KEY`), returned as `access_token` on register/login, sent back by the client as `Authorization: Bearer <token>` on every authenticated request. Tokens expire after **1 day** and there is **no refresh token and no server-side revocation** — "logout" is purely a client-side action (the endpoint exists but doesn't invalidate anything server-side). This is a deliberate MVP trade-off, not a bug, but worth knowing: a token keeps working until it naturally expires even after "logging out."
- **Auth guard**: `backend/middleware/auth.py`'s `get_current_user` dependency decodes the JWT and loads the `User` row. It's applied to `/api/chat`, `/api/quiz`, `/api/summary`, `/api/explore`, `/api/ask-more`, and every `/api/conversations/*` route — consistently now across all of them.
- **Rate limiting**: `/api/auth/register`, `/api/auth/login`, and `/api/auth/forgot-password` are limited to 5 requests/minute per IP (`slowapi`, in-memory store — fine for a single-process deployment; swap in a Redis storage backend if this ever runs with multiple workers).
- **Email verification / password reset**: `backend/utils/email.py::send_email()` sends via the Resend API if `RESEND_API_KEY` is set; otherwise it falls back to **printing the link to the server console** (`[DEV] ... link: ...`). Fine for local dev/demo without a Resend account configured.
- **Chat history**: every chat lives in a `Conversation` (id, user, title, subject, timestamps) which owns an ordered list of `ChatMessage` rows (role, content, timestamp). Deleting a conversation cascades and deletes its messages. Conversations are strictly per-user — `conversationRoute.py`'s `_get_owned_conversation` helper returns a 404 (not a 403) if you try to access someone else's conversation, so you can't even tell whether a given conversation ID belongs to someone else.
- **Streaming + persistence**: `/api/chat` streams the AI's reply via SSE. Because the database session tied to the HTTP request closes as soon as the streaming response starts, the code opens a **second, fresh database session** partway through the stream just to save the assistant's final reply once it's fully generated.
- **Graceful failure mid-stream**: if Groq errors out partway through a response (rate limit, timeout, etc.), the backend catches it, sends the client a proper `event: error` SSE frame with a readable message (e.g. "You're sending messages too fast"), and still saves whatever partial answer had already been generated instead of losing it. The frontend shows the error alongside the partial answer rather than replacing it.
- **Stop generating**: the composer's send button turns into a stop button while a response is streaming (`useChatStream`'s `abort()`, backed by a real `AbortController`). Clicking it always stops the client from receiving/showing more text. **Known limitation**: unlike the server-error case above, a client-initiated disconnect doesn't reliably trigger the same save-partial-reply path — Starlette/anyio can raise `RuntimeError: aclose(): asynchronous generator is already running` when cleaning up the stream generator on a client disconnect, which is a deeper async cleanup issue than this fix addresses. So stopping generation is instant and reliable; the partial answer being saved to that conversation's history on a *user-initiated* stop is not guaranteed (it is guaranteed on a *server-side* error).

## Frontend (frontend/)

A Vite + React + TypeScript SPA that replaces `backend/static/learnwise-2.html` entirely — `backend/main.py` no longer serves that file. It talks to the exact REST API documented in this README (nothing frontend-specific exists on the backend beyond CORS/`ALLOWED_ORIGINS`).

- **Routing**: `react-router-dom` — `/login`, `/register`, `/forgot-password`, `/reset-password`, `/verify-email` are public; `/chat`, `/chat/:conversationId`, `/courses`, `/courses/:courseId`, `/progress`, `/admin` require auth (a `ProtectedRoute` wrapper redirects to `/login` otherwise). `/courses` and `/courses/:courseId` are real pages (catalog + detail, browsing the `/api/courses/*` backend from Phase 3); `/progress`/`/admin` are still placeholder "coming soon" stub pages — seams for future work.
- **Courses section**: `CoursesPage` lists ingested courses grouped by semester with a search box; `CourseDetailPage` shows a course's metadata pills, description, materials list, and recordings grouped by category (Предавања/Аудиториски вежби/etc.), each linking out to its source. A left-sidebar nav (`NavTabs`, shared with the chat page) switches between Chat and Courses.
- **Auth**: JWT kept in `localStorage` (same trade-off the old HTML app had — the backend only issues bearer tokens, not httpOnly cookies, so this wasn't "fixed" here, just carried forward knowingly). `AuthContext` calls `GET /api/auth/me` on load to restore a session; a central API client clears the token and redirects to `/login` on any `401`.
- **Streaming chat**: `useChatStream` replicates the backend's exact SSE framing via `fetch` + `ReadableStream` (native `EventSource` can't send the required `Authorization` header) — same approach the old vanilla-JS app used, just ported into a hook. It also exposes `abort()` (backed by a real `AbortController`) for the composer's stop-generating button, and treats a connection that ends without a `[DONE]` sentinel as its own error state instead of leaving the message stuck showing "typing" forever.
- **Markdown rendering is sanitized**: AI responses and summaries render through `frontend/src/utils/markdown.ts`, which pipes `marked`'s output through DOMPurify before it hits `dangerouslySetInnerHTML`. `marked` alone does not sanitize — since responses can embed live web-search content, unsanitized output would be a real XSS vector.
- **State/data**: no react-query or similar — plain `fetch` wrapped in a small typed API client (`frontend/src/api/`) plus React Context/hooks. Deliberate: there are only ~6 REST resources, and a query library would fight the raw SSE code path more than it would help.
- **Study tools**: Quiz/Summary/Explore/Ask More render as modals over the chat page (not separate routes), matching the original app's UX.
- **Dev vs prod**: in dev, Vite proxies `/api` to `:8000` (see `frontend/vite.config.ts`) — no CORS needed. In prod, `npm run build` produces `frontend/dist`, which `backend/main.py` mounts directly at `/` if present, so the whole app can ship as a single FastAPI process.

## Course Data (courses / course_materials / recordings)

Ingested from the public, non-login-gated subdomains of **finki-hub.com** — an independent student-run open-source project (`github.com/finki-hub`), *not* the official university site, and explicitly not the login-gated Moodle at `courses.finki.ukim.mk` (out of scope — scraping that would need real student credentials).

- **predmeti.finki-hub.com** turned out to be a React SPA whose own data comes from a single public JSON asset (`assets.finki-hub.com/courses.json`) — `predmeti_scraper.py` fetches that directly, no HTML parsing needed.
- **snimki.finki-hub.com** is a static VitePress site built from Markdown in `github.com/finki-hub/recordings-listing` — `snimki_scraper.py` fetches the raw Markdown from GitHub and parses it (headers → categories/presenter+year groups, links → recordings or materials).
- **Important limitation, read before relying on this for real studying**: neither source publishes an actual course **syllabus**. `Course.description` is a synthesized blurb from metadata (course code, semester, credits, professors, prerequisites, tags) — FINKI's real syllabi live only behind the gated Moodle. `services/course_context.py` supplements this with the course's actual lecture-recording **topic titles** (e.g. "Циклуси (дел 1)", "Покажувачи") as the closest available stand-in for a topic outline, since those come from real lecture titles. This is disclosed in that file's docstring — don't oversell this feature as "the AI has read the syllabus."
- Ingestion is a standalone, manual/cron-able script (`python -m backend.services.ingestion.cli`), never triggered by live API traffic. It's a well-behaved client: real User-Agent, `robots.txt` check, ~1.5s delay between requests. Re-running it is safe (idempotent upserts, no duplicates).
- Only 3 courses have been ingested so far as a verification sample (`strukturno-programiranje`, `objektno-orientirano-programiranje`, `algoritmi-i-podatochni-strukturi`) — run the CLI yourself to pull more.

## Current Status

| Component | Status   |
|-----------|----------|
| AI Chat with Streaming | Complete |
| Web Search Integration | Complete, now cache-backed (see below) |
| Frontend | Complete — React + TypeScript SPA (`frontend/`), replaces the old static HTML |
| User Authentication | Complete (register, login, logout, JWT, email verify, password reset — see caveats above) |
| Chat History | Complete (conversations saved to DB, list/search/rename/delete/export, sidebar wired up) |
| Quiz Generator | Complete (auth required, optional `course_id` context) |
| Summary Service | Complete (auth required, optional `course_id` context) |
| Explore Feature | Complete (auth required, cache-backed, optional `course_id` context) |
| Database Layer | Complete (PostgreSQL + SQLAlchemy + Alembic) |
| Search-Result Caching | Complete (`cached_searches` table, exact + pg_trgm fuzzy match) |
| Middleware | Complete (JWT auth guard on all endpoints, CORS origin allowlist, rate limiting on auth routes) |
| Tests | Started (`backend/tests/test_search_cache.py`) |
| Course data / study content | Complete for a 3-course sample (see "Course Data" above) — metadata + lecture topics ingested, no real syllabus text available from any public source |
| Quiz from lecture video | Not started — R&D idea only, see Roadmap |
| Courses browsing (frontend) | Complete — catalog + detail pages, listing materials/recordings per course |
| Progress/Admin frontend pages | Stub placeholders only — real UI not built yet |

### Notes for the team

- **Frontend stack**: now a real React + TypeScript SPA in `frontend/` (see "Frontend" above) — `backend/static/learnwise-2.html` is no longer served, though it's still on disk for reference.
- **Email sending**: uses Resend if `RESEND_API_KEY` is set, otherwise falls back to console logging (see above) — set the key before this goes anywhere near production.
- **Auth is now required everywhere that touches the tutor or your data**: `/api/chat`, `/api/quiz`, `/api/summary`, `/api/explore`, `/api/ask-more`, and all `/api/conversations/*` endpoints all require a valid `Authorization: Bearer <token>` header.
- **Search provider**: this app uses **Tavily**, not Brave (an earlier version of this README said Brave — that was a documentation-only typo, the code has always called Tavily).
- **CORS**: `ALLOWED_ORIGINS` in `.env` controls which frontend origins may call the API (defaults to the Vite dev server + FastAPI's own port) — update it once the React app has a real deployed URL.

## API Endpoints

### Auth (`/api/auth`) - public unless noted
- `POST /register` - `{email, password, full_name?}` → `{access_token, token_type}`
- `POST /login` - `{email, password}` → `{access_token, token_type}`
- `POST /logout` - stateless, just returns a confirmation message
- `GET /me` - **requires auth** - returns the logged-in user's profile
- `GET /verify-email?token=...` - confirms the email (token is logged to console at registration, not emailed)
- `POST /forgot-password` - `{email}` → always returns a generic success message (doesn't leak which emails exist)
- `POST /reset-password` - `{token, new_password}`

### Conversations (`/api/conversations`) - all require auth
- `POST /` - create a conversation - `{title?, subject?}`
- `GET /?search=...` - list the current user's conversations, optionally filtered by title
- `GET /{id}` - get a conversation with its full message history
- `PATCH /{id}` - rename - `{title}`
- `DELETE /{id}`
- `GET /{id}/export?format=markdown|json` - download the conversation

### Chat & study tools (`/api/chat`, `/api/quiz`, `/api/summary`, `/api/explore`, `/api/ask-more`) - all require auth
All five accept an optional `course_id?: number` — if given and it matches a row in `courses`, that course's metadata + lecture topics are folded into the prompt context (see "Course Data" above for what this context actually contains).
- `POST /api/chat` - `{messages, subject?, search?, conversation_id?, course_id?}` — omit `conversation_id` to start a new conversation, or pass an existing one to keep appending to it. Returns a `text/event-stream`: an `event: conversation` message with `{id, title}` first (so the frontend knows which conversation was created/used), then an `event: sources` message with the search results if any, then a stream of `data: <chunk>` events, ending with `data: [DONE]`. Search results are served from `cached_searches` when a similar question was already searched, otherwise fetched live from Tavily and cached for next time.
- `POST /api/quiz` - `{messages, subject?, course_id?}` → a generated quiz
- `POST /api/summary` - `{messages, subject?, course_id?}` → a study summary
- `POST /api/explore` - `{messages, subject?, course_id?}` → related links (cache-backed, same as `/api/chat`)
- `POST /api/ask-more` - `{messages, subject?, course_id?}` → suggested follow-up questions

### Courses (`/api/courses`) - public, no auth needed (read-only catalog data, not user-specific)
- `GET /?semester=&search=` - list courses, optionally filtered
- `GET /{id}` - course detail, including `material_count`/`recording_count`
- `GET /{id}/materials` - non-recording resources (notes, external links, etc.)
- `GET /{id}/recordings?category=` - lecture/exercise recording links

## How It Works

1. User sends a question
2. Backend builds a search query from the question + selected subject
3. Tavily Search API returns 5 relevant results (titles, URLs, snippets)
4. Those results are injected into Groq's system prompt as context
5. Groq streams a tutor-style answer grounded in the live docs
6. Sources appear in the sidebar so the user can verify

## Roadmap

The team has agreed on the following next steps, roughly in priority order. See the shared planning doc/Trello for full detail — this section is a living summary so nobody has to go dig for it.

1. **Backend hardening + search-result caching** ✅ done — Tavily results are now cached in `cached_searches` (exact + `pg_trgm` fuzzy match on the normalized query), so a repeated or near-duplicate question is answered from cache instead of a fresh API call. Also landed: CORS now uses an explicit `ALLOWED_ORIGINS` allowlist instead of `*`, rate limiting on `/login`/`/register`/`/forgot-password` (5/min via `slowapi`), real email sending via Resend (falls back to console logging if unconfigured), consistent auth across `/api/quiz`/`/api/summary`/`/api/explore`/`/api/ask-more`, and the `services/` layer now actually has code in it (`search_cache.py`, `chat_service.py`).
2. **React frontend** ✅ done — `backend/static/learnwise-2.html` has been replaced by a real Vite + TypeScript SPA in `frontend/`, against the exact same REST API. FastAPI is now a pure JSON API (`backend/main.py` no longer serves the old static HTML); the old files are left on disk for reference but are unreferenced. See "Frontend" above. `/courses` and `/courses/:courseId` are real pages now (see item 3); `/progress` and `/admin` remain placeholder stubs — no real UI behind them yet.
3. **Course/study data** ✅ done for an initial sample — `Course`/`CourseMaterial`/`Recording` tables exist, `/api/courses/*` endpoints are live, the AI tutor accepts an optional `course_id` on chat/quiz/summary/explore/ask-more and folds in course context, and the frontend has a real Courses catalog + detail page (`/courses`, `/courses/:courseId`) to browse it all. See "Course Data" above for the **important caveat**: no real syllabus text exists in any public source, so this is metadata + lecture topics, not a full curriculum. Only 3 courses ingested so far — run the ingestion CLI to pull more.
4. **Quiz generation from lecture recordings** (idea, not yet started) — `snimki.finki-hub.com` only lists links to recordings (almost certainly YouTube), with no transcripts, and the lectures are in Macedonian with a lot of Macedonian/English code-switching around technical terms. Plan: try YouTube's own (even auto-generated) captions first via `youtube-transcript-api`; if quality is too poor on real sample lectures, fall back to self-hosted Whisper transcription; cache whatever transcript is produced permanently, the same way search results get cached in step 1. This needs a short manual quality spike on a couple of real lectures before any pipeline gets built — Macedonian ASR quality on code-heavy lectures is the real risk here, not the engineering.

## Extending It

### Add real email sending
Replace the `print(f"[DEV] ...")` lines in `backend/routes/auth/__init__.py` with a real provider call (Resend, SendGrid, SMTP, etc) — part of item 1 in the Roadmap above.

### Add YouTube transcript support if needed
```python
from youtube_transcript_api import YouTubeTranscriptApi
transcript = YouTubeTranscriptApi.get_transcript(video_id)
```
See item 4 in the Roadmap — validate transcript quality on real Macedonian lecture audio before building a full pipeline around this.

### Replace Tavily with other search providers
- **SerpAPI** (google results, paid)
- **DuckDuckGo** (unofficial, free, rate-limited)
