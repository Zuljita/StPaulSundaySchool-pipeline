import React from 'react';
import { IdentityChip } from './IdentityChip.jsx';

export function RunningHeader({ chip, right }) {
  return (
    <header
      style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'baseline',
        gap: '20px',
        borderBottom: 'var(--rule-medium) solid var(--border-masthead)',
        paddingBottom: '8px',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
        <span
          style={{
            fontFamily: 'var(--font-label)',
            fontSize: 'var(--size-chip-sm)',
            fontWeight: 'var(--weight-chip)',
            letterSpacing: 'var(--track-wordmark)',
            textTransform: 'uppercase',
            color: 'var(--text-display)',
          }}
        >
          St. Paul Sunday School
        </span>
        <IdentityChip size="small">{chip}</IdentityChip>
      </div>
      <p
        style={{
          margin: 0,
          fontFamily: 'var(--font-label)',
          fontSize: 'var(--size-meta)',
          fontWeight: 'var(--weight-label)',
          letterSpacing: 'var(--track-meta)',
          textTransform: 'uppercase',
          color: 'var(--text-meta)',
        }}
      >
        {right}
      </p>
    </header>
  );
}
