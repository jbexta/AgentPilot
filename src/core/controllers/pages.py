from core.managers.modules import ModulesController
from utils.helpers import convert_to_safe_case


class PagesController(ModulesController):
    def __init__(self, system):
        super().__init__(
            system, 
            module_type='pages', 
            load_to_path='gui.pages',
            class_based=True,
            inherit_from='QWidget',
            description="UI page modules for the application",
            long_description="Pages are QWidget modules that can be composed of Widget modules"
        )

    def test_all(self, main, only=None):
        # Settings' test walks every settings sub-page, which a full run
        # already tests individually, so only run it when asked for.
        if only is None:
            only = [n for n in self.get_modules(fetch_keys=('name',)) if n != 'settings']
        return super().test_all(main, only=only)

    def test_scaffold(self, main, module_name, module_cls):
        """Navigate to the page and assert it becomes visible.

        Pages live either at the top level (``main.main_pages.pages``) or
        nested under the settings page. We use the same click mechanism as
        the demo (``gui.demo.click_widget`` -> pyautogui) so the dispatch
        runs through Qt's normal event loop on the main thread.
        """
        from gui import demo as _demo
        from gui.demo import click_widget, _run_on_main as run_on_main
        from gui.tests import find_test_hook
        from gui.widgets.config_widget import ConfigWidget
        import traceback
        from unittest import SkipTest
        from types import SimpleNamespace

        # A single ``findChildren(ConfigWidget)`` from the root finds every
        # testable widget. All ConfigWidgets reachable via the old attribute
        # walk (widgets / pages / config_widget, plus WorkflowSettings members)
        # are layout-added and therefore Qt-parented, and findChildren even
        # returns Qt.Popup widgets (they keep a QObject parent) — so this is a
        # strict superset of the previous double-traversal, with no dedup or
        # recursion needed.
        def collect_config_widgets(root):
            found = [root] if isinstance(root, ConfigWidget) else []
            return found + root.findChildren(ConfigWidget)

        # --- previous implementation kept for reference --------------------
        # The old walk did a manual recursion over widgets/pages/config_widget
        # AND a per-node findChildren sweep — two overlapping traversals
        # (roughly quadratic, deduped by id()):
        #
        # def _collect_descendants(root, seen):
        #     if id(root) in seen:
        #         return []
        #     seen.add(id(root))
        #     collected = [root] if isinstance(root, ConfigWidget) else []
        #
        #     for attr_name, accessor in (
        #         ('widgets', lambda x: list(x) if x else []),
        #         ('pages', lambda x: list(x.values()) if x else []),
        #         ('config_widget', lambda x: [x] if x is not None else []),
        #     ):
        #         child_container = getattr(root, attr_name, None)
        #         if child_container is None:
        #             continue
        #         for child in accessor(child_container):
        #             collected.extend(_collect_descendants(child, seen))
        #
        #     try:
        #         for child in root.findChildren(ConfigWidget):
        #             if id(child) not in seen:
        #                 seen.add(id(child))
        #                 collected.append(child)
        #     except Exception:
        #         pass
        #
        #     return collected
        # -------------------------------------------------------------------

        # def test_widgets(root, main_arg):
        #     widgets = collect_config_widgets(root)
        #     failures = []
        #     for w in widgets:
        #         hook = getattr(w, 'test_widget', None)
        #         if not callable(hook):
        #             continue
        #         try:
        #             hook(main_arg, ui)
        #         except Exception:
        #             failures.append((type(w).__name__, traceback.format_exc()))
        #     if failures:
        #         blocks = [
        #             f"--- {cls} ---\n{tb.rstrip()}" for cls, tb in failures
        #         ]
        #         raise AssertionError(
        #             f"{len(failures)} widget test(s) failed:\n"
        #             + "\n".join(blocks)
        #         )

        # A page's own ``test_page`` beats the ``test_widget`` it inherits
        # (e.g. from ConfigDBTree); it can call ``self.test_widget`` itself.
        # def get_hook(w):
        #     return getattr(w, 'test_page', None) or getattr(w, 'test_widget', None)
        # Hooks now live in mirrored files under tests/ (see find_test_hook).
        get_hook = find_test_hook

        # The walk only visits widgets that opt in by defining a ``test_widget``
        # (or ``test_page``) hook. A hooked widget owns its subtree: hooked
        # descendants run only if its hook calls ``ui.test_widgets`` on them
        # (e.g. ConfigDBTree on its config_widget, ConfigPages on each page),
        # so nothing runs twice and children run while actually visible.
        def owned_hooked_widgets(root):
            hooked = [w for w in collect_config_widgets(root) if callable(get_hook(w))]
            if root in hooked:
                return [root]
            hooked_ids = {id(w) for w in hooked}

            def has_hooked_ancestor(w):
                parent = w.parentWidget()
                while parent is not None and parent is not root:
                    if id(parent) in hooked_ids:
                        return True
                    parent = parent.parentWidget()
                return False
            return [w for w in hooked if not has_hooked_ancestor(w)]

        # Returns how many hooks actually ran; a hook that raises
        # ``SkipTest`` (nothing it can test here) doesn't count.
        def test_widgets(root, main_arg):
            widgets = run_on_main(lambda: owned_hooked_widgets(root))
            failures = []
            ran = 0
            for w in widgets:
                try:
                    get_hook(w)(main_arg, ui)
                    ran += 1
                except InterruptedError:  # user stopped the run
                    raise
                except SkipTest as exc:
                    print(f"  skipped {type(w).__name__}: {exc}")
                except Exception:
                    failures.append((type(w).__name__, traceback.format_exc()))
                finally:
                    _demo.dismiss_modals()
            if failures:
                blocks = [
                    f"--- {cls} ---\n{tb.rstrip()}" for cls, tb in failures
                ]
                raise AssertionError(
                    f"{len(failures)} widget test(s) failed:\n"
                    + "\n".join(blocks)
                )
            return ran

        ui = SimpleNamespace(
            click_widget=_demo.click_widget,
            hover_widget=_demo.hover_widget,
            type_text=_demo.type_text,
            get_widget_coords=_demo.get_widget_coords,
            click_coords=_demo.click_coords,
            click_tree_item_cell=_demo.click_tree_item_cell,
            move_mouse=_demo.move_mouse,
            resolve_widget=_demo.resolve_widget,
            run_on_main=run_on_main,
            wait_until=_demo.wait_until,
            wait_for_modal=_demo.wait_for_modal,
            confirm=_demo.confirm,
            press=_demo.press,
            dismiss_modals=_demo.dismiss_modals,
            tree_names=_demo.tree_names,
            choose_menu_action=_demo.choose_menu_action,
            test_widgets=test_widgets,
            testing=lambda what: main._test_overlay.show_status(
                f'Testing {what}'),
        )

        page_load_errors = getattr(main, '_page_load_errors', {}) or {}
        if module_name in page_load_errors:
            raise AssertionError(
                f"Page '{module_name}' failed to construct during init:\n"
                f"{page_load_errors[module_name]}"
            )

        main_pages = main.main_pages
        settings_page = main_pages.pages.get('settings')

        if module_name in main_pages.pages:
            container = main_pages
            parent_button = None
        elif settings_page is not None and module_name in getattr(settings_page, 'pages', {}):
            container = settings_page
            already_on_settings = main_pages.content.currentWidget() is settings_page
            parent_button = (
                None if already_on_settings
                else main_pages.settings_sidebar.page_buttons.get('settings')
            )
        else:
            raise AssertionError(
                f"Page '{module_name}' not found in main_pages or settings sub-pages"
            )

        page = container.pages[module_name]
        page_test = get_hook(page)

        # A page is exercised if it declares ANY test contract: either a
        # ``test_page`` hook, or at least one ``test_widget`` somewhere in its
        # live ConfigWidget tree. Pages with neither are skipped without
        # navigating, so we don't pay to visit pages that have no coverage.
        #
        # Previously the gate was ``test_page`` only:
        #     if not callable(page_test):
        #         return 'skip'
        # which is why pages that merely *embed* a tested widget — e.g.
        # Blocks/Tools wrapping a WorkflowSettings — were skipped despite
        # having coverage. Gating on the widget walk too fixes that.
        has_widget_tests = run_on_main(lambda: any(
            callable(get_hook(w)) for w in collect_config_widgets(page)
        ))
        if not callable(page_test) and not has_widget_tests:
            return 'skip'

        print(f"TESTING PAGE: {module_name}")
        ui.testing(f'{module_name} page')

        _demo.dismiss_modals()  # a modal left by an earlier page would eat the clicks

        if parent_button is not None:
            click_widget(parent_button)
            _demo.wait_until(
                lambda: main_pages.content.currentWidget() is settings_page,
                message="Settings page did not open",
            )

        btn = container.settings_sidebar.page_buttons.get(module_name)
        if btn is None:
            raise AssertionError(
                f"No sidebar button for page '{module_name}' in container"
            )
        if run_on_main(lambda: container.content.currentWidget() is not page):
            click_widget(btn)

        _demo.wait_until(
            page.isVisible,
            message=f"Page '{module_name}' is not visible after navigation",
        )

        # XOR: a page that defines ``test_page`` drives its own testing fully
        # (it may call ``ui.test_widgets(self, main)`` itself if it also wants
        # the subtree walked). Pages without ``test_page`` fall back to the
        # automatic widget walk, invoking ``test_widget`` on every widget that
        # defines one.
        #
        # ``ui`` exposes the demo input helpers (click_widget, type_text,
        # hover_widget, click_tree_item_cell, ...).
        # if callable(page_test):
        #     page_test(main, ui)
        # else:
        #     ui.test_widgets(page, main)
        # The XOR above now falls out of subtree ownership: a page's own hook
        # (``test_page``) owns the whole page, otherwise its hooked
        # descendants run.
        # A page whose hooks all skipped tested nothing, so report it as such.
        if ui.test_widgets(page, main) == 0:
            return 'skip'

        # Previously both ran unconditionally (test_page then the walk):
        #     page_test(main, ui)
        #     ui.test_widgets(page, main)

    def initial_content(self, module_name: str):
        safe_name = convert_to_safe_case(module_name).capitalize()
        return f"""
            from gui.gui_utils.layouts import CVBoxLayout, CHBoxLayout
            from gui.widgets.config_db_tree import ConfigDBTree
            from gui.widgets.config_fields import ConfigFields
            from gui.widgets.config_joined import ConfigJoined
            from gui.widgets.config_json_tree import ConfigJsonTree
            from gui.widgets.config_pages import ConfigPages
            from gui.widgets.config_tabs import ConfigTabs

            class Page_{safe_name}_Settings(ConfigPages):
                display_name = \"\"\"{module_name}\"\"\"
                page_type = 'main'
                icon_path = ':/resources/icon-tasks.png'

                def __init__(self, parent):
                    super().__init__(parent=parent)
                    self.pages = {{}}
        """