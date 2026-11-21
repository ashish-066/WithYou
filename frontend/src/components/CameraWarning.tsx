/**
 * Pop-up for the candidate when the camera check (run by the voice agent on the
 * server) confirms a phone, another person or another device. Must sit inside
 * <LiveKitRoom>. The interview keeps running underneath: the clock never stops.
 */

import { useEffect, useRef, useState } from 'react';
import { useDataChannel } from '@livekit/components-react';

interface Notice {
  kind: string;
  title: string;
  message: string;
}

const decoder = new TextDecoder();

export function CameraWarning() {
  const [notice, setNotice] = useState<Notice | null>(null);
  const buttonRef = useRef<HTMLButtonElement | null>(null);

  useDataChannel('proctoring', (msg) => {
    try {
      const data = JSON.parse(decoder.decode(msg.payload));
      if (data?.type === 'camera_warning' && typeof data.title === 'string' && typeof data.message === 'string') {
        setNotice({ kind: String(data.kind ?? ''), title: data.title, message: data.message });
      }
    } catch {
      // Not a notice we understand
    }
  });

  useEffect(() => {
    if (notice) buttonRef.current?.focus();
  }, [notice]);

  if (!notice) return null;
  return (
    <div className="camera-warning-backdrop">
      <div
        className="camera-warning"
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="camera-warning-title"
        aria-describedby="camera-warning-message"
      >
        <h2 id="camera-warning-title">{notice.title}</h2>
        <p id="camera-warning-message">{notice.message}</p>
        <button ref={buttonRef} className="camera-warning-button" onClick={() => setNotice(null)}>
          I understand
        </button>
      </div>
    </div>
  );
}
