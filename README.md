# LearnWise – AI Tutor with Live Search

An AI tutor that searches live documentation before answering, so you always get accurate, up-to-date answers with sources.

## Trello Board
https://trello.com/b/UqREXgJa/timski-proekt

## Features

-  **Streaming AI chat** — answers appear word by word
-  **Live web search** — fetches current docs via Brave Search API
-  **Source sidebar** — see exactly where the AI got its info
-  **Subject mode** — focus on Python, FastAPI, React, etc.
-  **Clean dark UI** — markdown rendered, code highlighted

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
This creates all tables (`users`, `verification_tokens`, `conversations`, `chat_messages`). Whenever you pull new migration files from git, re-run this command to apply them to your local database.

### 4. Run
```bash
uvicorn backend.main:app --reload 
```

Open http://localhost:8000

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
└── backend/                     # Main application root
    │
    ├── main.py                  # FastAPI entry point - registers all routes
    │
    ├── ai/                      # AI integration layer
    │   └── chat.py              # GROQ API calls & streaming responses
    │
    ├── database/                # Data storage layer
    │   ├── session.py           # SQLAlchemy engine, SessionLocal, get_db dependency
    │   └── models.py            # ORM tables: User, VerificationToken, Conversation, ChatMessage
    │
    ├── middleware/               # Request/response processing
    │   └── auth.py               # get_current_user dependency (JWT auth guard)
    │
    ├── models/                  # Pydantic schemas
    │   ├── message.py           # Message schema: {role, content}
    │   ├── chatRequest.py       # Chat request: {messages, subject, search, conversation_id}
    │   ├── searchResult.py      # Search result: {title, url, snippet}
    │   ├── QuizRequest.py       # Quiz generation request
    │   ├── exploreRequest.py    # Topic exploration request
    │   ├── summaryRequest.py    # Summary generation request
    │   ├── authRequest.py       # Register/Login/ForgotPassword/ResetPassword schemas
    │   └── conversationRequest.py # Conversation create/update/list/detail schemas
    │
    ├── routes/                  # API endpoints (controllers)
    │   ├── health.py            # /api/health - Service health check
    │   ├── chatRoute.py         # /api/chat - Main streaming chat endpoint (persists to DB)
    │   ├── conversationRoute.py # /api/conversations/* - CRUD + export for chat history
    │   └── auth/                # /api/auth/* - Register, Login, Logout, Me, verify, reset
    │       └── __init__.py
    │
    ├── services/                # Business logic layer
    │   └── __init__.py          # (still empty - coming soon)
    │
    ├── static/                  # Frontend static files (plain HTML/CSS/JS, no build step)
    │   ├── index.html           # Alternative/older UI
    │   └── learnwise-2.html     # Main chat UI - served at "/", includes login/register modal
    │
    ├── utils/                   # Helper functions
    │   └── security.py          # Password hashing (bcrypt) + JWT create/decode
    │
    ├── web_search/              # Web search integration
    │   └── search.py            # Tavily API - search, query building
    │
    └── tests/                   # Unit & integration tests
        └── __init__.py          # Test files (coming soon)
