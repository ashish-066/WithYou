/**
 * Your garden: one plant per topic. A leaf for every concept (filled once
 * understood, an outline while still growing), the stem grows with the
 * learning level, and a flower opens when the whole topic is understood.
 * Tap a plant to study that topic again.
 */
import { useNavigate } from 'react-router-dom';

import type { Level } from '@/services/api';
import { sessionUrl } from './HomePage';

const ink = 'rgb(var(--c-ink))';
const green = 'rgb(var(--c-accent))';
const paper = 'rgb(var(--c-surface))';
const turmeric = 'rgb(var(--c-turmeric))';
const terracotta = 'rgb(var(--c-terracotta))';

type Topic = { topic: string; ideas_understood: number; ideas_total: number; level: Level | null };

export function Plant({ understood, total, level }: { understood: number; total: number; level: Level | null }) {
  const leaves = Math.max(1, Math.min(total || 1, 6));
  const done = total > 0 && understood >= total;
  // Stem height: sprout -> growing -> tall
  const height = level === 'confident' || done ? 74 : level === 'getting_there' ? 60 : 46;
  const top = 100 - height;
  const slots = Array.from({ length: leaves }, (_, i) => {
    const y = 96 - ((i + 1) * (height - 10)) / (leaves + 0.6);
    const left = i % 2 === 0;
    return { y, left, filled: i < understood };
  });
  return (
    <svg viewBox="0 0 100 140" width="100%" height="120" role="img" aria-hidden>
      {/* stem */}
      <path
        d={`M50 100 C48 ${100 - height * 0.4} 53 ${100 - height * 0.7} 50 ${top}`}
        style={{ fill: 'none', stroke: ink, strokeWidth: 3, strokeLinecap: 'round' }}
      />
      {/* leaves: one per concept */}
      {slots.map((s, i) =>
        s.left ? (
          <path
            key={i}
            d={`M50 ${s.y} C40 ${s.y - 12} 26 ${s.y - 10} 22 ${s.y - 4} C30 ${s.y + 4} 42 ${s.y + 4} 50 ${s.y} Z`}
            style={{ fill: s.filled ? green : paper, stroke: ink, strokeWidth: 2.2, strokeLinejoin: 'round' }}
          />
        ) : (
          <path
            key={i}
            d={`M50 ${s.y} C60 ${s.y - 12} 74 ${s.y - 10} 78 ${s.y - 4} C70 ${s.y + 4} 58 ${s.y + 4} 50 ${s.y} Z`}
            style={{ fill: s.filled ? green : paper, stroke: ink, strokeWidth: 2.2, strokeLinejoin: 'round' }}
          />
        ),
      )}
      {/* flower when the whole topic is understood, a bud otherwise */}
      {done ? (
        <g style={{ animation: 'buddy-bob 3s ease-in-out infinite' }}>
          {[0, 72, 144, 216, 288].map((a) => (
            <ellipse
              key={a}
              cx="50"
              cy={top - 9}
              rx="6"
              ry="9"
              transform={`rotate(${a} 50 ${top})`}
              style={{ fill: turmeric, stroke: ink, strokeWidth: 2 }}
            />
          ))}
          <circle cx="50" cy={top} r="5.5" style={{ fill: terracotta, stroke: ink, strokeWidth: 2 }} />
        </g>
      ) : (
        <ellipse cx="50" cy={top - 3} rx="4.5" ry="6" style={{ fill: green, stroke: ink, strokeWidth: 2 }} />
      )}
      {/* pot */}
      <path d="M30 100 L70 100 L65 132 L35 132 Z" style={{ fill: terracotta, stroke: ink, strokeWidth: 2.5, strokeLinejoin: 'round' }} />
      <path d="M27 96 L73 96 L73 104 L27 104 Z" style={{ fill: terracotta, stroke: ink, strokeWidth: 2.5, strokeLinejoin: 'round' }} />
    </svg>
  );
}

export function Garden({
  topics,
  ideasOf,
  levels,
}: {
  topics: Topic[];
  ideasOf: (understood: number, total: number) => string;
  levels: Record<Level, string>;
}) {
  const navigate = useNavigate();
  return (
    <ul className="mt-3 grid grid-cols-2 gap-3">
      {topics.map((tp) => (
        <li key={tp.topic}>
          <button
            onClick={() => navigate(sessionUrl('study', tp.topic))}
            className="sketch-soft flex w-full flex-col items-center bg-surface px-2 pb-3 pt-2 text-center"
          >
            <Plant understood={tp.ideas_understood} total={tp.ideas_total} level={tp.level} />
            <span className="mt-1 line-clamp-2 break-words font-display text-lead font-bold leading-snug text-ink">{tp.topic}</span>
            {tp.ideas_total > 0 && <span className="mt-1 text-meta text-muted">{ideasOf(tp.ideas_understood, tp.ideas_total)}</span>}
            {tp.level && <span className="mt-0.5 text-meta font-semibold text-accent">{levels[tp.level]}</span>}
          </button>
        </li>
      ))}
    </ul>
  );
}
