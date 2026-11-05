"""Background test runner that walks every ModulesController test scaffold."""

import importlib.util
import json
import os
import time

from PySide6.QtCore import QRunnable

from gui import system

TESTS_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..', '..', 'tests')
)
_mirror_modules = {}


def _load_mirror(module_name):
    """Load ``tests/<module path>.py`` for a dotted source module name."""
    if module_name not in _mirror_modules:
        path = os.path.join(TESTS_DIR, *module_name.split('.')) + '.py'
        module = None
        if os.path.isfile(path):
            spec = importlib.util.spec_from_file_location(
                f'_test_mirror.{module_name}', path
            )
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        _mirror_modules[module_name] = module
    return _mirror_modules[module_name]


def find_test_hook(obj):
    """Return the ``test_<ClassName>(self, main, ui)`` hook for ``obj``.

    Hooks live in a file under ``tests/`` mirroring the class's source path.
    The MRO is walked so a subclass's own hook beats an inherited one.
    """
    for cls in type(obj).__mro__:
        mirror = _load_mirror(cls.__module__)
        hook = getattr(mirror, f'test_{cls.__name__}', None)
        if callable(hook):
            return lambda main, ui: hook(obj, main, ui)
    return None


class TestRunnable(QRunnable):
    """Iterate ``system.manager.type_controllers`` and run each scaffold.

    Mirrors :class:`gui.demo.DemoRunnable` so :py:meth:`gui.main.Main.run_tests`
    can use the same boot mechanism (DB swap + ``init_app`` + thread pool
    dispatch) that the demo uses.
    """

    def __init__(self, main, overlay, only_pages=None):
        super().__init__()
        from gui.demo import enable_esc_cancel, start_main_pump
        start_main_pump()
        enable_esc_cancel()
        self.main = main
        self.overlay = overlay
        # When set, restrict the run to these page names; other module types
        # are skipped entirely.
        self.only_pages = only_pages
        self.results = {}

    def run(self):
        from gui.demo import wait_until
        wait_until(self.main.main_pages.isVisible, timeout=60)
        time.sleep(0.5)  # let layout settle

        try:
            results = {}
            try:
                for mtype, controller in system.manager.modules.type_controllers.items():
                    # Page filter active: only the pages controller runs.
                    if self.only_pages is not None and mtype != 'pages':
                        continue
                    results[mtype] = controller.test_all(self.main, only=self.only_pages)
            except InterruptedError:
                print("\nTests stopped by user.")
                self.main._last_test_failures = 1
                return
            # A requested page that didn't load (e.g. import error) must fail,
            # not silently drop out of the run.
            if self.only_pages is not None:
                pages = results.setdefault('pages', {})
                found = {name.lower() for name in pages}
                for name in self.only_pages:
                    if name.lower() not in found:
                        summary = f"Page {name!r} not found (failed to load?)"
                        pages[name] = ('fail', {'type': 'LookupError', 'summary': summary, 'traceback': summary})
            self.results = results
            self._report(results)
        finally:
            self.overlay.finish()
            # if self.on_finished:
            #     # QTimer.singleShot(0, self.on_finished)
            #     # A timer started on this worker never fires (no event loop).
            #     from gui.demo import post_to_main
            #     post_to_main(self.on_finished)

    def _report(self, results):
        import shutil
        total = passed = failed = skipped = 0
        sections = []
        non_assertion_failures = []
        skipped_by_type = {}

        for mtype, modules in results.items():
            if not modules:
                continue
            rows = []
            skips = []
            for name, (status, info) in modules.items():
                total += 1
                if status == 'pass':
                    passed += 1
                    rows.append(('PASS', name, ''))
                elif status == 'skip':
                    skipped += 1
                    skips.append(name)
                else:
                    failed += 1
                    summary = (info or {}).get('summary', '') if isinstance(info, dict) else ''
                    rows.append(('FAIL', name, summary))
                    if isinstance(info, dict) and info.get('type') != 'AssertionError':
                        non_assertion_failures.append((mtype, name, info.get('traceback', '')))
            sections.append((mtype, rows))
            if skips:
                skipped_by_type[mtype] = skips

        try:
            term_cols = shutil.get_terminal_size((100, 20)).columns
        except Exception:
            term_cols = 100

        lines = []
        for mtype, rows in sections:
            lines.append(f"\n[{mtype}]")
            if rows:
                lines.extend(self._render_table(rows, max_width=term_cols))
            else:
                lines.append("  (no tests run)")
            if mtype in skipped_by_type:
                names = skipped_by_type[mtype]
                lines.append(f"  skipped ({len(names)}): {', '.join(names)}")

        for mtype, name, tb in non_assertion_failures:
            lines.append(f"\n--- {mtype}.{name} traceback ---")
            lines.append(tb.rstrip())

        lines.append("")
        summary = f"Summary: {passed}/{total} passed, {failed} failed"
        if skipped:
            summary += f", {skipped} skipped"
        lines.append(summary)
        print("\n".join(lines))

        self.main._last_test_failures = failed

        try:
            # src/gui/tests.py -> project root -> tests/
            project_root = os.path.abspath(
                os.path.join(os.path.dirname(__file__), '..', '..')
            )
            tests_dir = os.path.join(project_root, 'tests')
            os.makedirs(tests_dir, exist_ok=True)
            out_path = os.path.join(tests_dir, 'last_run.json')
            with open(out_path, 'w') as f:
                json.dump(
                    {mt: {n: {'status': s, 'error': e} for n, (s, e) in mods.items()}
                     for mt, mods in results.items()},
                    f,
                    indent=2,
                    default=str,
                )
        except Exception as exc:
            print(f"(could not write tests/last_run.json: {exc})")

    @staticmethod
    def _render_table(rows, max_width=100):
        headers = ('Status', 'Module', 'Detail')
        all_rows = [headers] + list(rows)
        widths = [max(len(str(r[i])) for r in all_rows) for i in range(len(headers))]

        # Cap Detail column so the whole table fits in the terminal.
        # Layout overhead: "│ " + " │ " * 2 + " │" = 10 chars of borders/padding.
        overhead = 10
        budget = max_width - overhead - widths[0] - widths[1]
        if budget < 10:
            budget = 10
        if widths[2] > budget:
            widths[2] = budget

        def truncate(s, w):
            s = str(s)
            return s if len(s) <= w else s[: max(0, w - 1)] + '…'

        def fmt(row):
            cells = [truncate(c, w).ljust(w) for c, w in zip(row, widths)]
            return '│ ' + ' │ '.join(cells) + ' │'

        top = '┌' + '┬'.join('─' * (w + 2) for w in widths) + '┐'
        mid = '├' + '┼'.join('─' * (w + 2) for w in widths) + '┤'
        bot = '└' + '┴'.join('─' * (w + 2) for w in widths) + '┘'

        out = [top, fmt(headers), mid]
        for r in rows:
            out.append(fmt(r))
        out.append(bot)
        return out
