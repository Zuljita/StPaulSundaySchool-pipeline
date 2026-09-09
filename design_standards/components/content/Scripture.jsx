import React from 'react';

export function Scripture({ verses, columns = 2, size = 'var(--size-scripture)' }) {
  return (
    <div
      style={{
        columnCount: columns,
        columnGap: 'var(--grid-gutter)',
        columnRule: 'var(--rule-hair) solid var(--border-hairline-soft)',
        fontSize: size,
        lineHeight: 'var(--lh-scripture)',
      }}
    >
      <p style={{ margin: 0 }}>
        {verses.map((v, i) => (
          <React.Fragment key={v.n}>
            <sup style={{ fontFamily: 'var(--font-label)', fontSize: 'var(--size-verse-number)', color: 'var(--verse-number)' }}>{v.n}</sup>
            {v.text}
            {i < verses.length - 1 ? ' ' : null}
          </React.Fragment>
        ))}
      </p>
    </div>
  );
}
