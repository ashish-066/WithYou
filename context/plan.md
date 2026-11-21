# plan.md: Padippu Koottukaran reshape (working plan)

The source spec is `context/BUILD_PLAN.md`. This file turns it into concrete steps against the **real** repo, based on a code read on 2026-11-21. The running log is `context/RESHAPE_CHANGELOG.md`.

Rules I follow: one phase at a time; tests green before each commit; one commit per phase or logical step; stop and ask Ashish for anything I can't verify myself (audio, Malayalam quality, phone).

---

## Baseline (before any change)

| Item | State |
|---|---|
| Branch | `launch/phase-2`, with uncommitted WIP (17 modified, 2 untracked files) |
| Worker tests | 108 passed, 25 skipped |
| Avatar (API + voice agent) tests | 50 passed, 59 skipped (skips need Postgres) |
| Redis | running (brew) |
| Postgres | dev DB is the docker container `alex-postgres` on :5434. Colima is **stopped**, so it is down. |
| LiveKit | `livekit-agents==1.8.10` with the Deepgram, Cartesia, Silero, turn-detector, Bey and BVC plugins |
| Sarvam key | **not present** in `avatar/.env` or `worker/.env` |

## Key findings that change the BUILD_PLAN

1. **An official LiveKit Sarvam plugin exists.** `livekit-plugins-sarvam==1.8.10` matches our agents version exactly, so **no custom adapter is needed**. What it provides (read from the wheel source, still to be confirmed with a live probe):
   - TTS: `sarvam.TTS(model="bulbul:v3", target_language_code="ml-IN", speaker=...)` over the WebSocket `wss://api.sarvam.ai/text-to-speech/ws`. `ml-IN` is listed for v3. Speakers include `shubh` (the v3 default), plus `kavya`, `priya`, `neha` and others.
   - STT: `STTRealtime` uses `saaras:v3-realtime` over `wss://api.sarvam.ai/speech-to-text-realtime/ws` (streaming). There is also a batch `STT`.
   - LLM: `sarvam-105b` sits behind an OpenAI-compatible API at `https://api.sarvam.ai/v2`, authenticated with `SARVAM_API_KEY`.
2. **The worker LLM pool** (`worker/brain/models/llm_pool.py`) is Gemini-only, through `google.genai`, with a `FALLBACK_MODELS` list. Phase 2 adds Sarvam-105B as the first attempt (OpenAI-compatible HTTP), and Gemini stays as the fallback chain.
3. **The "role" drives the skill tree today.** `call_routes.create_call` gets `role_id` from an invite, and the worker builds the ladder/tree from the role's JD. For the buddy, the **topic** the learner names replaces the role and JD.

---

## Phase map with real files

### Spikes (P-0 / P-1 / P-2)
- `spikes/p0_tts.py` (Bulbul v3 `ml-IN` writes a WAV for you to play), `spikes/p1_stt.py` (Saaras on your recorded clip, timed), and `spikes/p2_phone.md` (steps).
- **Needs:** `SARVAM_API_KEY`. P-2 needs HTTPS reachable from your phone (LiveKit Cloud is already HTTPS, and the web client needs a tunnel or `vite --https`).

