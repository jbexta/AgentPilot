from pathlib import Path


def test_Page_Files(self, main, ui):
    """Up / Back / Forward buttons walk the directory history and keep
    the path bar in sync."""
    import time
    from gui.demo import _run_on_main as run_on_main

    nav = self.nav_panel
    start = run_on_main(lambda: self.current_path)
    if start.parent == start:
        run_on_main(lambda: self.navigate_to(Path.home()))
        start = run_on_main(lambda: self.current_path)

    def assert_at(path, action):
        current = run_on_main(lambda: self.current_path)
        assert current == path, (
            f"{action}: expected {path}, at {current}"
        )
        path_text = run_on_main(self.path_bar.path_edit.text)
        assert path_text == str(path), (
            f"{action}: path bar shows {path_text!r}, expected {path}"
        )

    ui.testing('Up / Back / Forward navigation')
    for btn, expected, action in (
        (nav.up_btn, start.parent, 'Up'),
        (nav.back_btn, start, 'Back'),
        (nav.forward_btn, start.parent, 'Forward'),
        (nav.back_btn, start, 'Back'),
    ):
        ui.click_widget(btn)
        time.sleep(0.3)
        assert_at(expected, action)

    assert run_on_main(nav.forward_btn.isEnabled), (
        "Forward should be enabled after navigating back"
    )
