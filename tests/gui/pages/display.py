from utils import sql


def test_Page_Display_Settings(self, main, ui):
    """Theme tiles mirror the themes table and the current display config,
    and switching themes applies the theme's values to the display fields."""
    import time
    from gui.demo import _run_on_main as run_on_main

    themes = self.widgets[0]

    def tile_names():
        return run_on_main(lambda: [tile.name for tile in themes.tiles])

    def current_display():
        return run_on_main(
            lambda: self.get_current_display_config()['display'])

    def assert_theme_applied(theme_name):
        expected = run_on_main(
            lambda: themes.get_theme_display_config(theme_name))
        assert current_display() == expected, (
            f"Display fields don't match theme {theme_name!r}"
        )

    ui.testing('theme tiles match themes table')
    db_themes = list(sql.get_results(
        "SELECT name, config FROM themes", return_type='dict').keys())
    names = tile_names()
    assert names == db_themes, (
        f"Theme tiles {names} don't match themes table {db_themes}"
    )

    original = themes.selected
    if original is None:
        display = current_display()
        matching = [
            name for name in db_themes
            if run_on_main(lambda: themes.get_theme_display_config(name))
            == display
        ]
        assert not matching, (
            f"No theme tile selected but config matches {matching}"
        )
        return  # switching away would lose the custom config

    ui.testing('switching themes')
    assert_theme_applied(original)
    other = next((name for name in db_themes if name != original), None)
    if other is None:
        return

    for theme_name in (other, original):
        run_on_main(lambda: themes.select_theme(theme_name))
        time.sleep(0.5)
        assert_theme_applied(theme_name)
        assert themes.selected == theme_name
