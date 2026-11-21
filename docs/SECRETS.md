# Secrets

Every credential the platform uses, who needs it, and how to rotate it.

## Rules

- Secrets live in the hosting platform's secret manager and reach services as
  environment variables. No `.env` files on servers, never in git (a gitleaks
  pre-commit hook and CI job enforce the second part).
- `.env` files are for local development only, created from `.env.example`.
- Each environment (dev / staging / production) has its **own** keys. Never
  share a production key with dev or staging.
- With `ENVIRONMENT=production`, services refuse to start if a required secret
  is missing (see the "Prod" column).
- If a secret may have leaked (committed, pasted in chat, logged, laptop lost):
  rotate it first, investigate second.

## Inventory

| Variable | Service(s) | Prod | Used for | Rotate |
|---|---|---|---|---|
| `AUTH_SECRET` | avatar API | required (32+ chars) | Signs login cookies and invite links | Generate a new random value (`python -c "import secrets; print(secrets.token_urlsafe(48))"`), deploy. Everyone is signed out and **unused invite links stop working** — resend them. |
| `REDIS_URL` (password) | avatar API, LiveKit agent, brain worker | password required | All live state, streams, auth records | Add the new password in Redis (`ACL SETUSER` / provider console), update `REDIS_URL` everywhere, restart, then remove the old password. |
| `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET` | avatar API, LiveKit agent | required | Room creation, participant tokens, agent connection, recording | Create a new key pair in LiveKit Cloud, deploy both services, delete the old key. Active calls keep running; new tokens use the new key. |
| `LIVEKIT_URL` | avatar API, LiveKit agent | required | LiveKit project endpoint | Not secret, but environment-specific. |
| `DEEPGRAM_API_KEY` | LiveKit agent | required | Speech-to-text | New key in Deepgram console → deploy agent → revoke old. |
| `CARTESIA_API_KEY` | LiveKit agent | required | Text-to-speech | New key in Cartesia → deploy agent → revoke old. |
| `BEY_API_KEY` | LiveKit agent | required | Beyond Presence avatar video | New key in Beyond Presence → deploy agent → revoke old. |
| `GOOGLE_API_KEY` / `GEMINI_API_KEY` | brain worker | required | Gemini LLM calls | New key in Google AI Studio / Cloud console → deploy workers → delete old. **The key committed in `backend/.env` (commit `d77e1c8`) must be revoked.** |
| `TAVILY_API_KEY` | brain worker | optional | Web search tool | New key in Tavily → deploy → revoke old. |
| `GITHUB_TOKEN` | brain worker | optional | GitHub profile crawling (rate limits) | Fine-grained token, public-read only, short expiry. Regenerate → deploy → delete old. |
| `PROXYCURL_API_KEY` | brain worker | optional | LinkedIn profile data | New key → deploy → revoke old. |
| `HUME_API_KEY` | brain worker | optional | Expression analysis of recordings | New key → deploy → revoke old. |
| `S3_ACCESS_KEY`, `S3_SECRET_KEY` | avatar API (LiveKit egress) | needed for recording | Writing interview recordings | Prefer an IAM role over static keys. Otherwise: new access key for the same IAM user → deploy → deactivate → delete the old key. |

Not secrets, but security-relevant settings: `CORS_ORIGINS` (explicit origins
required in production), `ALLOW_SIGNUP`, `ENABLE_DEMO`, `SANDBOX_MODE`
(`docker` required in production), `SANDBOX_IMAGE` (pin by digest).

## Accounts

- The first account is created with
  `cd avatar && uv run python -m scripts.create_user --platform-admin ...`
  (prompts for the password; never pass it on the command line).
- Platform admins can see every organization's data — keep that group tiny.
- Removing a user currently means deleting their `auth:user:{id}` record in
  Redis (their cookie stops working on the next request). A proper admin UI
  for this is a Phase 7 item.
