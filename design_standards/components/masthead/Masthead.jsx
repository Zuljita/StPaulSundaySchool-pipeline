import React from 'react';
import { IdentityChip } from './IdentityChip.jsx';

export function Masthead({ logoSrc, chip, title, date, occasion, reference, season, seasonColor = 'var(--season-trinity)' }) {
  return (
    <header
      style={{
        display: 'grid',
        gridTemplateColumns: '1fr auto',
        alignItems: 'end',
        gap: '24px',
        borderBottom: 'var(--rule-heavy) solid var(--border-masthead)',
        paddingBottom: '9px',
      }}
    >
      <div>
        <div style={{ display: 'flex', alignItems: 'flex-end', gap: '11px', marginBottom: '8px' }}>
          {logoSrc ? (
            <img src={logoSrc} alt="St. Paul Lutheran Church" style={{ display: 'block', width: 'var(--logo-width)', height: 'auto' }} />
          ) : null}
          <span
            style={{
              fontFamily: 'var(--font-label)',
              fontSize: '13px',
              fontWeight: 'var(--weight-chip)',
              letterSpacing: 'var(--track-wordmark)',
              textTransform: 'uppercase',
              color: 'var(--text-display)',
              paddingBottom: '1px',
            }}
          >
            Sunday School
          </span>
        </div>
        <div style={{ marginBottom: '8px' }}>
          <IdentityChip>{chip}</IdentityChip>
        </div>
        <h1
          style={{
            margin: 0,
            fontFamily: 'var(--font-display)',
            fontSize: 'var(--size-h1)',
            fontWeight: 400,
            lineHeight: 'var(--lh-display)',
            letterSpacing: '-0.01em',
            color: 'var(--text-display)',
          }}
        >
          {title}
        </h1>
      </div>
      <p
        style={{
          margin: 0,
          textAlign: 'right',
          fontFamily: 'var(--font-label)',
          fontSize: 'var(--size-meta)',
          fontWeight: 'var(--weight-label)',
          lineHeight: 'var(--lh-meta)',
          letterSpacing: 'var(--track-meta)',
          textTransform: 'uppercase',
          color: 'var(--text-meta)',
        }}
      >
        {date}
        <br />
        {occasion}
        <br />
        {reference}
        <br />
        <span style={{ color: seasonColor }}>■</span> {season}
      </p>
    </header>
  );
}
