/**
 * Call setup form for starting an interview.
 * Split-screen layout with infinite scroll image on left, form on right.
 */

import { useState, useRef, useEffect } from 'react';
import { uploadResume } from '../services/api';
import { listRoles } from '../services/roleApi';
import { listDSAProblems } from '../services/dsaApi';
import type { JobRole, DSAProblemMeta, InviteInfo } from '../types';

interface CallSetupProps {
  /** Candidate's invite link: round, role and problem come from it */
  invite?: { token: string; info: InviteInfo };
  onStart: (params: {
    inviteToken?: string;
    candidateName: string;
    roleId?: string;
    githubUrl?: string;
    linkedinUrl?: string;
    resumeText?: string;
    interviewMode?: 'round1' | 'round2_dsa';
    dsaProblemId?: string;
  }) => void;
  isLoading: boolean;
  error: string | null;
}

// Infinite Scroll Image Component
function InfiniteScrollImage() {
  return (
    <div className="pl-20 infinite-scroll-container">
      <div className="infinite-scroll-track">
        {/* Stack 3 copies of the image for seamless looping */}
        <img 
          src="/infiniteScrollCreateInterview.png" 
          alt="Decorative pattern" 
          className="infinite-scroll-image"
        />
        <img 
          src="/infiniteScrollCreateInterview.png" 
          alt="Decorative pattern" 
          className="infinite-scroll-image"
        />
        <img 
          src="/infiniteScrollCreateInterview.png" 
          alt="Decorative pattern" 
          className="infinite-scroll-image"
        />
      </div>
    </div>
  );
}

