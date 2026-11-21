/**
 * Interview room component with LiveKit video/audio.
 * Modern dark UI with BeyondPresence avatar and control bar.
 */

import { useCallback, useState } from 'react';
import { CameraWarning } from './CameraWarning';
import { ConfirmEndDialog } from './ConfirmEndDialog';
import {
  LiveKitRoom,
  RoomAudioRenderer,
  useLocalParticipant,
  VideoTrack,
  useTracks,
} from '@livekit/components-react';
import { Track } from 'livekit-client';

interface InterviewRoomProps {
  serverUrl: string;
  token: string;
  sessionId: string;
  onDisconnect: () => void;
  onEnd: () => void;
}

export function InterviewRoom({ serverUrl, token, onDisconnect, onEnd }: InterviewRoomProps) {
  const handleDisconnected = useCallback(() => {
    onDisconnect();
  }, [onDisconnect]);

  return (
    <LiveKitRoom
      serverUrl={serverUrl}
      token={token}
      connect={true}
      audio={true}
      video={true}
      onDisconnected={handleDisconnected}
      className="h-screen w-screen bg-black overflow-hidden"
    >
      <InterviewContent onEnd={onEnd} />
      <RoomAudioRenderer />
      <CameraWarning />
    </LiveKitRoom>
  );
}

// Voice Wave Animation Component - shown while waiting for avatar
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

// Control Button Component
function ControlButton({
  icon,
  hasDropdown = false,
  onClick,
  isActive = true,
  title
}: {
  icon: React.ReactNode;
  hasDropdown?: boolean;
  onClick?: () => void;
  isActive?: boolean;
  title?: string;
}) {
  return (
    <div className="control-button-group">
      <button
        className={`control-button ${!isActive ? 'inactive' : ''}`}
        onClick={onClick}
        title={title}
      >
        {icon}
      </button>
      {hasDropdown && (
        <button className="control-dropdown" title="Options">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor">
            <path d="M7 10l5 5 5-5z" />
          </svg>
        </button>
      )}
    </div>
  );
}

