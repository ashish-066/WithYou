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

## Phase 2 manual test, round 2: "something is happening", "it went on a loop" (2026-11-22)
- The transcript showed "learner" turns every 4–10 s (garbled Kannada/Hindi/English: "Straight Time maadodu", "क्या तो है?", "Poco phone"). Ashish: **nobody was talking**, and it looped.
- **Corrected diagnosis: echo, not people nearby.** On laptop speakers the buddy's own Bulbul voice came back through the mic. Sarvam STT (language auto) transcribed it as garbled "other languages". That cut the buddy off mid-sentence (the breaking), and then it answered its own echo (the loop). Browser echo cancellation wasn't enough.
- **Fix (Ashish chose "harder to interrupt"):** interruptions are **off by default** (`ALLOW_INTERRUPTIONS=false`), with `discard_audio_if_uninterruptible=True`, so mic audio is thrown away while the buddy speaks. All `session.say` calls follow the setting (they used to force `allow_interruptions=True`). If barge-in is turned back on, the thresholds are now 1.2 s / 3 words. Trade-off: the learner can't interrupt the buddy mid-sentence (replies are short).
- Test: `test_buddy_cannot_be_cut_off_by_its_own_echo_by_default`. Avatar **54 passed**.

## Phase 2 manual test, round 3: "I talked in Telugu, why did it reply in Malayalam?" (2026-11-22)
**Diagnosis from Redis:** Sarvam STT with `language=auto` transcribed Ashish's **Telugu speech as Kannada** (Kannada script *and* grammar: "ಮಾಡ್ತಾ ಇದೀನಿ"). The brain copied that script and replied in Kannada. The voice didn't recognise Kannada script, fell back to the **English** Bulbul voice reading Kannada text (the odd "Malayalam-ish" sound) and gave the English "No rush" nudge. Auto-detect was perfect on clean TTS audio but is unreliable on a real mic (Telugu/Kannada are close).

**Fixes:**
- **Recognition locked to the session language** (`STT_LANGUAGE=session`, default; `auto` still available). Switching updates it live (Sarvam in-band `config.update`, applies from the next utterance). Verified against the real service: locked te-IN → switched to ml-IN mid-stream → both finals exact.
- **Two ways to switch mid-session:**
  1. **Language buttons in the room** (മല / తెలు / EN) → data message (topic `buddy-language`) → agent switches listening and voice, and the buddy confirms in the new language.
  2. **By voice**, e.g. "ఇప్పుడు మలయాళంలో చెప్పు" / "speak English": new `worker/brain/language_switch.py` detects the request **in code** and changes the session language before the reply. (The model, told "Reply in Telugu", would say "OK, in Malayalam" and keep speaking Telugu.) The voice agent then follows the reply's script and also moves listening to it (Indian languages only; an English reply doesn't move listening).
- **Prompt:** transcripts may be in the wrong script; understand them, but always reply in the session language's own script; change language only on a clear request.
- **Voice:** text in another Indian script now keeps the current voice, never the English one.
- **Real brain:** the exact misheard Kannada turn in a Telugu session → reply in Telugu (317 Telugu chars, 0 Kannada); "ఇప్పుడు మలయాళంలో చెప్పు" → reply in Malayalam.
- **Tests:** worker **103 passed** (+9: switch requests incl. not-a-request and ambiguous cases, processor switches before the reply), avatar **56 passed** (+2: Kannada → current voice, listening follows the buddy, buttons switch both).
- **Phase 2 accepted by Ashish (2026-11-22)** ("let's put it like this and move to the next phase"): Malayalam/Telugu voice conversation works end to end; tuning can continue later. **Phase 2 exit checkpoint met.**

## Phase 3: The gentle evaluator loop ✅ (automated); voice test batched with later phases
Ashish is away and asked me to keep going phase by phase and test everything together at the end.

