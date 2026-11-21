/**
 * The buddy: a small hand-drawn leaf-green friend with a turmeric scarf and a
 * sprout on its head. Its face shows what it's doing, so the app feels like a
 * someone, not a dashboard:
 *   happy      ^ ^ eyes, wide smile (greetings, celebrating)
 *   listening  big round eyes, small "o" (the learner is talking)
 *   thinking   eyes up and to the side, thought dots
 *   speaking   mouth moving
 *   caring     soft closed eyes, gentle smile, a little heart (just talk)
 *   wave       happy + one arm waving (login, hello)
 * Colours come from the notebook tokens; motion respects reduced-motion.
 */
import type { CSSProperties } from 'react';

export type BuddyMood = 'happy' | 'listening' | 'thinking' | 'speaking' | 'caring' | 'wave';

const ink = 'rgb(var(--c-ink))';
const green = 'rgb(var(--c-accent))';
const paper = 'rgb(var(--c-surface))';
const turmeric = 'rgb(var(--c-turmeric))';
const terracotta = 'rgb(var(--c-terracotta))';

const S = (style: CSSProperties) => style;

export function Buddy({ mood = 'happy', size = 140, className }: { mood?: BuddyMood; size?: number; className?: string }) {
  const happyEyes = mood === 'happy' || mood === 'wave';
  return (
    <svg
      viewBox="0 0 140 150"
      width={size}
      height={(size * 150) / 140}
      className={className}
      role="img"
      aria-label="Your study buddy"
      style={{ overflow: 'visible' }}
    >
      {/* ground shadow */}
      <ellipse cx="70" cy="142" rx="38" ry="6" style={S({ fill: ink, opacity: 0.1 })} />

      <g style={{ animation: 'buddy-bob 3.2s ease-in-out infinite', transformOrigin: '70px 140px' }}>
        {/* sprout */}
        <path d="M70 30 C70 22 70 16 71 10" style={S({ fill: 'none', stroke: ink, strokeWidth: 3, strokeLinecap: 'round' })} />
        <path
          d="M71 12 C80 2 94 4 96 10 C88 16 78 17 71 12 Z"
          style={S({ fill: green, stroke: ink, strokeWidth: 2.5, strokeLinejoin: 'round' })}
        />
        <path
          d="M70 16 C62 8 50 9 48 14 C55 19 64 20 70 16 Z"
          style={S({ fill: green, stroke: ink, strokeWidth: 2.5, strokeLinejoin: 'round', opacity: 0.85 })}
        />

        {/* arms (behind the body) */}
        <path d="M24 92 C14 96 12 106 18 110" style={S({ fill: 'none', stroke: ink, strokeWidth: 3.5, strokeLinecap: 'round' })} />
        {mood === 'wave' ? (
          <g style={{ animation: 'buddy-wave 1.2s ease-in-out infinite', transformOrigin: '112px 86px' }}>
            <path d="M112 86 C124 76 128 64 124 54" style={S({ fill: 'none', stroke: ink, strokeWidth: 3.5, strokeLinecap: 'round' })} />
          </g>
        ) : (
          <path d="M116 92 C126 96 128 106 122 110" style={S({ fill: 'none', stroke: ink, strokeWidth: 3.5, strokeLinecap: 'round' })} />
        )}

        {/* body: a slightly lopsided round shape (drawn, not perfect) */}
        <path
          d="M70 28 C102 27 121 50 120 82 C119 114 98 136 69 136 C40 136 19 115 20 83 C21 51 39 29 70 28 Z"
          style={S({ fill: green, stroke: ink, strokeWidth: 3, strokeLinejoin: 'round' })}
        />
        {/* belly */}
        <path
          d="M70 92 C88 92 98 104 96 118 C93 129 82 133 70 133 C57 133 46 128 44 118 C42 104 52 92 70 92 Z"
          style={S({ fill: paper, opacity: 0.22 })}
        />

        {/* scarf */}
        <path
          d="M30 98 C50 108 90 108 110 98 L108 108 C88 117 52 117 32 108 Z"
          style={S({ fill: turmeric, stroke: ink, strokeWidth: 2.5, strokeLinejoin: 'round' })}
        />
        <path
          d="M88 108 L94 126 L84 124 L80 109"
          style={S({ fill: turmeric, stroke: ink, strokeWidth: 2.5, strokeLinejoin: 'round' })}
        />

        {/* cheeks */}
        <ellipse cx="44" cy="80" rx="7" ry="4.5" style={S({ fill: terracotta, opacity: 0.45 })} />
        <ellipse cx="96" cy="80" rx="7" ry="4.5" style={S({ fill: terracotta, opacity: 0.45 })} />

        {/* eyes */}
        {happyEyes && (
          <>
            <path d="M46 68 Q52 60 58 68" style={S({ fill: 'none', stroke: ink, strokeWidth: 3.5, strokeLinecap: 'round' })} />
            <path d="M82 68 Q88 60 94 68" style={S({ fill: 'none', stroke: ink, strokeWidth: 3.5, strokeLinecap: 'round' })} />
          </>
        )}
        {mood === 'caring' && (
          <>
            <path d="M46 67 Q52 72 58 67" style={S({ fill: 'none', stroke: ink, strokeWidth: 3.5, strokeLinecap: 'round' })} />
            <path d="M82 67 Q88 72 94 67" style={S({ fill: 'none', stroke: ink, strokeWidth: 3.5, strokeLinecap: 'round' })} />
          </>
        )}
        {(mood === 'listening' || mood === 'speaking') && (
          <g style={{ animation: 'buddy-blink 4s infinite', transformOrigin: '70px 66px' }}>
            <ellipse cx="52" cy="66" rx={mood === 'listening' ? 6.5 : 5.5} ry={mood === 'listening' ? 8 : 7} style={S({ fill: ink })} />
            <ellipse cx="88" cy="66" rx={mood === 'listening' ? 6.5 : 5.5} ry={mood === 'listening' ? 8 : 7} style={S({ fill: ink })} />
            <circle cx="54.5" cy="62.5" r="2.2" style={S({ fill: paper })} />
            <circle cx="90.5" cy="62.5" r="2.2" style={S({ fill: paper })} />
          </g>
        )}
        {mood === 'thinking' && (
          <>
            <ellipse cx="56" cy="62" rx="5" ry="6.5" style={S({ fill: ink })} />
            <ellipse cx="92" cy="62" rx="5" ry="6.5" style={S({ fill: ink })} />
            <circle cx="57.5" cy="59" r="1.8" style={S({ fill: paper })} />
            <circle cx="93.5" cy="59" r="1.8" style={S({ fill: paper })} />
            {/* thought dots */}
            <circle cx="114" cy="40" r="3" style={S({ fill: ink, opacity: 0.55 })} />
            <circle cx="122" cy="30" r="4" style={S({ fill: ink, opacity: 0.45 })} />
            <circle cx="132" cy="18" r="5.5" style={S({ fill: ink, opacity: 0.35 })} />
          </>
        )}

        {/* mouth */}
        {(mood === 'happy' || mood === 'wave') && (
          <path
            d="M58 84 Q70 98 82 84 Q70 90 58 84 Z"
            style={S({ fill: ink, stroke: ink, strokeWidth: 2.5, strokeLinejoin: 'round' })}
          />
        )}
        {mood === 'caring' && (
          <path d="M60 85 Q70 92 80 85" style={S({ fill: 'none', stroke: ink, strokeWidth: 3, strokeLinecap: 'round' })} />
        )}
        {mood === 'listening' && <ellipse cx="70" cy="87" rx="4" ry="4.5" style={S({ fill: ink })} />}
        {mood === 'thinking' && (
          <path d="M62 88 Q66 85 70 88 T78 88" style={S({ fill: 'none', stroke: ink, strokeWidth: 3, strokeLinecap: 'round' })} />
        )}
        {mood === 'speaking' && (
          <ellipse
            cx="70"
            cy="87"
            rx="8"
            ry="6"
            style={{ fill: ink, animation: 'buddy-talk 0.32s ease-in-out infinite', transformOrigin: '70px 87px' }}
          />
        )}

        {/* a little heart when caring */}
        {mood === 'caring' && (
          <path
            d="M118 44 C118 38 126 37 127 43 C128 37 136 38 136 44 C136 51 127 55 127 57 C127 55 118 51 118 44 Z"
            style={{ fill: terracotta, stroke: ink, strokeWidth: 2, animation: 'buddy-bob 2s ease-in-out infinite' }}
          />
        )}
      </g>
    </svg>
  );
}
