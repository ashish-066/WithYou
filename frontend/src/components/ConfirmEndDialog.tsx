/**
 * Asked before a candidate ends the interview, so a stray click on "End"
 * doesn't finish it. Ending can't be undone: the link can't be used again.
 */

import { useEffect, useRef } from 'react';

export function ConfirmEndDialog({
  open,
  ending,
  onCancel,
  onConfirm,
}: {
  open: boolean;
  ending?: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  const stayRef = useRef<HTMLButtonElement | null>(null);

  useEffect(() => {
    if (!open) return;
    stayRef.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onCancel();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onCancel]);

  if (!open) return null;
  return (
    <div className="camera-warning-backdrop">
      <div
        className="camera-warning camera-warning--neutral"
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="confirm-end-title"
        aria-describedby="confirm-end-message"
      >
        <h2 id="confirm-end-title">End the interview?</h2>
        <p id="confirm-end-message">
          Your answers so far will be sent to the hiring team. You can’t come back to this interview after ending it.
        </p>
        <div className="camera-warning-actions">
          {/* The safe choice first, and focused */}
          <button ref={stayRef} className="camera-warning-button" onClick={onCancel} disabled={ending}>
            Keep going
          </button>
          <button className="camera-warning-button camera-warning-button--danger" onClick={onConfirm} disabled={ending}>
            {ending ? 'Ending…' : 'End interview'}
          </button>
        </div>
      </div>
    </div>
  );
}
