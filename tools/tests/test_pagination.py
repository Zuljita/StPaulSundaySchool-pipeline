"""Exercise actual browser layout with invented, deliberately oversized sheets."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import fit_check
import paginate
from stpaul import browser
from stpaul.render import sheet


class Pagination(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            browser.find_browser()
        except browser.BrowserError as exc:
            import os
            if os.environ.get('GITHUB_ACTIONS') == 'true':
                raise
            raise unittest.SkipTest(str(exc))

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='stpaul-pagination-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        sheet.write_assets(self.root)

    def write(self, body, name='01-test.html'):
        heading = sheet._running_header('Test piece', 'Test date')
        footer = sheet._footer('Test piece', 'Page 1 of 1', ['Invented credit.'])
        markup = sheet.DOC.format(title='Pagination test', source_hash='a' * 64,
            assets=sheet.ASSET_DIR, stylesheet=sheet.STYLESHEET_NAME,
            continuation=f'<template id="continuation-header">{heading}</template>',
            pages=sheet._page(heading + body + footer, draft=True))
        path = self.root / name
        path.write_text(markup, encoding='utf-8')
        return path

    def assert_fits(self):
        rows = fit_check.measure(self.root)
        self.assertTrue(rows)
        for row in rows:
            self.assertNotIn('error', row)
            for key in ('over', 'footOver', 'sideways'):
                self.assertLessEqual(row[key], fit_check.TOLERANCE_PX, row)

    def test_continuations_preserve_text_steps_credits_and_are_repeatable(self):
        steps = []
        for i in range(9):
            prose = f'Unique-block-{i} ' + 'Invented example words for a long lesson step. ' * 25
            steps.append(f'<div class="step" id="step-{i}"><div class="when">{i}</div>'
                         f'<div class="what"><p>{prose}</p></div></div>')
        path = self.write('<div class="stack stack-lg"><h2>Lesson steps</h2>' + ''.join(steps) + '</div>')
        original = path.read_bytes()
        rows = paginate.prepare(self.root)
        self.assertGreater(rows[0]['pages'], 1)
        output = path.read_text(encoding='utf-8')
        pages = output.split('<section class="page"')[1:]
        for step in steps:
            self.assertEqual(output.count(step), 1)
            self.assertEqual(sum(step in page for page in pages), 1)
        self.assertEqual(output.count('Invented credit.'), 1)
        self.assertEqual(output.count('draft-mark'), len(pages))
        for i, page in enumerate(pages, 1):
            self.assertIn(f'Page {i} of {len(pages)}', page)
        self.assert_fits()
        first = path.read_bytes()
        paginate.prepare(self.root)
        self.assertEqual(first, path.read_bytes())
        path.write_bytes(original)
        paginate.prepare(self.root)
        self.assertEqual(first, path.read_bytes())

    def test_columns_preserve_every_block_and_heading_stays_with_text(self):
        paragraphs = ''.join(f'<div><h2>Heading-{i}</h2><p>Paragraph-{i} ' +
                             'Invented body words. ' * 35 + '</p></div>' for i in range(16))
        path = self.write('<div class="frame"><aside class="rail"><p>Rail text.</p></aside>'
                          '<div class="stack">' + paragraphs + '</div></div>')
        paginate.prepare(self.root)
        output = path.read_text(encoding='utf-8')
        pages = output.split('<section class="page"')[1:]
        for i in range(16):
            self.assertEqual(output.count(f'Heading-{i}</h2>'), 1)
            self.assertEqual(output.count(f'Paragraph-{i} '), 1)
            self.assertTrue(any(f'Heading-{i}</h2>' in p and f'Paragraph-{i} ' in p for p in pages))
        self.assertEqual(output.count('Rail text.'), 1)
        self.assert_fits()

    def test_oversized_atomic_block_leaves_entire_directory_untouched(self):
        good = self.write('<p>Short invented example.</p>')
        bad = self.write('<div class="step"><div class="when">1</div><div class="what"><p>' +
                         'An indivisible invented step. ' * 1500 + '</p></div></div>', '02-too-tall.html')
        before = {p: p.read_bytes() for p in (good, bad)}
        with self.assertRaisesRegex(browser.BrowserError, 'whole step block cannot fit'):
            paginate.prepare(self.root)
        self.assertEqual(before, {p: p.read_bytes() for p in before})

    def test_missing_fonts_fail_instead_of_measuring_fallback_type(self):
        path = self.write('<p>Short invented example.</p>')
        for font in self.root.rglob('*.woff2'):
            font.unlink()
        before = path.read_bytes()
        with self.assertRaisesRegex(browser.BrowserError, 'fonts failed'):
            paginate.prepare(self.root)
        self.assertEqual(before, path.read_bytes())

    def test_missing_pages_cannot_pass_the_independent_fit_check(self):
        (self.root / '01-empty.html').write_text('<html><body>Not a sheet</body></html>', encoding='utf-8')
        rows = fit_check.measure(self.root)
        self.assertEqual(len(rows), 1)
        self.assertIn('No printable pages', rows[0]['error'])


if __name__ == '__main__':
    unittest.main()
