/* Browser-only layout pass. No rewriting, font shrinking, or text splitting.
 * Each source page is a logical section; continuations stay within that section.
 * The output is static HTML, consumed by the independent fit and PDF checks.
 */
function paginate(doc) {
  const originals = [...doc.querySelectorAll('body > .page')];
  const running = doc.querySelector('#continuation-header')?.content.firstElementChild;
  if (!originals.length || !running) throw Error('Missing pages or continuation header. Rebuild the sheets.');
  const footer = originals.at(-1).querySelector('footer.sheet');
  if (!footer) throw Error('Missing sheet footer.');

  const isFurniture = el => el.matches('header, footer.sheet, .theme');
  const bodies = page => [...page.querySelector('.inner').children].filter(el => !isFurniture(el));
  const signature = pages => pages.flatMap(bodies).map(el => el.textContent).join('').replace(/\s+/g, '');
  const images = pages => pages.flatMap(bodies).flatMap(el =>
    [...el.querySelectorAll('img')].map(img => img.getAttribute('src'))).join('\n');
  const before = signature(originals), beforeImages = images(originals);
  const result = [];

  // A lesson step, verse panel, passage, picture, or writing area travels whole.
  // Ordinary sections can break between paragraphs and list items. A block too
  // tall even for a fresh page fails explicitly rather than clipping or shrinking.
  const atomic = '.step, .navy, .scripture, .pair, .art, .lines, p, li, h1, h2, h3';
  function leaves(el, ancestors = []) {
    if (el.matches(atomic) || !el.children.length || [...el.childNodes].some(
        n => n.nodeType === 3 && n.textContent.trim())) {
      return [{el, ancestors}];
    }
    return [...el.children].flatMap(child => leaves(child, [...ancestors, el]));
  }

  function fits(page) {
    const inner = page.querySelector('.inner');
    const foot = page.querySelector('footer.sheet');
    const box = page.getBoundingClientRect();
    const bottom = box.bottom - parseFloat(doc.defaultView.getComputedStyle(inner).paddingBottom);
    if (foot.getBoundingClientRect().bottom > bottom + 0.5) return false;
    if (page.scrollHeight > page.clientHeight + 2) return false;
    return [...page.querySelectorAll('.frame, .rail, .stack, .scripture')].every(
      el => el.scrollWidth <= el.clientWidth + 2 && el.getBoundingClientRect().bottom <=
        foot.getBoundingClientRect().top + 0.5);
  }

  for (const original of originals) {
    const chunks = bodies(original).flatMap(el => leaves(el));
    const groups = [];
    // Keep a heading with the next printable block, including nested headings.
    for (let i = 0; i < chunks.length; i++) {
      const group = [chunks[i]];
      while (group.at(-1).el.matches('h1, h2, h3') && i + 1 < chunks.length) {
        group.push(chunks[++i]);
      }
      groups.push(group);
    }
    const sourceInner = original.querySelector('.inner');
    let first = true;
    let page;
    function assemble(accepted, final = false) {
      const next = original.cloneNode(false);
      for (const mark of original.querySelectorAll(':scope > .draft-mark')) next.append(mark.cloneNode(true));
      const inner = sourceInner.cloneNode(false);
      next.append(inner);
      if (first) {
        for (const el of sourceInner.children) {
          if (el.matches('header, .theme')) inner.append(el.cloneNode(true));
        }
      } else inner.append(running.cloneNode(true));

      const clones = new Map();
      function container(source, parent) {
        if (clones.has(source)) return clones.get(source);
        const copy = source.cloneNode(false);
        clones.set(source, copy);
        parent.append(copy);
        // Preserve both grid tracks even when only one column continues. This
        // keeps type and line wrapping identical to the source skeleton.
        if (source.matches('.frame:not(.one), .bands.two, .bands.three, .pair')) {
          for (const col of source.children) {
            const shell = col.cloneNode(false);
            clones.set(col, shell);
            copy.append(shell);
          }
        }
        return copy;
      }
      for (const {el, ancestors} of accepted.flat()) {
        let parent = inner;
        for (const ancestor of ancestors) parent = container(ancestor, parent);
        const existing = clones.get(el);
        if (existing) existing.replaceWith(el.cloneNode(true));
        else parent.append(el.cloneNode(true));
      }
      const foot = footer.cloneNode(true);
      if (!final) foot.querySelectorAll('.credit').forEach(el => el.remove());
      inner.append(foot);
      if (page) page.replaceWith(next);
      else original.before(next);
      page = next;
    }

    let accepted = [];
    for (const group of groups) {
      const final = original === originals.at(-1) && group === groups.at(-1);
      assemble([...accepted, group], final);
      if (fits(page)) { accepted.push(group); continue; }
      if (accepted.length) {
        assemble(accepted);
        result.push(page);
        first = false;
        page = null;
        accepted = [];
        assemble([group], final);
      }
      if (!fits(page)) {
        const block = group.at(-1).el;
        throw Error(`A whole ${block.className || block.tagName.toLowerCase()} block cannot fit on a page. ` +
          'No text was removed; review the block or its layout.');
      }
      accepted.push(group);
    }
    if (!page) assemble([], original === originals.at(-1));
    result.push(page);
    original.remove();
  }
  if (signature(result) !== before || images(result) !== beforeImages) {
    throw Error('Pagination changed content. Refusing to write the sheet.');
  }
  result.forEach((page, i) => {
    const foot = page.querySelector('footer.sheet');
    foot.querySelector('.line > :last-child').textContent = `Page ${i + 1} of ${result.length}`;
    if (i < result.length - 1) foot.querySelectorAll('.credit').forEach(el => el.remove());
    if (!fits(page)) throw Error(`Final page ${i + 1} does not fit.`);
  });
  // HTML parsing places trailing document whitespace in the body. Canonicalise
  // that furniture so repeated layout passes do not add a newline each time.
  [...doc.body.childNodes].filter(n => n.nodeType === 3 && !n.textContent.trim()).forEach(n => n.remove());
  return {pages: result.length, html: '<!DOCTYPE html>\n' + doc.documentElement.outerHTML + '\n'};
}
