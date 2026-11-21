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

## Phase 1: Reskin the brain into a study buddy (English) ✅ (automated); manual test pending

### Changed
- **Persona:** `worker/brain/tools/fast/conversation.py` uses the BUILD_PLAN §10 persona prompt, with a per-turn **mode** (`chat` / `explain` / `check`) taken from the router's intent, and spoken-only output rules. User text is now in `<learner_input>` (added to the firewall's escape patterns); system steering is in `<system_instruction>`; the skill-tree hint becomes `<what_to_check_next>` (Phase 3 fills it). The language rule comes from the new worker setting `BUDDY_LANGUAGE` (`en` now, `ml` in Phase 2).
- **Router intents** (`brains/router.py`, regex first; `llm_router.py` model second, prompt rewritten): `explain_request` and `quiz_request` (new), `conversation`, `end_signal` (session phrases: "that's all for today", "I'm done", "bye"…), and `report_request` / `deep_analysis` (slow). The old `question` category was folded into `explain_request`, because its 0.70 confidence clashed with explain matches and would have forced an LLM routing call (extra latency) on "what is X?".
- **Deviation from the plan, on purpose:** the plan maps "prepare a gentle check" to `slow`. But the check question *is* the spoken reply, and the slow path doesn't publish early. So `quiz_request` goes to **fast** (mode `check`) to keep reply-before-scoring. The slow brain still does reports, and Phase 3's understanding-map update runs after the reply.
- **Topic tracking:** `current_topic` was never set before. It now follows what the buddy explained or checked.
- **Flow** (`interview_flow.py`): buddy wording for wrap-up, closing, confirm-end, move-on (silence → reassurance and a hint, no penalty), reconnect and goodbye lines. The budget is 30 min (wrap-up at 24, early wrap allowed from 10). A goodbye is still confirmed before ending.
- **Voice agent:** new greeting ("Hey there! I'm your study buddy. What shall we study today?…"), a gentler silence nudge, `AGENT_NAME` = "Study Buddy", and an avatar `BUDDY_LANGUAGE` setting for Phase 2.
- **State naming:** done at the prompt and transcript level (Learner/Buddy). The Redis/Postgres keys and the stream `message_type` values (`candidate_response`, `interview_ended`, `InterviewState`) are unchanged on purpose: renaming them would touch the Redis stream contract, which the plan says not to change without asking.

### Fixed along the way
- `ConversationInput.interview_phase` was a strict Literal: the new phase names would have made every reply fail validation. Now `warm_up | studying | closing`.

### Tests
- New `worker/tests/test_buddy_routing.py` (16): topic request → explain on the fast path with no LLM routing call; casual → chat; quiz → check; wrap-up → confirm → conclude; mode mapping; the prompt contains the persona and `<learner_input>`, and no "interviewer"/"candidate".
- worker **75 passed**, avatar **47 passed**; reply-before-scoring test (`test_processor_early_reply`) still green.
- **Real-brain smoke test** (real graph + Gemini, no voice): a tired "hi" got an empathetic chat reply; "Teach me about photosynthesis" got a warm 3-sentence explanation with an analogy and an offer to go deeper or check; "quiz me" got one gentle question; a half answer got praise for the right part and a hint for the rest, with no grading. 2.5–4.4 s per full turn (the reply is published before scoring).
- **[ASK ASHISH] pending:** voice test, "Teach me about photosynthesis".
- **[ASK ASHISH] Phase 1 manual test: PASSED (2026-11-21).** It feels like a buddy; explain/quiz/goodbye work by voice. **Phase 1 exit checkpoint met.**

## Scope change (Ashish, 2026-11-21): Malayalam **and Telugu**
Ashish doesn't speak Malayalam and wants Telugu too (so he can judge quality himself).
- Bulbul v3 TTS samples (`spikes/out/buddy_{te-IN,ml-IN}_{shubh,kavya}.wav`) are all HTTP 200, about 2.2 s (first call 9 s, cold).
- Saaras v3 STT round trip on those samples gave **exact** transcripts in both languages, about 1.2 s each (te-IN, ml-IN).

