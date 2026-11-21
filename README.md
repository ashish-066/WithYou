# Alex - AI-Powered First-Round Interview Screening

> **Full project guide:** [docs/PROJECT_GUIDE.md](docs/PROJECT_GUIDE.md): architecture, every service, data, security, API, configuration, running and deploying.

Alex is an employer-focused platform designed to help recruiters conduct fair, consistent, and scalable first-round interviews using AI.

## Demo

https://github.com/user-attachments/assets/f17bab02-a361-4d93-b847-a9d02f24d73d

## Why Alex?

Modern hiring often struggles ith inconsistent screening, interviewer bias, and the difficulty of evaluating large volumes of candidates. Alex addresses these challenges by providing an AI-driven interview system that enables organizations to:

- Scale first-round interviews without sacrificing quality
- Reduce interviewer bias through standardized AI-conducted sessions
- Provide transparent scoring that hiring managers and candidates can trust
- Streamline candidate evaluation with structured insights and automated assessments

## Core Innovation: Evidence-Based Skill Assessment

Traditional AI interview scoring is a black box. Alex changes that with a transparent, auditable methodology:

### Binary Question Skill Ladders

For each skill extracted from a job description, Alex generates 5 levels of binary (yes/no) questions:

| Level | Type | Example (Kubernetes) |
|-------|------|---------------------|
| 1 | Awareness | "Has the candidate mentioned container orchestration?" |
| 2 | Conceptual | "Can the candidate explain what a Pod is?" |
| 3 | Practical | "Has the candidate described deploying to a cluster?" |
| 4 | Problem-Solving | "Has the candidate debugged a failing deployment?" |
| 5 | Mastery | "Has the candidate designed multi-cluster architectures?" |

### Cited Evidence for Every Score

Every determination must cite exact transcript excerpts:

```
Question: "Has the candidate debugged a Kubernetes deployment?"
Answer: YES
Confidence: 0.92
Evidence: "...when our pods kept crashing, I used kubectl describe 
          to find the OOMKilled error and adjusted resource limits..."
          [Lines 45-47]
```

### Skill Transferability

Real-world skills transfer. A candidate's GCP experience counts toward AWS roles:

```
Candidate has: GCP (Level 4)
Role requires: AWS
Transfer rate: 80%
Effective AWS level: 3.2
```

### Elo Rankings for Objective Comparison

After 2+ candidates interview for a role, Alex enables skill-by-skill comparisons using standard Elo ratings (K=32).

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      Recruiter Dashboard                         │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐  │
│  │Session View │  │ SkillTree   │  │ Elo Rankings            │  │
│  │(Live/Replay)│  │Visualization│  │ Candidate Comparison    │  │
│  └─────────────┘  └─────────────┘  └─────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              │ SSE
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                   Avatar Service (FastAPI)                       │
│  • LiveKit video/audio with AI avatar                           │
│  • Real-time transcription (Deepgram)                           │
│  • Natural speech synthesis (Cartesia)                          │
└─────────────────────────────────────────────────────────────────┘
                              │ Redis Streams
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                   Worker Service (LangGraph)                     │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                   Scoring Engine                          │   │
│  │  JD Parser → Ladder Generator → Evidence Extractor        │   │
│  │      ↓              ↓                  ↓                  │   │
│  │  Question Selector ← Tree Manager → Score Calculator      │   │
│  │                          ↓                                │   │
│  │                     Elo System                            │   │
│  └──────────────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │           Dual-Brain Interview Agent                      │   │
│  │  Fast Brain (conversational) + Slow Brain (analytical)    │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

## Scoring Pipeline

```
Job Description → JD Parser → Skill Ladder Generator → Redis
                                                         │
Candidate Q&A → Evidence Extractor → Tree Manager → Skill Tree
                                          │
              Question Selector ← (guides interview flow)
                                          │
            Interview End → Score Calculator → Weighted Score
                                    │
                               Elo System → Rankings
```

## Scalability Model

Alex is designed to scale along the same axes as real interview volume: **concurrent sessions** and **transcription throughput**. The architecture intentionally uses **stateless services + Redis Streams** so each component can be scaled independently.

### Frontend (Recruiter Dashboard)

- **Stateless** React app; horizontal scaling is handled by the CDN / static hosting layer.
- Increase capacity by adding edge caching and serving built assets from object storage + CDN.

### Avatar Service (FastAPI + SSE + LiveKit control plane)

- **Horizontally scalable** because HTTP routes are stateless; session routing/state lives in Redis.
- **SSE fan-out**: multiple avatar instances can publish events, but each client maintains a single SSE connection to one instance (standard load balancer sticky-session behavior helps; alternatively terminate SSE at an API gateway that supports it).
- **Bottleneck** is typically real-time media (LiveKit) rather than the FastAPI service. LiveKit itself scales separately (SFU nodes).

### LiveKit Agent (real-time audio loop)

- Each active interview requires an agent worker to handle audio, transcription, and TTS orchestration.
- Scale by running **multiple agent processes** (or containers) and sharding sessions across them.

### Worker Service (LangGraph + scoring)

- The worker is built around **Redis Streams consumer groups**, enabling multiple worker replicas to share the workload.
- Scaling pattern:
  - Add more `worker` replicas → higher message processing throughput.
  - Redis Streams consumer groups ensure each message is processed by **exactly one** worker instance.
