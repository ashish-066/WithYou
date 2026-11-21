/**
 * Shown in the desktop app before an interview: explains what will be locked
 * and monitored, asks permission to close blocked apps, and checks the screens.
 */

import { useCallback, useEffect, useState } from 'react';
import type { DesktopStatus, PresenceDesktop } from '@/services/desktopApp';

interface SecureAppCheckProps {
  desktop: PresenceDesktop;
  onReady: () => void;
}

export function SecureAppCheck({ desktop, onReady }: SecureAppCheckProps) {
  const [status, setStatus] = useState<DesktopStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  // Asked to close but still running (on Windows, chat and meeting apps hide in the tray)
  const [stillRunning, setStillRunning] = useState<string[]>([]);

  const refresh = useCallback(async () => {
    setMessage(null);
    try {
      setStatus(await desktop.status());
    } catch {
      setMessage('Could not check this computer. Please try again.');
    }
  }, [desktop]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const closeApps = async (force: boolean) => {
    setBusy(true);
    try {
      const remaining = await desktop.closeBlockedApps({ force });
      await refresh();
      setStillRunning(remaining.map((app) => app.name));
      if (remaining.length > 0 && force) {
        setMessage('Some apps could not be closed. Please close them yourself (also from the system tray), then check again.');
      }
    } catch {
      setMessage('Closing the apps failed. Please close them yourself, then check again.');
    } finally {
      setBusy(false);
    }
  };

  const start = async () => {
    setBusy(true);
    try {
      if (await desktop.requestMedia()) {
        onReady();
      } else {
        setMessage(
          navigator.userAgent.includes('Windows')
            ? 'Camera or microphone access is turned off. In Windows Settings > Privacy & security, turn on Camera and Microphone, including "Let desktop apps access", then try again.'
            : 'Please allow camera and microphone access in your system settings, then try again.',
        );
      }
    } finally {
      setBusy(false);
    }
  };

  const blocked = status?.blockedApps ?? [];
  const extraScreens = (status?.displays ?? 1) > 1;
  const ready = status !== null && blocked.length === 0 && !extraScreens;

  return (
    <div className="loading-screen">
      <div className="loading-content" style={{ maxWidth: 560, textAlign: 'left' }}>
        <img src="/logo.png" alt="Presence View" style={{ height: 56, marginBottom: 16 }} />
        <h1 className="ended-title">Before you start</h1>

        <div className="ended-subtitle">
          <p>During this interview:</p>
          <ul style={{ margin: '8px 0 16px 20px', listStyle: 'disc' }}>
            <li>This app fills your screen and stays locked until you submit.</li>
            <li>Your camera and microphone are on, and the interview is recorded.</li>
            <li>
              The camera is checked for other people and devices; a photo is saved for your recruiter if one is
              detected.
            </li>
            <li>Your clipboard is cleared, and copy and paste are turned off.</li>
            <li>The app checks for the apps below and for extra screens. It only reports apps it blocks.</li>
            <li>Your recruiter sees what is flagged and makes the final decision.</li>
          </ul>
          <p>
            In an emergency, press <b>Ctrl or Cmd + Alt + Shift + E</b> to unlock the app. Your recruiter will see that
            you used it.
          </p>
        </div>

        {blocked.length > 0 && (
          <div className="ended-subtitle" style={{ marginTop: 16 }}>
            <p>
              <b>These apps need to close. Save your work in them first.</b>
            </p>
            <ul style={{ margin: '8px 0 12px 20px', listStyle: 'disc' }}>
              {blocked.map((app) => (
                <li key={app.name}>
                  {app.name} ({app.category})
                </li>
              ))}
            </ul>
            {stillRunning.length > 0 ? (
              <>
                <p style={{ marginBottom: 12 }}>
                  {stillRunning.join(', ')} {stillRunning.length === 1 ? 'is' : 'are'} still running in the background
                  (for example in the system tray). Force closing ends {stillRunning.length === 1 ? 'it' : 'them'}{' '}
                  without saving.
                </p>
                <button className="ended-button" onClick={() => closeApps(true)} disabled={busy}>
                  {busy ? 'Closing…' : 'Force close'}
                </button>
              </>
            ) : (
              <button className="ended-button" onClick={() => closeApps(false)} disabled={busy}>
                {busy ? 'Closing…' : 'Close these apps'}
              </button>
            )}
          </div>
        )}

        {extraScreens && (
          <p className="ended-subtitle" style={{ marginTop: 16 }}>
            <b>
              {status?.displays} screens are connected. Unplug the extra screens or turn off mirroring, then check
              again.
            </b>
          </p>
        )}

        {message && (
          <p className="ended-subtitle" role="alert" style={{ marginTop: 16 }}>
            <b>{message}</b>
          </p>
        )}

        <div style={{ display: 'flex', gap: 12, marginTop: 20 }}>
          <button className="ended-button" onClick={refresh} disabled={busy}>
            Check again
          </button>
          <button className="ended-button" onClick={start} disabled={busy || !ready}>
            I agree, continue
          </button>
        </div>
      </div>
    </div>
  );
}
