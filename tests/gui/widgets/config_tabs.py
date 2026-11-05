from unittest import SkipTest


def test_ConfigTabs(self, main, ui):
    # Visit every tab, verify it becomes current, and run its own hooks
    # while it is visible (this widget owns its tabs' subtrees).
    if not self.pages or not ui.run_on_main(self.isVisible):
        raise SkipTest(f"{type(self).__name__}: no visible tabs")
    original = ui.run_on_main(self.content.currentWidget)
    for page_name, page in self.pages.items():
        if ui.run_on_main(lambda: self.content.indexOf(page)) == -1:
            continue  # not added as a tab (e.g. filtered out)
        ui.testing(f'{type(self).__name__}: {page_name} tab')
        ui.run_on_main(lambda: self.goto_page(page_name))
        ui.wait_until(lambda: self.content.currentWidget() is page,
                      message=f"ConfigTabs.goto_page({page_name!r}) did not make the tab current")
        ui.test_widgets(page, main)
    original_name = next((n for n, p in self.pages.items() if p is original), None)
    if original_name:
        ui.run_on_main(lambda: self.goto_page(original_name))
