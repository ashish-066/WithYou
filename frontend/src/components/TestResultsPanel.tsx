/**
 * TestResultsPanel — displays code execution results from the sandbox.
 *
 * Shows pass/fail per test case with input, expected output, actual output,
 * error messages, and runtime. Derives correctness from execution results only
 * (never from AI inference).
 */

import type { DSAExecutionResult } from '../types';

interface TestResultsPanelProps {
  result: DSAExecutionResult | null;
  isRunning: boolean;
}

function PassBadge({ passed }: { passed: boolean }) {
  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: '4px',
        fontSize: '11px',
        fontWeight: 600,
        padding: '2px 8px',
        borderRadius: '12px',
        background: passed ? 'rgba(0,212,160,0.15)' : 'rgba(239,68,68,0.15)',
        color: passed ? '#00d4a0' : '#f87171',
        border: `1px solid ${passed ? 'rgba(0,212,160,0.3)' : 'rgba(239,68,68,0.3)'}`,
      }}
    >
      {passed ? '✓ Passed' : '✗ Failed'}
    </span>
  );
}

function SummaryBar({ result }: { result: DSAExecutionResult }) {
  const pct = result.tests_total > 0
    ? Math.round((result.tests_passed / result.tests_total) * 100)
    : 0;
  const color = pct === 100 ? '#00d4a0' : pct > 50 ? '#f59e0b' : '#ef4444';

  return (
    <div
      id="dsa-test-summary"
      style={{
        padding: '14px 16px',
        borderBottom: '1px solid rgba(255,255,255,0.07)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
        <span style={{ fontSize: '22px', fontWeight: 700, color }}>
          {result.tests_passed}/{result.tests_total}
        </span>
        <span style={{ fontSize: '12px', color: '#64748b' }}>tests passed</span>
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: '16px', fontSize: '12px', color: '#64748b' }}>
        {result.timed_out && (
          <span style={{ color: '#f87171' }}>⏱ Timed out</span>
        )}
        {result.total_runtime_ms > 0 && !result.timed_out && (
          <span>{result.total_runtime_ms.toFixed(0)}ms</span>
        )}
        <span
          style={{
            fontWeight: 600,
            fontSize: '13px',
            color,
          }}
        >
          {pct}%
        </span>
      </div>
    </div>
  );
}

export function TestResultsPanel({ result, isRunning }: TestResultsPanelProps) {
  const containerStyle: React.CSSProperties = {
    height: '100%',
    display: 'flex',
    flexDirection: 'column',
    background: '#0f1117',
    fontFamily: "'Inter', sans-serif",
    fontSize: '13px',
    color: '#e2e8f0',
    overflow: 'hidden',
  };

  if (isRunning) {
    return (
      <div style={{ ...containerStyle, alignItems: 'center', justifyContent: 'center', gap: '12px' }}>
        <div
          style={{
            width: '24px',
            height: '24px',
            border: '2px solid rgba(0,212,160,0.2)',
            borderTopColor: '#00d4a0',
            borderRadius: '50%',
            animation: 'spin 0.8s linear infinite',
          }}
        />
        <span style={{ color: '#64748b', fontSize: '12px' }}>Running code…</span>
      </div>
    );
  }

  if (!result) {
    return (
      <div style={{ ...containerStyle, alignItems: 'center', justifyContent: 'center' }}>
        <div style={{ textAlign: 'center', color: '#475569' }}>
          <div style={{ fontSize: '32px', marginBottom: '8px' }}>▷</div>
          <div style={{ fontSize: '13px' }}>Click <strong style={{ color: '#94a3b8' }}>Run Code</strong> to test your solution</div>
        </div>
      </div>
    );
  }

  // Compilation / system error
  if (result.compilation_error) {
    return (
      <div style={containerStyle}>
        <SummaryBar result={result} />
        <div style={{ padding: '16px', flex: 1, overflow: 'auto' }}>
          <div style={{ color: '#f87171', fontWeight: 600, marginBottom: '8px' }}>
            Compilation Error
          </div>
          <pre
            style={{
              margin: 0,
              fontFamily: 'monospace',
              fontSize: '12px',
              color: '#fca5a5',
              background: 'rgba(239,68,68,0.08)',
              border: '1px solid rgba(239,68,68,0.2)',
              borderRadius: '6px',
              padding: '12px',
              overflowX: 'auto',
              whiteSpace: 'pre-wrap',
            }}
          >
            {result.compilation_error}
          </pre>
        </div>
      </div>
    );
  }

  return (
    <div style={containerStyle}>
      <SummaryBar result={result} />
      <div style={{ flex: 1, overflowY: 'auto', padding: '12px 16px' }}>
        {result.test_results.map((tr, i) => (
          <div
            key={i}
            id={`test-case-${i}`}
            style={{
              marginBottom: '10px',
              border: `1px solid ${tr.passed ? 'rgba(0,212,160,0.15)' : 'rgba(239,68,68,0.2)'}`,
              borderRadius: '8px',
              background: tr.passed ? 'rgba(0,212,160,0.04)' : 'rgba(239,68,68,0.04)',
              overflow: 'hidden',
            }}
          >
            {/* Test case header */}
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                padding: '8px 12px',
                borderBottom: `1px solid ${tr.passed ? 'rgba(0,212,160,0.1)' : 'rgba(239,68,68,0.1)'}`,
              }}
            >
              <span style={{ fontSize: '12px', color: '#94a3b8' }}>
                Test {i + 1}{tr.description ? ` — ${tr.description}` : ''}
              </span>
              <PassBadge passed={tr.passed} />
            </div>

            {/* Test case detail */}
            <div style={{ padding: '10px 12px', display: 'grid', gap: '6px', fontFamily: 'monospace', fontSize: '11px' }}>
              <div>
                <span style={{ color: '#64748b' }}>Input: </span>
                <span style={{ color: '#cbd5e1' }}>{tr.input}</span>
              </div>
              <div>
                <span style={{ color: '#64748b' }}>Expected: </span>
                <span style={{ color: '#00d4a0' }}>{tr.expected_output}</span>
              </div>
              <div>
                <span style={{ color: '#64748b' }}>Got: </span>
                <span style={{ color: tr.passed ? '#00d4a0' : '#f87171' }}>
                  {tr.actual_output || '(empty)'}
                </span>
              </div>
              {tr.error && (
                <div>
                  <span style={{ color: '#64748b' }}>Error: </span>
                  <span style={{ color: '#fca5a5' }}>{tr.error}</span>
                </div>
              )}
              {tr.runtime_ms > 0 && (
                <div style={{ color: '#475569' }}>
                  {tr.runtime_ms.toFixed(1)}ms
                </div>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
