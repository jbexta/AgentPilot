from unittest import SkipTest


def test_ConfigPages(self, main, ui):
    # Visit every page, verify it becomes current, and run its own hooks
    # while it is visible (this widget owns its pages' subtrees).
    if not self.pages or not ui.run_on_main(self.isVisible):
        raise SkipTest(f"{type(self).__name__}: no visible pages")
    original = ui.run_on_main(self.content.currentWidget)
    for page_name, page in self.pages.items():
        ui.testing(f'{type(self).__name__}: {page_name} page')
        ui.run_on_main(lambda: self.goto_page(page_name))
        ui.wait_until(lambda: self.content.currentWidget() is page,
                      message=f"ConfigPages.goto_page({page_name!r}) did not make the page current")
        ui.test_widgets(page, main)
    original_name = next((n for n, p in self.pages.items() if p is original), None)
    if original_name:
        ui.run_on_main(lambda: self.goto_page(original_name))