## Phase 2, part A: brain + API in Malayalam/Telugu on Sarvam-105B ✅ (automated)
- **Decisions (Ashish):** languages are **Malayalam + Telugu (+ English)**, switchable **mid-conversation**. A start-screen picker sets the starting language. Default voice **Kavya** (Bulbul v3).
- **Switching is verified feasible:** Sarvam realtime STT with `language=auto` streamed a Telugu clip, then a Malayalam clip, in one session. Both finals were word-perfect and tagged `te-IN` / `ml-IN`.
- **API:** `POST /calls/` takes `language` (`ml-IN` default | `te-IN` | `en-IN`; anything else → 422). It's stored on the call (the voice agent reads it) and sent to the brain as `system_init {language}`. A language-only `system_init` saves state and **does not reply** (the agent greets; a reply would talk over it).
- **Brain language:** `state["language"]` comes from setup and then follows each turn's `language` field (sent by the agent from speech recognition; additive stream field, no contract change). The prompt's language rule follows it and lets the learner switch at any time. Closing goodbyes come in te/ml/en (`CLOSING_MESSAGES_BY_LANGUAGE`). **Ashish: please check the Telugu wording.**
- **Telugu/Malayalam intents:** native-script patterns for explain / quiz / goodbye in the router, and stop/yes/no in the flow (substring matches, because `\b` breaks inside Indic words).
- **Sarvam-105B is the primary brain** (`FAST_LLM_PROVIDER=sarvam`) for spoken replies; the Gemini list is the automatic fallback; analysis and reports stay on Gemini. **Key finding:** sarvam-105b spends its whole token budget on hidden reasoning (empty answer at 1024 tokens; 6.2 s with `low`). **`reasoning_effort: "none"` gives 1.0 s and valid JSON.**
- **Removed the per-answer interview scorer** (`response_scorer`: "communication"/"technical_depth" grades via a second model call after every reply). It held the session lock 1–6 s per turn; grading is a non-goal, and Phase 3 tracks understanding instead. **Whole turns now take 0.7–1.3 s (was 6–15 s).**
- **Bug fixed (from Phase 0):** the conclude node imported claim-verification helpers I'd deleted, so every session end crashed in the worker (hidden by the mocked graph in tests; the UI still ended). Rewritten: the goodbye is published **before** the report is written. Added an AST scan of every import, including lazy ones, in both services: 0 broken.
- **Also fixed (Phase 1 miss):** the fast-brain system prompt still said "AI interviewer".
- **Tests:** new `worker/tests/test_languages.py` (15) covers Sarvam first / Gemini on failure / analysis stays Gemini / reasoning off, language follows setup then speech, te/ml intents, native goodbye → confirm → goodbye in that script, and goodbye spoken before the report. Worker **90 passed**, avatar **49 passed**.
- **Real-brain smoke (Sarvam):** Telugu explain → quiz → half-answer coaching ("అవును, కరెక్ట్! … కానీ…") → switch to Malayalam on request. Each Sarvam answer took 0.7–1.3 s.
- (Correction: avatar had 48 tests at part A, not 49.)

## Phase 2, part B: voice agent + picker ✅ (automated); manual test pending
- **Voice agent on Sarvam** (`livekit-plugins-sarvam==1.8.10`, the official plugin; no custom adapter):
  - STT `STTRealtime(language="auto")`, i.e. `saaras:v3-realtime`, detects ml/te/en per utterance
  - TTS `sarvam.TTS("bulbul:v3", speaker="kavya")`
  - settings: `VOICE_PROVIDER` (`sarvam` | `deepgram` = English-only fallback for demo-proofing), `STT_LANGUAGE`, `TTS_MODEL`, `TTS_SPEAKER`, `BUDDY_LANGUAGE` (default `ml-IN`)
  - Production now requires `SARVAM_API_KEY` instead of the Deepgram key
