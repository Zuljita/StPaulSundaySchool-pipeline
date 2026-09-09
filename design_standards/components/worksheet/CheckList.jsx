import React from 'react';

export function CheckList({ items }) {
  return (
    <ul style={{ margin: 0, padding: 0, listStyle: 'none', display: 'grid', gap: '4px', fontSize: 'var(--size-body-sm)', lineHeight: 'var(--lh-body-tight)' }}>
      {items.map((item) => (
        <li key={item} style={{ display: 'flex', gap: '8px' }}>
          <span style={{ color: 'var(--checkbox)' }}>□</span>
          <span>{item}</span>
        </li>
      ))}
    </ul>
  );
}