export function CallSetup({ invite, onStart, isLoading, error }: CallSetupProps) {
  const [name, setName] = useState(invite?.info.candidate_name ?? '');
  const [selectedRoleId, setSelectedRoleId] = useState('');
  const [availableRoles, setAvailableRoles] = useState<JobRole[]>([]);
  const [interviewMode, setInterviewMode] = useState<'round1' | 'round2_dsa'>('round1');
  const [rulesAccepted, setRulesAccepted] = useState(false);
  const coding = (invite?.info.interview_mode ?? interviewMode) === 'round2_dsa';
  const [availableProblems, setAvailableProblems] = useState<DSAProblemMeta[]>([]);
  const [selectedProblemId, setSelectedProblemId] = useState('');
  const [githubUrl, setGithubUrl] = useState('');
  const [linkedinUrl, setLinkedinUrl] = useState('');
  const [resumeFile, setResumeFile] = useState<File | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    // The invite fixes the role and problem; candidates can't list them
    if (invite) return;
    // Load available job roles and DSA problems
    const loadData = async () => {
      try {
        const roleRes = await listRoles(true);
        setAvailableRoles(roleRes.roles);
      } catch (err) {
        console.error('Failed to load job roles:', err);
      }

      try {
        const problems = await listDSAProblems();
        setAvailableProblems(problems);
        if (problems.length > 0) {
          setSelectedProblemId(problems[0].problem_id);
        }
      } catch (err) {
        console.error('Failed to load DSA problems:', err);
      }
    };
    loadData();
  }, [invite]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (name.trim()) {
      let resumeText = undefined;

      if (resumeFile) {
        try {
          setIsUploading(true);
          const result = await uploadResume(resumeFile, invite?.token);
          resumeText = result.resume_text;
        } catch (err) {
          console.error('Failed to upload resume:', err);
          alert('Failed to upload resume. Proceeding without it.');
        } finally {
          setIsUploading(false);
        }
      }

      if (invite) {
        onStart({
          inviteToken: invite.token,
          candidateName: name.trim(),
          githubUrl: githubUrl.trim() || undefined,
          linkedinUrl: linkedinUrl.trim() || undefined,
          resumeText,
          interviewMode: invite.info.interview_mode,
          dsaProblemId: invite.info.dsa_problem_id || undefined,
        });
        return;
      }
      onStart({
        candidateName: name.trim(),
        roleId: selectedRoleId || undefined,
        githubUrl: githubUrl.trim() || undefined,
        linkedinUrl: linkedinUrl.trim() || undefined,
        resumeText,
        interviewMode,
        dsaProblemId: interviewMode === 'round2_dsa' ? (selectedProblemId || 'two_sum_001') : undefined,
      });
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      setResumeFile(e.target.files[0]);
    }
  };

  return (
    <div className="call-setup-container">
      {/* Left Side - Infinite Scroll Image */}
      <div className="call-setup-left">
        <InfiniteScrollImage />
      </div>

      {/* Right Side - Form */}
      <div className="call-setup-right">
        <div className="call-setup-form-wrapper">
          {/* Header */}
          <div className="call-setup-header">
            <h1 className="call-setup-title">Start Your Interview</h1>
            <p className="call-setup-subtitle">
              {invite
                ? `${invite.info.interview_mode === 'round2_dsa' ? 'Coding round' : 'Technical interview'}${
                    invite.info.role_title ? ` for ${invite.info.role_title}` : ''
                  }. Read the rules below to begin.`
                : 'Fill in your details to begin the AI-powered interview'}
            </p>
          </div>

          {/* Form */}
          <form onSubmit={handleSubmit} className="call-setup-form">
            {/* Name Field */}
            <div className="form-field">
              <label htmlFor="name" className="form-label">
                Your Name
              </label>
              <input
                id="name"
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Enter your name"
                required
                readOnly={!!invite}
                className="form-input"
              />
            </div>

            {!invite && (<>
            {/* Interview Round Mode Selection */}
            <div className="form-field">
              <label htmlFor="interviewMode" className="form-label">
                Interview Round
              </label>
              <select
                id="interviewMode"
                value={interviewMode}
                onChange={(e) => setInterviewMode(e.target.value as 'round1' | 'round2_dsa')}
                className="form-input form-select"
                style={{ fontWeight: 500 }}
              >
                <option value="round1">Round 1 — General Screening & System Design</option>
                <option value="round2_dsa">Round 2 — DSA Coding Round (Live Code & Avatar)</option>
              </select>
            </div>

            {/* DSA Problem Selection (shown only for Round 2) */}
            {interviewMode === 'round2_dsa' && (
              <div className="form-field">
                <label htmlFor="dsaProblem" className="form-label">
                  DSA Problem
                </label>
                <select
                  id="dsaProblem"
                  value={selectedProblemId}
                  onChange={(e) => setSelectedProblemId(e.target.value)}
                  className="form-input form-select"
                >
                  {availableProblems.length > 0 ? (
                    availableProblems.map((prob) => (
                      <option key={prob.problem_id} value={prob.problem_id}>
                        {prob.title} ({prob.difficulty})
                      </option>
                    ))
                  ) : (
                    <option value="two_sum_001">Two Sum (easy)</option>
                  )}
                </select>
              </div>
            )}

            {/* Role Selection */}
            <div className="form-field">
              <label htmlFor="role" className="form-label">
                Position
              </label>
              <select
                id="role"
                value={selectedRoleId}
                onChange={(e) => setSelectedRoleId(e.target.value)}
                className="form-input form-select"
              >
                <option value="">Select a role (optional)</option>
                {availableRoles.map((role) => (
                  <option key={role.role_id} value={role.role_id}>
                    {role.role_title}
                  </option>
                ))}
              </select>
            </div>
            </>)}

            {/* Profile details: only without an invite (a recruiter trying it out).
                With an invite, the organization already provided them. */}
            {!invite && (<>
            {/* GitHub and LinkedIn URLs */}
            <div className="form-row">
              <div className="form-field">
                <label htmlFor="github" className="form-label">
                  GitHub URL
                </label>
                <input
                  id="github"
                  type="url"
                  value={githubUrl}
                  onChange={(e) => setGithubUrl(e.target.value)}
                  placeholder="https://github.com/..."
                  className="form-input"
                />
              </div>
              <div className="form-field">
                <label htmlFor="linkedin" className="form-label">
                  LinkedIn URL
                </label>
                <input
                  id="linkedin"
                  type="url"
                  value={linkedinUrl}
                  onChange={(e) => setLinkedinUrl(e.target.value)}
                  placeholder="https://linkedin.com/..."
                  className="form-input"
                />
              </div>
            </div>

            {/* Resume Upload */}
            <div className="form-field">
              <label className="form-label">
                Resume (PDF/Image)
              </label>
              <div 
                onClick={() => fileInputRef.current?.click()}
                className="form-file-upload"
              >
                <svg className="form-file-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                </svg>
                {resumeFile ? (
                  <span className="form-file-name">{resumeFile.name}</span>
                ) : (
                  <span className="form-file-placeholder">Click to upload your resume</span>
                )}
              </div>
              <input
                ref={fileInputRef}
                type="file"
                accept=".pdf,image/*"
                onChange={handleFileChange}
                className="hidden"
              />
            </div>
            </>)}

            {/* Error Display */}
            {error && (
              <div className="form-error">
                {error}
              </div>
            )}

            {/* Rules, agreed before starting (enforced during the interview) */}
            <div className="interview-rules" aria-labelledby="interview-rules-title">
              <h3 id="interview-rules-title" className="interview-rules-title">Before you start</h3>
              <ul className="interview-rules-list">
                <li>The interview takes about 45 minutes in one sitting. The clock doesn't stop.</li>
                <li>
                  Stay in view of your camera. If you're out of view, the interviewer asks you to come back and
                  moves to a different question. Long or repeated absences end the interview.
                </li>
                <li>
                  Be alone, with no phone or other device in view. The camera is checked during the interview, and a
                  photo is saved for the hiring team if another person or a device is detected.
                </li>
                <li>
                  If you don't start answering within about 30 seconds, the interviewer moves on. Unanswered
                  questions count in the evaluation.
                </li>
                <li>If your connection drops, you can rejoin once, within 2 minutes, with the same link.</li>
                <li>
                  {coding
                    ? 'Explain your thinking out loud as you write your code.'
                    : 'Thinking out loud is welcome.'}
                </li>
              </ul>
              <label className="interview-rules-accept">
                <input
                  type="checkbox"
                  checked={rulesAccepted}
                  onChange={(e) => setRulesAccepted(e.target.checked)}
                />
                <span>I understand these rules</span>
              </label>
            </div>

            {/* Submit Button */}
            <button
              type="submit"
              disabled={isLoading || isUploading || !name.trim() || !rulesAccepted}
              className="form-submit-button"
            >
              {isLoading || isUploading ? (
                <>
                  <svg className="animate-spin" width="20" height="20" viewBox="0 0 24 24">
                    <circle
                      className="opacity-25"
                      cx="12"
                      cy="12"
                      r="10"
                      stroke="currentColor"
                      strokeWidth="4"
                      fill="none"
                    />
                    <path
                      className="opacity-75"
                      fill="currentColor"
                      d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                    />
                  </svg>
                  {isUploading ? 'Analyzing Resume...' : 'Connecting...'}
                </>
              ) : (
                'Start Interview'
              )}
            </button>
          </form>

          {/* What to Expect Section */}
          <div className="call-setup-info">
            <h3 className="info-title">What to expect</h3>
            <ul className="info-list">
              <li className="info-item">
                <span className="info-check">✓</span>
                AI interviewer with realistic avatar
              </li>
              <li className="info-item">
                <span className="info-check">✓</span>
                Profile-aware personalized questions
              </li>
              <li className="info-item">
                <span className="info-check">✓</span>
                Real-time skills assessment
              </li>
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
}
