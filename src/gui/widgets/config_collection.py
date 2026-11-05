import json

from PySide6.QtWidgets import QMessageBox
from typing_extensions import override

from gui import system


from gui.gui_utils.helpers import find_main, save_table_config
from gui.widgets.config_widget import ConfigWidget
from utils import sql
from utils.helpers import display_message, display_message_box, convert_to_safe_case, format_llm_tools, get_text, readable_class_name, set_module_type


@set_module_type('Widgets')
class ConfigCollection(ConfigWidget):
    agent_list_label = 'Pages'

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
    def get_agent_visualisation(self, refs):
        from textwrap import indent
        parts = [f'{readable_class_name(self)}:']
        tools = format_llm_tools(self, refs)
        if tools:
            parts.append(indent(tools, '    '))
        own = self.agent_visualisation()
        if own:
            parts.append(indent(own, '    '))
        parts.append(f'    {self.agent_list_label}:')
        current = self.content.currentWidget()
        current_name = None
        for page_name, page in self.pages.items():
            if page is current:
                current_name = page_name
                continue
            parts.append(f'        - {page_name}')
        if current_name is not None:
            parts.append(f'        - {current_name} (current)')
            sub = current.get_agent_visualisation(refs) if hasattr(current, 'get_agent_visualisation') else ''
            if sub:
                parts.append(indent(sub, ' ' * 12))
        return '\n'.join(parts)

    @override
    def get_config(self):
        config = {}
        format_block_keys = []
        for page_name, page in self.pages.items():
            if hasattr(self.content, 'tabBar'):
                is_vis = self.content.tabBar().isTabVisible(self.content.indexOf(page))
            else:
                page_button = self.settings_sidebar.page_buttons.get(page_name, None)
                # isVisibleTo, not isVisible: the latter is False whenever an
                # ancestor is hidden, so saving while this collection isn't the
                # displayed page would drop every page's config.
                is_vis = (page_button.isVisibleTo(self.settings_sidebar)
                          if page_button else False)

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

    @staticmethod
    def _write_module_data(module_id, new_class):
        """Update ``modules.config.data`` for the edited module.

        Routes through :func:`save_table_config` so the shared autobake
        hook fires (matches what happens when module source is edited
        via PageEditor).
        """
        config = sql.get_scalar(
            "SELECT config FROM modules WHERE id = ?",
            (module_id,), load_json=True,
        ) or {}
        config['data'] = new_class
        save_table_config(
            table_name='modules',
            item_id=module_id,
            value=json.dumps(config),
        )

    def add_page(self):  # todo dedupe
        result = self.get_edit_bar()
        edit_bar, page_editor = result if result else (None, None)
        if not edit_bar:
            return

        new_page_name, ok = get_text(self, "Enter name", "Enter a name for the new page:")
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
            self._write_module_data(edit_bar.editing_module_id, new_class)
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
                self._write_module_data(edit_bar.editing_module_id, new_class)
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
        # from gui.pages.modules import PageEditor
        #
        # page_widget = self.pages[page_name]
        # if hasattr(page_widget, 'toggle_widget_edit'):
        #     page_widget.toggle_widget_edit(True)
        #
        # main = find_main()
        # if getattr(main, 'module_popup', None):
        #     main.module_popup.close()
        #     main.module_popup = None
        # main.module_popup = PageEditor(main, page_name)
        # main.module_popup.load()
        # main.module_popup.show()
        find_main().open_page_editor()