- **Per-session correctness** is enforced with Redis-based distributed locking (Redlock-style) in the state/scoring managers, so parallel workers don’t corrupt the same session state.
- Practical tuning knobs:
  - Split streams by workload (e.g., transcription vs. scoring finalization) to reduce head-of-line blocking.
  - Increase consumer group prefetch/batch size for throughput.
  - Separate “fast brain” and “slow brain” into distinct worker pools to isolate latency-sensitive work.

### Redis (Streams + shared state)

- Redis is the central coordination layer:
  - **Streams**: durable queueing between services.
  - **State**: skill trees, Elo ratings, session metadata.
  - **Locks**: distributed session locks.
- Scale options depend on needs:
  - Single Redis for hackathon/dev.
  - Redis with persistence (AOF) for durability.
  - Redis Cluster / managed Redis for higher throughput and memory.
- Keys can be naturally partitioned by `role_id` and `session_id`, which maps well to Redis Cluster slotting.

### Failure Isolation & Backpressure

- If LLM calls slow down, Redis Streams provide a buffer so ingestion (transcription) can continue while processing catches up.
- Consumer groups allow:
  - **Backpressure control** via stream length trimming policies.
  - **Replay** of pending/unacked messages after crashes.
- Stateless services make it safe to restart/roll deployments without losing session state.

### What Scales First in Production

- **#1:** LiveKit infra (media concurrency)
- **#2:** Agent workers (audio + transcription orchestration)
- **#3:** Worker replicas (LLM/scoring throughput)
- **#4:** Redis (streams + state)

## Technology Stack

| Component | Technology |
|-----------|------------|
| Language | Python 3.11+ |
| Package Manager | uv (Astral) |
| Web Framework | FastAPI |
| AI Framework | LangGraph, LangChain, Google Gemini |
| Frontend | React 18, TypeScript, Tailwind CSS |
| State Management | Zustand |
| Video/Audio | LiveKit, Deepgram, Cartesia |
| Message Queue | Redis Streams |
| Visualization | Recharts |

## Project Structure

```
presence-view/
├── frontend/                  # Recruiter Dashboard
│   └── src/
│       ├── components/
│       │   ├── InterviewRoom.tsx       # Live session view
│       │   └── dashboard/
│       │       ├── SkillTree.tsx       # Evidence visualization
│       │       ├── EloRanking.tsx      # Candidate rankings
│       │       ├── Transcript.tsx      # Live transcription
│       │       └── MetricsPanel.tsx    # Session analytics
│       └── types/index.ts
│
├── avatar/                    # HTTP/SSE + LiveKit Service
│   ├── main.py
│   ├── api/                   # REST endpoints
│   ├── agents/                # LiveKit avatar agent
│   └── services/              # Session & stream management
│
└── worker/                    # AI Interview Engine
    ├── worker.py
    ├── brain/                 # Dual-brain interview agent
    │   ├── graph.py           # LangGraph workflow
    │   └── state.py           # Interview state
    └── scoring/               # Evidence-Based Scoring
        ├── models.py          # Pydantic schemas
        ├── jd_parser.py       # JD → weighted skills
        ├── ladder_generator.py    # Skills → binary questions
        ├── evidence_extractor.py  # Transcript → cited evidence
        ├── tree_manager.py    # Redis-backed skill trees
        ├── question_selector.py   # Adaptive questioning
        ├── score_calculator.py    # Weighted + transferable scores
        ├── elo_system.py      # Candidate rankings
        └── integration.py     # LangGraph integration
```

## Quick Start

### Prerequisites

- Python 3.11+
- Node.js 18+
- Redis
- uv (`pip install uv`)

### Installation

```bash
# Backend
cd avatar && uv sync && cd ..
cd worker && uv sync && cd ..

# Frontend
cd frontend && npm install
```

### Environment Setup

```bash
# avatar/.env
REDIS_URL=redis://localhost:6379/0
LIVEKIT_URL=wss://your-livekit-server
LIVEKIT_API_KEY=your-key
LIVEKIT_API_SECRET=your-secret
DEEPGRAM_API_KEY=your-key
CARTESIA_API_KEY=your-key

# worker/.env
REDIS_URL=redis://localhost:6379/0
GOOGLE_API_KEY=your-gemini-key
```

### Run

```bash
# Terminal 1: Redis
redis-server

# Terminal 2: Avatar HTTP/SSE
cd avatar && uv run python main.py

# Terminal 3: LiveKit Agent
cd avatar && uv run python -m agents.entrypoint dev

# Terminal 4: Worker
cd worker && uv run worker.py

# Terminal 5: Frontend
cd frontend && npm run dev
```

### Run in containers

```bash
docker compose up --build   # then open http://localhost:8080
```

Runs Redis, Postgres, migrations, the API, agent, worker (with an isolated
Docker daemon for candidate code) and the frontend, using `avatar/.env` and
`worker/.env` for API keys. See [docs/DEPLOY.md](docs/DEPLOY.md) for images,
health checks and production requirements.

## Scoring Details

### Skill Weights (from JD)

```python
{
    "kubernetes": 0.25,
    "python": 0.20,
    "aws": 0.20,
    "system_design": 0.15,
    "communication": 0.10,
    "ci_cd": 0.10
}
```

### Weighted Score Formula

```
Score = Σ (skill_weight × level_achieved / max_level × confidence)
```

### Elo System

- Initial rating: 1500
- K-factor: 32
- Skill-by-skill comparison with evidence
- Rankings shown after 2+ candidates

## Development

```bash
# Lint
cd avatar && uv run ruff check --fix . && uv run ruff format .
cd worker && uv run ruff check --fix . && uv run ruff format .
cd frontend && npm run lint

# Build
cd frontend && npm run build
```
