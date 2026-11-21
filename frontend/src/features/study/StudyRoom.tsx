/**
 * The learner's one screen during a session, mobile first:
 *   top     topic + "what we've covered" (the key ideas from the brain's map)
 *   middle  the buddy: avatar video when there is one, otherwise a state orb
 *           (listening / thinking / speaking), and the live transcript
 *   bottom  language switch, a big mic button, end
 * Audio only from the learner (no camera). The Start tap that opened this room
 * is the user gesture browsers need to play sound; StartAudio covers the rest.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import {
  LiveKitRoom,
  RoomAudioRenderer,
  StartAudio,
  VideoTrack,
  useLocalParticipant,
  useTracks,
  useTranscriptions,
  useVoiceAssistant,
} from '@livekit/components-react';
import { Track, type AudioCaptureOptions } from 'livekit-client';
import { Check, Mic, MicOff, PhoneOff } from 'lucide-react';

import { getProgress, type Progress } from '@/services/api';
import type { BuddyLanguage } from '@/types';
import { cx } from '@/ui/cx';
import { LANGUAGES, labels, saveLanguage } from './labels';

/** Data topic the voice agent listens on (avatar/agents/entrypoint.py LANGUAGE_TOPIC). */
const LANGUAGE_TOPIC = 'buddy-language';

/**
 * Mic clean-up in the browser (the agent also runs LiveKit's background-voice
 * cancellation): voiceIsolation keeps the nearest speaker where supported.
 */
const MIC_OPTIONS: AudioCaptureOptions = {
  echoCancellation: true,
  noiseSuppression: true,
  autoGainControl: true,
  voiceIsolation: true,
};

interface StudyRoomProps {
  serverUrl: string;
  token: string;
  callId: string;
  language: BuddyLanguage;
  onEnd: () => void;
}

export function StudyRoom({ serverUrl, token, callId, language, onEnd }: StudyRoomProps) {
  return (
    <LiveKitRoom
      serverUrl={serverUrl}
      token={token}
      connect
      audio={MIC_OPTIONS}
      video={false}
      onDisconnected={onEnd}
      data-area="app"
      className="flex h-[100dvh] flex-col bg-canvas text-ink"
    >
      <Session callId={callId} startLanguage={language} onEnd={onEnd} />
      <RoomAudioRenderer />
    </LiveKitRoom>
  );
}

function Session({ callId, startLanguage, onEnd }: { callId: string; startLanguage: BuddyLanguage; onEnd: () => void }) {
  const [language, setLanguage] = useState<BuddyLanguage>(startLanguage);
  const t = labels(language);
  const progress = useProgress(callId);
  const [confirmEnd, setConfirmEnd] = useState(false);
  const [ending, setEnding] = useState(false);

  // The brain may switch language (the learner asked by voice): follow it on screen
  useEffect(() => {
    const spoken = progress?.language as BuddyLanguage | undefined;
    if (spoken && LANGUAGES.some((l) => l.code === spoken)) setLanguage(spoken);
  }, [progress?.language]);

  return (
    <>
      <header className="flex items-start justify-between gap-3 px-4 pb-2 pt-[max(12px,env(safe-area-inset-top))]">
        <div className="min-w-0">
          <p className="text-meta text-muted">{t.topic}</p>
          <p className="truncate font-display text-h3">{progress?.topic || t.noTopic}</p>
        </div>
        <button
          onClick={() => setConfirmEnd(true)}
          className="inline-flex h-10 shrink-0 items-center gap-1.5 rounded-full border border-line-strong px-4 text-body text-ink"
        >
          <PhoneOff size={16} aria-hidden />
          {t.end}
        </button>
      </header>

      <Covered progress={progress} language={language} />

      <main className="flex min-h-0 flex-1 flex-col items-center px-4">
        <Buddy language={language} />
        <Transcript language={language} />
      </main>

      <Controls language={language} onLanguage={setLanguage} />

      <StartAudio
        label={t.tapForSound}
        className="fixed inset-x-4 bottom-28 z-20 rounded-full bg-accent px-5 py-3 text-lead text-accent-on"
      />
      {confirmEnd && (
        <EndDialog
          language={language}
          ending={ending}
          onCancel={() => setConfirmEnd(false)}
          onConfirm={() => {
            setEnding(true);
            onEnd();
          }}
        />
      )}
    </>
  );
}

