/**
 * /session?mode=study|talk&topic=…: a live session, full screen.
 * Starts right away (the tap on Home / Learn that got here is the user gesture
 * browsers need for audio), then the room, then the recap.
 */
import { useEffect, useRef } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { ArrowRight, Home, RotateCcw } from 'lucide-react';

import { useAuth } from '@/hooks/useAuth';
import { useInterviewCall } from '@/hooks/useInterviewCall';
import { usePrefs } from '@/features/app/prefs';
import { Buddy as BuddyFace } from '@/features/app/Buddy';
import { Scribble, SpeechBubble } from '@/features/app/notebook';
import type { SessionMode } from '@/types';
import { labels } from './labels';
import { RecapCard } from './RecapCard';
import { StudyRoom } from './StudyRoom';

export function StudyPage() {
  const [params] = useSearchParams();
  const mode: SessionMode = params.get('mode') === 'talk' ? 'talk' : 'study';
  const topic = params.get('topic')?.trim() || undefined;
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { state, callData, error, endedSessionId, startCall, endCurrentCall } = useInterviewCall();
  const { user } = useAuth();
  const { language, voice } = usePrefs();
  const t = labels(language);
  const started = useRef(false);

  const start = () => startCall(user?.name || 'Learner', language, mode, topic, voice);

  useEffect(() => {
    if (started.current) return;
    started.current = true;
    start();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // A finished session shows up in history and progress
  useEffect(() => {
    if (state === 'ended') queryClient.invalidateQueries({ queryKey: ['me'] });
  }, [state, queryClient]);

  if (state === 'connected' && callData) {
    return (
      <StudyRoom
        serverUrl={callData.livekit_url}
        token={callData.livekit_token}
        callId={callData.call_id}
        language={language}
        mode={mode}
        onEnd={endCurrentCall}
      />
    );
  }

  if (state === 'ended') {
    return (
      <div data-area="notebook" className="paper min-h-[100dvh] px-5 text-ink">
        <main className="mx-auto flex w-full max-w-md flex-col gap-6 py-[max(32px,env(safe-area-inset-top))]">
          <div className="flex items-end gap-2">
            <BuddyFace mood={mode === 'talk' ? 'caring' : 'happy'} size={104} className="shrink-0" />
            <SpeechBubble className="mb-10 min-w-0 flex-1">
              <p className="font-display text-h3 font-bold leading-tight">{t.finished}</p>
              <p className="text-body text-muted">{t.finishedBody}</p>
            </SpeechBubble>
          </div>
          {endedSessionId && <RecapCard sessionId={endedSessionId} language={language} />}
          <div className="flex flex-col gap-2">
            <button
              onClick={() => navigate('/')}
              className="sketch inline-flex h-12 items-center justify-center gap-2 bg-accent text-lead font-semibold text-accent-on"
            >
              <Home size={18} aria-hidden />
              {t.home}
            </button>
            <button
              onClick={start}
              className="sketch-soft inline-flex h-12 items-center justify-center gap-2 bg-surface text-lead"
            >
              <RotateCcw size={18} aria-hidden />
              {t.startAgain}
            </button>
          </div>
        </main>
      </div>
    );
  }

  // Connecting (or the start failed)
  return (
    <div data-area="notebook" className="paper flex min-h-[100dvh] flex-col items-center justify-center px-6 text-center text-ink">
      <BuddyFace mood={state === 'error' ? 'thinking' : 'wave'} size={150} />
      {topic && (
        <p className="mt-6 font-display text-h3 font-bold">
          <Scribble>{topic}</Scribble>
        </p>
      )}
      {state === 'error' ? (
        <>
          <p role="alert" className="mt-4 max-w-sm text-body text-bad">
            {error}
          </p>
          <div className="mt-6 flex gap-2">
            <button onClick={() => navigate('/')} className="sketch-soft h-11 bg-surface px-5 text-body">
              {t.home}
            </button>
            <button
              onClick={start}
              className="sketch inline-flex h-11 items-center gap-2 bg-accent px-5 text-body font-semibold text-accent-on"
            >
              {t.startAgain}
              <ArrowRight size={16} aria-hidden />
            </button>
          </div>
        </>
      ) : (
        <p role="status" className="mt-4 font-hand text-lead text-terracotta">
          {t.waiting}
        </p>
      )}
    </div>
  );
}
