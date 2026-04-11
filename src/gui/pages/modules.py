"""
Modules Page Module.

This module provides the modules management page for the Agent Pilot GUI interface.
The page enables users to manage, install, and configure the various module types
that extend Agent Pilot's functionality, including custom pages, widgets, providers,
and other extensible components.

Key Features:
- Module installation and uninstallation
- Module type management (managers, pages, widgets, etc.)
- Runtime module loading and configuration
- Module dependency tracking
- Custom module development support
- Module status monitoring and updates
- Integration with the dynamic module system

The page provides comprehensive module lifecycle management, enabling users to
extend Agent Pilot's capabilities through custom and third-party modules.
"""

from PySide6.QtGui import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget, QMessageBox, QSizePolicy

from gui import system
from gui.widgets.config_widget import ConfigWidget
from gui.widgets.config_db_tree import ConfigDBTree
from gui.widgets.config_fields import ConfigFields
from gui.widgets.config_joined import ConfigJoined
from gui.util import find_main, CVBoxLayout, CHBoxLayout, IconButton, FramelessResizeMixin
from utils import sql
from utils.helpers import display_message, set_module_type


@set_module_type(module_type='Pages')
class Page_Module_Settings(ConfigDBTree):
    display_name = 'Modules'
    icon_path = ":/resources/icon-jigsaw.png"
    page_type = 'main'  # either 'settings', 'main', or 'any' ('any' means it can be pinned between main and settings)

    def __init__(self, parent):
        super().__init__(
            parent=parent,
            table_name='modules',
            manager='modules',
            query="""
                SELECT
                    name,
                    id,
                    baked,
                    -- COALESCE(json_extract(config, '$.enabled'), 1),
                    folder_id
                FROM modules
                ORDER BY pinned DESC, ordr, name COLLATE NOCASE""",
            schema=[
                {
                    'text': 'Modules',
                    'key': 'name',
                    'type': str,
                    'stretch': True,
                },
                {
                    'key': 'id',
                    'type': int,
                    'visible': False,
                },
                {
                    'key': 'baked',
                    'type': int,
                    'visible': False,
                },
            ],
            # extra_data=lambda: self.extra_data(),
            add_item_options={'title': 'Add module', 'prompt': 'Enter a name for the module:'},
            del_item_options={'title': 'Delete module', 'prompt': 'Are you sure you want to delete this module?'},
            folder_key='modules',
            readonly=False,
            layout_type='horizontal',
            tree_header_hidden=True,
            config_widget=Module_Config_Widget(parent=self),
            folder_config_widget=self.Folder_Config_Widget(parent=self),
            searchable=True,
            default_item_icon=':/resources/icon-jigsaw-solid.png',
        )
        self.splitter.setSizes([400, 1000])
    
    def load(self, **kwargs):
        super().load(**kwargs)
        disabled_ids = sql.get_results(
            "SELECT id FROM modules WHERE COALESCE(json_extract(config, '$.enabled'), 1) = 0",
            return_type='list'
        )
        self.tree._disabled_ids = disabled_ids

    def unbake_item(self):
        item_id = self.get_selected_item_id()
        if not item_id:
            return
        sql.execute('UPDATE modules SET baked = 0 WHERE id = ?', (item_id,))
        self.load()

    def bake_item(self, force=False):
        item_id = self.get_selected_item_id()
        if not item_id:
            return

        # # Get module data from database
        module_name = sql.get_scalar('SELECT name FROM modules WHERE id = ?', (item_id,))
        module_config = sql.get_scalar('SELECT config FROM modules WHERE id = ?', (item_id,), load_json=True)
        
        source_code = module_config.get('data', '')
        file_path = get_module_abs_path(item_id)
        
        # Check if file exists and ask for confirmation if not forcing
        if file_path.exists():
            if not force:
                retval = QMessageBox.question(
                    self,
                    "File Exists",
                    f"The file {file_path} already exists. Do you want to overwrite it?",
                    QMessageBox.Yes | QMessageBox.No
                )
                if retval != QMessageBox.Yes:
                    return
        
        try:
            # Ensure directory exists
            file_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Write source code to file
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(source_code)
            
            # Update the module to mark it as baked
            sql.execute('UPDATE modules SET baked = 1 WHERE id = ?', (item_id,))
            
            if not force:
                display_message(
                    message=f"Successfully baked module {module_name} to {file_path}",
                    icon=QMessageBox.Information,
                )
            
        except Exception as e:
            display_message(
                message=f"Error baking module {module_name}: {e}",
                icon=QMessageBox.Critical,
            )
    
    def on_context_menu(self, menu):
        item_id = self.get_selected_item_id()
        if not item_id:
            return
        enabled = sql.get_scalar(
            "SELECT COALESCE(json_extract(config, '$.enabled'), 1) FROM modules WHERE id = ?",
            (item_id,)
        )
        menu.addSeparator()
        btn = menu.addAction('Enable' if not enabled else 'Disable')
        btn.triggered.connect(lambda: self.toggle_module_enabled(item_id, enabled))

    def toggle_module_enabled(self, module_id, currently_enabled):
        new_val = 0 if currently_enabled else 1
        sql.execute("""
            UPDATE modules SET config = json_set(config, '$.enabled', ?)
            WHERE id = ?
        """, (new_val, module_id))
        system.manager.load()
        main = find_main()
        main.main_pages.build_schema()
        if 'settings' in main.main_pages.pages:
            main.main_pages.pages['settings'].build_schema()

    def on_item_selected(self):
        super().on_item_selected()

        item_id = self.get_selected_item_id()
        if not item_id:
            return
        
        folder_id = sql.get_scalar('SELECT folder_id FROM modules WHERE id = ?', (item_id,))
        if not folder_id:
            return
        folder_name = sql.get_scalar('SELECT name FROM folders WHERE id = ?', (folder_id,))
        if not folder_name:
            return
        controller = self.manager.type_controllers.get(folder_name.lower())
        if not controller:
            return
        
