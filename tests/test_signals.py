# SPDX-License-Identifier: GPL-2.0-or-later
"""Unix shutdown compatibility, without GTK or PyGObject."""
import ast
from types import SimpleNamespace
import signal
import unittest
from unittest.mock import Mock

from test_image_loading import SOURCE, functions


class SignalTest(unittest.TestCase):
    def test_supported_glib_registers_orderly_shutdown_for_both_signals(self):
        paint = next(node for node in SOURCE.body if isinstance(node, ast.ClassDef)
                     and node.name == 'Paint')
        init = next(node for node in paint.body if isinstance(node, ast.FunctionDef)
                    and node.name == '__init__')
        # Run the actual window setup through signal registration, before the
        # stack and gallery need settings, workers and pictures.
        setup = []
        for node in init.body:
            if (isinstance(node, ast.Assign)
                    and any(isinstance(target, ast.Attribute) and target.attr == 'stack'
                            for target in node.targets)):
                break
            setup.append(node)
        callbacks = {}

        def unix_signal_add(priority, signum, handler):
            self.assertEqual(priority, 0)
            self.assertNotIn(signum, callbacks)
            callbacks[signum] = handler
            return len(callbacks)

        # GLib 2.80 exposes unix_signal_add; GLibUnix has no signal_add.
        ns = functions('quit', namespace={
            'GLib': SimpleNamespace(PRIORITY_DEFAULT=0, unix_signal_add=unix_signal_add),
            'GLibUnix': SimpleNamespace(), 'signal': signal,
            'Gtk': Mock(), 'Pango': Mock(), 'ON_HALTIA': False})
        app = SimpleNamespace(save=Mock(), conversion=Mock(), app=Mock())
        app.quit = lambda: ns['quit'](app)
        app.back = Mock()
        app.add_picture = Mock()
        app.show_settings = Mock()
        app.on_key = Mock()
        app.on_button = Mock()
        ns.update(self=app, app=app.app)
        exec(compile(ast.Module(body=setup, type_ignores=[]), 'haltia-paint', 'exec'), ns)
        self.assertEqual(set(callbacks), {signal.SIGTERM, signal.SIGINT})
        for signum, callback in callbacks.items():
            with self.subTest(signal=signum):
                app.save.reset_mock()
                app.conversion.reset_mock()
                app.app.reset_mock()
                self.assertIs(callback(), False)  # remove the GLib source
                app.save.assert_called_once_with()
                app.conversion.stop.assert_called_once_with()
                app.app.quit.assert_called_once_with()


if __name__ == '__main__':
    unittest.main()
