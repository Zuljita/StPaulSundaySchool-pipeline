import React from 'react';

export function Sheet({ children, variant = 'default' }) {
  const pad =
    variant === 'lesson'
      ? 'var(--lesson-pad-top) var(--page-pad-side) var(--lesson-pad-foot)'
      : 'var(--page-pad-top) var(--page-pad-side) var(--page-pad-foot)';
  return (
    <section
      className="page"
      style={{
        width: 'var(--page-width)',
        height: 'var(--page-height)',
        fontFamily: 'var(--font-body)',
        color: 'var(--text-body)',
        background: 'var(--surface-page)',
        boxSizing: 'border-box',
      }}
    >
      <div style={{ padding: pad, height: '100%', boxSizing: 'border-box', display: 'flex', flexDirection: 'column' }}>
        {children}
      </div>
    </section>
  );
}
