# LearnWise – AI Tutor with Live Search

An AI tutor that searches live documentation before answering, so you always get accurate, up-to-date answers with sources.

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

### 3. Run
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
│
└── backend/                     # Main application root
    │
    ├── main.py                  # FastAPI entry point - registers all routes
    │
    ├── ai/                      # AI integration layer
    │   └── chat.py              # GROQ API calls & streaming responses
    │
    ├── database/                # Data storage layer
    │   └── __init__.py          # Database models & connection (coming soon)
    │
    ├── middleware/              # Request/response processing
    │   └── __init__.py          # Auth, rate limiting, CORS (coming soon)
    │
    ├── models/                  # Pydantic schemas
    │   ├── message.py           # Message schema: {role, content}
    │   ├── chatRequest.py       # Chat request: {messages, subject, search}
    │   ├── searchResult.py      # Search result: {title, url, snippet}
    │   ├── QuizRequest.py       # Quiz generation request
    │   ├── exploreRequest.py    # Topic exploration request
    │   └── summaryRequest.py    # Summary generation request
    │
    ├── routes/                  # API endpoints (controllers)
    │   ├── health.py            # /api/health - Service health check
    │   ├── chatRoute.py         # /api/chat - Main streaming chat endpoint
    │   └── auth/                # Authentication routes (coming soon)
    │       └── __init__.py      # /api/auth/* - Register, Login, Logout
    │
    ├── services/                # Business logic layer
    │   └── __init__.py          # Auth, Chat, Quiz services (coming soon)
    │
    ├── static/                  # Frontend static files
    │   ├── index.html           # Main chat UI
    │   └── learnwise-2.html     # Alternative UI design
    │
    ├── utils/                   # Helper functions
    │   └── __init__.py          # Validators, ID generators (coming soon)
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
- auth/: Authentication endpoints (planned)

### Models (models/)
- Request/response validation using Pydantic
- Type-safe data structures
- Automatic API documentation generation

## Current Status

| Component | Status   |
|-----------|----------|
| AI Chat with Streaming | Complete |
| Web Search Integration | Complete |
| Static UI | Complete |
| User Authentication | Planned  |
| Chat History | Planned  |
| Quiz Generator | Complete |
| Summary Service | Complete |
| Explore Feature | Complete |
| Database Layer | Planned  |
| Middleware | Planned  |
| Tests | Planned  |

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

### Add conversation memory (PostgreSQL)
```python
# Store messages per user_id in a DB instead of sending full history each time
```

### Add YouTube transcript support if needed
```python
from youtube_transcript_api import YouTubeTranscriptApi
transcript = YouTubeTranscriptApi.get_transcript(video_id)
```

### Replace Tavily with other search providers
- **SerpAPI** (google results, paid)
- **DuckDuckGo** (unofficial, free, rate-limited)
