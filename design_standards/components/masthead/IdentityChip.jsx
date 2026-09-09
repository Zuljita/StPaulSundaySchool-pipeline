import React from 'react';

export function IdentityChip({ children, size = 'default', style }) {
  const small = size === 'small';
  return (
    <span
      style={{
        background: 'var(--surface-solid)',
        color: 'var(--on-solid)',
        padding: small ? 'var(--chip-pad-sm)' : 'var(--chip-pad)',
        fontFamily: 'var(--font-label)',
        fontSize: small ? 'var(--size-chip-sm)' : 'var(--size-chip)',
        fontWeight: 'var(--weight-chip)',
        letterSpacing: 'var(--track-label)',
        textTransform: 'uppercase',
        ...style,
      }}
    >
      {children}
    </span>
  );
}
