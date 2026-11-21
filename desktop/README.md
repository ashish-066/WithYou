# Presence View desktop app

Shows the interview page in a locked window (Electron), for Mac and Windows. The app icon is `build/icon.png`
(made from the Presence View logo); `src/icon.png` is the window and taskbar icon.

## What it does

1. Opens from an interview link (`presenceview://interview?invite=TOKEN`).
2. Explains what's monitored, lists blocked apps from `src/blocklist.js`, and closes them only if the candidate agrees.
3. Locks when the interview starts: full screen, no close or quit, no copy and paste, clipboard cleared.
4. Reports to the recruiter's session: blocked apps, extra screens, leaving the window, close attempts, emergency exit.
5. Unlocks when the interview ends.

If the app dies while locked (force quit, crash, power loss), a lock file stays on disk. The next start reports it,
locks again and offers to rejoin.

## Safety rules

- **Emergency exit:** Ctrl or Cmd + Alt + Shift + E always unlocks the app, and the recruiter sees it was used.
- **Time limit:** the lock ends by itself after 4 hours.
- **Closing apps:** only apps in the blocklist, never system folders, and only after the candidate agrees. They're asked
  to close first. On Windows, chat and meeting apps (Teams, Slack, Discord, WhatsApp, Zoom) then just hide in the
  system tray, so the app lists what's still running and ends it only if the candidate clicks "Force close".
- **Shutting down:** the app never holds up the computer shutting down.

## What it can't do

No normal app can stop force quit on Windows, Ctrl+Alt+Delete, the power button or a second device. Those are detected
where possible and reported, not prevented. If a candidate force quits and never reopens the app, nothing is reported.

## Run it

```bash
npm install
npm test
npm start -- "presenceview://interview?invite=TOKEN"
```

`app-config.json` sets the app address. Unpackaged runs can override it with `PRESENCE_APP_URL`, and
`PRESENCE_DEV_NO_KIOSK=1` runs without full-screen lock, which is safer while developing.
`PRESENCE_DEV_IGNORE_APPS=Claude,Slack` leaves those apps alone during a test.

## Build installers

```bash
npm run dist
```

Set `appUrl` in `app-config.json` to the production address first. Candidates need signed installers: an Apple Developer
account and notarization on Mac, and a code-signing certificate on Windows. Without them they get security warnings.
