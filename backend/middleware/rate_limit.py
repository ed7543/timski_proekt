from slowapi import Limiter
from slowapi.util import get_remote_address

# In-memory store - fine for a single-process student deployment. If this ever
# runs behind multiple workers/processes, swap in a Redis-backed storage_uri.
limiter = Limiter(key_func=get_remote_address)
