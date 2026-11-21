# Demo kit: Padippu Koottukaran (Study Buddy)

Written for the HackaThoni stage. Everything here exists in the code; the voice
parts still need Ashish's rehearsal (see "Before going on stage").

---

## 1. Run it (laptop, 4 terminals, from the repo root)

```bash
cd worker && uv run worker.py
cd avatar && uv run python main.py
cd avatar && uv run python -m agents.entrypoint dev
cd frontend && npm run dev            # http://localhost:3000
```

Needs Redis (`brew services start redis`) and the dev Postgres (`colima start`, container `alex-postgres`).

**On a phone:** `cloudflared tunnel --url http://localhost:3000` → open the `https://….trycloudflare.com` link on the phone (HTTPS is required for the mic). Sign in, then "Add to Home Screen" to install the app.

---

## 2. Topics to demo (tested end to end through the real brain)

| # | Language | Say this | What the audience sees |
|---|---|---|---|
| 1 | తెలుగు | "ప్రకాశసంశ్లేషణ అంటే ఏమిటి? నాకు చెప్పు" → "నన్ను క్విజ్ చేయి" → half-right answer ("మొక్కలు సూర్యరశ్మి వాడతాయి, ఆకులు ఎర్రగా ఉంటాయి అనుకుంటా") → "ఏమో" → right answer | Warm explanation, one gentle question, "…కరెక్ట్! కానీ…" coaching, one kind follow-up, the idea chip turns green, recap card at the end |
| 2 | മലയാളം | "പ്രകാശസംശ്ലേഷണം എന്താണെന്ന് പറഞ്ഞുതരാമോ?" | Same loop in Malayalam |
| 3 | switch | mid-session: "ఇప్పుడు మలయాళంలో చెప్పు" (or tap മല) | The buddy switches language, voice and listening on the spot |

Good second topics: the water cycle, fractions ("what is a half plus a quarter?"), Newton's first law.

---

## 3. The 3-minute pitch

**0:00 Problem (30 s).** Millions of students in Kerala and Andhra study alone at night. Videos don't listen. Tests judge. Nobody checks *gently* whether you actually understood, in your own language.

**0:30 What it is (20 s).** Padippu Koottukaran: a study buddy you talk to, in Malayalam or Telugu. It teaches, asks, *listens to your real answer* and coaches you. It never grades.

**0:50 Live demo (90 s).** Topic 1 on the phone. Point at the idea chips turning green, and the "you're close!" coaching. End the session and show the recap card.

**2:20 How it works / unfair edge (30 s).** Not a weekend prototype: a real-time voice and evaluation engine we built for AI interviews, reshaped tonight.
- Sarvam Saaras speech recognition, Sarvam-105B, Bulbul voice
- Replies in about 1 s, because the answer is spoken *before* any assessment runs
- Understanding is checked against the learner's own words (quoted evidence), and turned into coaching instead of a score

**2:50 Close (10 s).** "Learning shouldn't feel like an exam. It should feel like a friend sitting next to you."

---

## 4. Fallbacks (pre-staged; flip one setting, restart that process)

| If this breaks… | Do this |
|---|---|
| **The network blocks LiveKit** (IPv6-only hotspots, e.g. Jio: the agent can't join rooms) | Use venue Wi-Fi for the laptop, or turn IPv6 off for that interface: `networksetup -listallnetworkservices`, then `networksetup -setv6off "<service>"` (undo: `-setv6automatic`) |
| Sarvam voice/speech is down | `VOICE_PROVIDER=deepgram` in `avatar/.env` (English voice; tap **EN**) |
| Sarvam-105B is slow or failing | Automatic: replies fall back to Gemini. To force it: `FAST_LLM_PROVIDER=gemini` in `worker/.env` |
| Noisy hall: the buddy reacts to chatter | Headset mic. Tap the **mic button** to mute between turns (manual push-to-talk). `ALLOW_INTERRUPTIONS` is already off |
| The buddy cuts you off mid-sentence or waits too long | `avatar/.env`: interruptions stay off; for pauses, tune `TURN_HANDLING` endpointing (`min_delay` / `max_delay` in `agents/entrypoint.py`) |
| The avatar video is gone | Expected while BeyondPresence is out of credits: the voice-only orb is the design |
| Everything is down | Play the backup clip (record a 30 s screen recording of a good session **before** the event) |

---

## 5. Before going on stage (needs Ashish)
- [ ] A full session on the phone over the network you'll use, timed to 3 minutes with the pitch
- [ ] Check the Telugu greeting, goodbyes and recap wording (written by Claude, not checked by a native speaker)
- [ ] Record the 30 s backup clip
- [ ] Charge the phone; carry a headset mic
