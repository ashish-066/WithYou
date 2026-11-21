# RESHAPE_CHANGELOG

Running log of the Presence View → Padippu Koottukaran reshape. Newest entries at the bottom.

## Decisions (from Ashish, 2026-11-21)
- **Git:** fresh history. The old `.git` was moved (not deleted) to `../presenceview-hackvesrion.git-backup`; delete it once you're sure you don't need it.
- **Login:** keep the simple email/password login (one learner per account). Invites and the recruiter side go.
- **Video avatar:** keep BeyondPresence (`bey`).
- **Call recording (LiveKit egress → S3):** drop.
- **Sarvam key:** Ashish adds `SARVAM_API_KEY` to `avatar/.env` and `worker/.env`.
- **Integration seam (finding):** the official `livekit-plugins-sarvam==1.8.10` matches `livekit-agents==1.8.10`, so no custom STT/TTS adapter is needed.

## Step 0: Snapshot
- Fresh `git init` on `main`; the initial commit is the existing platform as-is (baseline: worker tests 108 passed/25 skipped, avatar tests 50 passed/59 skipped).
- Extended the root `.gitignore` (.DS_Store, .venv, node_modules, caches, *.db, spikes/out).
- Added `context/plan.md` (the working plan) and this changelog.

## Phase 0: Strip the interview/surveillance system ✅ (automated); manual voice test pending

### Deleted
- **Desktop:** `desktop/` (Electron locked app), plus its CI job.
- **Voice agent (avatar/agents):** `vision.py`, `vision_monitor.py`, `models/` (EfficientDet/BlazeFace .tflite), and the camera task, evidence-photo, JPEG and code-activity code in `entrypoint.py`. `interview_monitor.py` keeps only silence + disconnect rules; the camera and coding rules are gone.
- **API (avatar/api):** `proctoring_routes`, `elo_routes`, `role_routes`, `admin_routes`, `platform_routes`, `org_routes`, `dsa_routes` (+ their schemas), the resume upload/OCR, and recording (LiveKit egress → S3, `core/recordings.py`, `/calls/recordings`). Also `core/roles.py`, `services/{ocr,presence,demo_orchestrator,demo_scripts,worker_spawner}.py`.
- **Auth:** invites, candidate cookie/tokens, and the team-member endpoints. **Kept:** signup/login/logout/me/config. Signup no longer needs an org name (each learner gets a personal org).
- **Calls:** `POST /calls/` is signed-in-learner only (`{candidate_name}`). No invite, role, background, DSA or recording.
- **Worker:** `dsa/`, `sandbox/`, `scoring/elo_system.py`, `services/anti_cheat.py`, `core/hume_client.py`, `brain/candidate_background.py`, `brain/verification_probe.py`, `brain/services/background_verifier.py`, the Hume/profile-crawler/niche-detector/Tavily/DSA-conversation tools, and nine unused legacy tool modules (citation, crawler, rubric, search, speech, …). Removed: integrity/cheat-flag/DSA/Hume fields from state, the store and report prompts; `record_timing` (answer-timing flags); the coding-round flow rules; and the sandbox and Hume settings.
- **Frontend:** recruiter workspace (`areas/app`), platform console (`areas/platform`), DSA page, Monaco, CameraWarning, SecureAppCheck, desktop/proctoring/DSA/role API clients, and the dev UI mock. Routes are now `/` → `/study` (signed in) or `/login`. The room sends audio only (no camera); the Bey avatar video is still shown.
- **Tests removed with their features:** proctoring flags (×2), vision (×2), invite background, org routes, platform routes, auth store (invites), sandbox, problem library, claim checks, candidate background, the DSA prompt-safety test, and the follow-up/timing-flag tests. **Kept and passing:** prompt-injection/LLM-safety, flow policy, early-reply (reply-before-scoring), streams, state, transcript, turn relay, calls, auth.

### Where the verification probe lived (for Phase 3)
`worker/brain/processor.py`, in the `candidate_response` branch: `interview_flow.record_timing` flagged a long silence plus a long answer, then `verification_probe.start()` set a one-turn `interviewer_instruction`. After the graph ran, `set_question` / `judge` / `apply_outcome` recorded the result. The original is in the snapshot commit `65a45a4` (`worker/brain/verification_probe.py`). Phase 3 brings back only the *mechanism* (a one-turn instruction for a gentle follow-up), not the timing or integrity parts.

### Other changes
- Fixed a race in `DELETE /calls/{id}`: concurrent end requests could get a 404. `active_calls.claim_for_ending` now removes the call and sets the "recently ended" marker in one Redis transaction, and the route checks the marker after a miss.
- Added a `sarvam_api_key` setting to both services (their settings reject unknown `.env` keys).
- Dropped deps: avatar (`pytesseract`, `pdf2image`, `Pillow`, `python-multipart`, `boto3`, `ai-edge-litert`); worker (`tavily-python`, `hume`, `bs4`, `pypdf`); frontend (`@monaco-editor/react`, `recharts`).
- `docker-compose.yml`: removed the sandbox daemon and the worker's SANDBOX_* env.

