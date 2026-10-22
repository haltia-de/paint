# SPDX-License-Identifier: GPL-2.0-or-later
"""Keep the current release's notes and package metadata in step."""

from pathlib import Path
import re
import unittest
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]


class ReleaseTests(unittest.TestCase):
    def test_current_release_matches_news_and_packages(self):
        news = (ROOT / 'NEWS.md').read_text()
        current = news.split('\n## ', 1)[1].split('\n## ', 1)[0]
        heading, body = current.split('\n', 1)
        version, date = re.fullmatch(r'(\d+\.\d+\.\d+) \((\d{4}-\d{2}-\d{2})\)',
                                     heading).groups()
        release = ET.parse(ROOT / 'data/io.github.haltia_de.Paint.metainfo.xml').find(
            './releases/release')
        self.assertEqual(release.attrib, {'version': version, 'date': date})
        for language, section in [('ru', 'Русский'), ('en', 'English')]:
            text = body.split('### ' + section + '\n', 1)[1].split('\n### ', 1)[0]
            expected = [line[2:] for line in text.splitlines() if line.startswith('- ')]
            actual = [item.text for item in release.findall('./description/ul/li')
                      if item.get('{http://www.w3.org/XML/1998/namespace}lang', 'en')
                      == language]
            self.assertTrue(expected)
            self.assertEqual(actual, expected)
        apkbuild = (ROOT / 'packaging/alpine/APKBUILD').read_text()
        self.assertIn('\npkgver=' + version + '\n', apkbuild)
        self.assertIn('\npkgrel=0\n', apkbuild)
        self.assertIn('py3-haltia-kit>=2.3.0', apkbuild)
        self.assertTrue((ROOT / 'debian/changelog').read_text().startswith(
            'haltia-paint (' + version + ') unstable; urgency=medium\n'))
