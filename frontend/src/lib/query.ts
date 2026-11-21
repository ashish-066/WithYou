import { QueryClient } from '@tanstack/react-query';
import { ApiError } from './api';

/**
 * Data fetching for the new pages. Lists refetch when the window regains focus;
 * live views set their own refetchInterval (and only while the tab is visible,
 * which is react-query's default).
 */
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 15_000,
      // Retrying "not found" or "no access" only delays the error page
      retry: (count, err) => !(err instanceof ApiError && err.status >= 400 && err.status < 500) && count < 2,
    },
  },
});
