/**
 * History: every past session, grouped by day; tap one for its recap and the
 * topic's key ideas (study) or the gentle note (just talk).
 */
import { Link, useNavigate, useParams } from 'react-router-dom';
import { ArrowRight, BookOpen, Check, ChevronLeft, Circle, CircleDashed, MessageCircleHeart, Phone } from 'lucide-react';

import type { SessionSummary } from '@/services/api';
import type { BuddyLanguage } from '@/types';
import { cx } from '@/ui/cx';
import { useSession, useSessions } from './data';
import { sessionUrl } from './HomePage';
import { usePrefs } from './prefs';
import { LevelBadge } from './ProgressProfile';
import { strings, type Strings } from './strings';

function dayLabel(iso: string | null, t: Strings, language: BuddyLanguage) {
  if (!iso) return '';
  const d = new Date(iso);
  const today = new Date();
  const yesterday = new Date();
  yesterday.setDate(today.getDate() - 1);
  if (d.toDateString() === today.toDateString()) return t.today;
  if (d.toDateString() === yesterday.toDateString()) return t.yesterday;
  return d.toLocaleDateString(language, { weekday: 'short', day: 'numeric', month: 'short' });
}

function timeLabel(iso: string | null, language: BuddyLanguage) {
  return iso ? new Date(iso).toLocaleTimeString(language, { hour: 'numeric', minute: '2-digit' }) : '';
}

export function HistoryPage() {
  const { language } = usePrefs();
  const t = strings(language);
  const { data, isLoading } = useSessions();
  const sessions = data?.sessions ?? [];

  const groups: { label: string; items: SessionSummary[] }[] = [];
  for (const s of sessions) {
    const label = dayLabel(s.created_at, t, language);
    const group = groups[groups.length - 1];
    if (group && group.label === label) group.items.push(s);
    else groups.push({ label, items: [s] });
  }

  return (
    <div className="space-y-6">
      <h1 className="font-display text-h2">{t.historyTitle}</h1>
      {isLoading && <p className="text-body text-muted">{t.loading}</p>}
      {!isLoading && sessions.length === 0 && (
        <div className="rounded-ui border border-dashed border-line-strong p-6 text-center text-body text-muted">
          {t.historyEmpty}
        </div>
      )}
      {groups.map((g) => (
        <section key={g.label} aria-label={g.label}>
          <h2 className="text-meta text-muted">{g.label}</h2>
          <ul className="mt-2 divide-y divide-line rounded-ui border border-line bg-surface">
            {g.items.map((s) => (
              <li key={s.session_id}>
                <Link to={`/history/${s.session_id}`} className="flex items-center gap-3 px-4 py-3">
                  <ModeIcon mode={s.mode} />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-lead text-ink">
                      {s.mode === 'talk' ? t.justTalk : s.topic || t.noTopic}
                    </span>
                    <span className="block truncate text-meta text-muted">
                      {timeLabel(s.created_at, language)}
                      {s.mode === 'study' && s.level && ` · ${t.levels[s.level]}`}
                      {s.mood && ` · ${t.moodNames[s.mood.label]}`}
                      {s.title && ` · ${s.title}`}
                    </span>
                  </span>
                  <ArrowRight size={18} aria-hidden className="shrink-0 text-muted" />
                </Link>
              </li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}

function ModeIcon({ mode }: { mode: 'study' | 'talk' }) {
  const Icon = mode === 'talk' ? MessageCircleHeart : BookOpen;
  return (
    <span
      className={cx(
        'flex h-10 w-10 shrink-0 items-center justify-center rounded-full',
        mode === 'talk' ? 'bg-accent/10 text-accent' : 'bg-accent text-accent-on',
      )}
    >
      <Icon size={20} aria-hidden />
    </span>
  );
}

export function SessionDetailPage() {
  const { id = '' } = useParams();
  const { language } = usePrefs();
  const t = strings(language);
  const navigate = useNavigate();
  const { data: s, isLoading, isError } = useSession(id);

  return (
    <div className="space-y-6">
      <button onClick={() => navigate(-1)} className="inline-flex items-center gap-1 text-body text-muted">
        <ChevronLeft size={18} aria-hidden />
        {t.back}
      </button>
      {isLoading && <p className="text-body text-muted">{t.loading}</p>}
      {isError && <p className="text-body text-muted">{t.sessionNotFound}</p>}
      {s && (
        <>
          <header className="flex items-start gap-3">
            <ModeIcon mode={s.mode} />
            <div className="min-w-0">
              <h1 className="font-display text-h2">{s.mode === 'talk' ? t.justTalk : s.topic || t.noTopic}</h1>
              <p className="text-body text-muted">
                {dayLabel(s.created_at, t, language)} · {timeLabel(s.created_at, language)}
                {s.mood && ` · ${t.moodNames[s.mood.label]}`}
              </p>
              {s.mode === 'study' && s.level && (
                <div className="mt-2">
                  <LevelBadge level={s.level} label={t.levels[s.level]} />
                </div>
              )}
            </div>
          </header>

          {s.recap && (
            <section className="rounded-ui border border-line bg-surface p-5">
              {s.recap.title && <h2 className="font-display text-h3">{s.recap.title}</h2>}
              <p className="mt-2 text-lead">{s.recap.summary}</p>
              {s.recap.next_time && <p className="mt-3 text-body text-muted">{s.recap.next_time}</p>}
              {s.recap.help && (
                <div role="note" className="mt-4 rounded-ui border border-accent bg-accent/10 p-3 text-body">
                  {s.recap.help}
                </div>
              )}
            </section>
          )}

          {s.ideas.length > 0 && (
            <section aria-labelledby="ideas-title">
              <h2 id="ideas-title" className="text-meta text-muted">
                {t.keyIdeas} · {t.ideasOf(s.ideas_understood, s.ideas_total)}
              </h2>
              <p className="mt-0.5 text-meta text-muted">{t.conceptsHelp}</p>
              <ul className="mt-2 space-y-2">
                {s.ideas.map((idea, i) => (
                  <li key={i} className="flex items-start gap-3 rounded-ui border border-line bg-surface px-4 py-3">
                    <IdeaIcon status={idea.status} />
                    <span className="min-w-0 flex-1 text-body text-ink">{idea.text}</span>
                    <span className="shrink-0 text-meta text-muted">{t.status[idea.status]}</span>
                  </li>
                ))}
              </ul>
            </section>
          )}

          {s.mode === 'study' && s.topic && (
            <button
              onClick={() => navigate(sessionUrl('study', s.topic ?? undefined))}
              className="inline-flex h-12 w-full items-center justify-center gap-2 rounded-full bg-accent text-lead text-accent-on"
            >
              {t.studyAgain}
              <ArrowRight size={18} aria-hidden />
            </button>
          )}
          {s.recap?.help && (
            <a href="tel:14416" className="inline-flex h-12 w-full items-center justify-center gap-2 rounded-full border border-accent text-lead text-accent">
              <Phone size={18} aria-hidden />
              {t.helpCall}
            </a>
          )}
        </>
      )}
    </div>
  );
}

export function IdeaIcon({ status }: { status: 'unseen' | 'partial' | 'gap' | 'understood' }) {
  if (status === 'understood')
    return (
      <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-accent text-accent-on">
        <Check size={13} aria-hidden />
      </span>
    );
  if (status === 'partial' || status === 'gap')
    return <CircleDashed size={20} aria-hidden className="mt-0.5 shrink-0 text-warn" />;
  return <Circle size={20} aria-hidden className="mt-0.5 shrink-0 text-line-strong" />;
}
