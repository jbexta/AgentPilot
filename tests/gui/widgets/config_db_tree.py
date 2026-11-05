from unittest import SkipTest

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QInputDialog, QTreeWidgetItem

from gui.widgets.config_db_tree import ConfigDBTree


def test_ConfigDBTree(self, main, ui):
    """Generic CRUD smoke test inherited by every ConfigDBTree.

    Clicks each tree toolbar button (Filter, New Folder, Add, Delete) and
    drives the create -> read -> delete flow against the live database
    (which is the disposable ``test_data.db`` during a test run).

    Execution model: the scaffold runs this on a worker thread and drives
    the GUI with synthesized OS input. ``add_item`` / ``add_folder`` open a
    modal ``QInputDialog`` and ``delete_item`` a modal ``QMessageBox`` —
    each blocks the *main* thread, but the worker can still type into / click
    them via pyautogui. The scaffold dismisses any modal left open after
    each hook, so a failure here can't wedge later tests.

    Trees without the standard name prompt (no ``add_item_options``, or an
    overridden ``add_item``) opt out by raising ``SkipTest`` instead of
    asserting against a contract they don't follow.
    """
    # CRUD needs a real table + manager + the toolbar; bail out otherwise.
    buttons = getattr(getattr(self, 'tree_buttons', None), 'inner_widget', None)
    if buttons is None or self.table_name is None or self.manager is None:
        raise SkipTest(f"{type(self).__name__}: no toolbar, table or manager")

    cls = type(self).__name__
    test_item = 'ZZ_crud_test_item'
    test_folder = 'ZZ_crud_test_folder'

    def action(attr):
        """Return a visible toolbar QAction by attribute name, else None."""
        a = getattr(buttons, attr, None)
        return a if a is not None and ui.run_on_main(a.isVisible) else None

    def row_count(name):
        return self.db_connector.get_scalar(
            f"SELECT COUNT(*) FROM `{self.table_name}` WHERE name = ?", (name,)
        )

    def enter_name(name):
        ui.wait_for_modal(QInputDialog)
        ui.type_text(name)
        ui.press('enter')

    def first_real_item():
        def _find():
            items = self.tree.findItems('', Qt.MatchContains | Qt.MatchRecursive)
            return next((i.text(0) for i in items if i.data(0, Qt.UserRole) != 'folder'), None)
        return ui.run_on_main(_find)

    # --- CREATE an item via the Add button + name prompt -------
    # Trees without a name prompt (no add_item_options, or a custom
    # add_item) don't follow this contract and opt out.
    btn_add = action('btn_add')
    has_name_prompt = self.add_item_options and type(self).add_item is ConfigDBTree.add_item
    if btn_add is None or not has_name_prompt:
        raise SkipTest(f"{type(self).__name__}: no standard Add name prompt")
    ui.testing(f'{cls}: add item')
    ui.click_widget(btn_add)
    enter_name(test_item)
    ui.wait_until(lambda: row_count(test_item) == 1,
                  message=f"{cls}: Add did not insert {test_item!r} into {self.table_name!r}")
    ui.wait_until(lambda: test_item in ui.tree_names(self.tree),
                  message=f"{cls}: Add did not show a row named {test_item!r}")

    # --- READ: selecting the new row selects/loads it ----------
    ui.testing(f'{cls}: select item')
    ui.click_tree_item_cell(self.tree, test_item, 0)
    selected_name = lambda: self.db_connector.get_scalar(
        f"SELECT name FROM `{self.table_name}` WHERE id = ?",
        (self.get_selected_item_id(),),
    )
    ui.wait_until(lambda: selected_name() == test_item,
                  message=f"{cls}: selecting {test_item!r} did not select its row")

    # --- test the config widget(s) against this freshly created,
    # selected item (e.g. the WorkflowSettings panel for an agent).
    # Done while the new item is selected, before it's deleted, so the
    # embedded config has a valid item loaded and a visible panel. ---
    if self.config_widget is not None:
        ui.test_widgets(self.config_widget, main)

    # --- CREATE then DELETE a folder (if this tree has folders) -
    btn_new_folder = action('btn_new_folder')
    btn_delete = action('btn_delete')
    assert btn_delete is not None, (
        f"{cls}: no Delete button available to remove the test row"
    )
    if btn_new_folder is not None:
        ui.testing(f'{cls}: add and delete folder')
        ui.click_widget(btn_new_folder)
        enter_name(test_folder)
        ui.wait_until(lambda: test_folder in ui.tree_names(self.tree),
                      message=f"{cls}: New Folder did not create {test_folder!r}")
        ui.click_tree_item_cell(self.tree, test_folder, 0)
        current_text = lambda: (self.tree.currentItem() or QTreeWidgetItem()).text(0)
        ui.wait_until(lambda: current_text() == test_folder,
                      message=f"{cls}: clicking folder {test_folder!r} did not select it")
        ui.click_widget(btn_delete)
        ui.confirm()
        ui.wait_until(lambda: test_folder not in ui.tree_names(self.tree),
                      message=f"{cls}: Delete did not remove folder {test_folder!r}")

    # --- DELETE the item via the Delete button + confirm box ---
    ui.testing(f'{cls}: delete item')
    ui.click_tree_item_cell(self.tree, test_item, 0)
    ui.wait_until(lambda: selected_name() == test_item,
                  message=f"{cls}: clicking {test_item!r} did not select it")
    ui.click_widget(btn_delete)
    ui.confirm()
    ui.wait_until(lambda: row_count(test_item) == 0,
                  message=f"{cls}: Delete did not remove {test_item!r} from {self.table_name!r}")
    ui.wait_until(lambda: test_item not in ui.tree_names(self.tree),
                  message=f"{cls}: Delete did not remove the row {test_item!r}")

    # Leave a real item selected so config-widget tests that run after
    # this one have a populated, visible config panel.
    name = first_real_item()
    if name is not None:
        ui.click_tree_item_cell(self.tree, name, 0)