class Module_Config_Widget(ConfigJoined):
    def __init__(self, parent):
        super().__init__(parent=parent)
        self.widgets = [
            self.Module_Config_Fields(parent=self),
        ]

    class Module_Config_Fields(ConfigFields):
        def __init__(self, parent):
            super().__init__(parent=parent)
            # # self.IS_DEV_MODE = True
            # self.main = find_main()
            self.status = 'unloaded'  # 'loaded', 'unloaded', 'modified', 'error', 'externally modified'
            self.schema = [
                {
                    'text': 'Avatar',
                    'key': 'icon_path',
                    'type': 'image',
                    'diameter': 30,
                    'circular': False,
                    'border': False,
                    'default': ':/resources/icon-jigsaw-solid.png',
                    'label_position': None,
                    'row_key': 0,
                },
                {
                    'text': 'Name',
                    'type': str,
                    'default': 'Unnamed module',
                    'stretch_x': True,
                    'text_size': 14,
                    # 'text_alignment': Qt.AlignCenter,
                    'label_position': None,
                    'transparent': True,
                    'row_key': 0,
                },
                {
                    'text': '',
                    'key': 'toggle_description',
                    'type': 'button_toggle',
                    # 'checkable': True,
                    'default': False,
                    'icon_path': ':/resources/icon-description.png',
                    'tooltip': 'Toggle description',
                    'label_position': None,
                    'row_key': 0,
                },
                {
                    'text': 'Description',
                    'type': str,
                    'default': '',
                    'num_lines': 10,
                    'stretch_x': True,
                    'stretch_y': True,
                    'transparent': True,
                    'visibility_predicate': lambda fields: fields.config.get('toggle_description', False),
                    'placeholder_text': 'Description',
                    'gen_block_folder_name': 'todo',
                    'wrap_text': True,
                    'monospaced': True,
                    'label_position': None,
                },
                {
                    'text': 'Load on startup',
                    'type': bool,
                    'default': True,
                    'row_key': 1,
                },
                {
                    'text': 'Load && run',
                    'key': 'load_button',
                    'type': 'button',
                    'tooltip': 'Re-import the module and execute it',
                    'target': self.reimport,
                    'label_position': None,
                    'row_key': 1,
                },
                {
                    'text': 'Unload',
                    'key': 'unload_button',
                    'type': 'button',
                    'tooltip': 'Unload the module',
                    'target': self.unload,
                    'label_position': None,
                    'row_key': 1,
                },
                {
                    'text': 'Data',
                    'type': str,
                    'default': '',
                    'num_lines': 2,
                    'stretch_x': True,
                    'stretch_y': True,
                    'highlighter': 'python',
                    'fold_mode': 'python',
                    'monospaced': True,
                    'gen_block_folder_name': 'page_module',
                    'label_position': None,
                },
            ]

        def after_init(self):
            self.lbl_status = QLabel(self)
            self.lbl_status.setProperty("class", 'dynamic_color')
            self.lbl_status.setMaximumWidth(250)
            self.lbl_status.move(40, 30)
        
        def update_config(self):
            module_id = self.get_item_id()
            module_metadata = sql.get_scalar('SELECT metadata FROM modules WHERE id = ?', (module_id,), load_json=True)
            module_hash = module_metadata.get('hash')

            super().update_config()
        
        def get_item_id(self):
            return self.parent.parent.get_selected_item_id()
        
        def load(self):
            super().load()

            module_id = self.get_item_id()
            # module_metadata = system.manager.modules.get_cell(module_id, 'metadata')
            module_metadata = sql.get_scalar('SELECT metadata FROM modules WHERE id = ?', (module_id,), load_json=True)
            if not module_metadata:
                self.set_status('Unloaded')
                return

            module_hash = module_metadata.get('hash')
            is_baked = sql.get_scalar('SELECT baked FROM modules WHERE id = ?', (module_id,)) == 1
            is_loaded = False  # module_id in system.manager.modules.loaded_module_hashes
            if is_baked:
                baked_hash = sql.get_scalar('SELECT uuid FROM modules WHERE id = ?', (module_id,))

                self.set_status('Baked')
                
            elif is_loaded:
                loaded_hash = system.manager.modules.loaded_module_hashes[module_id]
                is_modified = module_hash != loaded_hash
                if is_modified:
                    self.set_status('Modified')
                else:
                    self.set_status('Loaded')
            else:
                self.set_status('Unloaded')

        def set_status(self, status, text=None):
            if text is None:
                text = status
            status_color_classes = {
                'Loaded': '#6aab73',
                'Unloaded': '#B94343',
                'Baked': '#438BB9',
                'Modified': '#438BB9',
                'Error': '#B94343',
                'Externally Modified': '#B94343',
            }
            can_reimport = status in ['Modified', 'Unloaded']
            self.load_button_wgt.setVisible(can_reimport)
            self.unload_button_wgt.setVisible(status == 'Loaded')
            self.lbl_status.setText(text)
            self.lbl_status.setStyleSheet(f"color: {status_color_classes[status]};")

        def reimport(self):
            module_id = self.get_item_id()
            if not module_id:
                return

            try:
                row = sql.get_results(
                    "SELECT m.id, m.uuid, m.name, m.config, m.metadata, "
                    "(SELECT fp.name FROM folders fp WHERE fp.id = m.folder_id) AS folder_path "
                    "FROM modules m WHERE m.id = ?",
                    (module_id,)
                )
                if not row:
                    self.set_status('Error', 'Module not found in database')
                    return
                row = row[0]
                module_name = row[2]
                folder_name = row[5]
                if not folder_name:
                    self.set_status('Error', 'Module folder not found')
                    return
                controller = system.manager.modules.type_controllers.get(folder_name.lower())
                if not controller:
                    self.set_status('Error', f'No controller for type: {folder_name}')
                    return
                module_path = controller.get_module_path(module_name)
                controller.load_db_module(module_path, row)
                self.set_status('Loaded')
                if folder_name.lower() == 'pages':
                    main = find_main()
                    main.main_pages.build_schema()
            except Exception as e:
                self.set_status('Error', f"Error: {str(e)}")

        def unload(self):
            module_id = self.get_item_id()
            if not module_id:
                return

            module_name = sql.get_scalar(
                "SELECT name FROM modules WHERE id = ?", (module_id,)
            )
            folder_id = sql.get_scalar(
                "SELECT folder_id FROM modules WHERE id = ?", (module_id,)
            )
            folder_name = sql.get_scalar(
                "SELECT name FROM folders WHERE id = ?", (folder_id,)
            ) if folder_id else None

            if folder_name and module_name:
                controller = system.manager.modules.type_controllers.get(folder_name.lower())
                if controller:
                    import sys as _sys
                    module_path = controller.get_module_path(module_name)
                    if module_path in _sys.modules:
                        del _sys.modules[module_path]
                    if module_name in controller:
                        del controller[module_name]

            self.set_status('Unloaded')
            if folder_name and folder_name.lower() == 'pages':
                main = find_main()
                main.main_pages.build_schema()


