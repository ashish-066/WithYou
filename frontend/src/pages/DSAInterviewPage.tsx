/**
 * DSAInterviewPage — Round 2 DSA coding interview experience.
 *
 * Layout (3-panel split):
 * ┌──────────────────────────────────────────────────────┐
 * │  [Problem Statement]  │  [Code Editor]  │  [Video]   │
 * │  Left Panel (30%)     │  Center (45%)   │  Right(25%)│
 * │                       │                 │            │
 * │                       │  [Test Results] │  [Transcript]│
 * │                       │  Bottom (40%)   │            │
 * └──────────────────────────────────────────────────────┘
 *
 * - Problem panel: DSAProblemPublic (no reference solution)
 * - Code editor: Monaco with Python syntax, "Run Code" button
 * - Test results: Execution results from sandbox (authoritative)
 * - Video: LiveKit avatar (Presence speaking & listening)
 * - Transcript: Real-time discussion & execution feedback
 */

import { useEffect, useRef, useState, useCallback } from 'react';
import { CameraWarning } from '../components/CameraWarning';
import { ConfirmEndDialog } from '../components/ConfirmEndDialog';
import Editor, { loader } from '@monaco-editor/react';
import {
  LiveKitRoom,
  RoomAudioRenderer,
  useLocalParticipant,
  VideoTrack,
  useTracks,
} from '@livekit/components-react';
import { Track } from 'livekit-client';

import { ProblemStatement } from '../components/ProblemStatement';
import { TestResultsPanel } from '../components/TestResultsPanel';
import { getDSAProblemPublic } from '../services/dsaApi';
import { endCall } from '../services/api';
import type { DSAExecutionResult, DSAProblemPublic } from '../types';

const API_BASE = '/api';

// The editor loads from the CDN (allowed by the CSP). Pin a version instead of
// the loader's default (0.55.1, which bundles an older, vulnerable DOMPurify).
loader.config({
  paths: { vs: 'https://cdn.jsdelivr.net/npm/monaco-editor@0.57.0/min/vs' },
});

interface DSAInterviewPageProps {
  sessionId: string;
  callId: string;
  livekitUrl: string;
  livekitToken: string;
  problemId: string;
  candidateName: string;
  onEnd: () => void;
}

const PYTHON_STARTER = `def solution(*args):
    """
    Write your solution here.
    
    The function receives the problem inputs as positional arguments.
    Return the answer.
    """
    pass
`;

const DARK_THEME_STYLES: React.CSSProperties = {
  background: '#0a0b0e',
  color: '#e2e8f0',
  fontFamily: "'Inter', -apple-system, sans-serif",
  height: '100vh',
  overflow: 'hidden',
  display: 'flex',
  flexDirection: 'column',
};

// =============================================================================
// Sub-components
// =============================================================================