function InterviewContent({ onEnd }: { onEnd: () => void }) {
  const [confirmEnd, setConfirmEnd] = useState(false);
  const [ending, setEnding] = useState(false);
  const { localParticipant } = useLocalParticipant();

  // State for mic/camera toggles
  const [isMicOn, setIsMicOn] = useState(true);
  const [isCameraOn, setIsCameraOn] = useState(true);


  // Get all video tracks (Camera, ScreenShare, Unknown) to catch any avatar video stream
  const allVideoTracks = useTracks(
    [Track.Source.Camera, Track.Source.ScreenShare, Track.Source.Unknown],
    { onlySubscribed: false }
  );

  // Find the avatar's video track (any remote participant publishing video)
  const avatarVideoTrack = allVideoTracks.find(
    (track) =>
      track.participant.identity !== localParticipant?.identity &&
      (track.publication?.track !== undefined ||
       track.participant.identity.includes('bey') ||
       track.participant.identity.includes('avatar') ||
       track.participant.identity.includes('agent'))
  );

  // Find the local user's video track for the self-view
  const localVideoTrack = allVideoTracks.find(
    (track) => track.participant.identity === localParticipant?.identity
  );


  // Camera checks (presence, other people, phones) run on the server, in the
  // voice agent, on this video: the browser can't fake or block them

  // Speaking indicators
  const avatarParticipant = avatarVideoTrack?.participant;
  const isUserSpeaking = localParticipant?.isSpeaking ?? false;
  const isAvatarSpeaking = avatarParticipant?.isSpeaking ?? false;

  // Toggle handlers
  const toggleMic = useCallback(async () => {
    if (localParticipant) {
      await localParticipant.setMicrophoneEnabled(!isMicOn);
      setIsMicOn(!isMicOn);
    }
  }, [localParticipant, isMicOn]);

  const toggleCamera = useCallback(async () => {
    if (localParticipant) {
      await localParticipant.setCameraEnabled(!isCameraOn);
      setIsCameraOn(!isCameraOn);
    }
  }, [localParticipant, isCameraOn]);

  return (
    <div className="interview-container">
      {/* Main Content Area - Avatar or Voice Wave */}
      <div className="main-content">
        {avatarVideoTrack ? (
          <div className={`avatar-video-wrapper ${isAvatarSpeaking ? 'speaking' : ''}`}>
            <VideoTrack
              trackRef={avatarVideoTrack}
              className="avatar-video"
            />
            {/* Speaking indicator for avatar */}
            {isAvatarSpeaking && (
              <div className="avatar-speaking-indicator">
                <span className="pulse-dot"></span>
                <span className="pulse-dot"></span>
                <span className="pulse-dot"></span>
              </div>
            )}
          </div>
        ) : (
          <VoiceWaveAnimation />
        )}
      </div>

      {/* Self-view PIP - Bottom Right */}
      <div className={`pip-container ${isUserSpeaking ? 'speaking' : ''}`}>
        {localVideoTrack && isCameraOn ? (
          <VideoTrack
            trackRef={localVideoTrack}
            className="pip-video"
          />
        ) : (
          <div className="pip-placeholder">
            <svg className="pip-icon" viewBox="0 0 24 24" fill="currentColor">
              <path d="M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z" />
            </svg>
          </div>
        )}
      </div>

      {/* Bottom Control Bar */}
      <div className="control-bar">
        <div className="control-bar-left">
          {/* Microphone Button */}
          <ControlButton
            icon={
              isMicOn ? (
                <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
                  <path d="M12 14c1.66 0 3-1.34 3-3V5c0-1.66-1.34-3-3-3S9 3.34 9 5v6c0 1.66 1.34 3 3 3z" />
                  <path d="M17 11c0 2.76-2.24 5-5 5s-5-2.24-5-5H5c0 3.53 2.61 6.43 6 6.92V21h2v-3.08c3.39-.49 6-3.39 6-6.92h-2z" />
                </svg>
              ) : (
                <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
                  <path d="M19 11h-1.7c0 .74-.16 1.43-.43 2.05l1.23 1.23c.56-.98.9-2.09.9-3.28zm-4.02.17c0-.06.02-.11.02-.17V5c0-1.66-1.34-3-3-3S9 3.34 9 5v.18l5.98 5.99zM4.27 3L3 4.27l6.01 6.01V11c0 1.66 1.33 3 2.99 3 .22 0 .44-.03.65-.08l1.66 1.66c-.71.33-1.5.52-2.31.52-2.76 0-5.3-2.1-5.3-5.1H5c0 3.41 2.72 6.23 6 6.72V21h2v-3.28c.91-.13 1.77-.45 2.54-.9L19.73 21 21 19.73 4.27 3z" />
                </svg>
              )
            }
            hasDropdown={true}
            onClick={toggleMic}
            isActive={isMicOn}
            title={isMicOn ? "Mute microphone" : "Unmute microphone"}
          />

          {/* Camera Button */}
          <ControlButton
            icon={
              isCameraOn ? (
                <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
                  <path d="M17 10.5V7c0-.55-.45-1-1-1H4c-.55 0-1 .45-1 1v10c0 .55.45 1 1 1h12c.55 0 1-.45 1-1v-3.5l4 4v-11l-4 4z" />
                </svg>
              ) : (
                <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
                  <path d="M21 6.5l-4 4V7c0-.55-.45-1-1-1H9.82L21 17.18V6.5zM3.27 2L2 3.27 4.73 6H4c-.55 0-1 .45-1 1v10c0 .55.45 1 1 1h12c.21 0 .39-.08.54-.18L19.73 21 21 19.73 3.27 2z" />
                </svg>
              )
            }
            hasDropdown={true}
            onClick={toggleCamera}
            isActive={isCameraOn}
            title={isCameraOn ? "Turn off camera" : "Turn on camera"}
          />
        </div>

        {/* End Call Button */}
        <button className="end-call-button" onClick={() => setConfirmEnd(true)}>
          <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
            <path d="M12 9c-1.6 0-3.15.25-4.6.72v3.1c0 .39-.23.74-.56.9-.98.49-1.87 1.12-2.66 1.85-.18.18-.43.28-.7.28-.28 0-.53-.11-.71-.29L.29 13.08c-.18-.17-.29-.42-.29-.7 0-.28.11-.53.29-.71C3.34 8.78 7.46 7 12 7s8.66 1.78 11.71 4.67c.18.18.29.43.29.71 0 .28-.11.53-.29.71l-2.48 2.48c-.18.18-.43.29-.71.29-.27 0-.52-.11-.7-.28-.79-.74-1.69-1.36-2.67-1.85-.33-.16-.56-.5-.56-.9v-3.1C15.15 9.25 13.6 9 12 9z" />
          </svg>
          <span>END CALL</span>
        </button>
      </div>
      <ConfirmEndDialog
        open={confirmEnd}
        ending={ending}
        onCancel={() => setConfirmEnd(false)}
        onConfirm={() => {
          setEnding(true);
          onEnd();
        }}
      />
    </div>
  );
}
