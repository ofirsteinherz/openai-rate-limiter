import time
import asyncio
from tokencost import calculate_prompt_cost

class GCRARateLimiter:
    def __init__(self, request_limit_per_minute, token_limit_per_minute, debug=False):
        self.request_limit = request_limit_per_minute
        self.token_limit = float(token_limit_per_minute)  # Convert to float for consistency
        self.debug = debug

        # Track the last request time for GCRA enforcement
        self.last_request_time = 0
        self.request_interval = 60 / self.request_limit

        # Track the last token consumption
        self.token_bucket = float(self.token_limit)  # Ensure the token bucket is initialized as float
        self.last_token_fill_time = time.time()
        self.token_fill_rate = float(self.token_limit / 60)  # tokens per second

        self.lock = asyncio.Lock()  # Lock for synchronizing access to the rate limiter

        if self.debug:
            print(f"Rate limiter initialized: {self.request_limit} requests/min and {self.token_limit} tokens/min.", flush=True)

    def calculate_token_usage(self, messages, max_tokens, model):
        """Calculate the number of tokens required for a request."""
        content = ' '.join([msg['content'] for msg in messages])
        num_tokens = calculate_prompt_cost(content, model=model)  # Use dynamic model argument
        num_tokens = float(num_tokens)  # Convert num_tokens to float
        num_tokens += max_tokens  # Add max tokens for completion
        if self.debug:
            print(f"Calculated token usage: {num_tokens} tokens for model {model} (prompt + completion estimate)", flush=True)
        return num_tokens

    async def enforce_rate_limit_async(self, num_tokens):
        """Asynchronous version of rate limit enforcement."""
        async with self.lock:  # Ensure that rate limiting operations are atomic
            current_time = time.time()

            # Request rate limiting
            time_since_last_request = current_time - self.last_request_time
            if time_since_last_request < self.request_interval:
                sleep_duration = self.request_interval - time_since_last_request
                if self.debug:
                    print(f"Sleeping for {sleep_duration:.3f} seconds due to request rate limit.", flush=True)
                await asyncio.sleep(sleep_duration)

            # Token bucket refill
            time_since_last_fill = current_time - self.last_token_fill_time
            self.token_bucket = min(self.token_limit, self.token_bucket + float(time_since_last_fill) * self.token_fill_rate)
            self.last_token_fill_time = current_time

            # Check if we have enough tokens
            if num_tokens > self.token_bucket:
                wait_time = (num_tokens - self.token_bucket) / self.token_fill_rate
                if self.debug:
                    print(f"Sleeping for {wait_time:.3f} seconds to accumulate enough tokens.", flush=True)
                await asyncio.sleep(wait_time)
                self.token_bucket = 0
            else:
                self.token_bucket -= num_tokens

            # Ensure the token bucket does not go negative
            if self.token_bucket < 0:
                if self.debug:
                    print(f"Warning: Token bucket is negative: {self.token_bucket}", flush=True)
                self.token_bucket = 0

            if self.debug:
                print(f"Token bucket after request: {self.token_bucket}/{self.token_limit} tokens remaining.", flush=True)

            # Mark the request time
            self.last_request_time = time.time()
