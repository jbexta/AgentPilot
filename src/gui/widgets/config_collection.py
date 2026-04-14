from PySide6.QtWidgets import QMessageBox, QInputDialog
from typing_extensions import override

from gui import system


from gui.util import find_main
from gui.widgets.config_widget import ConfigWidget
from utils import sql
from utils.helpers import display_message, display_message_box, convert_to_safe_case, set_module_type


@set_module_type('Widgets')
class ConfigCollection(ConfigWidget):
    def __init__(self, parent):
        super().__init__(parent=parent)
        self.content = None
        self.pages = {}

    @override
    def load(self):
        current_page = self.content.currentWidget()
        if current_page and hasattr(current_page, 'load'):
            current_page.load()

    @override
    def get_config(self):
        config = {}
        format_block_keys = []
        for page_name, page in self.pages.items():
            if hasattr(self.content, 'tabBar'):
                is_vis = self.content.tabBar().isTabVisible(self.content.indexOf(page))
            else:
                page_button = self.settings_sidebar.page_buttons.get(page_name, None)
                is_vis = page_button.isVisible() if page_button else False

            if (not getattr(page, 'propagate_config', True) or
                    not hasattr(page, 'get_config') or
                    # not getattr(page, 'conf_namespace', None) or
                    not is_vis
            ):
                continue

            page_config = page.get_config()
            fbk = page_config.pop('_format_block_keys', [])
            format_block_keys.extend(fbk)
            config.update(page_config)

        if format_block_keys:
            config['_format_block_keys'] = format_block_keys
        return config

    def add_page(self):  # todo dedupe
        result = self.get_edit_bar()
        edit_bar, page_editor = result if result else (None, None)
        if not edit_bar:
            return

        new_page_name, ok = QInputDialog.getText(self, "Enter name", "Enter a name for the new page:")
        if not ok:
            return

        # safe_name = convert_to_safe_case(new_page_name)
        if new_page_name in self.pages:
            display_message(
                f"A page named '{new_page_name}' already exists.",
                title="Page Exists",
                icon=QMessageBox.Warning,
            )
            return

        from gui.builder import modify_class_add_page
        new_class = modify_class_add_page(edit_bar.editing_module_id, edit_bar.class_map, new_page_name)
        if new_class:
            # `config` is a table json column (a dict)
            # the code needs to go in the 'data' key
            sql.execute("""
                UPDATE modules
                SET config = json_set(config, '$.data', ?)
                WHERE id = ?
            """, (new_class, edit_bar.editing_module_id))

            system.manager.load()  # _manager('modules')
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

        result = self.get_edit_bar()
        edit_bar, page_editor = result if result else (None, None)
        if edit_bar:
            safe_name = convert_to_safe_case(page_name)
            from gui.builder import modify_class_delete_page
            new_class = modify_class_delete_page(edit_bar.editing_module_id, edit_bar.class_map, safe_name)
            if new_class:
                sql.execute("""
                    UPDATE modules
                    SET config = json_set(config, '$.data', ?)
                    WHERE id = ?
                """, (new_class, edit_bar.editing_module_id))

                system.manager.load()
                page_editor.load()
                page_editor.config_widget.widgets[0].reimport()
                self.pages.pop(page_name, None)
                self.build_schema()
        else:
            module_id = sql.get_scalar(
                "SELECT id FROM modules WHERE name = ?", (page_name,)
            )
            if not module_id:
                return
            system.manager.modules.delete(module_id)
            self.pages.pop(page_name, None)
            self.build_schema()

    def edit_page(self, page_name):
        from gui.pages.modules import PageEditor

        page_widget = self.pages[page_name]
        if hasattr(page_widget, 'toggle_widget_edit'):
            page_widget.toggle_widget_edit(True)

        main = find_main()
        if getattr(main, 'module_popup', None):
            main.module_popup.close()
            main.module_popup = None
        main.module_popup = PageEditor(main, page_name)
        main.module_popup.load()
        main.module_popup.show()