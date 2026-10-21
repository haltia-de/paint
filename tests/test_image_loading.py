# SPDX-License-Identifier: GPL-2.0-or-later
"""Image loading failures and worker hand-offs, without GTK."""
import ast
import gzip
import io
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock
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
    def test_file_pixel_cap_precedes_decode(self):
        pixbuf = Mock()
        pixbuf.get_file_info.return_value = (object(), 10000, 10000)
        ns = functions('pixbuf_file', namespace={
            'GdkPixbuf': SimpleNamespace(Pixbuf=pixbuf), 'MAX_IMAGE_PIXELS': 64_000_000})
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
            'MAX_IMAGE_PIXELS': 64_000_000})
        ns['pixbuf_of']((8000, 6000), 640, 520)
        loader.set_size.assert_called_with(640, 480)
        with self.assertRaises(OSError):
            ns['pixbuf_of']((10000, 10000), 640, 520)
        loader.set_size.assert_called_with(1, 1)

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
