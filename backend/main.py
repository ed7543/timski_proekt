import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware


from backend.middleware.rate_limit import limiter
from backend.routes import health, chatRoute, auth, conversationRoute, courseRoute
from config import ALLOWED_ORIGINS

app = FastAPI(title="LearnWise AI Tutor")

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

# Dev (Vite on :5173) proxies /api straight to this server, so no CORS is
# needed there. ALLOWED_ORIGINS still matters for any other client hitting
# the API directly (e.g. a separately-hosted frontend, or tools like Postman).
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(chatRoute.router)
app.include_router(auth.router)
app.include_router(conversationRoute.router)
app.include_router(courseRoute.router)

# Production build: serve the compiled React app for anything that isn't
# /api/*. Registered after the routers above so it never shadows them.
frontend_dist = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend", "dist")
if os.path.exists(frontend_dist):
    app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")