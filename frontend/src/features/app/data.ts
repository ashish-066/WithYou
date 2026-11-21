/** Server data for the app screens (react-query: cached, refreshed on focus). */
import { useQuery } from '@tanstack/react-query';

import { getMySession, getMySessions, getMyStats } from '@/services/api';

export const useSessions = () => useQuery({ queryKey: ['me', 'sessions'], queryFn: getMySessions });
export const useStats = () => useQuery({ queryKey: ['me', 'stats'], queryFn: getMyStats });
export const useSession = (id: string) =>
  useQuery({ queryKey: ['me', 'session', id], queryFn: () => getMySession(id), enabled: !!id });
