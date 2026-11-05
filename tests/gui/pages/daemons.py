from PySide6.QtCore import Qt

from gui.pages.daemons import STATUS_COLORS, scan_daemons


def test_Page_Daemons_Settings(self, main, ui):
    """Rows mirror the daemon folders on disk and selecting one
    selects that row. Read-only: nothing is started or renamed."""
    import time
    from gui.demo import _run_on_main as run_on_main

    def tree_rows():
        def _impl():
            return [
                self.tree.topLevelItem(i).data(0, Qt.UserRole)
                for i in range(self.tree.topLevelItemCount())
            ]
        return run_on_main(_impl)

    ui.testing('daemon rows match disk')
    rows = tree_rows()
    expected = [row['name'] for row in scan_daemons()]
    names = [row['name'] for row in rows]
    assert names == expected, (
        f"Daemon rows {names} don't match daemons on disk {expected}"
    )
    for row in rows:
        assert row['status'] in STATUS_COLORS, (
            f"Daemon {row['name']!r} has unknown status {row['status']!r}"
        )

    ui.testing('selecting daemon rows')
    for name in names[:3]:
        ui.click_tree_item_cell(self.tree, name, 0)
        time.sleep(0.3)
        selected = run_on_main(self.selected_row)
        assert selected and selected['name'] == name, (
            f"Clicking {name!r} didn't select it"
        )
