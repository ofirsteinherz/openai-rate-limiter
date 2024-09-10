Here is a basic **README.md** for your project:

---

# OpenAI Rate Limiter

## Description

A Python tool for managing rate limits and token consumption when interacting with the OpenAI API. It ensures compliance with OpenAI's request and token limits by tracking input and output token usage, with an added 50% buffer for maximum token outputs. The tool supports sending multiple requests in parallel while respecting API rate limits.

## Features

- **Rate Limiting**: Enforces request and token limits per minute.
- **Token Tracking**: Tracks input and output tokens, dynamically adjusting based on the maximum tokens used in responses.
- **Concurrency Management**: Handles multiple concurrent API requests.
- **50% Output Buffer**: Adds a 50% buffer to the maximum token usage to avoid exceeding token limits.