def get_module_file_path(module_id, module_name=None):
    """Resolve a module ID to a relative file path.

    Parameters
    ----------
    module_id : int
        Database ID of the module.
    module_name : str, optional
        Module name override. Queried from DB if not provided.

    Returns
    -------
    pathlib.Path or None
        Relative path like ``src/gui/pages/foo.py``, or ``None``
        if the module cannot be resolved.
    """
    from pathlib import Path

    module_config = sql.get_scalar(
        'SELECT config FROM modules WHERE id = ?',
        (module_id,), load_json=True,
    )
    folder_id = sql.get_scalar(
        'SELECT folder_id FROM modules WHERE id = ?',
        (module_id,),
    )
    if module_name is None:
        module_name = sql.get_scalar(
            'SELECT name FROM modules WHERE id = ?',
            (module_id,),
        )

    if not module_config or not module_name:
        return None

    folder_name = None
    if folder_id:
        folder_name = sql.get_scalar(
            'SELECT name FROM folders WHERE id = ?',
            (folder_id,),
        )
    if not folder_name:
        print(f'Folder name not found for module {module_name} in folder {folder_id}')
        return None

    type_controller = system.manager.modules.type_controllers.get(
        folder_name.lower(),
    )
    load_to_path = getattr(type_controller, 'load_to_path', None)
    if not load_to_path:
        print(f'Load to path not found for module {module_name} in folder {folder_name}')
        return None

    base_path = f"src/{load_to_path.replace('.', '/')}"
    return Path(base_path) / f"{module_name.lower()}.py"