- **Language switching:** `agents/language.py` (pure, tested).
  - Each final transcript's language → `TurnRelay.language` → sent with the turn (additive `language` field) → the brain replies in it.
  - Before every line (greeting, brain replies, silence nudge), `BuddyVoice.prepare()` picks the TTS language from the line's **script** (Telugu/Malayalam Unicode blocks, else English) and calls `update_options` only when it changes. Verified in plugin source: Sarvam sends the language in a per-stream config, so it applies to the next line even on a pooled socket.
- **Greetings and the "no rush" nudge** in Malayalam, Telugu and English; the starting language comes from the call (`active_calls`). **Ashish: please check the Telugu lines.**
- **Frontend:** start screen has a മലയാളം / తెలుగు / English picker (remembered in localStorage) → `POST /calls/ {language}`.
- **Environment bug found and fixed:** both `.venv`s were copied from `~/nlp/Alex`, so `pytest`/`alembic`/etc. scripts had shebangs pointing at **that** project's interpreter. Every `uv run pytest` before now ran on `~/nlp/Alex`'s installed packages (with this repo's code), and only the new Sarvam plugin exposed it. The services were unaffected (`uv run python …` uses this venv). Fixed with `uv sync --reinstall` in both, plus a path fix in the `activate*` scripts. Both suites re-run on the correct venvs: green.
- **Tests:** new `avatar/tests/test_language.py` (5): script → language, code normalisation, greeting/nudge per language, turns carry the language, voice switches only on change. **avatar 53 passed, worker 90 passed**, frontend builds.
- **Real agent test** (isolated dispatch name `padippu-test`; Ashish's agent was also registered): job received → Bey 402 → voice-only → Sarvam TTS WebSocket connected (bulbul:v3/kavya) → Malayalam greeting synthesized → realtime STT `session.begin` (saaras:v3-realtime). **0 errors.**
- **[ASK ASHISH] pending:** the big voice test, in Telugu (and Malayalam), plus a language switch mid-session.

## Phase 2 manual test, round 1: "voice breaks / pauses" (2026-11-22)
Ashish: it works, but the voice breaks. Diagnosis from the session transcript in Redis:
1. **Not TTS speed.** Measured Bulbul v3 streaming for a 4-sentence Telugu reply: first audio 0.58 s, 25.6 s of audio generated in 5.3 s, **0 playback stalls**.
2. **Ghost turns from people talking nearby** (Ashish confirmed): two Kannada sentences, "3.5 mm 400. C pin port", "Oxfin", and fragments 2–5 s apart. Each one became a learner turn and cut the buddy off mid-sentence. That's the breaking.
3. **Mojibake bug:** one reply was stored and spoken as `à°à°…`. The conversation parser's fallback decoded with `unicode_escape` (UTF-8 read as Latin-1); it never showed in English. **Fixed** (`338aebf`): lenient JSON extraction (fences, surrounding text, raw newlines) plus proper JSON unescaping; regression tests added.

**Noise (Ashish chose noise cancellation; option 2 only if that's not enough):**
- **Server:** LiveKit **BVC** (background voice cancellation) is already applied to the learner's audio before VAD/STT (checked: the legacy `RoomInputOptions` still maps to it in agents 1.8). It removes quieter background voices; loud nearby talk can still leak.
- **Browser (new):** the mic is captured with `voiceIsolation` (OS/browser voice focus, Chrome/Safari where supported), `noiseSuppression`, `echoCancellation`, `autoGainControl`.
- **Option 2, ready but not enabled:** `INTERRUPT_MIN_DURATION` / `INTERRUPT_MIN_WORDS` in `avatar/.env` (default 0.8 s / 2 words; for a noisy hall try 1.2 / 3).
- **Recommendation for the demo:** a headset mic (closest voice wins) is the single biggest help against hall chatter.
