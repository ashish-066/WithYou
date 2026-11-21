/**
 * Study session page: a start screen, then the live room.
 * (Phase 4 turns this into the mobile-first learner screen.)
 */

import { useState } from 'react';
import { InterviewRoom } from '../components/InterviewRoom';
import type { BuddyLanguage } from '../types';
import { useAuth } from '../hooks/useAuth';
import { useInterviewCall } from '../hooks/useInterviewCall';

function VoiceWaveAnimation() {
  return (
    <div className="voice-wave-container">
      <div className="voice-wave">
        <span className="bar bar-1"></span>
        <span className="bar bar-2"></span>
        <span className="bar bar-3"></span>
        <span className="bar bar-4"></span>
        <span className="bar bar-5"></span>
      </div>
    </div>
  );
}

const LANGUAGES: { code: BuddyLanguage; label: string }[] = [
  { code: 'ml-IN', label: 'മലയാളം' },
  { code: 'te-IN', label: 'తెలుగు' },
  { code: 'en-IN', label: 'English' },
];
const LANGUAGE_KEY = 'buddy-language';

function savedLanguage(): BuddyLanguage {
  try {
    const v = localStorage.getItem(LANGUAGE_KEY);
    if (LANGUAGES.some((l) => l.code === v)) return v as BuddyLanguage;
  } catch {
    /* private mode etc. */
  }
  return 'ml-IN';
}

export function InterviewPage() {
  const [language, setLanguage] = useState<BuddyLanguage>(savedLanguage);
  const choose = (code: BuddyLanguage) => {
    setLanguage(code);
    try {
      localStorage.setItem(LANGUAGE_KEY, code);
    } catch {
      /* ignore */
    }
  };
  const { state, callData, error, startCall, endCurrentCall } = useInterviewCall();
  const { user } = useAuth();
  const name = user?.name || 'Learner';

  if (state === 'connecting') {
    return (
      <div className="loading-screen">
        <div className="loading-content">
          <VoiceWaveAnimation />
          <p className="loading-text">
            Connecting<span className="loading-dots"></span>
          </p>
        </div>
      </div>
    );
  }

  if (state === 'connected' && callData) {
    return (
      <InterviewRoom
        serverUrl={callData.livekit_url}
        token={callData.livekit_token}
        sessionId={callData.session_id}
        onDisconnect={endCurrentCall}
        onEnd={endCurrentCall}
      />
    );
  }

  const ended = state === 'ended';
  return (
    <div className="loading-screen">
      <div className="loading-content">
        <div>
          <h1 className="ended-title">{ended ? 'Session finished' : `Hi ${name}!`}</h1>
          <p className="ended-subtitle">
            {ended ? 'Nice work today.' : 'Ready to study together? Tap start and say hello.'}
          </p>
          {error && <p className="ended-subtitle">{error}</p>}
        </div>
        {/* Starting language; switching mid-session works by just speaking another one */}
        <div role="radiogroup" aria-label="Language" style={{ display: 'flex', gap: 8, justifyContent: 'center', flexWrap: 'wrap' }}>
          {LANGUAGES.map((l) => (
            <button
              key={l.code}
              role="radio"
              aria-checked={language === l.code}
              onClick={() => choose(l.code)}
              className="ended-button"
              style={{ opacity: language === l.code ? 1 : 0.45, minWidth: 96 }}
            >
              {l.label}
            </button>
          ))}
        </div>
        {/* A tap starts audio too (browsers only play sound after a user gesture) */}
        <button onClick={() => startCall(name, language)} className="ended-button">
          {ended ? 'Start another session' : 'Start'}
        </button>
      </div>
    </div>
  );
}
