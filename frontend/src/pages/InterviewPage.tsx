/**
 * Interview page that manages the flow between setup and active call.
 * Supports both Round 1 (general) and Round 2 (DSA coding) interview modes.
 */

import { useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { CallSetup } from '../components/CallSetup';
import { useAuth } from '../hooks/useAuth';
import { lookupInvite } from '../services/authApi';
import type { InviteInfo } from '../types';
import { InterviewRoom } from '../components/InterviewRoom';
import { DSAInterviewPage } from './DSAInterviewPage';
import { useInterviewCall } from '../hooks/useInterviewCall';
import { useSecureMode } from '../hooks/useSecureMode';
import { SecureAppCheck } from '../components/SecureAppCheck';
import { DESKTOP_DOWNLOAD_URL, desktopLink, getDesktop } from '../services/desktopApp';

// Voice Wave Animation Component (for loading screen)
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

function Notice({ title, body, children }: { title: string; body: string; children?: React.ReactNode }) {
  return (
    <div className="loading-screen">
      <div className="loading-content">
        <div>
          <img src="/logo.png" alt="Presence View" style={{ height: 56, margin: '0 auto 16px' }} />
          <h1 className="ended-title">{title}</h1>
          <p className="ended-subtitle">{body}</p>
        </div>
        {children}
      </div>
    </div>
  );
}

function OpenInApp({ inviteToken, onContinueInBrowser }: { inviteToken: string; onContinueInBrowser?: () => void }) {
  return (
    <Notice
      title="Open this interview in the Presence View app"
      body={
        onContinueInBrowser
          ? 'This interview runs in a locked app. If you continue in a browser, your recruiter will see that you did not use it.'
          : 'This interview can only be taken in the Presence View app.'
      }
    >
      <a className="ended-button" href={desktopLink(inviteToken)}>
        Open in the app
      </a>
      {DESKTOP_DOWNLOAD_URL && (
        <a className="ended-button" href={DESKTOP_DOWNLOAD_URL}>
          Download the app
        </a>
      )}
      {onContinueInBrowser && (
        <button className="ended-button" onClick={onContinueInBrowser}>
          Continue in browser
        </button>
      )}
    </Notice>
  );
}

export function InterviewPage() {
  const { state, callData, error, interviewMode, dsaProblemId, startCall, endCurrentCall } = useInterviewCall();
  const { user, loading: authLoading } = useAuth();
  const [params] = useSearchParams();
  const inviteToken = params.get('invite');
  const [invite, setInvite] = useState<InviteInfo | null>(null);
  const [inviteError, setInviteError] = useState<string | null>(null);
  const [inviteLoading, setInviteLoading] = useState(!!inviteToken);
  const [secureCheckPassed, setSecureCheckPassed] = useState(false);
  const [browserChosen, setBrowserChosen] = useState(false);
  const desktop = getDesktop();

  useSecureMode({
    state,
    sessionId: callData?.session_id ?? null,
    inviteToken,
    inviteDead: !inviteLoading && (!!inviteError || invite?.status === 'expired'),
    browserMode: !!inviteToken && !desktop && browserChosen,
  });

  useEffect(() => {
    if (!inviteToken) return;
    lookupInvite(inviteToken)
      .then(setInvite)
      .catch((err) => setInviteError(err instanceof Error ? err.message : 'This interview link is not valid'))
      .finally(() => setInviteLoading(false));
  }, [inviteToken]);

  // Show loading state while connecting
  if (state === 'connecting') {
    return (
      <div className="loading-screen">
        <div className="loading-content">
          <VoiceWaveAnimation />
          <p className="loading-text">
            Connecting to interview<span className="loading-dots"></span>
          </p>
        </div>
      </div>
    );
  }

  // DSA Round 2 — show the coding interview room
  if (state === 'connected' && callData && interviewMode === 'round2_dsa') {
    return (
      <DSAInterviewPage
        sessionId={callData.session_id}
        callId={callData.call_id}
        livekitUrl={callData.livekit_url}
        livekitToken={callData.livekit_token}
        problemId={dsaProblemId ?? ''}
        candidateName="Candidate"
        onEnd={endCurrentCall}
      />
    );
  }

  // Round 1 — original interview room (unchanged)
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

  // Show setup form when idle or error state
  if (state === 'idle' || state === 'error') {
    if (inviteToken) {
      if (inviteLoading) return <div className="loading-screen" />;
      if (inviteError || !invite) {
        return <Notice title="Link not valid" body={inviteError ?? 'This interview link is not valid.'} />;
      }
      if (invite.status === 'revoked') {
        return (
          <Notice
            title="Link withdrawn"
            body="This interview link was withdrawn. Ask your recruiter whether there’s a new one."
          />
        );
      }
      if (invite.status === 'expired') {
        return (
          <Notice title="Link expired" body="This interview link has expired. Ask your recruiter for a new one." />
        );
      }
      if (!desktop && invite.require_secure_app) {
        return <OpenInApp inviteToken={inviteToken} />;
      }
      if (invite.status === 'used') {
        // Only the browser that started the interview can rejoin it
        return (
          <Notice
            title="Interview already started"
            body={error ?? 'If you were disconnected, you can rejoin from the same browser.'}
          >
            <button
              className="ended-button"
              onClick={() =>
                startCall({
                  inviteToken,
                  candidateName: invite.candidate_name,
                  interviewMode: invite.interview_mode,
                  dsaProblemId: invite.dsa_problem_id || undefined,
                })
              }
            >
              Rejoin interview
            </button>
          </Notice>
        );
      }
      if (desktop && !secureCheckPassed) {
        return <SecureAppCheck desktop={desktop} onReady={() => setSecureCheckPassed(true)} />;
      }
      if (!desktop && !browserChosen) {
        return <OpenInApp inviteToken={inviteToken} onContinueInBrowser={() => setBrowserChosen(true)} />;
      }
      return (
        <CallSetup invite={{ token: inviteToken, info: invite }} onStart={startCall} isLoading={false} error={error} />
      );
    }

    if (authLoading) return <div className="loading-screen" />;
    if (!user) {
      return (
        <Notice title="Interview link needed" body="Open the interview link your recruiter sent you to begin.">
          <Link to="/login?next=%2Finterview" className="ended-button">
            Recruiter sign in
          </Link>
        </Notice>
      );
    }

    // Signed-in recruiter trying an interview without an invite
    return <CallSetup onStart={startCall} isLoading={false} error={error} />;
  }

  // Show ended state
  return (
    <div className="loading-screen">
      <div className="loading-content">
        <div>
          <h1 className="ended-title">Interview Complete</h1>
          <p className="ended-subtitle">Thank you for your time!</p>
        </div>
        {!inviteToken && (
          <button onClick={() => window.location.reload()} className="ended-button">
            Start New Interview
          </button>
        )}
      </div>
    </div>
  );
}