/** Topic and key ideas, polled from the API (the brain updates them after each reply). */
function useProgress(callId: string): Progress | null {
  const [progress, setProgress] = useState<Progress | null>(null);
  useEffect(() => {
    let live = true;
    const load = () =>
      getProgress(callId)
        .then((p) => live && setProgress(p))
        .catch(() => undefined);
    load();
    const id = window.setInterval(load, 4000);
    return () => {
      live = false;
      window.clearInterval(id);
    };
  }, [callId]);
  return progress;
}

/** "What we've covered": one chip per key idea; understood ones are filled. */
function Covered({ progress, language }: { progress: Progress | null; language: BuddyLanguage }) {
  const ideas = progress?.ideas ?? [];
  if (!ideas.length) return null;
  const t = labels(language);
  return (
    <section aria-label={t.covered(progress!.covered, ideas.length)} className="px-4 pb-2">
      <p className="text-meta text-muted">{t.covered(progress!.covered, ideas.length)}</p>
      <ul className="mt-1.5 flex gap-1.5 overflow-x-auto pb-1">
        {ideas.map((idea, i) => (
          <li
            key={i}
            title={idea.text}
            className={cx(
              'flex max-w-[70vw] shrink-0 items-center gap-1 rounded-full border px-3 py-1 text-meta',
              idea.status === 'understood' && 'border-accent bg-accent text-accent-on',
              (idea.status === 'partial' || idea.status === 'gap') && 'border-warn text-ink',
              idea.status === 'unseen' && 'border-line text-muted',
            )}
          >
            {idea.status === 'understood' && <Check size={14} aria-hidden />}
            <span className="truncate">{idea.text}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}

/** The buddy: avatar video if the avatar is on, otherwise an orb that shows its state. */
function Buddy({ language }: { language: BuddyLanguage }) {
  const t = labels(language);
  const { state } = useVoiceAssistant();
  const { localParticipant } = useLocalParticipant();
  const videos = useTracks([Track.Source.Camera, Track.Source.Unknown], { onlySubscribed: true });
  const avatar = videos.find((v) => v.participant.identity !== localParticipant?.identity);

  const label =
    state === 'speaking'
      ? t.speaking
      : state === 'thinking'
        ? t.thinking
        : state === 'listening'
          ? t.listening
          : t.waiting;

  return (
    <div className="flex shrink-0 flex-col items-center py-3">
      {avatar ? (
        <VideoTrack trackRef={avatar} className="h-48 w-48 rounded-full object-cover" />
      ) : (
        <div
          aria-hidden
          className={cx(
            'h-36 w-36 rounded-full border-4 transition-all duration-300 sm:h-44 sm:w-44',
            state === 'speaking' && 'scale-105 animate-pulse border-accent bg-accent',
            state === 'thinking' && 'animate-pulse border-accent bg-accent/30',
            state === 'listening' && 'border-accent bg-accent/10',
            !['speaking', 'thinking', 'listening'].includes(state) && 'border-line bg-sunken',
          )}
        />
      )}
      <p role="status" className="mt-3 text-lead text-muted">
        {label}
      </p>
    </div>
  );
}

/** Live transcript: the learner on the right, the buddy on the left (last few lines). */
function Transcript({ language }: { language: BuddyLanguage }) {
  const t = labels(language);
  const lines = useTranscriptions();
  const { localParticipant } = useLocalParticipant();
  const end = useRef<HTMLDivElement | null>(null);
  const recent = lines.filter((l) => l.text.trim()).slice(-8);

  useEffect(() => {
    end.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [recent.length, recent[recent.length - 1]?.text]);

  return (
    <div className="w-full max-w-xl min-h-0 flex-1 overflow-y-auto pb-2" aria-live="polite">
      <ul className="flex flex-col gap-2">
        {recent.map((line) => {
          const mine = line.participantInfo.identity === localParticipant?.identity;
          return (
            <li key={line.streamInfo.id} className={cx('flex', mine ? 'justify-end' : 'justify-start')}>
              <div
                className={cx(
                  'max-w-[85%] rounded-ui px-3 py-2 text-lead',
                  mine ? 'bg-accent text-accent-on' : 'border border-line bg-surface text-ink',
                )}
              >
                <span className="sr-only">{mine ? t.you : t.buddy}: </span>
                {line.text}
              </div>
            </li>
          );
        })}
      </ul>
      <div ref={end} />
    </div>
  );
}

/** Language switch and the big mic button. */
function Controls({ language, onLanguage }: { language: BuddyLanguage; onLanguage: (l: BuddyLanguage) => void }) {
  const t = labels(language);
  const { localParticipant, isMicrophoneEnabled } = useLocalParticipant();

  const toggleMic = useCallback(async () => {
    await localParticipant?.setMicrophoneEnabled(!isMicrophoneEnabled);
  }, [localParticipant, isMicrophoneEnabled]);

  const switchTo = useCallback(
    async (code: BuddyLanguage) => {
      if (!localParticipant || code === language) return;
      // The agent switches listening + voice and confirms in the new language
      await localParticipant.publishData(new TextEncoder().encode(code), { reliable: true, topic: LANGUAGE_TOPIC });
      saveLanguage(code);
      onLanguage(code);
    },
    [localParticipant, language, onLanguage],
  );

  return (
    <footer className="flex items-center justify-between gap-3 border-t border-line bg-surface px-4 pb-[max(16px,env(safe-area-inset-bottom))] pt-3">
      <div role="radiogroup" aria-label="Language" className="flex gap-1">
        {LANGUAGES.map((l) => (
          <button
            key={l.code}
            role="radio"
            aria-checked={language === l.code}
            onClick={() => switchTo(l.code)}
            className={cx(
              'h-10 min-w-11 rounded-full px-3 text-body',
              language === l.code ? 'bg-ink text-canvas' : 'border border-line text-muted',
            )}
          >
            {l.short}
          </button>
        ))}
      </div>
      <button
        onClick={toggleMic}
        aria-pressed={!isMicrophoneEnabled}
        aria-label={isMicrophoneEnabled ? t.mute : t.unmute}
        className={cx(
          'flex h-16 w-16 shrink-0 items-center justify-center rounded-full',
          isMicrophoneEnabled ? 'bg-accent text-accent-on' : 'border-2 border-bad text-bad',
        )}
      >
        {isMicrophoneEnabled ? <Mic size={28} aria-hidden /> : <MicOff size={28} aria-hidden />}
      </button>
      {!isMicrophoneEnabled && <span className="sr-only">{t.muted}</span>}
    </footer>
  );
}

function EndDialog({
  language,
  ending,
  onCancel,
  onConfirm,
}: {
  language: BuddyLanguage;
  ending: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  const t = labels(language);
  const stay = useRef<HTMLButtonElement | null>(null);
  useEffect(() => {
    stay.current?.focus();
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onCancel();
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onCancel]);

  return (
    <div className="fixed inset-0 z-30 flex items-end justify-center bg-ink/40 p-4 sm:items-center">
      <div
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="end-title"
        className="w-full max-w-sm rounded-ui bg-surface p-5 text-ink"
      >
        <h2 id="end-title" className="font-display text-h3">
          {t.endTitle}
        </h2>
        <p className="mt-1 text-lead text-muted">{t.endBody}</p>
        <div className="mt-5 flex flex-col gap-2">
          <button ref={stay} onClick={onCancel} disabled={ending} className="h-12 rounded-full bg-accent text-lead text-accent-on">
            {t.keepGoing}
          </button>
          <button onClick={onConfirm} disabled={ending} className="h-12 rounded-full border border-line-strong text-lead">
            {ending ? t.ending : t.end}
          </button>
        </div>
      </div>
    </div>
  );
}