```

## Architecture Layers Explained

| Layer | Directory | Purpose |
|-------|-----------|---------|
| Presentation | routes/ | API endpoints - handles HTTP requests/responses |
| Business Logic | services/ | Core functionality - quiz generation, auth logic |
| Data Access | database/ | Database models and connections |
| AI Integration | ai/ | GROQ API calls and prompt engineering |
| Search | web_search/ | Tavily API integration for live documentation |
| Middleware | middleware/ | Request processing - auth, rate limiting |
| Models | models/ | Pydantic schemas for request/response validation |
| Utils | utils/ | Helper functions used across the app |
| Static | static/ | Frontend HTML, CSS, JS files |
| Tests | tests/ | Unit and integration tests |

## Data Flow

```
1. User sends message → routes/chatRoute.py
2. Web search (if enabled) → web_search/search.py → Tavily API
3. Build context → ai/chat.py
4. AI response → GROQ API (streaming)
5. Save to database → database/models.py
6. Return response → routes/chatRoute.py → User
```

## Key Components

### AI Layer (ai/chat.py)
- Handles all GROQ API interactions
- Manages system prompts and context injection
- Streams responses back to the client

### Web Search (web_search/search.py)
- Integrates with Tavily Search API
- Builds optimized search queries
- Formats search results for AI context

### Routes (routes/)
- chatRoute.py: Main chat endpoint with SSE streaming
- health.py: Service health monitoring
- auth/: Authentication endpoints (register, login, logout, me, verify-email, forgot/reset password)
- conversationRoute.py: Chat history CRUD + export

### Models (models/)
- Request/response validation using Pydantic
- Type-safe data structures
- Automatic API documentation generation

## Current Status

| Component | Status   |
|-----------|----------|
| AI Chat with Streaming | Complete |
| Web Search Integration | Complete |
| Static UI | Complete (plain HTML/JS, not React - see note below) |
| User Authentication | Complete (register, login, logout, JWT, email verify, password reset) |
| Chat History | Complete (conversations saved to DB, list/search/delete/export, sidebar wired up) |
| Quiz Generator | Complete |
| Summary Service | Complete |
| Explore Feature | Complete |
| Database Layer | Complete (PostgreSQL + SQLAlchemy + Alembic) |
| Middleware | Partial (JWT auth guard done; rate limiting/CORS hardening still open) |
| Tests | Planned  |

### Notes for the team

- **Frontend stack**: the UI (`backend/static/learnwise-2.html`) is plain HTML/CSS/vanilla JS served directly by FastAPI, not React. This was already the case before the auth/chat-history work started. The original team plan mentions React for some personas - if that's still required, migrating the existing UI into React components (with a build step) is a separate, sizeable task that hasn't been started. Worth confirming with the team/instructor whether the current stack is acceptable.
- **Email sending**: email verification and password reset currently just log the link to the server console (`[DEV] ... link: ...`) instead of sending a real email - no email provider is wired up yet. Fine for local dev/demo, but needs a real provider (e.g. Resend, SendGrid, or SMTP) before this goes anywhere near production.
- **Auth is required for chat**: `/api/chat` and all `/api/conversations/*` endpoints now require a valid `Authorization: Bearer <token>` header (i.e. the user must be logged in). `/api/quiz`, `/api/summary`, `/api/explore`, `/api/ask-more` are still open/stateless for now.

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

### Chat (`/api/chat`) - requires auth
Same as before (`{messages, subject, search}`) plus an optional `conversation_id` - omit it to start a new conversation, or pass an existing one to keep appending to it. The SSE stream now starts with an `event: conversation` message containing `{id, title}` so the frontend knows which conversation was created/used.

## How It Works

1. User sends a question
2. Backend builds a search query from the question + selected subject
3. Brave Search API returns 5 relevant results (titles, URLs, snippets)
4. Those results are injected into Groq's system prompt as context
5. Groq streams a tutor-style answer grounded in the live docs
6. Sources appear in the sidebar so the user can verify

## Extending It

### Add ask more
```python
@app.post("/api/ask")
async def ask_more(topic: str):
    # Search docs for the topic, then ask Groq to generate MCQs
    ...
```

### Add real email sending
Replace the `print(f"[DEV] ...")` lines in `backend/routes/auth/__init__.py` with a real provider call (Resend, SendGrid, SMTP, etc).

### Add YouTube transcript support if needed
```python
from youtube_transcript_api import YouTubeTranscriptApi
transcript = YouTubeTranscriptApi.get_transcript(video_id)
```

### Replace Tavily with other search providers
- **SerpAPI** (google results, paid)
- **DuckDuckGo** (unofficial, free, rate-limited)
