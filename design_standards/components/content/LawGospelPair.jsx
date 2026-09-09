import React from 'react';
import { SectionLabel } from './SectionLabel.jsx';

export function LawGospelPair({ law, gospel }) {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
      <div style={{ borderTop: 'var(--rule-heavy) solid var(--rule-law)', paddingTop: '7px' }}>
        <SectionLabel tone="law" size="small" style={{ marginBottom: '4px' }}>The Law</SectionLabel>
        <p style={{ margin: 0, fontSize: 'var(--size-body-sm)', lineHeight: 'var(--lh-scripture)' }}>{law}</p>
      </div>
      <div style={{ borderTop: 'var(--rule-heavy) solid var(--rule-gospel)', paddingTop: '7px' }}>
        <SectionLabel size="small" style={{ marginBottom: '4px' }}>The Gospel</SectionLabel>
        <p style={{ margin: 0, fontSize: 'var(--size-body-sm)', lineHeight: 'var(--lh-scripture)' }}>{gospel}</p>
      </div>
    </div>
  );
}
