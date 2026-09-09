import React from 'react';

export function SectionLabel({ children, tone = 'blue', size = 'default', style }) {
  const color = tone === 'onSolid' ? 'var(--on-solid-label)' : tone === 'law' ? 'var(--rule-law)' : 'var(--text-label)';
  return (
    <h2
      style={{
        margin: '0 0 5px',
        fontFamily: 'var(--font-label)',
        fontSize: size === 'small' ? 'var(--size-meta)' : 'var(--size-label)',
        fontWeight: 'var(--weight-label)',
        letterSpacing: 'var(--track-label)',
        textTransform: 'uppercase',
        color,
        ...style,
      }}
    >
      {children}
    </h2>
  );
}
