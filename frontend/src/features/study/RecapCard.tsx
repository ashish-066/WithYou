/**
 * The kind end-of-session recap, for the learner: what we studied, where you
 * got sharper, one thing for next time. No scores. Written by the brain after
 * the goodbye, so it can take a few seconds: polled until ready.
 */
import { useEffect, useState } from 'react';
import { Check, Sparkles } from 'lucide-react';

import { getRecap, type Recap } from '@/services/api';
import type { BuddyLanguage } from '@/types';
import { labels } from './labels';

const POLL_MS = 2500;
const GIVE_UP_MS = 45_000;

export function RecapCard({ sessionId, language }: { sessionId: string; language: BuddyLanguage }) {
  const t = labels(language);
  const [recap, setRecap] = useState<Recap | null>(null);
  const [gaveUp, setGaveUp] = useState(false);

  useEffect(() => {
    let live = true;
    const started = Date.now();
    const poll = async () => {
      try {
        const r = await getRecap(sessionId);
        if (!live) return;
        if (r.status === 'ready' && r.recap) return setRecap(r.recap);
        if (r.status === 'failed') return setGaveUp(true);
      } catch {
        /* keep trying until the give-up time */
      }
      if (Date.now() - started > GIVE_UP_MS) return live && setGaveUp(true);
      window.setTimeout(poll, POLL_MS);
    };
    poll();
    return () => {
      live = false;
    };
  }, [sessionId]);

  if (gaveUp && !recap) return null;
  if (!recap) {
    return (
      <p role="status" className="animate-pulse text-lead text-muted">
        {t.recapWriting}
      </p>
    );
  }

  return (
    <section aria-labelledby="recap-title" className="rounded-ui border border-line bg-surface p-5">
      <h2 id="recap-title" className="font-display text-h3 text-ink">
        {recap.title || t.recapCovered}
      </h2>
      <p className="mt-2 text-lead text-ink">{recap.summary}</p>
      {recap.covered.length > 0 && (
        <>
          <h3 className="mt-4 text-meta text-muted">{t.recapCovered}</h3>
          <ul className="mt-1 space-y-1">
            {recap.covered.map((c, i) => (
              <li key={i} className="flex gap-2 text-body text-ink">
                <Check size={16} className="mt-0.5 shrink-0 text-accent" aria-hidden />
                {c}
              </li>
            ))}
          </ul>
        </>
      )}
      {recap.improved.length > 0 && (
        <>
          <h3 className="mt-4 text-meta text-muted">{t.recapImproved}</h3>
          <ul className="mt-1 space-y-1">
            {recap.improved.map((c, i) => (
              <li key={i} className="flex gap-2 text-body text-ink">
                <Sparkles size={16} className="mt-0.5 shrink-0 text-accent" aria-hidden />
                {c}
              </li>
            ))}
          </ul>
        </>
      )}
      {recap.help && (
        <div role="note" className="mt-4 rounded-ui border border-accent bg-accent/10 p-3">
          <h3 className="text-meta text-ink">{t.helpTitle}</h3>
          <p className="mt-1 text-body text-ink">{recap.help}</p>
        </div>
      )}
      {recap.next_time && (
        <>
          <h3 className="mt-4 text-meta text-muted">{t.recapNext}</h3>
          <p className="mt-1 text-body text-ink">{recap.next_time}</p>
        </>
      )}
    </section>
  );
}
