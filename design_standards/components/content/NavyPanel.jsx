import React from 'react';
import { SectionLabel } from './SectionLabel.jsx';

export function NavyPanel({ label, children, credit }) {
  return (
    <div style={{ background: 'var(--surface-solid)', color: 'var(--on-solid)', padding: 'var(--panel-pad)' }}>
      <SectionLabel tone="onSolid" style={{ marginBottom: '4px' }}>{label}</SectionLabel>
      <p style={{ margin: 0, fontFamily: 'var(--font-display)', fontSize: 'var(--size-panel-verse)', lineHeight: 'var(--lh-quote)' }}>
        {children}
      </p>
      {credit ? (
        <p
          style={{
            margin: '4px 0 0',
            fontFamily: 'var(--font-label)',
            fontSize: 'var(--size-meta)',
            letterSpacing: '0.12em',
            textTransform: 'uppercase',
            color: 'var(--on-solid-label)',
          }}
        >
          {credit}
        </p>
      ) : null}
    </div>
  );
}
