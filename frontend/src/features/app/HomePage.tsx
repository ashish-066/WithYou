/**
 * Home, as a notebook page: the buddy greets you in a speech bubble, your
 * streak is a margin note, the two ways to start are drawn boxes, "pick up where
 * you left off" is a taped sticky note, and topics / moods are drawn chips.
 * Everything comes from the learner's own history (suggestions, stats).
 */
import { Link, useNavigate } from 'react-router-dom';
import { ArrowRight, BookOpen, Flame, MessageCircleHeart } from 'lucide-react';

import { useAuth } from '@/hooks/useAuth';
import { cx } from '@/ui/cx';
import { Buddy } from './Buddy';
import { useSessions, useStats, useSuggestions } from './data';
import { MarginNote, Scribble, SpeechBubble, StickyNote } from './notebook';
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
  const suggestions = useSuggestions();
  const firstName = (user?.name || '').split(' ')[0];

  const lastStudy = sessions.data?.sessions.find((s) => s.mode === 'study' && s.topic);
  const open = suggestions.data?.continue[0];
  const resume = open
    ? {
        topic: open.topic,
        understood: open.ideas_understood,
        total: open.ideas_total,
        note: open.next_concept ? t.continueNext(open.next_concept) : null,
      }
    : lastStudy
      ? { topic: lastStudy.topic!, understood: lastStudy.ideas_understood, total: lastStudy.ideas_total, note: lastStudy.next_time }
      : null;
  const personal = [
    ...(suggestions.data?.continue.slice(1).map((c) => c.topic) ?? []),
    ...(suggestions.data?.next_topics ?? []),
  ].filter((v, i, a) => v && a.indexOf(v) === i);
  const quick = personal.length ? personal.slice(0, 8) : TOPIC_SUGGESTIONS[language];

  return (
    <div className="space-y-8">
      {/* date + me */}
      <header className="flex items-center justify-between">
        <MarginNote>
          {new Date().toLocaleDateString(language, { weekday: 'long', day: 'numeric', month: 'long' })}
        </MarginNote>
        <Link
          to="/me"
          aria-label={t.nav.profile}
          className="sketch flex h-11 w-11 items-center justify-center bg-turmeric-soft font-display text-lead font-bold text-ink"
        >
          {(firstName[0] || 'S').toUpperCase()}
        </Link>
      </header>

      {/* the buddy says hello */}
      <section className="flex items-end gap-2">
        <Buddy mood="happy" size={112} className="-mb-1 shrink-0" />
        <SpeechBubble className="mb-10 min-w-0 flex-1">
          <p className="font-display text-h3 font-bold leading-tight">{t.greet(partOfDay(), firstName)}!</p>
          <p className="mt-0.5 text-lead text-muted">{t.heroAsk}</p>
        </SpeechBubble>
      </section>

      {stats.data && stats.data.sessions_total > 0 && (
        <p className="-mt-4 flex items-start gap-2 text-body text-ink">
          <Flame size={18} aria-hidden className="mt-0.5 shrink-0 text-terracotta" />
          {t.streakLine(stats.data.streak_days, stats.data.sessions_this_week, stats.data.ideas_understood)}
        </p>
      )}

      {/* two ways to start: drawn boxes */}
      <section className="space-y-4">
        <button
          onClick={() => navigate('/learn')}
          className="sketch group flex w-full items-center gap-4 bg-accent px-5 py-5 text-left text-accent-on transition-transform active:translate-y-0.5"
        >
          <BookOpen size={34} aria-hidden className="shrink-0" />
          <span className="min-w-0 flex-1">
            <span className="block font-display text-h3 font-bold">{t.studyTitle}</span>
            <span className="block text-body opacity-90">{t.studyBody}</span>
          </span>
          <ArrowRight size={22} aria-hidden className="shrink-0 transition-transform group-hover:translate-x-1" />
        </button>
        <button
          onClick={() => navigate(sessionUrl('talk'))}
          className="sketch group flex w-full items-center gap-4 bg-surface px-5 py-5 text-left text-ink transition-transform active:translate-y-0.5"
        >
          <MessageCircleHeart size={34} aria-hidden className="shrink-0 text-terracotta" />
          <span className="min-w-0 flex-1">
            <span className="block font-display text-h3 font-bold">{t.talkTitle}</span>
            <span className="block text-body text-muted">{t.talkBody}</span>
          </span>
          <ArrowRight size={22} aria-hidden className="shrink-0 transition-transform group-hover:translate-x-1" />
        </button>
      </section>

      {/* pick up where you left off: a sticky note */}
      {resume && (
        <section aria-labelledby="continue-title" className="px-1 pt-2">
          <StickyNote tilt={-1.2}>
            <h2 id="continue-title" className="font-hand text-[22px] leading-6 text-terracotta">
              {t.continueTitle}
            </h2>
            <p className="mt-1 font-display text-h3 font-bold text-ink">{resume.topic}</p>
            {resume.total > 0 && (
              <div className="mt-2 flex items-center gap-2">
                <span className="flex gap-1.5" aria-label={t.ideasOf(resume.understood, resume.total)}>
                  {Array.from({ length: resume.total }, (_, i) => (
                    <span
                      key={i}
                      className={cx(
                        'h-3.5 w-3.5 rounded-full border-2 border-ink/80',
                        i < resume.understood ? 'bg-accent' : 'bg-transparent',
                      )}
                    />
                  ))}
                </span>
                <span className="text-meta text-muted">{t.ideasOf(resume.understood, resume.total)}</span>
              </div>
            )}
            {resume.note && <p className="mt-2 text-body text-ink">{resume.note}</p>}
            <button
              onClick={() => navigate(sessionUrl('study', resume.topic))}
              className="mt-4 inline-flex items-center gap-1.5 font-display text-lead font-bold text-accent underline decoration-2 underline-offset-4"
            >
              {t.continueCta}
              <ArrowRight size={18} aria-hidden />
            </button>
          </StickyNote>
        </section>
      )}

      {/* for you */}
      <section aria-labelledby="quick-title">
        <h2 id="quick-title" className="font-display text-h3 font-bold">
          <Scribble>{personal.length ? t.forYou : t.quickTopics}</Scribble>
        </h2>
        <ul className="mt-4 flex flex-wrap gap-2.5">
          {quick.map((topic, i) => (
            <li key={topic}>
              <button
                onClick={() => navigate(sessionUrl('study', topic))}
                className="sketch-soft bg-surface px-4 py-2 text-body text-ink transition-transform hover:-rotate-1"
                style={{ transform: `rotate(${(i % 3) - 1}deg)` }}
              >
                {topic}
              </button>
            </li>
          ))}
        </ul>
      </section>

      {/* mood check-in */}
      <section aria-labelledby="mood-title">
        <h2 id="mood-title" className="font-display text-h3 font-bold">
          <Scribble color="terracotta">{t.moodTitle}</Scribble>
        </h2>
        <ul className="mt-4 flex flex-wrap gap-2.5">
          {t.moods.map((m) => (
            <li key={m.id}>
              <button
                onClick={() => navigate(sessionUrl('talk', m.label))}
                className="sketch-soft bg-turmeric-soft px-4 py-2 text-body text-ink transition-transform hover:rotate-1"
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