def get_module_abs_path(module_id, module_name=None):
    """Resolve a module ID to an absolute file path.

    Combines :func:`get_module_file_path` with the Application
    project's ``working_dir``.

    Returns
    -------
    pathlib.Path or None
    """
    from pathlib import Path

    rel_path = get_module_file_path(module_id, module_name=module_name)
    if rel_path is None:
        return None

    app_config = sql.get_scalar(
        "SELECT config FROM projects WHERE name = 'Application'",
        load_json=True,
    )
    if not app_config:
        return None

    working_dir = app_config.get('working_dir', '')
    if not working_dir:
        return None

    return Path(working_dir) / rel_path


class PageEditor(FramelessResizeMixin, ConfigWidget):
    def __init__(self, main, module_name):
        super().__init__(parent=main)
        from plugins.projects.gui.project_types.application import (
            ApplicationProject,
        )

        self.main = main
        self.module_name = module_name
        self.layout = CVBoxLayout(self)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.init_frameless_resize()
        self.setMinimumSize(300, 200)
        self.resize(500, self.main.height())
        self._snapped = True
        self._unsnapped_height = self.main.height()
        self._snap_threshold = 20

        # Title bar with close button
        self.titlebar = QWidget(parent=self)
        self.titlebar_layout = QHBoxLayout(self.titlebar)
        self.lbl_title = QLabel(parent=self.titlebar)
        self.lbl_title.setSizePolicy(
            QSizePolicy.Expanding, QSizePolicy.Preferred,
        )
        font = self.lbl_title.font()
        font.setBold(True)
        self.lbl_title.setFont(font)
        self.titlebar_layout.addWidget(self.lbl_title)
        self.btn_close = IconButton(
            parent=self.titlebar,
            icon_path=':/resources/close.png',
            # icon_size_percent=0.5,
            size=20,
        )
        self.btn_close.clicked.connect(self.close)
        self.titlebar_layout.addWidget(self.btn_close)
        self.layout.addWidget(self.titlebar)

        self.lbl_title.setText(f'Editing module > {module_name}')

        # Application project widget
        self.project_widget = ApplicationProject(parent=self)
        self.project_widget.build_schema()
        self.layout.addWidget(self.project_widget)

        # Hide the Project_Fields row (Path picker + project type)
        self.project_widget.widgets[0].hide()

        # Hide the 'Block Maps' tab
        bottom_tabs = self.project_widget.widgets[2]
        for i in range(bottom_tabs.content.count()):
            if bottom_tabs.content.tabText(i) == 'Block Maps':
                bottom_tabs.content.setTabVisible(i, False)
                break

    def close(self):
        if hasattr(self, 'project_widget'):
            poll_timer = getattr(self.project_widget, '_poll_timer', None)
            if poll_timer:
                poll_timer.stop()
        self.hide()

    def _move_window(self, global_pos):
        if self._snapped:
            diff = global_pos.x() - self._mouse_global_pos.x()
            if abs(diff) < self._snap_threshold:
                return
            self._snapped = False
            self.resize(self.width(), self._unsnapped_height)

        super()._move_window(global_pos)

        right_edge = self.x() + self.width()
        main_left = self.main.x()
        if abs(right_edge - main_left) < self._snap_threshold:
            self._unsnapped_height = self.height()
            self._snapped = True
            self._snap_to_main()

    def _snap_to_main(self):
        self.move(self.main.x() - self.width(), self.main.y())
        self.resize(self.width(), self.main.height())

    def showEvent(self, event):
        self._snap_to_main()
        super().showEvent(event)

    def load(self):
        project_id = sql.get_scalar(
            "SELECT id FROM projects WHERE name = 'Application'",
        )
        app_config = sql.get_scalar(
            "SELECT config FROM projects WHERE name = 'Application'",
            load_json=True,
        )
        if not app_config:
            return
        self.project_widget.load_config(app_config)

        file_tree = self.project_widget.widgets[1]
        file_tree.load()

        # Load the tasks tree with the correct project ID
        if project_id:
            bottom_tabs = self.project_widget.widgets[2]
            tasks_tree = bottom_tabs.pages.get('Chat')
            if tasks_tree:
                tasks_tree.kind = f'PROJECT:{project_id}'
                tasks_tree.folder_key = f'project:{project_id}:task'
                tasks_tree.load()

        controller = system.manager.modules.type_controllers.get('pages')
        if controller and controller.load_to_path:
            import os
            module_file = self.module_name.lower() + '.py'

            # Core path
            core_path = os.path.join(
                'src', controller.load_to_path.replace('.', os.sep), module_file,
            )
            if os.path.isfile(core_path):
                file_tree.navigate_to(os.path.abspath(core_path))
            else:
                # Plugin paths
                for fs_path, _dotted in controller.get_plugin_module_dirs():
                    candidate = os.path.join(fs_path, module_file)
                    if os.path.isfile(candidate):
                        file_tree.navigate_to(os.path.abspath(candidate))
                        break