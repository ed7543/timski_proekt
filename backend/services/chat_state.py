"""Advisory, in-memory tracking of which conversations currently have an
assistant reply streaming - lets a polling client show "someone is asking
something..." instead of silence while another member's message generates.

Never blocks a second send - see routes/chatRoute.py's event_stream(), which
calls start_generating/stop_generating around the Groq call but nothing
here ever rejects a request. Entries self-expire after _STALE_AFTER_SECONDS
rather than relying solely on stop_generating() being reached: a client
disconnect mid-stream doesn't reliably run the generator's cleanup
synchronously (Starlette/anyio may defer it to async-generator GC), and
under more than one worker process, start_generating and its matching
stop_generating for the same request can land on different workers
entirely, leaving a flag stuck true forever in whichever one never saw the
stop call. The expiry bounds that to a few minutes of stale "generating"
display instead of "until the process restarts" - it does not make this
correct under multiple workers (each still has its own in-memory dict, same
single-process assumption middleware/rate_limit.py's in-memory Limiter
storage makes), just failsafe rather than stuck-forever. A real multi-worker
deployment would need a shared store (e.g. Redis with its own native TTL)
instead, same as that rate limiter would."""
import threading
from time import monotonic

_STALE_AFTER_SECONDS = 120  # generous - well beyond any real Groq response time

_generating_started_at: dict[int, float] = {}
_lock = threading.Lock()


def start_generating(conversation_id: int) -> None:
    with _lock:
        _generating_started_at[conversation_id] = monotonic()


def stop_generating(conversation_id: int) -> None:
    with _lock:
        _generating_started_at.pop(conversation_id, None)


def is_generating(conversation_id: int) -> bool:
    started_at = _generating_started_at.get(conversation_id)
    if started_at is None:
        return False
    return (monotonic() - started_at) < _STALE_AFTER_SECONDS
