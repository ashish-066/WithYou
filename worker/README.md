# Presence View Brain Worker

Skeleton brain layer for the Presence View AI Interview Platform.

## Quick Start

```bash
# Install dependencies
pip install -e .

# Start Redis (required)
docker run -p 6379:6379 redis:7

# Run the API server (health checks)
python main.py

# Run the worker (message processing)
python worker.py
```

## Testing Scalability

1. Start multiple workers in separate terminals
2. Use the `/test/publish` endpoint to send messages
3. Observe that each message is processed by only one worker

See `docs/TECHNICAL_DESIGN.md` for full architecture details.
