import React from 'react';

export function ThemeLine({ children, levelQuestion }) {
  return (
    <p
      style={{
        margin: 0,
        fontFamily: 'var(--font-display)',
        fontStyle: 'italic',
        fontSize: 'var(--size-theme)',
        lineHeight: 'var(--lh-theme)',
        color: 'var(--text-label)',
      }}
    >
      {children}
      {levelQuestion ? (
        <span
          style={{
            color: 'var(--text-meta)',
            fontStyle: 'normal',
            fontSize: 'var(--size-body-sm)',
            fontFamily: 'var(--font-body)',
          }}
        >
          {' '}
          {levelQuestion}
        </span>
      ) : null}
    </p>
  );
}
