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
