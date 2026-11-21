/** Server data for the app screens (react-query), in the learner's current language. */
import { useQuery } from '@tanstack/react-query';

import { getMySession, getMySessions, getMyStats, getMySuggestions } from '@/services/api';
import { usePrefs } from './prefs';

export function useSessions() {
  const { language } = usePrefs();
  return useQuery({ queryKey: ['me', 'sessions', language], queryFn: () => getMySessions(language) });
}

export function useStats() {
  const { language } = usePrefs();
  return useQuery({ queryKey: ['me', 'stats', language], queryFn: () => getMyStats(language) });
}

export function useSuggestions() {
  const { language } = usePrefs();
  return useQuery({ queryKey: ['me', 'suggestions', language], queryFn: () => getMySuggestions(language) });
}

export function useSession(id: string) {
  const { language } = usePrefs();
  return useQuery({
    queryKey: ['me', 'session', id, language],
    queryFn: () => getMySession(id, language),
    enabled: !!id,
  });
}
