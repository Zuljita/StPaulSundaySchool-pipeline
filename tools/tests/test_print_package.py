"""The download must contain the final files, including browser-produced PDFs."""
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from print_pdf import finish_package
from stpaul.render import package


class PrintPackage(unittest.TestCase):
    def test_final_pdf_and_paginated_html_replace_the_provisional_package(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            handouts = root / 'handouts'
            handouts.mkdir()
            html = handouts / '01-test.html'
            html.write_text('Before pagination', encoding='utf-8')
            stamp = (2026, 9, 20, 0, 0, 0)
            archive = package.write(root, 'test', date_time=stamp)
            record = root / 'BUILD-PROVENANCE.json'
            record.write_text(json.dumps({'source_sha256': 'a' * 64,
                'outputs': ['handouts/01-test.html', archive.name]}), encoding='utf-8')
            html.write_text('After pagination', encoding='utf-8')
            pdf = handouts / '01-test.pdf'
            pdf.write_bytes(b'Invented PDF bytes for a packaging test')
            finish_package(handouts, [pdf])
            with zipfile.ZipFile(archive) as z:
                self.assertEqual(z.read('handouts/01-test.pdf'), pdf.read_bytes())
                self.assertEqual(z.read('handouts/01-test.html'), html.read_bytes())
                self.assertTrue(all(i.date_time == stamp for i in z.infolist()))
            provenance = json.loads(record.read_text(encoding='utf-8'))
            self.assertIn('handouts/01-test.pdf', provenance['outputs'])
            self.assertEqual(provenance['source_sha256'], 'a' * 64)
            first = archive.read_bytes(), record.read_bytes()
            finish_package(handouts, [pdf])
            self.assertEqual(first, (archive.read_bytes(), record.read_bytes()))
