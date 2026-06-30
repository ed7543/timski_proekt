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

## Project Structure

```
learnwise/
.
├── README.md
├── backend
│   ├── ai
│   │   └── chat.py
│   ├── main.py
│   ├── models
│   │   ├── QuizRequest.py
│   │   ├── chatRequest.py
│   │   ├── exploreRequest.py
│   │   ├── message.py
│   │   ├── searchResult.py
│   │   └── summaryRequest.py
│   ├── routes
│   │   ├── chatRoute.py
│   │   └── health.py
│   ├── static
│   │   ├── index.html
│   │   └── learnwise-2.html
│   └── web_search
│       └── search.py
├── config.py
└── requirements.txt
```

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

### Replace Brave with other search providers
- **SerpAPI** (google results, paid)
- **Tavily** (optimized for AI, free tier)
- **DuckDuckGo** (unofficial, free, rate-limited)
