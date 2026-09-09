import React from 'react';

export function ArtworkPanel({ src, credit, height = 'var(--artwork-height)', position = '50% 22%' }) {
  return (
    <figure style={{ margin: 0, height, flex: 'none', display: 'flex', flexDirection: 'column', gap: '4px' }}>
      <img
        src={src}
        alt={credit || ''}
        style={{
          display: 'block',
          width: '100%',
          flex: 1,
          minHeight: 0,
          objectFit: 'cover',
          objectPosition: position,
          border: 'var(--rule-hair) solid var(--border-hairline)',
        }}
      />
      {credit ? (
        <figcaption
          style={{
            fontFamily: 'var(--font-label)',
            fontSize: 'var(--size-art-credit)',
            lineHeight: 1.4,
            letterSpacing: '0.06em',
            textTransform: 'uppercase',
            color: 'var(--text-meta)',
          }}
        >
          {credit}
        </figcaption>
      ) : null}
    </figure>
  );
}
