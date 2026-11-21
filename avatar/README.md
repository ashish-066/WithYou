# Presence View Avatar Service

The Avatar Service handles the interview avatar layer for the Presence View AI Interview Platform. It publishes transcriptions (simulated STT output) to Redis streams and subscribes to AI responses for delivery to connected clients.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         AVATAR SERVICE                                   │
│                                                                          │
│  ┌─────────────┐     POST /transcriptions      ┌───────────────────────┐│
│  │   Client    │ ─────────────────────────────▶│     FastAPI Server    ││
│  │  (Browser/  │                               │                       ││
│  │   Postman)  │ ◀───────────────────────────  │  - Publishes to Redis ││
│  └─────────────┘    SSE: /sessions/{id}/resp   │  - Routes responses   ││
│                                                └───────────┬───────────┘│
│                                                            │            │
│  ┌─────────────────────────────────────────────────────────┘            │
│  │                                                                      │
│  ▼                                                                      │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │                     Background Listener                           │   │
│  │  - Consumes from interview:responses                              │   │
│  │  - Dispatches to session queues                                   │   │
│  │  - Delivers via SSE to connected clients                          │   │
│  └──────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                          Redis Streams                                   │
│  ┌─────────────────────────────────┐  ┌─────────────────────────────────┐│
│  │     interview:requests          │  │     interview:responses         ││
│  │     (consumed by Brain)         │  │     (published by Brain)        ││
│  └─────────────────────────────────┘  └─────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────────────┘
```

## Quick Start

### Prerequisites

- Python 3.11+
- [uv](https://github.com/astral-sh/uv) package manager
- Redis 7+ running locally

### Installation

```bash
cd avatar

# Install dependencies with uv
uv sync

# Or with pip
pip install -e .
```

### Configuration

Copy the example environment file:

```bash
cp .env.example .env
```

Edit `.env` as needed. Key settings:

| Variable | Default | Description |
|----------|---------|-------------|
| `REDIS_URL` | `redis://localhost:6379/0` | Redis connection URL |
| `PORT` | `8001` | HTTP server port |
| `DEBUG` | `false` | Enable debug logging |

### Running

Start Redis (if not already running):

```bash
docker run -p 6379:6379 redis:7
```

Start the Avatar Service:

```bash
# With uv
uv run python main.py

# Or directly
python main.py
```

The service will start on `http://localhost:8001`.

## API Endpoints

### Health & Info

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Health check with Redis status |
| `GET` | `/info` | Service configuration info |
| `GET` | `/streams` | Redis stream statistics |

### Sessions

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/sessions` | Register a new session |
| `GET` | `/sessions` | List all active sessions |
| `GET` | `/sessions/{id}` | Get session info |
| `DELETE` | `/sessions/{id}` | Unregister a session |

### Transcriptions

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/transcriptions` | Publish a transcription to Redis |

### Responses (SSE)

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/sessions/{id}/responses` | Stream responses via SSE |

## Usage Examples

### 1. Start a Session

```bash
curl -X POST http://localhost:8001/sessions \
  -H "Content-Type: application/json" \
  -d '{"session_id": "test-session-001"}'
```

### 2. Connect to SSE Stream

In a separate terminal:

```bash
curl -N http://localhost:8001/sessions/test-session-001/responses
```

### 3. Send a Transcription

```bash
curl -X POST http://localhost:8001/transcriptions \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "test-session-001",
    "content": "I have 5 years of experience with Kubernetes"
  }'
```

### 4. JavaScript Client Example

```javascript
// Connect to SSE stream
const sessionId = 'test-session-001';
const evtSource = new EventSource(`/sessions/${sessionId}/responses`);

evtSource.addEventListener('connected', (e) => {
  console.log('Connected:', JSON.parse(e.data));
});

evtSource.addEventListener('response', (e) => {
  const data = JSON.parse(e.data);
  console.log('AI Response:', data.content);
});

evtSource.addEventListener('ping', (e) => {
  // Keepalive ping every 30s
});

evtSource.onerror = (e) => {
  console.error('SSE error:', e);
};

// Send transcription
async function sendTranscription(content) {
  const response = await fetch('/transcriptions', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: sessionId, content }),
  });
  return response.json();
}
```

## Development

### Running Tests

```bash
uv run pytest
```

### Code Formatting

```bash
uv run ruff format .
uv run ruff check --fix .
```

### API Documentation

When running, visit:
- Swagger UI: `http://localhost:8001/docs`
- ReDoc: `http://localhost:8001/redoc`

## Message Format

### Transcription (Published to `interview:requests`)

```json
{
  "session_id": "abc123",
  "message_type": "candidate_response",
  "content": "I have 5 years of experience...",
  "timestamp": "2026-01-28T10:30:00Z",
  "source": "avatar"
}
```

### Response (Consumed from `interview:responses`)

```json
{
  "session_id": "abc123",
  "message_type": "avatar_response",
  "content": "Tell me more about your Kubernetes experience...",
  "timestamp": "2026-01-28T10:30:05Z",
  "worker_id": "brain-w1"
}
```

## Project Structure

```
avatar/
├── main.py              # FastAPI app with background listener
├── pyproject.toml       # Project configuration
├── core/
│   ├── config.py        # Pydantic settings
│   └── redis.py         # Redis connection management
├── services/
│   ├── streams.py       # Redis Streams publisher/subscriber
│   └── session.py       # Session routing manager
├── api/
│   ├── routes.py        # FastAPI route definitions
│   └── schemas.py       # Pydantic request/response models
└── tests/
    └── ...
```