function VoiceWaveAnimation() {
  return (
    <div className="voice-wave-container" style={{ transform: 'scale(0.85)' }}>
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

function PanelHeader({ title, right }: { title: string; right?: React.ReactNode }) {
  return (
    <div
      style={{
        height: '38px',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '0 14px',
        borderBottom: '1px solid rgba(255,255,255,0.07)',
        background: '#0d0f14',
        flexShrink: 0,
      }}
    >
      <span style={{ fontSize: '11px', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.08em', color: '#64748b' }}>
        {title}
      </span>
      {right}
    </div>
  );
}

function StatusDot({ active }: { active: boolean }) {
  return (
    <span
      style={{
        display: 'inline-block',
        width: '7px',
        height: '7px',
        borderRadius: '50%',
        background: active ? '#00d4a0' : '#475569',
        boxShadow: active ? '0 0 6px #00d4a0' : 'none',
        marginRight: '6px',
      }}
    />
  );
}

// =============================================================================
// Room Content Component (inside LiveKit context)
// =============================================================================

interface DSARoomContentProps {
  sessionId: string;
  callId: string;
  problemId: string;
  candidateName: string;
  onEnd: () => void;
}

function DSARoomContent({
  sessionId,
  callId,
  problemId,
  candidateName,
  onEnd,
}: DSARoomContentProps) {
  const { localParticipant } = useLocalParticipant();
  const [problem, setProblem] = useState<DSAProblemPublic | null>(null);
  const [code, setCode] = useState(PYTHON_STARTER);
  const [isRunning, setIsRunning] = useState(false);
  const [execResult, setExecResult] = useState<DSAExecutionResult | null>(null);
  const [isEnding, setIsEnding] = useState(false);
  const [activeBottomTab, setActiveBottomTab] = useState<'tests' | 'transcript'>('tests');
  const [transcript] = useState<{ role: string; content: string }[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [isMicOn, setIsMicOn] = useState(true);
  const transcriptEndRef = useRef<HTMLDivElement>(null);

  // Track video streams
  const allVideoTracks = useTracks(
    [Track.Source.Camera, Track.Source.ScreenShare, Track.Source.Unknown],
    { onlySubscribed: false }
  );

  const avatarVideoTrack = allVideoTracks.find(
    (track) =>
      track.participant.identity !== localParticipant?.identity &&
      (track.publication?.track !== undefined ||
       track.participant.identity.includes('bey') ||
       track.participant.identity.includes('avatar') ||
       track.participant.identity.includes('agent'))
  );

  const localVideoTrack = allVideoTracks.find(
    (track) => track.participant.identity === localParticipant?.identity
  );

  const isAvatarSpeaking = avatarVideoTrack?.participant.isSpeaking ?? false;

  // Load problem on mount
  useEffect(() => {
    getDSAProblemPublic(problemId)
      .then(setProblem)
      .catch((e) => setLoadError(e.message));
  }, [problemId]);

  // Auto-scroll transcript
  useEffect(() => {
    transcriptEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [transcript]);

  // Poll for execution results via session state endpoint
  useEffect(() => {
    if (!isRunning) return;
    const interval = setInterval(async () => {
      try {
        // Candidate-safe endpoint: only the test-run result, not session state
        const res = await fetch(`${API_BASE}/calls/dsa/result/${sessionId}`);
        if (!res.ok) return;
        const data = await res.json();
        if (data?.last_execution_result) {
          setExecResult(data.last_execution_result as DSAExecutionResult);
          setIsRunning(false);
          clearInterval(interval);
        }
      } catch {
        // ignore polling errors
      }
    }, 1500);
    return () => clearInterval(interval);
  }, [isRunning, sessionId]);

  // Let Presence see the editor as the candidate types (debounced, silent)
  useEffect(() => {
    if (!code.trim()) return;
    const t = setTimeout(() => {
      fetch(`${API_BASE}/calls/dsa/code_snapshot`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionId, code }),
      }).catch(() => {});
    }, 2000);
    return () => clearTimeout(t);
  }, [code, sessionId]);

  const handleRunCode = useCallback(async () => {
    if (!code.trim() || isRunning) return;
    setIsRunning(true);
    setActiveBottomTab('tests');

    try {
      const res = await fetch(`${API_BASE}/calls/dsa/execute`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionId, code, language: 'python' }),
      });
      if (!res.ok) {
        console.warn('Failed to submit code execution request');
        setIsRunning(false);
      }
    } catch (e) {
      console.error(e);
      setIsRunning(false);
    }
  }, [code, isRunning, sessionId]);

  const [confirmEnd, setConfirmEnd] = useState(false);

  const handleEndInterview = async () => {
    if (isEnding) return;
    setIsEnding(true);
    try {
      await endCall(callId);
    } finally {
      onEnd();
    }
  };

  const toggleMic = useCallback(async () => {
    if (localParticipant) {
      const newEnabled = !isMicOn;
      await localParticipant.setMicrophoneEnabled(newEnabled);
      setIsMicOn(newEnabled);
    }
  }, [localParticipant, isMicOn]);

  return (
    <div id="dsa-interview-page" style={DARK_THEME_STYLES}>
      {/* Top bar */}
      <div
        style={{
          height: '48px',
          background: '#080a0d',
          borderBottom: '1px solid rgba(255,255,255,0.07)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '0 20px',
          flexShrink: 0,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <span style={{ fontWeight: 700, fontSize: '14px', color: '#f8fafc', letterSpacing: '-0.01em' }}>
            Presence View
          </span>
          <span style={{ fontSize: '11px', color: '#64748b', padding: '2px 8px', background: 'rgba(100,116,139,0.1)', borderRadius: '4px' }}>
            Round 2 · DSA
          </span>
          {problem && (
            <span style={{ fontSize: '12px', color: '#94a3b8' }}>
              {problem.title}
            </span>
          )}
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <button
            onClick={toggleMic}
            style={{
              padding: '6px 12px',
              borderRadius: '6px',
              border: `1px solid ${isMicOn ? 'rgba(0,212,160,0.3)' : 'rgba(239,68,68,0.3)'}`,
              background: isMicOn ? 'rgba(0,212,160,0.08)' : 'rgba(239,68,68,0.08)',
              color: isMicOn ? '#00d4a0' : '#f87171',
              fontSize: '12px',
              fontWeight: 500,
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
            }}
          >
            {isMicOn ? '🎙️ Mic On' : '🔇 Mic Muted'}
          </button>
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <StatusDot active={!isEnding} />
            <span style={{ fontSize: '12px', color: '#64748b' }}>{candidateName}</span>
          </div>
          <button
            id="dsa-end-interview-btn"
            onClick={() => setConfirmEnd(true)}
            disabled={isEnding}
            style={{
              padding: '6px 14px',
              borderRadius: '6px',
              border: '1px solid rgba(239,68,68,0.3)',
              background: 'rgba(239,68,68,0.08)',
              color: '#f87171',
              fontSize: '12px',
              fontWeight: 600,
              cursor: isEnding ? 'not-allowed' : 'pointer',
            }}
          >
            {isEnding ? 'Ending…' : 'End Interview'}
          </button>
          <ConfirmEndDialog
            open={confirmEnd}
            ending={isEnding}
            onCancel={() => setConfirmEnd(false)}
            onConfirm={handleEndInterview}
          />
        </div>
      </div>

      {/* 3-panel split layout */}
      <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
        {/* ── LEFT: Problem Statement (30%) ── */}
        <div
          id="dsa-problem-panel"
          style={{
            width: '30%',
            minWidth: '260px',
            borderRight: '1px solid rgba(255,255,255,0.07)',
            display: 'flex',
            flexDirection: 'column',
            overflow: 'hidden',
          }}
        >
          <PanelHeader
            title="Problem"
            right={
              problem ? (
                <span
                  style={{
                    fontSize: '10px',
                    fontWeight: 700,
                    textTransform: 'uppercase',
                    color:
                      problem.difficulty === 'easy'
                        ? '#34d399'
                        : problem.difficulty === 'medium'
                        ? '#fbbf24'
                        : '#f87171',
                  }}
                >
                  {problem.difficulty}
                </span>
              ) : null
            }
          />
          <div style={{ flex: 1, overflowY: 'auto' }}>
            {loadError ? (
              <div style={{ padding: '20px', color: '#f87171', fontSize: '13px' }}>
                Error loading problem: {loadError}
              </div>
            ) : problem ? (
              <ProblemStatement problem={problem} />
            ) : (
              <div style={{ padding: '20px', color: '#64748b', fontSize: '13px' }}>
                Loading problem statement…
              </div>
            )}
          </div>
        </div>

        {/* ── CENTER: Editor (top 60%) + Tests/Transcript (bottom 40%) (45%) ── */}
        <div
          id="dsa-center-panel"
          style={{
            flex: 1,
            borderRight: '1px solid rgba(255,255,255,0.07)',
            display: 'flex',
            flexDirection: 'column',
            overflow: 'hidden',
          }}
        >
          {/* Top: Editor */}
          <div style={{ height: '60%', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
            <PanelHeader
              title="Python 3"
              right={
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <button
                    id="dsa-run-code-btn"
                    onClick={handleRunCode}
                    disabled={isRunning}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '6px',
                      padding: '4px 12px',
                      borderRadius: '5px',
                      border: 'none',
                      background: isRunning ? '#1e293b' : '#00d4a0',
                      color: isRunning ? '#64748b' : '#000000',
                      fontWeight: 700,
                      fontSize: '11px',
                      cursor: isRunning ? 'not-allowed' : 'pointer',
                      letterSpacing: '0.02em',
                      transition: 'all 0.15s',
                    }}
                  >
                    {isRunning ? (
                      <>
                        <span
                          style={{
                            display: 'inline-block',
                            width: '10px',
                            height: '10px',
                            borderRadius: '50%',
                            border: '2px solid #64748b',
                            borderTopColor: '#00d4a0',
                            animation: 'spin 0.8s linear infinite',
                          }}
                        />
                        Running…
                      </>
                    ) : (
                      <>▶ Run Code</>
                    )}
                  </button>
                </div>
              }
            />

            <Editor
              height="100%"
              language="python"
              theme="vs-dark"
              value={code}
              onChange={(v) => setCode(v ?? '')}
              options={{
                fontSize: 13,
                fontFamily: "'JetBrains Mono', 'Fira Code', Menlo, monospace",
                minimap: { enabled: false },
                scrollBeyondLastLine: false,
                lineNumbers: 'on',
                automaticLayout: true,
                padding: { top: 12, bottom: 12 },
                tabSize: 4,
                insertSpaces: true,
                suggestOnTriggerCharacters: true,
              }}
            />
          </div>

          {/* Bottom tabs: Tests / Transcript */}
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', borderTop: '1px solid rgba(255,255,255,0.07)', overflow: 'hidden' }}>
            {/* Tab bar */}
            <div style={{ display: 'flex', height: '36px', borderBottom: '1px solid rgba(255,255,255,0.07)', background: '#0d0f14', flexShrink: 0 }}>
              {(['tests', 'transcript'] as const).map((tab) => (
                <button
                  key={tab}
                  id={`dsa-tab-${tab}`}
                  onClick={() => setActiveBottomTab(tab)}
                  style={{
                    padding: '0 16px',
                    border: 'none',
                    background: 'transparent',
                    color: activeBottomTab === tab ? '#f8fafc' : '#64748b',
                    fontSize: '11px',
                    fontWeight: 600,
                    textTransform: 'capitalize',
                    cursor: 'pointer',
                    borderBottom: activeBottomTab === tab ? '2px solid #00d4a0' : '2px solid transparent',
                    transition: 'all 0.15s',
                  }}
                >
                  {tab === 'tests' ? `Tests${execResult ? ` (${execResult.tests_passed}/${execResult.tests_total})` : ''}` : 'Transcript'}
                </button>
              ))}
            </div>

            {/* Tab content */}
            <div style={{ flex: 1, overflow: 'hidden' }}>
              {activeBottomTab === 'tests' ? (
                <TestResultsPanel result={execResult} isRunning={isRunning} />
              ) : (
                <div
                  id="dsa-transcript-panel"
                  style={{
                    height: '100%',
                    overflowY: 'auto',
                    padding: '12px 16px',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: '8px',
                  }}
                >
                  {transcript.length === 0 ? (
                    <div style={{ color: '#475569', fontSize: '12px', textAlign: 'center', marginTop: '20px' }}>
                      Presence's responses will appear here
                    </div>
                  ) : (
                    transcript.map((m, i) => (
                      <div
                        key={i}
                        style={{
                          background: m.role === 'assistant' ? 'rgba(0,212,160,0.05)' : 'rgba(255,255,255,0.03)',
                          border: `1px solid ${m.role === 'assistant' ? 'rgba(0,212,160,0.1)' : 'rgba(255,255,255,0.05)'}`,
                          borderRadius: '8px',
                          padding: '10px 12px',
                          fontSize: '13px',
                          color: m.role === 'assistant' ? '#a7f3d0' : '#cbd5e1',
                        }}
                      >
                        <div style={{ fontSize: '10px', color: '#475569', marginBottom: '4px', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                          {m.role === 'assistant' ? 'Presence' : 'You'}
                        </div>
                        {m.content}
                      </div>
                    ))
                  )}
                  <div ref={transcriptEndRef} />
                </div>
              )}
            </div>
          </div>
        </div>

        {/* ── RIGHT: Presence Video (25%) ── */}
        <div
          id="dsa-video-panel"
          style={{
            width: '25%',
            minWidth: '240px',
            display: 'flex',
            flexDirection: 'column',
            overflow: 'hidden',
          }}
        >
          <PanelHeader
            title="Presence"
            right={
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '11px', color: isAvatarSpeaking ? '#00d4a0' : '#475569' }}>
                <StatusDot active={isAvatarSpeaking} />
                {isAvatarSpeaking ? 'Speaking' : 'Listening'}
              </div>
            }
          />

          {/* LiveKit video renderer */}
          <div
            style={{
              flex: 1,
              background: '#06080b',
              position: 'relative',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              overflow: 'hidden',
            }}
          >
            {avatarVideoTrack ? (
              <div className={`avatar-video-wrapper ${isAvatarSpeaking ? 'speaking' : ''}`} style={{ width: '100%', height: '100%', borderRadius: 0 }}>
                <VideoTrack
                  trackRef={avatarVideoTrack}
                  className="avatar-video"
                  style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                />
                {isAvatarSpeaking && (
                  <div className="avatar-speaking-indicator" style={{ bottom: '12px' }}>
                    <span className="pulse-dot"></span>
                    <span className="pulse-dot"></span>
                    <span className="pulse-dot"></span>
                  </div>
                )}
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '12px' }}>
                <VoiceWaveAnimation />
                <span style={{ fontSize: '12px', color: '#64748b' }}>Presence is connecting…</span>
              </div>
            )}

            {/* PIP for local camera */}
            {localVideoTrack && (
              <div
                style={{
                  position: 'absolute',
                  bottom: '12px',
                  right: '12px',
                  width: '80px',
                  height: '60px',
                  borderRadius: '6px',
                  overflow: 'hidden',
                  border: '1px solid rgba(255,255,255,0.2)',
                  background: '#000',
                  boxShadow: '0 4px 12px rgba(0,0,0,0.5)',
                }}
              >
                <VideoTrack
                  trackRef={localVideoTrack}
                  style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                />
              </div>
            )}
          </div>

          {/* Hint indicator */}
          <div
            style={{
              padding: '10px 14px',
              borderTop: '1px solid rgba(255,255,255,0.07)',
              fontSize: '11px',
              color: '#64748b',
              background: '#0a0b0e',
            }}
          >
            💡 Discuss your approach with Presence verbally as you code
          </div>
        </div>
      </div>
    </div>
  );
}

// =============================================================================
// Exported Component with LiveKit Wrapper
// =============================================================================

export function DSAInterviewPage({
  sessionId,
  callId,
  livekitUrl,
  livekitToken,
  problemId,
  candidateName,
  onEnd,
}: DSAInterviewPageProps) {
  const handleDisconnected = useCallback(() => {
    onEnd();
  }, [onEnd]);

  return (
    <LiveKitRoom
      serverUrl={livekitUrl}
      token={livekitToken}
      connect={true}
      audio={true}
      video={true}
      onDisconnected={handleDisconnected}
      style={{ height: '100vh', width: '100vw', background: '#0a0b0e', overflow: 'hidden' }}
    >
      <CameraWarning />
      <DSARoomContent
        sessionId={sessionId}
        callId={callId}
        problemId={problemId}
        candidateName={candidateName}
        onEnd={onEnd}
      />
      <RoomAudioRenderer />
    </LiveKitRoom>
  );
}
