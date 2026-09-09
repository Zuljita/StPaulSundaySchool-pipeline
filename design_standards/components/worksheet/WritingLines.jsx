import React from 'react';

export function WritingLines({ count, numbered = false, height = 'var(--writing-height)' }) {
  const rows = Array.from({ length: count }, (_, i) => i + 1);
  return (
    <div style={{ display: 'grid', gap: 'var(--writing-gap)' }}>
      {rows.map((i) =>
        numbered ? (
          <div key={i} style={{ display: 'flex', alignItems: 'baseline', gap: '7px' }}>
            <span style={{ fontFamily: 'var(--font-label)', fontSize: 'var(--size-chip-sm)', color: 'var(--text-meta)' }}>{i}</span>
            <span style={{ flex: 1, borderBottom: 'var(--rule-hair) solid var(--rule-writing)', height }} />
          </div>
        ) : (
          <span key={i} style={{ borderBottom: 'var(--rule-hair) solid var(--rule-writing)', height }} />
        )
      )}
    </div>
  );
}
