/**
 * /session?mode=study|talk&topic=…: a live session, full screen.
 * Starts right away (the tap on Home / Learn that got here is the user gesture
 * browsers need for audio), then the room, then the recap.
 */
import { useEffect, useRef } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { ArrowRight, BookOpen, Home, MessageCircleHeart, RotateCcw } from 'lucide-react';

import { useAuth } from '@/hooks/useAuth';
import { useInterviewCall } from '@/hooks/useInterviewCall';
import { usePrefs } from '@/features/app/prefs';
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

  const Icon = mode === 'talk' ? MessageCircleHeart : BookOpen;

  if (state === 'ended') {
    return (
      <div data-area="app" className="min-h-[100dvh] bg-canvas px-5 text-ink">
        <main className="mx-auto flex w-full max-w-md flex-col gap-6 py-[max(40px,env(safe-area-inset-top))]">
          <div className="flex h-14 w-14 items-center justify-center rounded-full bg-accent text-accent-on">
            <Icon size={28} aria-hidden />
          </div>
          <div>
            <h1 className="font-display text-h1">{t.finished}</h1>
            <p className="mt-2 text-lead text-muted">{t.finishedBody}</p>
          </div>
          {endedSessionId && <RecapCard sessionId={endedSessionId} language={language} />}
          <div className="flex flex-col gap-2">
            <button
              onClick={() => navigate('/')}
              className="inline-flex h-12 items-center justify-center gap-2 rounded-full bg-accent text-lead text-accent-on"
            >
              <Home size={18} aria-hidden />
              {t.home}
            </button>
            <button
              onClick={start}
              className="inline-flex h-12 items-center justify-center gap-2 rounded-full border border-line-strong text-lead"
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
    <div data-area="app" className="flex min-h-[100dvh] flex-col items-center justify-center bg-canvas px-6 text-center text-ink">
      <div className="relative flex h-28 w-28 items-center justify-center">
        <span className="absolute inset-0 animate-ping rounded-full bg-accent/20" aria-hidden />
        <span className="relative flex h-24 w-24 items-center justify-center rounded-full bg-accent text-accent-on">
          <Icon size={40} aria-hidden />
        </span>
      </div>
      {topic && <p className="mt-8 font-display text-h3">{topic}</p>}
      {state === 'error' ? (
        <>
          <p role="alert" className="mt-4 max-w-sm text-body text-bad">
            {error}
          </p>
          <div className="mt-6 flex gap-2">
            <button onClick={() => navigate('/')} className="h-11 rounded-full border border-line-strong px-5 text-body">
              {t.home}
            </button>
            <button
              onClick={start}
              className="inline-flex h-11 items-center gap-2 rounded-full bg-accent px-5 text-body text-accent-on"
            >
              {t.startAgain}
              <ArrowRight size={16} aria-hidden />
            </button>
          </div>
        </>
      ) : (
        <p role="status" className="mt-4 text-lead text-muted">
          {t.waiting}
        </p>
      )}
    </div>
  );
}
