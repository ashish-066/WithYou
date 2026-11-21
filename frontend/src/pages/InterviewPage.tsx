/**
 * Study session page: a start screen, then the live room.
 * (Phase 4 turns this into the mobile-first learner screen.)
 */

import { InterviewRoom } from '../components/InterviewRoom';
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

export function InterviewPage() {
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
        {/* A tap starts audio too (browsers only play sound after a user gesture) */}
        <button onClick={() => startCall(name)} className="ended-button">
          {ended ? 'Start another session' : 'Start'}
        </button>
      </div>
    </div>
  );
}
