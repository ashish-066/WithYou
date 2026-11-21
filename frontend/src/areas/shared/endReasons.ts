import type { Tone } from '@/ui';

/** How an interview ended (worker: brain/interview_flow.py). */
const END_REASONS: Record<string, { label: string; status: string; tone: Tone }> = {
  completed: { label: 'Completed normally', status: 'Completed', tone: 'good' },
  time_limit: { label: 'Reached the time limit', status: 'Completed', tone: 'good' },
  turn_limit: { label: 'Reached the question limit', status: 'Completed', tone: 'good' },
  candidate_ended: { label: 'Candidate chose to stop', status: 'Ended early', tone: 'warn' },
  user_ended: { label: 'Ended with the End button', status: 'Completed', tone: 'good' },
  no_response: { label: 'Candidate stopped responding', status: 'Incomplete', tone: 'bad' },
  left_view: { label: 'Out of camera view too long or too often', status: 'Incomplete', tone: 'bad' },
  disconnected: { label: 'Connection lost, not back in time', status: 'Incomplete', tone: 'bad' },
  abandoned: { label: 'No activity; closed automatically', status: 'Incomplete', tone: 'bad' },
};

export function endReason(reason: string | null | undefined) {
  if (!reason) return null;
  return END_REASONS[reason] ?? { label: reason.replace(/_/g, ' '), status: 'Completed', tone: 'good' as Tone };
}

export const isIncomplete = (reason: string | null | undefined) => endReason(reason)?.status === 'Incomplete';