**New `worker/brain/understanding.py`, the understanding map in `state["understanding"]`:** the topic's 3–4 key ideas (in the session language), each `unseen | partial | gap | understood`, with the learner's own words as evidence, plus attempts and a `struggled` flag (for Phase 5's call-backs).
- **Reused from the interview platform:**
  - `EvidenceExtractor.extract_single` (Yes/No/Insufficient + exact quote + confidence) with `filter_confirmed_extractions` (≥ 0.7). We also require the quote to actually appear in the learner's answer (no invented evidence).
  - `QuestionSelector.calculate_skill_priorities` (weight × remaining × recency) picks the next idea: missed > half-shown > untouched, not one just asked.
  - The old verification probe's *mechanism*: a one-turn instruction decided before the reply. A vague answer to the buddy's question gets **exactly one** short, encouraging follow-up; a second vague answer gets the idea explained kindly. No timing flags, no judgment.
- **Before the reply** (processor): is this turn an answer to the buddy's question? Clear requests (quiz, bye, summary, strong "explain/what is") take over. **Hesitant answers ending in "?" still count as answers**: "maybe the sun?" was routing as a question. Answers are coached: new **`coach`** mode is encouragement → gap → hint, never "wrong" or a score. `<what_to_check_next>` = the selected idea.
- **After the reply** (graph `scoring_process` node, bounded to 8 s, since the lock is held): list ideas for a new topic, assess an answer against the open ideas, and record which idea the buddy just asked about (including moving on to the next idea after a correct answer).
- **Fixed during the real-brain run:** the scoring client (gemini-3.5-flash) took 17–21 s or timed out (504) for idea listing and assessment. These now use the fast pool (Sarvam-105B first, Gemini fallback): **0.4–2.1 s per whole turn**.
- **Registered** `understanding` (JSON) and `answering_check` (bool) in the state manager, otherwise they'd come back from Redis as strings.
- **Tests:** new `worker/tests/test_understanding.py` (9):
  - nails A, misses B → B is targeted next; understood ideas are never re-asked
  - evidence must be the learner's own words; low-confidence Yes isn't counted
  - vague answer → exactly one follow-up (English/Telugu/Malayalam hedges)
  - coaching order and no grading; "maybe?" is coached as an answer
  - processor round trip through Redis
  - **Worker 112 passed.**
- **Real-brain loops (English and Telugu):** teach → quiz → half-right ("You're close!… green helper…" / "…కరెక్ట్! కానీ…") → vague (one follow-up / "కంగారు పడకు") → correct (marked understood with the learner's quote → moves on to the next idea).

## Phase 4: Mobile-first PWA ✅ (automated + phone-size screenshots); phone test batched
- **One learner screen** (`frontend/src/features/study/`): `StudyPage` (start: greeting, language picker, big Start, which is also the user gesture browsers need for audio) → `StudyRoom`. The room has:
  - **top:** topic + "what we've covered" chips, one per key idea from the Phase 3 map, filled when understood
  - **middle:** avatar video if present, otherwise a state orb (listening / thinking / speaking via `useVoiceAssistant`) and the live transcript (`useTranscriptions`; learner right, buddy left)
  - **bottom:** language pills (switch mid-session) and a big mic button
  - an End button with a confirmation; `StartAudio` fallback if autoplay is blocked
  - all UI labels in Malayalam / Telugu / English, following the session language (and the brain's spoken switches)
  - layout uses `100dvh` + safe-area insets
  - Removed the old `InterviewPage`, `InterviewRoom` and `ConfirmEndDialog`
- **API:** `GET /calls/{call_id}/progress` → `{topic, language, ideas: [{text, status}], covered}` from the brain's Redis state; owner-only; no scores or evidence. Test added (avatar **57 passed**).
- **PWA:**
  - `manifest.webmanifest` (name "പഠിപ്പ് കൂട്ടുകാരൻ · Study Buddy", start `/study`, standalone, theme #0F5B4C)
  - icons 192/512 + maskable + apple-touch (generated open-book icon)
  - `sw.js` caches **nothing live**: navigation-only offline fallback; API, WebRTC and assets always come from the network
  - iOS meta tags; registration in `main.tsx`
  - `npm run check:pwa`: installability check on `dist/` (manifest, icons, SW + fetch handler, registration). Lighthouse isn't installed and removed its PWA audit.
- **Cleanup:** removed the Presence View marketing landing page (`public/landing`, nginx rules). nginx CSP no longer allows the Monaco CDN; camera permission off.
- **Phone access:** `npm run dev:phone` (LAN) and Vite allows `*.trycloudflare.com`, so `cloudflared tunnel --url http://localhost:3000` gives the HTTPS a phone needs for the mic.
- **Screenshots at 390×844** (headless Chrome, real session): start screen and room render correctly in Telugu, with nothing cut off.

### ⚠️ Found while testing: this network breaks LiveKit (demo risk)
- During the Phase 4 run the agent (and a bare `rtc.Room().connect()` with no app code) **timed out joining rooms**, while LiveKit's REST API, the `/rtc` handshake via curl and token validation all worked.
- **Cause:** the laptop is on an **IPv6-only NAT64 network** (DNS returns `64:ff9b::…`; no Wi-Fi association, so likely a phone hotspot). `curl -6` to LiveKit times out; `curl -4` works in 0.8 s. LiveKit's native SDK tries the IPv6 address and doesn't fall back.
- **Not an app bug,** but **the plan's "demo on your own hotspot" fallback can hit exactly this.** Options for Ashish:
  - use normal Wi-Fi (IPv4) for the laptop
  - or turn IPv6 off on that interface while demoing (`networksetup -setv6off "<service>"`, back with `-setv6automatic`)
  - or host the agent somewhere with IPv4

## Phase 5: Recap, session memory, warmth, demo-proofing ✅ (automated); rehearsal pending
- **Kind recap card** (the report writer, reskinned, `worker/brain/tools/slow/report_generator.py`): the same entry points, so the conclude node, retry sweep, Postgres save and report requests all keep working.
  - `generate_descriptive_report` → `{title, summary, covered, improved, next_time, language}`, written warmly to the learner in the session language, from the understanding map + full transcript. No scores; doesn't invent progress; shaky ideas become "next time".
  - Model: fast pool first (Sarvam), slow as fallback. **With no model at all, a plain recap is built from the map** in te/ml/en.
  - `generate_analytics_report` → the map's ideas/status and "clicked after a struggle" (no model call).
  - All old interview-report prompts are gone.
- **API** `GET /calls/recap/{session_id}` → pending/ready/failed + recap (live state, else Postgres); owner-only; test added.
- **Frontend:** the finish screen shows the `RecapCard` (polls until the brain has written it), with labels in ml/te/en.
- **Session memory:** the reply prompt gets `<session_memory>`: ideas that were hard and then clicked ("celebrate!"), and ones still in progress ("be encouraging"). The buddy calls back to them only to cheer or encourage.
- **Real brain (Telugu):** goodbye + recap in 0.7 s; the recap is accurate (photosynthesis + chlorophyll covered; "next time: carbon dioxide and water", the idea still open), warm, and has no scores.
- **Demo kit** `context/DEMO.md`: how to run (incl. phone via cloudflared), 3 tested topics, the 3-minute pitch, a fallback table (IPv6 hotspot, `VOICE_PROVIDER=deepgram`, `FAST_LLM_PROVIDER=gemini`, noisy hall, avatar, backup clip), and the pre-stage checklist.
- **Tests:** worker **114 passed** (+ recap fallback in Telugu with no score words, session memory), avatar **58 passed** (+ recap endpoint), frontend build + PWA check OK.
- **[ASK ASHISH] pending for all phases together:** phone session over the demo network, Telugu wording check, 3-minute rehearsal, backup clip.

## Combined test (2026-11-22): ✅ PASSED on the phone, in Telugu
- **Network fix for the hotspot:** IPv6 on this hotspot is completely broken (even to Google), but the Mac still preferred it, and LiveKit's SDK has no IPv4 fallback, so rooms couldn't be joined. Ashish turned IPv6 off (`sudo networksetup -setv6off Wi-Fi`; undo with `-setv6automatic`); room join then OK in 1.7 s.
- **New LiveKit project** `aa-v5cciyrx` (key updated by Ashish in `avatar/.env`): REST auth and room join verified.
- **Phone access** via Cloudflare quick tunnel (`cloudflared tunnel --url http://localhost:3000`): page and API checked through the tunnel.
- **Ashish:** "working, checked in Telugu, we are rocking". The full session on the phone works end to end. **Phases 3–5 exit checkpoints met** (pending only the stage rehearsal items in `context/DEMO.md`).

## Humanish pass (2026-11-22), after Ashish's phone screenshot
Ashish: "the UI looks good but it doesn't give the same humanish feeling". Two causes in the screenshot:
1. **It looked like a chat app** (small round face + chat bubbles). **Now, with the avatar on, the room is a video call:** the face fills the screen, the current line shows as a subtitle (buddy, or the learner while talking), and topic / covered chips / controls float on translucent bars. The voice-only look (orb + chat) is unchanged. Verified with the real avatar (BeyondPresence, new key) at 390×844.
2. **The reply was robotic:** the filler "అంటే" was sent as a turn, and the buddy *defined the word* in formal "మీరు". Prompt changes:
   - fillers and fragments get a short "go on" ("హా, చెప్పు…"), never an explanation
   - always the informal you (నువ్వు / നീ)
   - 1–3 short sentences; react like a person first; vary openings; no comments on how they feel unless they raise it
   - Real brain: "అంటే" → "హా, చెప్పు… నీకు ఏది కావాలంటే అది మొదలుపెట్టు."; "బోర్ గా ఉంది" → "అరె, బోర్ కొట్టడం సహజమేనే…"; gravity → "ఓహ్, గ్రావిటీ అంటే చాలా సింపుల్!…"
- **End-of-turn patience:** LiveKit's end-of-turn model doesn't know Telugu/Malayalam, so a pause alone ends the turn. Wait 0.9 s instead of 0.5 s (`ENDPOINTING_MIN_DELAY`), so a thinking pause isn't sent as its own turn.
- Tests: worker 114, avatar 58; frontend builds.

## "It changed to the AI interview thing" (2026-11-22)
- **Cause:** LiveKit project `aa-v5cciyrx` (the key Ashish switched to) has the **old Presence View interviewer deployed** somewhere (not on this laptop). It joins **every** new room automatically, with a BeyondPresence avatar named "Presence". Proven: in a room where our agent was *not* dispatched, `agent-AJ_…` + `bey-avatar` ("Presence") joined within 4 s.
- **Fix (Ashish):** a new LiveKit project, `withyou-vbwmh652`. Verified: no uninvited agent in 16 s; our agent is dispatched → avatar started → greeting complete.
- Our agent only ever joins by explicit dispatch (`padippu-buddy`), so it can't cause this itself. **Lesson for the demo:** use a LiveKit project with nothing else deployed on it.

## "Just talk" mode: the emotional buddy (2026-11-22, Ashish's request, beyond BUILD_PLAN)
- **Start screen:** choose **Study** (as before) or **Just talk** (ఊరికే మాట్లాడదాం / വെറുതെ സംസാരിക്കാം), plus the language. `POST /calls/ {mode}` → stored on the call → `system_init {mode}` → `state["session_mode"]`.
- **Talk mode** (`worker/brain/talk.py`):
  - its own listener persona: reflect feelings, one gentle open question, short; no toxic positivity, no diagnosis ("a buddy, not a therapist"); practical ideas only if wanted; studying only if asked
  - no understanding map, coaching or quiz bookkeeping
  - talk-mode wording for wrap-up / silence / goodbye; its own greeting in ml/te/en (agent)
  - the room hides topic and idea chips
  - the end card is a gentle note; **what was shared is never put on the card** (covered/improved cleared in code, since the model repeated private details)
- **Crisis safety in both modes:** self-harm / wanting-to-die language (English, Telugu, Malayalam) is detected **in code**. The next reply gets a one-turn instruction: calm, serious, thank them for telling, ask if they're safe, talk to someone trusted, **Tele-MANAS 14416**, **112** in danger, "a buddy, not a counsellor". It's never cheerful and never ends the session, even if phrased as a goodbye. The end card then always shows the helpline text word for word (`help`). Everyday phrases ("this exam is killing me", "I could die laughing") don't trigger it.
- **Real brain (Telugu, talk mode):** exam stress → validating + gentle question; fear of mom scolding → empathy, no study push; "కొన్నిసార్లు నాకు చనిపోవాలని అనిపిస్తుంది" → "నువ్వు ఇప్పుడు safe గా ఉన్నావా? … buddy ని మాత్రమే, counsellor ని కాదు … 14416 … 112". The opening ("I'm happy you told me") was fixed to "thank you for telling me".
- **Tests:** new `worker/tests/test_talk.py` (19): crisis phrases en/te/ml, everyday non-crisis phrases, safety reply in study mode that doesn't end the session, talk mode skips study bookkeeping, listener prompt, talk goodbye + private card + helpline. **Worker 133, avatar 58**; frontend builds.

## Phase 6: Production-level app (2026-11-22). Ashish: "it's just two buttons; judges won't find it interesting"
Plan written to `context/plan.md` (Phase 6). Built:
- **Backend:**
  - migration **0006** (`interviews.language`, `topic`, `user_id` + index)
  - `GET /me/sessions`, `/me/sessions/{id}` (talk sessions never expose what was shared), `/me/stats` (day streak in IST, this week, ideas understood, topics with progress, last-14-days activity)
  - calls take a starting **topic** (the brain plans its key ideas at setup; the agent greets with it) and a **voice** (Kavya/Shubh)
  - mood chips start talk sessions: the greeting acknowledges the mood and the talk prompt knows it
  - Tests: avatar **61** (+ `test_me_routes.py`), worker **135**
- **App** (`frontend/src/features/app/`), all in ml/te/en:
  - **app shell:** bottom tab bar on phones, side rail on desktop
  - **Home:** greeting by time of day, real stats tiles (streak / this week / ideas), two rich mode cards, "pick up where you left off" (topic progress bar + the recap's next-time line), quick-topic chips, mood check-in
  - **Learn:** type any topic or pick from your topics / suggestions
  - **History:** grouped by day → **Session detail:** recap card + key ideas with status, "study this again", helpline button if needed
  - **Progress:** streak, 14-day strip, totals, per-topic progress
  - **Profile:** language, buddy voice, Help & safety (tap-to-call 14416), sign out
  - **/session:** auto-starts from the tap, with a connecting animation → room → recap with Home / Again
  - Login and 404 rebranded (no more "Presence View"); the old recruiter dashboard frame was removed; the PWA starts at `/`
- **Verified:** screenshots at 390×844 (and 1280 desktop) of login, Home, Learn, History, detail, Progress and Profile, with a seeded demo learner (`demo.learner@studybuddy.local` / `demo-password-123`, 4 Telugu sessions in the dev DB). Build + PWA check OK.

## Phase 7: Personal, multilingual, tracks feelings and learning (2026-11-22)
Ashish's feedback (and "if stuck, note it and move ahead"). Done:
- **History fixed:** found in the real data:
  - the brain's placeholder topic "not chosen yet" was shown as a topic
  - connect-and-leave sessions with no learner turns cluttered the list
  - talk sessions got topics ("humor")
  - pre-migration sessions had no mode/language
  
  Now: empty sessions are hidden, placeholders are never topics, talk sessions have no topic, and the language is inferred from the transcript script for old sessions. The worker also stops saving placeholder topics, and saves `mode`, `self_mood` (mood chip) and `crisis`.
- **"Pick up where you left off" in the chosen language:** saved text (topic, recap title/summary/next-time, concepts, suggestions) is translated to the UI language with **Sarvam Translate** (`sarvam-translate:v1`, verified live; Redis-cached 30 days; the original on any failure). `?lang=` on all `/me` endpoints. Verified: a Malayalam "സൗരയൂഥം" session shows as "సౌర వ్యవస్థ" in the Telugu UI.
- **Suggestions from your own history:** `GET /me/suggestions` returns unfinished topics (with their next open concept) and the topics the buddy suggested next at the end of sessions. The recap now returns `suggested_next` (real brain: "ఆక్సిజన్ విడుదల, మొక్కల శ్వాసక్రియ, ఆకుల నిర్మాణం"). Home: the continue card comes from it, and "నీ కోసం / For you" chips; defaults only for new learners.
- **"Ideas" → "Concepts"** (కాన్సెప్ట్స్ / കൺസെപ്റ്റുകൾ) everywhere, with a one-line explainer.
- **Feelings and learning levels:**
  - The recap call also returns a gentle **mood read** (level 1–5 + label from a fixed set; validated, else dropped). Real brain: `{level: 4, label: happy}`.
  - `GET /me/stats` adds a 14-day mood timeline, a summary (average / trend / most common), a **learning level** per topic (Just started / Getting there / Confident, from the share of concepts understood), and `crisis_recent`.
  - **Insights** screen (was Progress): streak, a "how you've been feeling" chart + gentle summary, learning level badges, the concepts explainer, an "only you can see this, not a diagnosis" note, and a Tele-MANAS nudge if crisis language came up recently. History and session detail show the level and mood too.
- **Tests:** worker **136**; avatar **67** (+ history filters, suggestions, insights, translation display, translate cache/fallback). Verified at 390×844 with the demo learner.
- **Noted, not done:**
  - the in-session recap card (`/calls/recap`) is shown in the session's own language, which matches the UI unless the learner switched language mid-session
  - mood reads exist only for sessions recorded from now on (older ones show no mood)

## Session summary so far (2026-11-22), for Ashish
Commits on `main` (fresh history; the old `.git` was moved to `../presenceview-hackvesrion.git-backup`):

| Step | Commit | What |
|---|---|---|
| Snapshot | `65a45a4` | Presence View as-is before the reshape |
| Phase 0 | `b895eaa` | Proctoring, hiring, desktop app, DSA round and recording removed; one signed-in learner |
| Fixes | `977de04`, `6f1be37` | Named agent dispatch; voice-only fallback when BeyondPresence fails; Redis read timeout; Deepgram TTS (Cartesia out of credits) |
| Phase 1 | `64a87dd` | Study-buddy persona; chat/explain/check intents; gentle flow |
| Phase 2 | `5240384`, `4156b37` | Sarvam-105B brain (reasoning off, ~1 s), Saaras STT, Bulbul v3 TTS (Kavya); Malayalam + Telugu + English; language picker |
| Voice fixes | `338aebf`, `64c94dd`, `c857a3d`, `ae85d62` | Mojibake in Indic replies; noise suppression; echo loop (buddy hearing itself); Telugu misheard as Kannada (STT locked to the session language, switch by buttons or voice) |
| Phase 3 | `00f68ea` | Gentle evaluator: concept map, coaching, one follow-up for vague answers |
| Phase 4 | `fa6b1e3` | Mobile-first learner screen; installable PWA |
| Phase 5 | `ab80a16` | Kind recap card, session memory, demo kit (`context/DEMO.md`) |
| Phone test | `9f2a660` | Passed in Telugu. Hotspot IPv6 broke LiveKit → `sudo networksetup -setv6off Wi-Fi` |
| Humanish | `b11744a` | Video-call layout with the avatar; fillers, informal "you", shorter replies |
| LiveKit | `5266b6c` | Old interviewer deployed on project `aa-v5cciyrx` joined every room → moved to clean project `withyou-vbwmh652` |
| Talk mode | `53f86a8` | "Just talk" emotional buddy + crisis safety (Tele-MANAS 14416 / 112) |
| Phase 6 | `2682c89`, `6a0b714` | Production app: Home, Learn, History, Insights, Profile; `/me` API; migration 0006 |
| Phase 7 | `2fdb0f9`, `8714915` | History fixes; translation to the chosen language; personal suggestions; "ideas" → concepts; mood + learning levels |

**Demo account:** `demo.learner@studybuddy.local` / `demo-password-123` (5 sessions, streak, concepts, moods, one Malayalam session).

**Running locally:** 4 tabs (worker, API, agent, web) + a Cloudflare tunnel for the phone; keep IPv6 off on the hotspot.

## Phase 8 (in progress): "the UI still feels AI-ish". Direction chosen: notebook + buddy character
Done so far (committed as work in progress, not yet visible: the pages don't use it yet):
- Fonts: Baloo Tammudu 2 (Telugu + Latin), Baloo Chettan 2 (Malayalam), Caveat (handwritten notes), self-hosted via @fontsource.
- A `notebook` theme area in `src/ui/tokens.css`: warm paper, pencil ink, leaf green, turmeric, terracotta, margin red; ruled-paper background (SVG pattern, since the UI rules forbid gradients); `.sketch` hand-drawn borders; `.sticky` notes with `.tape`; `.highlight`; buddy animations (bob, blink, talk); respects reduced motion.
- Tailwind: `turmeric`, `turmeric-soft`, `terracotta` colours and a `font-hand` family.

Next:
- an SVG buddy character with expressions (happy / listening / thinking / speaking / caring) for Home and voice sessions
- notebook-style Home (speech-bubble greeting, sticky-note "next time", margin-note streak), diary-style History, hand-plotted Insights, a notebook login
- screenshots, then commit
- Phase 8 done: buddy character (`features/app/Buddy.tsx`: happy, listening, thinking, speaking, caring, wave) on Login, Home, the session screens (its face follows the voice state instead of the orb) and the desktop rail; notebook primitives (`features/app/notebook.tsx`: SpeechBubble, StickyNote with tape, Scribble underline, MarginNote); paper + margin line on every screen; drawn boxes and buttons on Learn, History, Insights, Profile, the recap ("next time" is a sticky note). Build and UI rules pass; checked by screenshots at 390×844.

## Feature: study a page from your textbook (photo)
- Learn → "Study a page from your book" → camera. The phone shrinks the photo (max 1600 px JPEG) and sends it to `POST /api/pages/read` (`avatar/api/page_routes.py`).
- Gemini reads the page: topic, 2–4 key ideas and a one-line summary in the chosen language, plus the page text. `gemini-3.5-flash-lite` (~2 s), backup `gemini-3.1-flash-lite`; `gemini-3.8-flash` took over 40 s or returned 503, so it isn't used. Non-study photos get a friendly "try a clearer photo".
- The page is kept in Redis for 24 h under `page:{user}:{id}`, readable only by its owner. `POST /calls/` with `page_id` sends it in `system_init`; the worker uses the page's ideas as the session plan (no planning call) and puts the page text in the buddy's prompt ("your book says…").
- Config: `GOOGLE_API_KEY` added to `avatar/.env` (same key as the worker), `PAGE_MODELS`.
- Tested: unit tests (worker 138, API 69 passing); live Gemini read in Telugu and Malayalam; end-to-end upload in the app (screenshots). Not yet tested: a full voice session started from a page.

## Feature: Test your knowledge (you teach the buddy)
- Learn has a switch: "Learn it" (the buddy teaches) or "Test your knowledge" (the student teaches, the buddy is a curious younger student). A photographed page also offers "Test me on this page".
- `style: learn|teach` goes from `POST /calls/` → saved call (agent greeting: "Today you're the teacher…", in ml/te/en) → `system_init` → worker `study_style`.
- Worker: reply mode "student"; the role swap goes in the prompt's `<system_instruction>` slot (it lost to the "explain" rule when it sat in session memory, seen live: the buddy explained). Safety, goodbye and follow-up instructions still win. Every real explanation (4+ words) is assessed, so concepts turn green as the student teaches. The buddy asks "why / what if / example?" and now and then slips in one plausible wrong idea as a genuine guess.
- Live check in Telugu: the buddy repeats what it heard, asks "what happens in a dark room?", and suggests "plants eat soil, right?". Tests: worker 139, API 70.

## Feature: your garden (Insights)
- The learning-level bars are replaced by a garden (`features/app/Garden.tsx`): one plant per topic, one leaf per concept (green once understood, an outline while growing), a taller stem as the level rises, and a flower when the whole topic is understood. Tap a plant to study that topic again. Text in ml/te/en.
- Fix found in the screenshots: Sarvam Translate sometimes returns chatter ("The translation of the input text…") for short topic names. `looks_broken()` now keeps the original text and doesn't cache the bad result; the bad cache entry was deleted. Tests: API 71.

## Deployed (2026-11-22)
- **Live at https://13.205.190.12.sslip.io** (Let's Encrypt HTTPS via Caddy; sslip.io gives a free name for the IP).
- AWS account profile `alex`, region ap-south-1, kept apart from the interview platform's `alex-staging-*` servers and VPC: instance `i-0611864ba60c5c91a` (t3.medium, Ubuntu 24.04, 30 GB), security group `sg-08444f2c795ae8ce7` (80/443 open, SSH only from the owner's IP), Elastic IP `eipalloc-0eb599900b9982454`, key pair `study-buddy` (`~/.ssh/study_buddy`). Everything is tagged `project=study-buddy`. About $1–1.5 a day.
- One server runs everything in Docker: Postgres, Redis, migrations, API, voice agent, brain worker, frontend (nginx), Caddy. Files: `deploy/buddy/`. Redeploy after a commit: `deploy/buddy/deploy.sh 13.205.190.12`. Secrets go over SSH from `avatar/.env` and `worker/.env`; the server's own `.env` holds generated DB/Redis passwords and AUTH_SECRET. Sign-up is on.
- Fixes for production: nginx upload limit 1 MB → 10 MB (page photos), camera allowed for the app itself, avatar image no longer copies the removed DSA module, and the agent image tolerates the LiveKit download tool crashing on exit when the model files are present.
- The demo learner was copied (only their organisation, user and 8 sessions). Checked: all 7 services healthy, the agent registered with LiveKit (India South), login works, the photo feature works on the live site.
- **The laptop's agent must not run at the same time** (same LiveKit project and agent name: LiveKit could give a call to the laptop).
- Teardown: terminate `i-0611864ba60c5c91a`, release `eipalloc-0eb599900b9982454`, then delete `sg-08444f2c795ae8ce7` and key pair `study-buddy`.

## Tamil and Hindi (2026-11-22)
- New languages `ta-IN` and `hi-IN` everywhere the first three are: API checks, voice agent (greetings, topic / talk / mood / teach greetings, nudges, "switched" lines; Tamil and Devanagari script detection so the voice follows the reply), brain (informal நீ / तुम, spoken not formal style), voice switching ("தமிழ்ல சொல்லு", "हिंदी में बोलो", "speak tamil"), goodbyes + yes/no, explain/quiz intents, recap fallback text, helpline text, talk goodbyes, photo reading, and the app (about 200 phrases each, language buttons, topic suggestions, Baloo Thambi 2 + Baloo 2 fonts).
- Tamil "bye" (பை) only counts as a whole word: it is inside பையன் ("boy").
- **Needs a native speaker's review before real students use it:** the Tamil and Hindi crisis phrases in `worker/brain/talk.py` (safety), and the app/buddy wording.
- Live checks: Sarvam-105B replies naturally in both (Hindi mixes in some English, which is normal Hinglish); Bulbul v3 Kavya speaks both. Tests: worker 143, API 72.
- In the study room the five language buttons scroll sideways if the screen is narrow.