### Phase 0: Strip proctoring and hiring
DELETE:
- `desktop/` (Electron, whole folder), plus `frontend/src/services/desktopApp.ts`, `hooks/useSecureMode.ts` and `components/SecureAppCheck.tsx`
- Voice agent: `avatar/agents/vision.py`, `vision_monitor.py`, the camera-task, evidence and JPEG code in `entrypoint.py`, `avatar/KMS/` (model files), the `ai-edge-litert` dependency and `.local-evidence/`
- `avatar/api/proctoring_routes.py` + schemas, `worker/services/anti_cheat.py`, `frontend/src/services/proctoringApi.ts` and `components/CameraWarning.tsx`
- Verification probe timing-flag path: `worker/brain/verification_probe.py` (note where it was hooked in, because Phase 3 brings it back as a gentle follow-up)
- Elo: `worker/scoring/elo_system.py`, `avatar/api/elo_routes.py` + schemas, and `RankingsPage`
- Hiring and recruiter: invites (routes, `InvitesPage`), `org_routes`, `TeamPage`, `RolesPage`/`role_routes`, the recruiter report view, the `/platform` ops area, DSA/coding round (`worker/dsa`, `worker/sandbox`, `dsa_routes`, `DSAInterviewPage`, Monaco), Hume, Tavily, and the profile crawler and background verifier
- Tests that cover only deleted features (`test_proctoring_flags` ×2, `test_vision*`, `test_invite_background`, `test_org_routes`, `test_platform_routes`, `test_sandbox`, `test_problem_library`, `test_claim_check_nulls`, `test_candidate_background`)

KEEP: TurnRelay, Redis streams contract, `listen_for_brain_responses`, `InterviewMonitor` (silence/disconnect only), LangGraph graph, `prompt_injection`/`prompt_firewall`, LLM pool, scoring tree/ladder/evidence/question-selector, report generator, and the transcript.

Stub rather than rewrite: where deletions cascade, the call sites become no-ops. **The Redis stream contract is not touched.**

Exit: suites green, no proctoring code left (a grep for `vision|proctor|elo|invite|integrity` turns up only intentional leftovers), and the English voice loop still talks **[ASK ASHISH]**.

### Phase 1: Brain becomes the study buddy (English)
- New persona prompt in the fast-brain conversation (`worker/brain/tools/fast/conversation.py` and `brains/fast_brain.py`)
- Router intents (`brains/router.py` regex first, then `llm_router.py`): fast = chat/explain, slow = gentle check/plan, conclude = wrap-up
- Semantics in state, prompts and greeting: candidate→learner, interview→session (mechanical; data structures stay)
- `<candidate_input>` becomes `<learner_input>` if it's a trivial rename
- Tests: topic→explain, casual→chat, wrap-up→conclude. The reply-before-scoring test (`test_processor_early_reply`) stays green.

### Phase 2: Sarvam + Malayalam ⭐
- `avatar/pyproject.toml`: add `livekit-plugins-sarvam==1.8.10` and drop Deepgram/Cartesia (keep them only if you want an English fallback switch, see Phase 5)
- `entrypoint.py`: `sarvam.STTRealtime(language="ml-IN")` and `sarvam.TTS(model="bulbul:v3", target_language_code="ml-IN", speaker=<config>)`, with voice, language and model in `core/config.py`
- Worker: Sarvam-105B as the primary in `llm_pool.py`, with the Gemini list kept as fallback
- Malayalam greeting and Malayalam-by-default persona; retune endpointing if needed
- Tests: mocked adapter tests (audio→text, text→audio) and pool fallback (Sarvam fails→Gemini)

### Phase 3: Gentle evaluator loop
- Topic→sub-points ladder (reuse `scoring/ladder_generator.py` + `tree_manager.py`)
- Evidence extractor → understanding map; question selector targets the weakest sub-point
- Gentle follow-up (the probe returns as pedagogy): at most one per vague answer
- Coaching format: encouragement → gap → hint, never a score
- Tests per BUILD_PLAN §Phase 3

### Phase 4: Mobile-first PWA
- One learner screen: mic button, live Malayalam transcript, topic, a "covered" indicator
- Tailwind mobile-first, user-gesture audio start, `manifest.webmanifest` + a minimal SW (no caching of API or WebRTC)
- `npm run build` + type-check; Lighthouse installability check

### Phase 5: Recap, warmth, demo-proofing
- Report generator becomes a kind recap card; struggles get called back within the session
- Fallback toggles (English voice, push-to-talk) and 2–3 rehearsed topics

---

## Open questions / decisions (status)
Tracked in `RESHAPE_CHANGELOG.md` → "Decisions".
