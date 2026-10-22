# SPDX-License-Identifier: GPL-2.0-or-later
"""Image loading failures and worker hand-offs, without GTK."""
import ast
import gzip
import io
import math
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import xml.etree.ElementTree as ET


SOURCE = ast.parse((Path(__file__).resolve().parents[1] / 'haltia-paint').read_text())


def functions(*names, namespace):
    nodes = [node for node in SOURCE.body if isinstance(node, ast.FunctionDef)
             and node.name in names]
    paint = next(node for node in SOURCE.body if isinstance(node, ast.ClassDef)
                 and node.name == 'Paint')
    nodes += [node for node in paint.body if isinstance(node, ast.FunctionDef)
              and node.name in names]
    exec(compile(ast.Module(body=nodes, type_ignores=[]), 'haltia-paint', 'exec'), namespace)
    return namespace


class ImageLoadingTest(unittest.TestCase):
    def region_parser(self):
        # Only path validation is under test; drawing needs no GTK or cairo.
        context = SimpleNamespace(
            new_path=lambda: None, move_to=Mock(), line_to=lambda x, y: None,
            close_path=lambda: None, copy_path=lambda: (), append_path=lambda path: None,
            path_extents=lambda: (0, 0, 10, 10))
        ns = functions('regions_of', 'read_regions', namespace={
            'gzip': gzip, 'ET': ET, 'math': math, 'Region': SimpleNamespace,
            'SVG': '{http://www.w3.org/2000/svg}', 'GRID': 100,
            'cairo': SimpleNamespace(Error=RuntimeError, Context=lambda surface: context,
                                     ImageSurface=Mock(), FORMAT_A8=0)})
        return ns['regions_of'], context

    def test_every_bundled_picture_loads_regions(self):
        regions_of, _ = self.region_parser()
        paths = sorted((Path(__file__).resolve().parents[1] / 'pictures').glob('*.svgz'))
        self.assertTrue(paths)
        for path in paths:
            with self.subTest(picture=path.name):
                with gzip.open(path) as fh:
                    head = ET.parse(fh).getroot().attrib
                pic = {'path': path, 'palette': head['data-palette'].split(),
                       'count': int(head['data-count'])}
                self.assertEqual(len(regions_of(pic)), pic['count'])
                self.assertIn('grid', pic)

    def test_short_rings_are_skipped_but_invalid_coordinates_fail(self):
        for ring in ('', '1 2', '1 2 3 4', '1', '1 2 3', 'nan 0', 'inf 0', 'bad 0'):
            with self.subTest(ring=ring), tempfile.TemporaryDirectory() as folder:
                regions_of, context = self.region_parser()
                path = Path(folder) / 'picture.svgz'
                with gzip.open(path, 'wt') as fh:
                    fh.write('<svg xmlns="http://www.w3.org/2000/svg">'
                             '<path data-n="1" data-label="1 1 1" '
                             'd="M%sZM0 0 10 0 0 10Z"/></svg>' % ring)
                pic = {'path': path, 'palette': ['#ffffff'], 'count': 1}
                if ring in ('', '1 2', '1 2 3 4'):
                    self.assertEqual(len(regions_of(pic)), 1)
                    context.move_to.assert_called_once_with(0, 0)
                else:
                    with self.assertRaises(OSError):
                        regions_of(pic)
                    self.assertNotIn('regions', pic)

    def test_file_pixel_cap_precedes_decode(self):
        pixbuf = Mock()
        pixbuf.get_file_info.return_value = (object(), 10000, 10000)
        ns = functions('pixbuf_file', namespace={
            'GdkPixbuf': SimpleNamespace(Pixbuf=pixbuf), 'MAX_IMAGE_PIXELS': 64_000_000,
            'open': lambda *args: io.BytesIO(b'jpeg'), 'check_png_header': lambda data: None})
        with self.assertRaises(OSError):
            ns['pixbuf_file']('huge.png', 640, 520)
        pixbuf.new_from_file_at_scale.assert_not_called()
        pixbuf.get_file_info.return_value = (object(), 8000, 6000)
        ns['pixbuf_file']('photo.jpg', 640, 520)
        pixbuf.new_from_file_at_scale.assert_called_once_with('photo.jpg', 640, 520, True)

    def test_byte_loader_sets_size_before_pixels(self):
        class Loader:
            def connect(self, signal, callback):
                self.callback = callback

            def write(self, data):
                self.callback(self, *data)

            set_size = Mock()
            close = Mock()
            get_pixbuf = Mock()

        loader = Loader()
        ns = functions('pixbuf_of', namespace={
            'GdkPixbuf': SimpleNamespace(PixbufLoader=lambda: loader),
            'MAX_IMAGE_PIXELS': 64_000_000, 'check_png_header': lambda data: None})
        ns['pixbuf_of']((8000, 6000), 640, 520)
        loader.set_size.assert_called_with(640, 480)
        with self.assertRaises(OSError):
            ns['pixbuf_of']((10000, 10000), 640, 520)
        loader.set_size.assert_called_with(1, 1)

    def test_png_cap_precedes_any_decoder(self):
        pixbuf = Mock()
        ns = functions('check_png_header', 'pixbuf_file', 'pixbuf_of', namespace={
            'GdkPixbuf': pixbuf, 'MAX_IMAGE_PIXELS': 64_000_000})
        header = (b'\x89PNG\r\n\x1a\n' + (13).to_bytes(4, 'big') + b'IHDR'
                  + (10000).to_bytes(4, 'big') * 2)
        with tempfile.NamedTemporaryFile() as fh:
            fh.write(header)
            fh.flush()
            with self.assertRaises(OSError):
                ns['pixbuf_file'](fh.name, 100, 100)
        with self.assertRaises(OSError):
            ns['pixbuf_of'](header, 100, 100)
        self.assertEqual(pixbuf.mock_calls, [])
        ns['check_png_header'](header[:16] + (8000).to_bytes(4, 'big') * 2)

    def test_download_deadline_stops_trickling_response(self):
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.read1.return_value = b'x'
        clock = Mock()
        clock.monotonic.side_effect = [0, 1, 30, 31, 61]
        ns = functions('read_download', namespace={'time': clock})
        with patch('urllib.request.urlopen', return_value=response):
            with self.assertRaises(TimeoutError):
                ns['read_download'](object(), 100)
        self.assertEqual(response.read1.call_count, 2)
        response.__exit__.assert_called_once()

    def test_download_without_private_socket_attribute(self):
        response = io.BytesIO(b'image')
        response.geturl = lambda: 'https://example.invalid/image'
        ns = functions('read_download', namespace={
            'time': SimpleNamespace(monotonic=lambda: 0)})
        with patch('urllib.request.urlopen', return_value=response):
            self.assertEqual(ns['read_download'](object(), 100),
                             (b'image', 'https://example.invalid/image'))

    def test_cancelled_thumbnail_jobs_do_not_block_user_pool(self):
        import queue
        import threading
        node = next(n for n in SOURCE.body if isinstance(n, ast.ClassDef)
                    and n.name == 'Workers')
        ns = {'queue': queue, 'threading': threading,
              'sys': SimpleNamespace(stderr=io.StringIO())}
        exec(compile(ast.Module(body=[node], type_ignores=[]), 'haltia-paint', 'exec'), ns)
        thumbs, users = ns['Workers'](1), ns['Workers'](1)
        entered, release, done = threading.Event(), threading.Event(), threading.Event()
        cancelled = threading.Event()
        stale = Mock()

        def slow():
            entered.set()
            release.wait(2)

        thumbs.submit(slow)
        self.assertTrue(entered.wait(2))
        thumbs.submit(stale, cancelled=cancelled)
        cancelled.set()
        try:
            users.submit(done.set)
            self.assertTrue(done.wait(2))
        finally:
            release.set()
        drained = threading.Event()
        thumbs.submit(drained.set)
        self.assertTrue(drained.wait(2))
        stale.assert_not_called()

    def test_double_save_and_long_unicode_title(self):
        import os
        import re
        import time
        threads = []
        callbacks = []
        image = Mock()
        def write_png(path):
            self.assertTrue(Path(path).name.startswith('.'))
            Path(path).write_bytes(b'png')

        image.write_to_png.side_effect = write_png
        with tempfile.TemporaryDirectory() as folder:
            ns = functions('save_to_gallery', namespace={
                'SAVED': folder, 're': re, 'os': os, 'time': time,
                'tempfile': tempfile, 'without_regions': dict, 'hex_rgb': str,
                'regions_of': lambda pic: [], 'whole_picture': lambda *args: image,
                'threading': SimpleNamespace(Thread=lambda **kw: SimpleNamespace(
                    start=lambda: threads.append(kw['target']))),
                'GLib': SimpleNamespace(idle_add=lambda *args: callbacks.append(args)),
                'dialogs': Mock(), 'sys': SimpleNamespace(stderr=io.StringIO()),
                'cairo': SimpleNamespace(Error=RuntimeError)})
            app = SimpleNamespace(saving=False, win=object())
            pic = {'name': 'Я' * 300, 'palette': []}
            ns['save_to_gallery'](app, pic)
            ns['save_to_gallery'](app, pic)
            self.assertEqual(len(threads), 1)
            threads.pop()()
            files = list(Path(folder).iterdir())
            self.assertEqual(len(files), 1)
            self.assertLess(len(files[0].name.encode()), 120)
            self.assertEqual(files[0].read_bytes(), b'png')
            callback, text = callbacks.pop()
            callback(text)
            self.assertFalse(app.saving)
            image.write_to_png.side_effect = ValueError('unexpected render failure')
            ns['save_to_gallery'](app, pic)
            threads.pop()()
            callback, text = callbacks.pop()
            callback(text)
            self.assertFalse(app.saving)
            self.assertEqual(text, 'Не удалось сохранить.')
            self.assertEqual(list(Path(folder).iterdir()), files)

    def test_return_to_search_restarts_cancelled_thumbnails(self):
        import threading
        ns = functions('show_search', 'search_more', namespace={'threading': threading})
        button = Mock()
        stack = Mock()
        stack.get_child_by_name.return_value = None
        cancelled = threading.Event()
        cancelled.set()
        app = SimpleNamespace(
            search_page=object(), leave_preview=Mock(), stack=stack,
            title=Mock(), back_button=Mock(), find_button=Mock(), settings_button=Mock(),
            win=Mock(), search_cancel=cancelled,
            results=SimpleNamespace(get_children=lambda: [SimpleNamespace(
                get_child=lambda: button)]), more_button=Mock(), search_note=Mock(),
            search_next=24, search_gen=1, search_query='cats', run_search=Mock())
        ns['show_search'](app)
        self.assertIsNot(app.search_cancel, cancelled)
        self.assertFalse(app.search_cancel.is_set())
        button.load_thumbnail.assert_called_once()
        app.search_cancel.set()
        ns['search_more'](app)
        self.assertFalse(app.search_cancel.is_set())
        app.run_search.assert_called_once_with(1, 'cats', 24)

    def test_thumbnail_retry_uses_fresh_event_and_cached_image(self):
        import threading
        gtk = Mock()
        ns = functions('result_card', namespace={
            'Gtk': gtk, 'Pango': Mock(), 'downloaded_any': lambda qid: False,
            'pixbuf_of': lambda *args: 'pixels', 'fetch_image': Mock(return_value=b'png'),
            'GLib': SimpleNamespace(idle_add=lambda callback: callback())})
        app = SimpleNamespace(search_cancel=threading.Event(), search_pool=Mock(),
                              search_gen=1)
        item = dict(title='Cat', author='', year=None, qid='Q1', thumb='url')
        button = ns['result_card'](app, 1, item)
        job = app.search_pool.submit.call_args.args[0]
        app.search_cancel.set()
        job()
        self.assertNotIn('small', item)
        app.search_cancel = threading.Event()
        button.load_thumbnail()
        self.assertIs(app.search_pool.submit.call_args.kwargs['cancelled'], app.search_cancel)
        app.search_pool.submit.call_args.args[0]()
        self.assertEqual(item['small'], 'pixels')
        app.search_pool.reset_mock()
        button.load_thumbnail()
        app.search_pool.submit.assert_not_called()
        gtk.Image.return_value.set_from_pixbuf.assert_called_with('pixels')

    def test_corrupt_regions_are_io_errors_and_not_cached(self):
        ns = functions('regions_of', 'read_regions', namespace={
            'gzip': gzip, 'ET': ET, 'cairo': SimpleNamespace(Error=RuntimeError)})
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'broken.svgz'
            with gzip.open(path, 'wb') as fh:
                fh.write(b'<svg><path')
            pic = {'path': str(path)}
            with self.assertRaises(OSError):
                ns['regions_of'](pic)
            self.assertNotIn('regions', pic)

    def test_failed_board_preserves_current_page_and_last(self):
        write_last = Mock()
        ns = functions('open', namespace={
            'without_regions': dict, 'Board': Mock(side_effect=OSError('broken')),
            'write_last': write_last, 'ET': ET, 'cairo': SimpleNamespace(Error=RuntimeError),
            'sys': SimpleNamespace(stderr=io.StringIO()), 'dialogs': Mock()})
        app = SimpleNamespace(win=object(), leave_preview=Mock(), stack=Mock(), board=object())
        old_board = app.board
        self.assertFalse(ns['open'](app, {'id': 'bad', 'path': 'bad.svgz'}))
        self.assertIs(app.board, old_board)
        app.leave_preview.assert_not_called()
        app.stack.remove.assert_not_called()
        write_last.assert_not_called()

    def test_photo_selection_defers_io(self):
        ns = functions('photo_chosen', namespace={})
        app = SimpleNamespace(pool=Mock(), stack=Mock())
        ns['photo_chosen'](app, '/does/not/exist.jpg')
        app.pool.submit.assert_called_once()


