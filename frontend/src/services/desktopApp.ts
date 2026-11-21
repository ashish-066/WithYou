/**
 * Connection to the Presence View desktop app. `window.presenceDesktop` exists
 * only when the page is running inside that app (see desktop/src/preload.js).
 */

import type { CheatFlagType, SeverityLevel } from '@/types';

export interface BlockedApp {
  name: string;
  category: string;
}

export interface DesktopStatus {
  version: string;
  locked: boolean;
  displays: number;
  blockedApps: BlockedApp[];
}

export interface DesktopViolation {
  flag_type: CheatFlagType;
  severity: SeverityLevel;
  description: string;
}

export interface PresenceDesktop {
  status: () => Promise<DesktopStatus>;
  /** Asks blocked apps to close; { force: true } ends them. Returns those still running. */
  closeBlockedApps: (options?: { force?: boolean }) => Promise<BlockedApp[]>;
  requestMedia: () => Promise<boolean>;
  lock: (inviteToken: string | null) => Promise<void>;
  unlock: () => Promise<void>;
  onViolation: (callback: (violation: DesktopViolation) => void) => () => void;
}

declare global {
  interface Window {
    presenceDesktop?: PresenceDesktop;
  }
}

export function getDesktop(): PresenceDesktop | undefined {
  return window.presenceDesktop;
}

/** Opens this invite in the installed desktop app. */
export function desktopLink(inviteToken: string): string {
  return `presenceview://interview?invite=${encodeURIComponent(inviteToken)}`;
}

export const DESKTOP_DOWNLOAD_URL: string | undefined = import.meta.env.VITE_DESKTOP_DOWNLOAD_URL;
