/** Learn: pick or type a topic, then study it with the buddy. */
import { useState, type FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowRight, ChevronLeft, Search } from 'lucide-react';

import { useStats } from './data';
import { sessionUrl } from './HomePage';
import { Scribble } from './notebook';
import { PagePhoto } from './PagePhoto';
import { usePrefs } from './prefs';
import { TOPIC_SUGGESTIONS, strings } from './strings';

export function LearnPage() {
  const { language } = usePrefs();
  const t = strings(language);
  const navigate = useNavigate();
  const stats = useStats();
  const [topic, setTopic] = useState('');
  const start = (value: string) => value.trim() && navigate(sessionUrl('study', value.trim()));
  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    start(topic);
  };
  const mine = stats.data?.topics ?? [];

  return (
    <div className="space-y-7">
      <button onClick={() => navigate(-1)} className="inline-flex items-center gap-1 text-body text-muted">
        <ChevronLeft size={18} aria-hidden />
        {t.back}
      </button>
      <h1 className="font-display text-h2 font-bold">
        <Scribble>{t.learnTitle}</Scribble>
      </h1>

      <form onSubmit={onSubmit} className="space-y-3">
        <label className="sketch flex h-14 items-center gap-3 bg-surface px-4">
          <Search size={20} aria-hidden className="shrink-0 text-muted" />
          <input
            autoFocus
            value={topic}
            onChange={(e) => setTopic(e.target.value)}
            placeholder={t.learnPlaceholder}
            maxLength={120}
            aria-label={t.learnTitle}
            className="h-full min-w-0 flex-1 bg-transparent text-lead text-ink outline-none placeholder:text-muted"
          />
        </label>
        <button
          type="submit"
          disabled={!topic.trim()}
          className="inline-flex h-14 w-full items-center justify-center gap-2 sketch bg-accent text-lead font-semibold text-accent-on disabled:opacity-50"
        >
          {t.learnStart}
          <ArrowRight size={18} aria-hidden />
        </button>
      </form>

      <PagePhoto />

      {mine.length > 0 && (
        <section aria-labelledby="mine-title">
          <h2 id="mine-title" className="text-meta text-muted">
            {t.yourTopics}
          </h2>
          <ul className="mt-2 sketch-soft divide-y divide-line bg-surface">
            {mine.slice(0, 5).map((tp) => (
              <li key={tp.topic}>
                <button onClick={() => start(tp.topic)} className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left">
                  <span className="min-w-0">
                    <span className="block truncate text-lead text-ink">{tp.topic}</span>
                    {tp.ideas_total > 0 && (
                      <span className="block text-meta text-muted">{t.ideasOf(tp.ideas_understood, tp.ideas_total)}</span>
                    )}
                  </span>
                  <ArrowRight size={18} aria-hidden className="shrink-0 text-muted" />
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section aria-labelledby="ideas-title">
        <h2 id="ideas-title" className="text-meta text-muted">
          {t.suggestions}
        </h2>
        <ul className="mt-2 flex flex-wrap gap-2">
          {TOPIC_SUGGESTIONS[language].map((s) => (
            <li key={s}>
              <button
                onClick={() => start(s)}
                className="sketch-soft bg-surface px-4 py-2 text-body text-ink"
              >
                {s}
              </button>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
