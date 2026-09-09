import React from 'react';
import { SectionLabel } from './SectionLabel.jsx';

export function TintPanel({ items, accent = false }) {
  return (
    <div
      style={{
        background: 'var(--surface-tint)',
        padding: 'var(--tint-pad)',
        display: 'grid',
        gap: '5px',
        borderTop: accent ? 'var(--rule-heavy) solid var(--rule-gospel)' : undefined,
      }}
    >
      {items.map((it) => (
        <div key={it.label}>
          <SectionLabel size="small" style={{ marginBottom: '2px', letterSpacing: '0.12em' }}>{it.label}</SectionLabel>
          <p style={{ margin: 0, fontSize: 'var(--size-scripture-sm)', lineHeight: 'var(--lh-body-tight)' }}>{it.text}</p>
        </div>
      ))}
    </div>
  );
}
