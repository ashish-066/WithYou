import { createContext, useCallback, useContext, useMemo, useRef, useState, type ReactNode } from 'react';
import { X } from 'lucide-react';
import { StatusLabel, type Tone } from './StatusLabel';

interface Toast {
  id: number;
  message: string;
  tone: Tone;
}

interface ToastApi {
  /** Short confirmation after an action ("Invite revoked"). Errors stay until dismissed. */
  show: (message: string, tone?: Tone) => void;
}

const ToastContext = createContext<ToastApi | null>(null);

const toneWord: Partial<Record<Tone, string>> = { good: 'Done', bad: 'Failed', warn: 'Note' };

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const next = useRef(1);

  const dismiss = useCallback((id: number) => setToasts((t) => t.filter((x) => x.id !== id)), []);

  const show = useCallback(
    (message: string, tone: Tone = 'good') => {
      const id = next.current++;
      setToasts((t) => [...t.slice(-2), { id, message, tone }]);
      if (tone !== 'bad') setTimeout(() => dismiss(id), 4000);
    },
    [dismiss],
  );

  const api = useMemo(() => ({ show }), [show]);

  return (
    <ToastContext.Provider value={api}>
      {children}
      <div
        aria-live="polite"
        className="pointer-events-none fixed left-1/2 top-4 z-[60] flex w-[min(22rem,calc(100vw-2rem))] -translate-x-1/2 flex-col gap-2"
      >
        {toasts.map((t) => (
          <div
            key={t.id}
            className="pointer-events-auto flex items-start gap-3 border border-line-strong bg-surface px-4 py-3"
          >
            <div className="min-w-0 flex-1">
              {toneWord[t.tone] && <StatusLabel tone={t.tone}>{toneWord[t.tone]}</StatusLabel>}
              <p className="mt-0.5 text-body text-ink">{t.message}</p>
            </div>
            <button
              type="button"
              onClick={() => dismiss(t.id)}
              aria-label="Dismiss"
              className="text-muted hover:text-ink"
            >
              <X className="h-4 w-4" aria-hidden />
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast(): ToastApi {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error('useToast must be used inside <ToastProvider>');
  return ctx;
}
