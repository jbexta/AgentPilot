from PySide6.QtWidgets import QMessageBox, QInputDialog
from typing_extensions import override

from src.gui.widgets.config_widget import ConfigWidget

from src.gui.util import find_main_widget
from src.utils import sql
from src.utils.helpers import display_message, display_message_box, convert_to_safe_case


class ConfigCollection(ConfigWidget):
    def __init__(self, parent):
        super().__init__(parent=parent)
        self.content = None
        self.pages = {}
        # self.hidden_pages = []  # !! #
        # self.include_in_breadcrumbs = False

    @override
    def load(self):
        current_page = self.content.currentWidget()
        if current_page and hasattr(current_page, 'load'):
            current_page.load()

    def add_page(self):  # todo dedupe
        edit_bar = getattr(self, 'edit_bar', None)
        if not edit_bar:
            return
        page_editor = edit_bar.page_editor
        if not page_editor:
            return
        if edit_bar.editing_module_id != page_editor.module_id:
            return

        new_page_name, ok = QInputDialog.getText(self, "Enter name", "Enter a name for the new page:")
        if not ok:
            return

        # safe_name = convert_to_safe_case(new_page_name)
        if new_page_name in self.pages:
            display_message(
                self,
                f"A page named '{new_page_name}' already exists.",
                title="Page Exists",
                icon=QMessageBox.Warning,
            )
            return

        from src.gui.builder import modify_class_add_page
        new_class = modify_class_add_page(edit_bar.editing_module_id, edit_bar.class_map, new_page_name)
        if new_class:
            # `config` is a table json column (a dict)
            # the code needs to go in the 'data' key
            sql.execute("""
                UPDATE modules
                SET config = json_set(config, '$.data', ?)
                WHERE id = ?
            """, (new_class, edit_bar.editing_module_id))

            from src.system import manager
            manager.load()  # _manager('modules')
            page_editor.load()
            page_editor.config_widget.widgets[0].reimport()

    def delete_page(self, page_name):
        retval = display_message_box(
            icon=QMessageBox.Warning,
            title="Delete page",
            text=f"Are you sure you want to permenantly delete the page '{page_name}'?",
            buttons=QMessageBox.Yes | QMessageBox.No,
        )
        if retval != QMessageBox.Yes:
            return

        edit_bar = getattr(self, 'edit_bar', None)
        if not edit_bar:
            return
        page_editor = edit_bar.page_editor
        if not page_editor:
            return
        if edit_bar.editing_module_id != page_editor.module_id:
            return

        safe_name = convert_to_safe_case(page_name)
        from src.gui.builder import modify_class_delete_page
        new_class = modify_class_delete_page(edit_bar.editing_module_id, edit_bar.class_map, safe_name)
        if new_class:
            # `config` is a table json column (a dict)
            # the code needs to go in the 'data' key
            sql.execute("""
                UPDATE modules
                SET config = json_set(config, '$.data', ?)
                WHERE id = ?
            """, (new_class, edit_bar.editing_module_id))

            from src.system import manager
            manager.load()  # _manager('modules')
            page_editor.load()
            page_editor.config_widget.widgets[0].reimport()

    def edit_page(self, page_name):
        from src.gui.pages.modules import PageEditor
        from src.system import manager
        page_modules = manager.modules.get_modules_in_folder(
            module_type='Pages',
            fetch_keys=('uuid', 'name',)
        )

        # get the id KEY where the name VALUE is page_name
        module_id = next((_id for _id, name in page_modules if name == page_name), None)
        if not module_id:
            return

        page_widget = self.pages[page_name]
        # setattr(page_widget, 'user_editing', True)
        if hasattr(page_widget, 'toggle_widget_edit'):
            page_widget.toggle_widget_edit(True)
            # page_widget.build_schema()  # !! #

        main = find_main_widget(self)
        if getattr(main, 'module_popup', None):
            main.module_popup.close()
            main.module_popup = None
        main.module_popup = PageEditor(main, module_id)
        main.module_popup.load()
        main.module_popup.show()  # todo dedupe