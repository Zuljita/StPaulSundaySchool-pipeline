One printed sheet: the 816×1056 page box, its margins, and the flex column that pins the footer.

```jsx
<Sheet>
  <Masthead … />
  <div style={{ flex: 'none' }}>…</div>
  <SheetFooter left="Primary 1–2 · Student Handout · Month 00, 0000" right="Page 1 of 1" />
</Sheet>
```

The box clips; it does not reflow. Verify zero overflow on every page before printing.
