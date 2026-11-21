/**
 * /study: pick a language, tap Start (the tap also unlocks audio), study, finish.
 */
import { useState } from 'react';
import { BookOpen } from 'lucide-react';

import { useAuth } from '@/hooks/useAuth';
import { useInterviewCall } from '@/hooks/useInterviewCall';
import type { BuddyLanguage } from '@/types';
import { cx } from '@/ui/cx';
import { LANGUAGES, labels, saveLanguage, savedLanguage } from './labels';
import { RecapCard } from './RecapCard';
import { StudyRoom } from './StudyRoom';

export function StudyPage() {
  const { state, callData, error, endedSessionId, startCall, endCurrentCall } = useInterviewCall();
  const { user } = useAuth();
  const [language, setLanguage] = useState<BuddyLanguage>(savedLanguage);
  const t = labels(language);
  const name = user?.name || '';

  if (state === 'connected' && callData) {
    return (
      <StudyRoom
        serverUrl={callData.livekit_url}
        token={callData.livekit_token}
        callId={callData.call_id}
        language={language}
        onEnd={endCurrentCall}
      />
    );
  }

  const ended = state === 'ended';
  const connecting = state === 'connecting';
  return (
    <div data-area="app" className="flex min-h-[100dvh] flex-col bg-canvas px-5 text-ink">
      <main className="mx-auto flex w-full max-w-sm flex-1 flex-col justify-center gap-8 py-10">
        <div>
          <div className="flex h-14 w-14 items-center justify-center rounded-full bg-accent text-accent-on">
            <BookOpen size={28} aria-hidden />
          </div>
          <h1 className="mt-5 font-display text-h1">{ended ? t.finished : name ? t.hi(name) : t.appName}</h1>
          <p className="mt-2 text-lead text-muted">{ended ? t.finishedBody : t.tagline}</p>
        </div>

        {ended && endedSessionId && <RecapCard sessionId={endedSessionId} language={language} />}

        <fieldset>
          <legend className="text-meta text-muted">{t.pickLanguage}</legend>
          <div role="radiogroup" className="mt-2 flex flex-col gap-2">
            {LANGUAGES.map((l) => (
              <button
                key={l.code}
                role="radio"
                aria-checked={language === l.code}
                onClick={() => {
                  setLanguage(l.code);
                  saveLanguage(l.code);
                }}
                className={cx(
                  'h-14 rounded-ui border px-4 text-left text-lead',
                  language === l.code ? 'border-accent bg-accent/10 text-ink' : 'border-line bg-surface text-muted',
                )}
              >
                {l.label}
              </button>
            ))}
          </div>
        </fieldset>

        <div>
          {error && (
            <p role="alert" className="mb-3 text-body text-bad">
              {error}
            </p>
          )}
          {/* This tap is the user gesture that lets the browser play the buddy's voice */}
          <button
            onClick={() => startCall(name || 'Learner', language)}
            disabled={connecting}
            className="h-14 w-full rounded-full bg-accent text-lead text-accent-on disabled:opacity-60"
          >
            {connecting ? t.connecting : ended ? t.startAgain : t.start}
          </button>
        </div>
      </main>
    </div>
  );
}