try:
    from PIL import Image, ImageChops, ImageEnhance, ImageFilter, ImageOps
except ImportError:
    Image = None


@unittest.skipIf(Image is None, 'needs Pillow')
class ShrinkTest(unittest.TestCase):
    def shrink(self, image, side, crop=None):
        source = ast.parse((Path(__file__).resolve().parents[1] / 'pbn.py').read_text())
        node = next(n for n in source.body if isinstance(n, ast.FunctionDef) and n.name == 'shrink')
        ns = dict(Image=Image, ImageChops=ImageChops, ImageEnhance=ImageEnhance,
                  ImageFilter=ImageFilter, ImageOps=ImageOps,
                  np=SimpleNamespace(asarray=lambda image: image))
        exec(compile(ast.Module(body=[node], type_ignores=[]), 'pbn.py', 'exec'), ns)
        return ns['shrink'](image, side, crop)

    def test_jpeg_is_reduced_before_transpose(self):
        from unittest.mock import patch
        data = io.BytesIO()
        Image.new('RGB', (4000, 3000), 'red').save(data, 'JPEG')
        data.seek(0)
        with Image.open(data) as image:
            original = ImageOps.exif_transpose
            sizes = []

            def transpose(image):
                sizes.append(image.size)
                return original(image)

            with patch.object(ImageOps, 'exif_transpose', side_effect=transpose):
                result = self.shrink(image, 200)
            self.assertLessEqual(max(sizes[0]), 600)
            self.assertEqual(result.size, (200, 150))

    def test_orientation_and_crop_use_upright_coordinates(self):
        image = Image.new('RGB', (1200, 800), 'red')
        image.getexif()[274] = 6  # clockwise quarter turn
        result = self.shrink(image, 200, (0, 0, 1, 0.5))
        self.assertEqual(result.size, (200, 150))


if __name__ == '__main__':
    unittest.main()
