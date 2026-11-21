/** Progress ("your learning journey") and Profile (language, voice, help & safety). */
import { useNavigate } from 'react-router-dom';
import { Check, Flame, HeartPulse, LifeBuoy, Lock, LogOut, Phone } from 'lucide-react';

import { useAuth } from '@/hooks/useAuth';
import { LANGUAGES } from '@/features/study/labels';
import { cx } from '@/ui/cx';
import { useStats } from './data';
import { sessionUrl } from './HomePage';
import { usePrefs, type Voice } from './prefs';
import { strings } from './strings';

export function ProgressPage() {
  const { language } = usePrefs();
  const t = strings(language);
  const navigate = useNavigate();
  const { data, isLoading } = useStats();

  return (
    <div className="space-y-7">
      <header>
        <h1 className="font-display text-h2">{t.insightsTitle}</h1>
        <p className="mt-1 flex items-start gap-1.5 text-meta text-muted">
          <Lock size={14} aria-hidden className="mt-0.5 shrink-0" />
          {t.privateNote}
        </p>
      </header>
      {isLoading && <p className="text-body text-muted">{t.loading}</p>}
      {data && (
        <>
          {/* Streak + last 14 days */}
          <section className="rounded-ui border border-line bg-surface p-5">
            <div className="flex items-center gap-3">
              <span className="flex h-12 w-12 items-center justify-center rounded-full bg-accent text-accent-on">
                <Flame size={24} aria-hidden />
              </span>
              <div>
                <p className="font-display text-h2">{t.streak(data.streak_days)}</p>
                <p className="text-meta text-muted">{t.streakLabel}</p>
              </div>
            </div>
            <p className="mt-5 text-meta text-muted">{t.last14}</p>
            <ol className="mt-2 flex justify-between gap-1" aria-label={t.last14}>
              {data.last_14_days.map((d) => (
                <li
                  key={d.day}
                  title={d.day}
                  aria-label={`${d.day}: ${d.active ? 'active' : 'no session'}`}
                  className={cx(
                    'flex aspect-square min-w-0 flex-1 items-center justify-center rounded-full',
                    d.active ? 'bg-accent text-accent-on' : 'bg-sunken',
                  )}
                >
                  {d.active && <Check size={12} aria-hidden />}
                </li>
              ))}
            </ol>
          </section>

          {/* How you've been feeling */}
          <section aria-labelledby="feeling-title" className="rounded-ui border border-line bg-surface p-5">
            <h2 id="feeling-title" className="flex items-center gap-2 font-display text-h3">
              <HeartPulse size={20} aria-hidden className="text-accent" />
              {t.feelingTitle}
            </h2>
            {data.mood ? (
              <>
                <p className="mt-2 text-body text-ink">
                  {t.feelingSummary(data.mood.common_label ? t.moodNames[data.mood.common_label] : t.moodNames.calm, data.mood.trend)}
                </p>
                <MoodChart days={data.last_14_days} names={t.moodNames} />
              </>
            ) : (
              <p className="mt-2 text-body text-muted">{t.feelingEmpty}</p>
            )}
            {data.crisis_recent && (
              <a href="tel:14416" className="mt-4 flex items-start gap-3 rounded-ui border border-accent bg-accent/10 p-3 text-body text-ink">
                <Phone size={18} aria-hidden className="mt-0.5 shrink-0 text-accent" />
                {t.helpNudge}
              </a>
            )}
          </section>

          <section className="flex gap-2">
            <Tile value={data.sessions_total} label={t.sessionsTotal} />
            <Tile value={data.topics.length} label={t.topicsLearned} />
            <Tile value={data.ideas_understood} label={t.ideasLabel} />
          </section>

          {/* Learning level per topic */}
          <section aria-labelledby="topics-title">
            <h2 id="topics-title" className="font-display text-h3">
              {t.learningTitle}
            </h2>
            <p className="mt-1 text-meta text-muted">{t.conceptsHelp}</p>
            {data.topics.length === 0 ? (
              <p className="mt-3 rounded-ui border border-dashed border-line-strong p-5 text-body text-muted">
                {t.progressEmpty}
              </p>
            ) : (
              <ul className="mt-3 space-y-2">
                {data.topics.map((tp) => {
                  const pct = tp.ideas_total ? (100 * tp.ideas_understood) / tp.ideas_total : 0;
                  return (
                    <li key={tp.topic}>
                      <button
                        onClick={() => navigate(sessionUrl('study', tp.topic))}
                        className="w-full rounded-ui border border-line bg-surface px-4 py-3 text-left"
                      >
                        <span className="flex items-center justify-between gap-3">
                          <span className="truncate text-lead text-ink">{tp.topic}</span>
                          {tp.level && <LevelBadge level={tp.level} label={t.levels[tp.level]} />}
                        </span>
                        {tp.ideas_total > 0 && (
                          <>
                            <span className="mt-2 block h-1.5 overflow-hidden rounded-full bg-sunken">
                              <span className="block h-full rounded-full bg-accent" style={{ width: `${pct}%` }} />
                            </span>
                            <span className="mt-1 block text-meta text-muted">
                              {t.ideasOf(tp.ideas_understood, tp.ideas_total)}
                            </span>
                          </>
                        )}
                      </button>
                    </li>
                  );
                })}
              </ul>
            )}
          </section>
        </>
      )}
    </div>
  );
}

