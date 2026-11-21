/**
 * ProblemStatement — renders the DSA problem description, constraints,
 * difficulty badge, and public test cases.
 *
 * Candidate-safe: only receives DSAProblemPublic (no reference solution).
 */

import type { DSAProblemPublic, DSATestCase } from '../types';

interface ProblemStatementProps {
  problem: DSAProblemPublic;
}

const DIFFICULTY_COLORS: Record<string, string> = {
  easy: '#00d4a0',
  medium: '#f59e0b',
  hard: '#ef4444',
};

function TestCaseBlock({ tc, index }: { tc: DSATestCase; index: number }) {
  return (
    <div
      style={{
        background: 'rgba(255,255,255,0.04)',
        border: '1px solid rgba(255,255,255,0.08)',
        borderRadius: '8px',
        padding: '10px 14px',
        marginTop: '8px',
        fontFamily: 'monospace',
        fontSize: '12px',
      }}
    >
      <div style={{ color: '#94a3b8', marginBottom: '4px', fontFamily: 'inherit' }}>
        Example {index + 1}{tc.description ? ` — ${tc.description}` : ''}
      </div>
      <div>
        <span style={{ color: '#64748b' }}>Input: </span>
        <span style={{ color: '#e2e8f0' }}>{tc.input}</span>
      </div>
      <div>
        <span style={{ color: '#64748b' }}>Output: </span>
        <span style={{ color: '#00d4a0' }}>{tc.expected_output}</span>
      </div>
    </div>
  );
}

export function ProblemStatement({ problem }: ProblemStatementProps) {
  const diffColor = DIFFICULTY_COLORS[problem.difficulty] || '#94a3b8';

  return (
    <div
      id="dsa-problem-statement"
      style={{
        height: '100%',
        overflowY: 'auto',
        padding: '20px',
        color: '#e2e8f0',
        fontFamily: "'Inter', sans-serif",
        fontSize: '14px',
        lineHeight: '1.7',
      }}
    >
      {/* Title row */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '16px' }}>
        <h2 style={{ margin: 0, fontSize: '18px', fontWeight: 700, color: '#f8fafc' }}>
          {problem.title}
        </h2>
        <span
          style={{
            fontSize: '11px',
            fontWeight: 600,
            textTransform: 'uppercase',
            letterSpacing: '0.05em',
            color: diffColor,
            border: `1px solid ${diffColor}40`,
            padding: '2px 8px',
            borderRadius: '12px',
            background: `${diffColor}15`,
          }}
        >
          {problem.difficulty}
        </span>
      </div>

      {/* Tags */}
      {problem.tags.length > 0 && (
        <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap', marginBottom: '16px' }}>
          {problem.tags.map((tag) => (
            <span
              key={tag}
              style={{
                fontSize: '11px',
                color: '#94a3b8',
                background: 'rgba(148,163,184,0.1)',
                border: '1px solid rgba(148,163,184,0.2)',
                borderRadius: '4px',
                padding: '2px 8px',
              }}
            >
              {tag}
            </span>
          ))}
        </div>
      )}

      {/* Problem statement */}
      <div style={{ marginBottom: '20px', color: '#cbd5e1', whiteSpace: 'pre-wrap' }}>
        {problem.statement}
      </div>

      {/* Constraints */}
      {problem.constraints.length > 0 && (
        <div style={{ marginBottom: '20px' }}>
          <h3 style={{ fontSize: '13px', fontWeight: 600, color: '#94a3b8', marginBottom: '8px', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
            Constraints
          </h3>
          <ul style={{ margin: 0, paddingLeft: '18px', color: '#94a3b8' }}>
            {problem.constraints.map((c, i) => (
              <li key={i} style={{ marginBottom: '2px', fontFamily: 'monospace', fontSize: '12px' }}>
                {c}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Examples */}
      {problem.public_test_cases.length > 0 && (
        <div>
          <h3 style={{ fontSize: '13px', fontWeight: 600, color: '#94a3b8', marginBottom: '8px', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
            Examples
          </h3>
          {problem.public_test_cases.map((tc, i) => (
            <TestCaseBlock key={i} tc={tc} index={i} />
          ))}
        </div>
      )}
    </div>
  );
}
