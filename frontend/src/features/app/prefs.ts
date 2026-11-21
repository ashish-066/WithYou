/**
 * The learner's preferences on this device: language and buddy voice.
 * Kept in localStorage (best effort) and shared across screens.
 */
import { useCallback, useSyncExternalStore } from 'react';

import type { BuddyLanguage } from '@/types';
import { saveLanguage, savedLanguage } from '@/features/study/labels';

export type Voice = 'kavya' | 'shubh';
const VOICE_KEY = 'buddy-voice';
const EVENT = 'buddy-prefs';

function readVoice(): Voice {
  try {
    return localStorage.getItem(VOICE_KEY) === 'shubh' ? 'shubh' : 'kavya';
  } catch {
    return 'kavya';
  }
}

function subscribe(cb: () => void) {
  window.addEventListener(EVENT, cb);
  window.addEventListener('storage', cb);
  return () => {
    window.removeEventListener(EVENT, cb);
    window.removeEventListener('storage', cb);
  };
}

export function usePrefs() {
  const language = useSyncExternalStore(subscribe, savedLanguage, () => 'ml-IN' as BuddyLanguage);
  const voice = useSyncExternalStore(subscribe, readVoice, () => 'kavya' as Voice);
  const setLanguage = useCallback((l: BuddyLanguage) => {
    saveLanguage(l);
    window.dispatchEvent(new Event(EVENT));
  }, []);
  const setVoice = useCallback((v: Voice) => {
    try {
      localStorage.setItem(VOICE_KEY, v);
    } catch {
      /* ignore */
    }
    window.dispatchEvent(new Event(EVENT));
  }, []);
  return { language, voice, setLanguage, setVoice };
}
