/**
 * Home: greeting, real stats (streak, this week, ideas learned), the two ways
 * to start (study / just talk), quick topics, "pick up where you left off" from
 * the last study session, and a mood check-in that opens a talk session.
 */
import { Link, useNavigate } from 'react-router-dom';
import { ArrowRight, BookOpen, CalendarCheck, Flame, Lightbulb, MessageCircleHeart } from 'lucide-react';

import { useAuth } from '@/hooks/useAuth';
import { cx } from '@/ui/cx';
import { useSessions, useStats } from './data';
import { usePrefs } from './prefs';
import { TOPIC_SUGGESTIONS, partOfDay, strings } from './strings';

export function sessionUrl(mode: 'study' | 'talk', topic?: string) {
  const q = new URLSearchParams({ mode });
  if (topic) q.set('topic', topic);
  return `/session?${q.toString()}`;
}

export function HomePage() {
  const { user } = useAuth();
  const { language } = usePrefs();
  const t = strings(language);
  const navigate = useNavigate();
  const stats = useStats();
  const sessions = useSessions();
  const firstName = (user?.name || '').split(' ')[0];
  const lastStudy = sessions.data?.sessions.find((s) => s.mode === 'study' && s.topic);

  return (
    <div className="space-y-7">
      <header className="flex items-center justify-between gap-3">
        <div className="min-w-0">
          <p className="text-body text-muted">{new Date().toLocaleDateString(language, { weekday: 'long', day: 'numeric', month: 'long' })}</p>
          <h1 className="mt-0.5 font-display text-h2">{t.greet(partOfDay(), firstName)}</h1>
        </div>
        <Link
          to="/me"
          aria-label={t.nav.profile}
          className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-accent text-lead text-accent-on"
        >
          {(firstName[0] || 'S').toUpperCase()}
        </Link>
      </header>

      {/* Stats: three tiles in a row (flex, not a grid) */}
      <section aria-label={t.nav.progress} className="flex gap-2">
        <Stat Icon={Flame} value={stats.data ? t.streak(stats.data.streak_days) : '–'} label={t.streakLabel} />
        <Stat Icon={CalendarCheck} value={stats.data ? String(stats.data.sessions_this_week) : '–'} label={t.weekLabel} />
        <Stat Icon={Lightbulb} value={stats.data ? String(stats.data.ideas_understood) : '–'} label={t.ideasLabel} />
      </section>

      {/* The two ways to start */}
      <section className="flex flex-col gap-3">
        <button
          onClick={() => navigate('/learn')}
          className="group rounded-ui bg-accent p-5 text-left text-accent-on"
        >
          <div className="flex items-start justify-between gap-4">
            <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-full bg-accent-on/15">
              <BookOpen size={26} aria-hidden />
            </span>
            <ArrowRight size={22} aria-hidden className="mt-1 transition-transform group-hover:translate-x-1" />
          </div>
          <h2 className="mt-4 font-display text-h3">{t.studyTitle}</h2>
          <p className="mt-1 text-body opacity-90">{t.studyBody}</p>
        </button>

        <button
          onClick={() => navigate(sessionUrl('talk'))}
          className="group rounded-ui border border-line bg-surface p-5 text-left text-ink"
        >
          <div className="flex items-start justify-between gap-4">
            <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-full bg-accent/10 text-accent">
              <MessageCircleHeart size={26} aria-hidden />
            </span>
            <ArrowRight size={22} aria-hidden className="mt-1 text-muted transition-transform group-hover:translate-x-1" />
          </div>
          <h2 className="mt-4 font-display text-h3">{t.talkTitle}</h2>
          <p className="mt-1 text-body text-muted">{t.talkBody}</p>
        </button>
      </section>

      {/* Pick up where you left off */}
      {lastStudy && (
        <section aria-labelledby="continue-title" className="rounded-ui border border-line bg-surface p-5">
          <h2 id="continue-title" className="text-meta text-muted">
            {t.continueTitle}
          </h2>
          <p className="mt-1 font-display text-h3">{lastStudy.topic}</p>
          {lastStudy.ideas_total > 0 && (
            <>
              <div
                className="mt-3 h-2 overflow-hidden rounded-full bg-sunken"
                role="progressbar"
                aria-valuemin={0}
                aria-valuemax={lastStudy.ideas_total}
                aria-valuenow={lastStudy.ideas_understood}
              >
                <div
                  className="h-full rounded-full bg-accent"
                  style={{ width: `${(100 * lastStudy.ideas_understood) / lastStudy.ideas_total}%` }}
                />
              </div>
              <p className="mt-1.5 text-meta text-muted">{t.ideasOf(lastStudy.ideas_understood, lastStudy.ideas_total)}</p>
            </>
          )}
          {lastStudy.next_time && <p className="mt-3 text-body text-ink">{lastStudy.next_time}</p>}
          <button
            onClick={() => navigate(sessionUrl('study', lastStudy.topic ?? undefined))}
            className="mt-4 inline-flex h-11 items-center gap-2 rounded-full bg-ink px-5 text-body text-canvas"
          >
            {t.continueCta}
            <ArrowRight size={16} aria-hidden />
          </button>
        </section>
      )}

      {/* Quick topics */}
      <section aria-labelledby="quick-title">
        <h2 id="quick-title" className="text-meta text-muted">
          {t.quickTopics}
        </h2>
        <ul className="-mx-4 mt-2 flex gap-2 overflow-x-auto px-4 pb-1">
          {TOPIC_SUGGESTIONS[language].map((topic) => (
            <li key={topic} className="shrink-0">
              <button
                onClick={() => navigate(sessionUrl('study', topic))}
                className="h-10 rounded-full border border-line-strong bg-surface px-4 text-body text-ink"
              >
                {topic}
              </button>
            </li>
          ))}
        </ul>
      </section>

      {/* Mood check-in: opens a talk session that starts from the feeling */}
      <section aria-labelledby="mood-title">
        <h2 id="mood-title" className="text-meta text-muted">
          {t.moodTitle}
        </h2>
        <ul className="mt-2 flex flex-wrap gap-2">
          {t.moods.map((m) => (
            <li key={m.id}>
              <button
                onClick={() => navigate(sessionUrl('talk', m.label))}
                className={cx('h-10 rounded-full border border-accent/40 bg-accent/5 px-4 text-body text-ink')}
              >
                {m.label}
              </button>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}

function Stat({ Icon, value, label }: { Icon: typeof Flame; value: string; label: string }) {
  return (
    <div className="min-w-0 flex-1 rounded-ui border border-line bg-surface px-3 py-3">
      <Icon size={18} aria-hidden className="text-accent" />
      <p className="mt-1.5 truncate font-display text-h3">{value}</p>
      <p className="truncate text-meta text-muted">{label}</p>
    </div>
  );
}
