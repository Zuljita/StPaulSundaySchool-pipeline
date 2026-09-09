import React from 'react';

export function LessonStep({ n, minutes, children, texts }) {
  return (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: 'var(--step-minute-col) 1fr',
        gap: 'var(--step-gutter)',
        alignItems: 'start',
        borderTop: 'var(--rule-hair) solid var(--border-hairline-soft)',
        paddingTop: '6px',
      }}
    >
      <p
        style={{
          margin: 0,
          fontFamily: 'var(--font-label)',
          fontSize: 'var(--size-label)',
          fontWeight: 'var(--weight-label)',
          letterSpacing: 'var(--track-meta)',
          textTransform: 'uppercase',
          color: 'var(--text-label)',
        }}
      >
        {n} · {minutes} min
      </p>
      <div>
        <p style={{ margin: texts ? '0 0 6px' : 0, fontSize: 'var(--size-body-lead)', lineHeight: 'var(--lh-body-tight)' }}>{children}</p>
        {texts || null}
      </div>
    </div>
  );
}
