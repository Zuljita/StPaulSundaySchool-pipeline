import React from 'react';

export function SheetFooter({ left, right, credit }) {
  const line = (
    <div style={{ display: 'flex', justifyContent: 'space-between', gap: '16px', textTransform: 'uppercase' }}>
      <span>{left}</span>
      <span>{right}</span>
    </div>
  );
  return (
    <footer
      style={{
        borderTop: 'var(--rule-hair) solid var(--border-hairline)',
        marginTop: 'auto',
        paddingTop: '7px',
        display: 'grid',
        gap: credit ? '6px' : 0,
        fontFamily: 'var(--font-label)',
        fontSize: 'var(--size-meta)',
        lineHeight: 1.5,
        letterSpacing: '0.06em',
        color: 'var(--text-meta)',
      }}
    >
      {line}
      {credit ? (
        <p style={{ margin: 0, fontSize: 'var(--size-credit)', letterSpacing: 'var(--track-credit)', lineHeight: 1.5 }}>{credit}</p>
      ) : null}
    </footer>
  );
}
