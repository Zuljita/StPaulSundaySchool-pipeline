Footer pinned to the foot of the sheet: piece and date left, page count right, over a hairline.

```jsx
<SheetFooter left="Primary 1–2 · Teacher's Guide · Month 00, 0000" right="Page 2 of 3" credit="…" />
```

Pass `credit` on exactly one page per document. Its `margin-top: auto` is what pins it, so every sibling needs `flex: none`.
