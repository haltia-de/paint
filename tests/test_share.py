# SPDX-License-Identifier: GPL-2.0-or-later
"""Shared photos and application file forwarding, without GTK."""
import ast
import hashlib
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from test_image_loading import SOURCE, functions


class ShareTest(unittest.TestCase):
    def test_copy_survives_sender_changes(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'camera.png'
            source.write_bytes(b'photo')
            ns = functions('keep_shared_photo', namespace={
                'DATA': folder, 'os': os, 'tempfile': tempfile, 'hashlib': hashlib})
            saved = Path(ns['keep_shared_photo'](str(source), source.read_bytes()))
            source.write_bytes(b'changed')
            source.unlink()
            self.assertEqual(saved.read_bytes(), b'photo')
            self.assertEqual(list(saved.parent.iterdir()), [saved])

    def test_shared_selection_copies_before_decode_and_previews(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'camera.webp'
            source.write_bytes(b'photo')
            saved = str(Path(folder) / 'private.webp')
            keep = Mock(return_value=saved)
            decode = Mock(return_value=object())
            ns = functions('photo_chosen', namespace={
                'os': os, 'hashlib': hashlib, 'keep_shared_photo': keep,
                'pixbuf_file': decode, 'GLib': SimpleNamespace(Error=RuntimeError,
                    idle_add=lambda callback, item: callback(item)),
                'sections': SimpleNamespace(MY_PHOTOS='photos'), 'sys': sys,
                'dialogs': Mock()})
            app = SimpleNamespace(pool=SimpleNamespace(submit=lambda work: work()),
                                  stack=Mock(), show_preview=Mock())
            ns['photo_chosen'](app, str(source), shared=True)
            keep.assert_called_once_with(str(source), b'photo')
            decode.assert_called_once_with(saved, 640, 520)
            item = app.show_preview.call_args.args[0]
            self.assertEqual(item['file'], saved)
            self.assertEqual(item['title'], 'camera')
            self.assertTrue(item['own'])

    def app_class(self):
        class Application:
            def __init__(self, **kwargs):
                self.flags = kwargs['flags']

        ns = {'Gtk': SimpleNamespace(Application=Application), 'APP_ID': 'paint',
              'Gio': SimpleNamespace(ApplicationFlags=SimpleNamespace(HANDLES_OPEN=4)),
              'dialogs': Mock()}
        node = next(n for n in SOURCE.body if isinstance(n, ast.ClassDef) and n.name == 'App')
        exec(compile(ast.Module(body=[node], type_ignores=[]), 'haltia-paint', 'exec'), ns)
        return ns

    def test_open_activates_and_forwards_to_existing_window(self):
        ns = self.app_class()
        app = ns['App']()
        self.assertEqual(app.flags, 4)
        app.paint = SimpleNamespace(win=Mock(), photo_chosen=Mock())
        photo = Mock()
        photo.get_path.return_value = '/camera/photo.jpg'
        app.do_open([photo], 1, '')
        app.paint.win.present.assert_called_once()
        app.paint.photo_chosen.assert_called_once_with('/camera/photo.jpg', shared=True)

    def test_non_local_file_reports_error(self):
        ns = self.app_class()
        app = ns['App']()
        app.paint = SimpleNamespace(win=Mock(), photo_chosen=Mock())
        photo = Mock()
        photo.get_path.return_value = None
        app.do_open([photo], 1, '')
        app.paint.photo_chosen.assert_not_called()
        ns['dialogs'].info.assert_called_once()

    def test_first_open_creates_window_before_selection(self):
        ns = self.app_class()
        app = ns['App']()
        paint = SimpleNamespace(photo_chosen=Mock())
        app.do_activate = lambda: setattr(app, 'paint', paint)
        photo = Mock()
        photo.get_path.return_value = '/camera/photo.jpg'
        app.do_open([photo], 1, '')
        paint.photo_chosen.assert_called_once_with('/camera/photo.jpg', shared=True)

    def test_command_line_preserves_files_and_legacy_open(self):
        for args, open_id, forwarded in [
                (['paint', '/photo with spaces.png'], None, ['paint', '/photo with spaces.png']),
                (['paint', '--open', 'builtin-fox'], 'builtin-fox', ['paint'])]:
            with self.subTest(args=args):
                app = Mock()
                factory = Mock(return_value=app)
                ns = functions('main', namespace={
                    'sys': SimpleNamespace(argv=args), 'App': factory, 'paths': Mock()})
                ns['main']()
                factory.assert_called_once_with(open_id)
                app.run.assert_called_once_with(forwarded)

    def test_desktop_advertises_single_photo_receiver(self):
        text = (Path(__file__).resolve().parents[1] /
                'data/io.github.haltia_de.Paint.desktop').read_text()
        for line in ('Exec=haltia-paint %f', 'X-Haltia-Share=true',
                     'MimeType=image/jpeg;image/png;image/webp;'):
            self.assertIn(line, text.splitlines())
