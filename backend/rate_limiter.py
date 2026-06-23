import os
import time
import threading
from collections import defaultdict
from backend.logging_config import logger

class InMemoryRateLimiter:
    """
    Lightweight, thread-safe, in-memory rate limiter using a sliding window.
    """
    def __init__(self):
        # Configure limits from environment variables
        try:
            self.requests_limit = int(os.getenv("RATE_LIMIT_REQUESTS", "10"))
            self.window_seconds = int(os.getenv("RATE_LIMIT_WINDOW", "60"))
        except ValueError:
            logger.error("Invalid RATE_LIMIT_REQUESTS or RATE_LIMIT_WINDOW in env. Defaulting to 10 requests / 60 seconds.")
            self.requests_limit = 10
            self.window_seconds = 60
            
        self.history = defaultdict(list)
        self.lock = threading.Lock()
        
        logger.info(f"Rate Limiter initialized: limit={self.requests_limit} reqs, window={self.window_seconds}s")

    def is_rate_limited(self, key: str) -> bool:
        """
        Checks if a key (e.g. user ID or IP) is rate limited.
        If limited, returns True. Otherwise records the request timestamp and returns False.
        """
        now = time.time()
        with self.lock:
            # Filter timestamps to keep only those within the sliding window
            self.history[key] = [t for t in self.history[key] if now - t < self.window_seconds]
            
            if len(self.history[key]) >= self.requests_limit:
                logger.warning(f"Rate limit exceeded for key: {key} ({len(self.history[key])}/{self.requests_limit} requests)")
                return True
            
            self.history[key].append(now)
            return False

# Global rate limiter instance
rate_limiter = InMemoryRateLimiter()