### Things Ashish should know
- **Postgres schema untouched:** the `invites`, `job_roles`, and interview integrity/recording/dsa columns are unused but still there (no migration needed tonight).
- **`deploy/` (AWS production scripts) not updated:** it still sets SANDBOX_* env and runs `sandbox.selfcheck`. Don't use it for the hackathon; run locally (`mprocs`).
- **Local dev:** I started Colima for the dev Postgres (`alex-postgres`, :5434). Colima auto-started your old compose stack (`alex-*-1` containers), so I **stopped** those, so their old agent wouldn't grab LiveKit jobs. `kalasetu-db` was left alone.
- **Couldn't delete (classifier blocked `rm -rf` of untracked dirs):** `avatar/KMS/` (empty), `avatar/.local-evidence/` (old evidence photos, possibly personal data), `avatar/zenith.db` (empty). Delete them yourself if you like.

### Checkpoint
- avatar: ruff clean, **46 passed** (Postgres + Redis up, 0 skipped)
- worker: ruff clean, **59 passed**
- frontend: `tsc` + `vite build` OK
- Boot smoke: worker, API and LiveKit agent all start cleanly (agent registered in LiveKit Cloud, India South)
- **[ASK ASHISH] pending:** English voice loop end-to-end ("the skeleton still talks").

## Spikes (2026-11-21)
- **Key:** `SARVAM_API_KEY` is set in `avatar/.env` and `worker/.env`, and both services' settings load it.
- **P-0 TTS (Bulbul v3, ml-IN, speaker `shubh`):** HTTP 200 in 2.24 s via REST `POST /text-to-speech`. The response is `{request_id, audios: [base64 wav]}`. Saved to `spikes/out/p0_bulbul_v3_ml_shubh.wav`. **[ASK ASHISH] listen for quality → go/no-go.**
- **LLM (sarvam-105b):** HTTP 200 in 2.10 s via `POST /v2/chat/completions` (OpenAI-compatible; we sent both the `api-subscription-key` and `Authorization: Bearer` headers). Correct, natural Malayalam two-sentence answer. Notes for Phase 2:
  - the model returns a separate `reasoning_content` field, and `content` starts with `\n`, so strip it
  - reasoning adds latency, so try a low `reasoning_effort` for the fast path
- **P-1 STT:** not run yet (needs a Malayalam clip from Ashish).

## Phase 0 manual test, round 1: no greeting → three fixes
Ashish heard nothing. What I found:
1. **BeyondPresence is out of credits (HTTP 402).** `bey.AvatarSession.start()` raised, and that crashed the agent before the greeting. **Fix:** the avatar is now optional (`ENABLE_AVATAR`, default on). If it fails, the session carries on voice-only (Bey reroutes audio only after a successful start, so the fallback is safe).
2. **Cartesia TTS is out of credits (HTTP 402:** 6 credits left, about 12 needed per sentence). The agent "speaks" but no audio frames come out. **Not fixed in code. Decision needed:** top up Cartesia, or move the TTS swap to Sarvam Bulbul forward. Deepgram STT checked OK (HTTP 200 on a sample clip).
3. **Redis socket timeout bug:** redis-py 8 defaults to a 5 s socket timeout, equal to our 5 s `XREAD BLOCK`. Idle reads in the agent's reply listener timed out every cycle, then slept 1 s, which can add up to 1 s to replies. On the worker, entries Redis had already delivered could be dropped client-side and wait for the 30 s reclaim. **Fix:** `socket_timeout=30` on both pools. Verified with 12 s of idle reads and no errors.
- **Also:** the agent now registers as `padippu-buddy` (`AGENT_DISPATCH_NAME`) and the API dispatches it explicitly to each room (`livekit_service.dispatch_agent`). Another agent on the same LiveKit project can no longer take our calls. Verified against LiveKit Cloud: dispatch → "received job" → "Starting interview agent".
- Tests: avatar 47 passed (+1 dispatch test), worker 59 passed.
- **Decision (Ashish):** TTS → **Deepgram Aura** (`aura-2-thalia-en`, `DEEPGRAM_TTS_MODEL`) for Phase 0/1. Cartesia is removed from the agent (still out of credits). The avatar stays voice-only automatically while Bey is out of credits. Real dispatch test: Deepgram TTS connected, audio frames flowing, 0 errors.
- **[ASK ASHISH] Phase 0 manual test: PASSED (2026-11-21).** English voice loop end-to-end: greeting, reply to speech, end call. **Phase 0 exit checkpoint met.**