/** 14 days of the buddy's gentle mood read: taller = brighter. Days without one are dots. */
function MoodChart({
  days,
  names,
}: {
  days: { day: string; mood_level: number | null; mood_label: string | null }[];
  names: Record<string, string>;
}) {
  return (
    <ol className="mt-4 flex h-24 items-end justify-between gap-1" aria-label="Mood, last 14 days">
      {days.map((d) => {
        const level = d.mood_level;
        return (
          <li
            key={d.day}
            className="flex h-full min-w-0 flex-1 flex-col items-center justify-end"
            title={level ? `${d.day}: ${names[d.mood_label ?? 'calm'] ?? d.mood_label}` : d.day}
            aria-label={level ? `${d.day}: ${names[d.mood_label ?? 'calm'] ?? d.mood_label}` : `${d.day}: none`}
          >
            {level ? (
              <span
                className={cx(
                  'w-full max-w-4 rounded-full',
                  level >= 4 ? 'bg-accent' : level >= 3 ? 'bg-line-strong' : 'bg-warn',
                )}
                style={{ height: `${20 + (level - 1) * 20}%` }}
              />
            ) : (
              <span className="h-1.5 w-1.5 rounded-full bg-line" />
            )}
          </li>
        );
      })}
    </ol>
  );
}

export function LevelBadge({ level, label }: { level: 'just_started' | 'getting_there' | 'confident'; label: string }) {
  return (
    <span
      className={cx(
        'shrink-0 rounded-full px-2.5 py-0.5 text-meta',
        level === 'confident' && 'bg-accent text-accent-on',
        level === 'getting_there' && 'bg-accent/15 text-accent',
        level === 'just_started' && 'border border-line-strong text-muted',
      )}
    >
      {label}
    </span>
  );
}

function Tile({ value, label }: { value: number; label: string }) {
  return (
    <div className="min-w-0 flex-1 rounded-ui border border-line bg-surface px-3 py-3">
      <p className="font-display text-h2">{value}</p>
      <p className="truncate text-meta text-muted">{label}</p>
    </div>
  );
}

export function ProfilePage() {
  const { user, logout } = useAuth();
  const { language, voice, setLanguage, setVoice } = usePrefs();
  const t = strings(language);
  const navigate = useNavigate();
  const voices: Voice[] = ['kavya', 'shubh'];

  return (
    <div className="space-y-7">
      <header className="flex items-center gap-4">
        <span className="flex h-16 w-16 items-center justify-center rounded-full bg-accent font-display text-h2 text-accent-on">
          {(user?.name?.[0] || 'S').toUpperCase()}
        </span>
        <div className="min-w-0">
          <h1 className="truncate font-display text-h2">{user?.name}</h1>
          <p className="truncate text-body text-muted">{user?.email}</p>
        </div>
      </header>

      <Choice
        title={t.language}
        options={LANGUAGES.map((l) => ({ id: l.code, label: l.label }))}
        value={language}
        onChange={(v) => setLanguage(v as typeof language)}
      />
      <Choice
        title={t.voice}
        options={voices.map((v) => ({ id: v, label: t.voices[v] }))}
        value={voice}
        onChange={(v) => setVoice(v as Voice)}
      />

      <section aria-labelledby="help-title" className="rounded-ui border border-accent/40 bg-accent/5 p-5">
        <h2 id="help-title" className="flex items-center gap-2 font-display text-h3">
          <LifeBuoy size={20} aria-hidden className="text-accent" />
          {t.helpTitle}
        </h2>
        <p className="mt-2 text-body text-ink">{t.helpBody}</p>
        <a
          href="tel:14416"
          className="mt-4 inline-flex h-11 items-center gap-2 rounded-full bg-accent px-5 text-body text-accent-on"
        >
          <Phone size={16} aria-hidden />
          {t.helpCall}
        </a>
      </section>

      <button
        onClick={async () => {
          await logout();
          navigate('/login');
        }}
        className="inline-flex h-11 items-center gap-2 rounded-full border border-line-strong px-5 text-body text-ink"
      >
        <LogOut size={16} aria-hidden />
        {t.signOut}
      </button>
    </div>
  );
}

function Choice({
  title,
  options,
  value,
  onChange,
}: {
  title: string;
  options: { id: string; label: string }[];
  value: string;
  onChange: (id: string) => void;
}) {
  return (
    <fieldset>
      <legend className="text-meta text-muted">{title}</legend>
      <div role="radiogroup" className="mt-2 divide-y divide-line rounded-ui border border-line bg-surface">
        {options.map((o) => (
          <button
            key={o.id}
            role="radio"
            aria-checked={value === o.id}
            onClick={() => onChange(o.id)}
            className="flex w-full items-center justify-between px-4 py-3.5 text-left text-lead"
          >
            <span className={value === o.id ? 'text-ink' : 'text-muted'}>{o.label}</span>
            {value === o.id && <Check size={18} aria-hidden className="text-accent" />}
          </button>
        ))}
      </div>
    </fieldset>
  );
}
