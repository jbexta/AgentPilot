import asyncio
import os
import shutil

import qasync
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QCheckBox, QMessageBox
from gui.widgets.config_db_tree import ConfigDBTree
from gui.gui_utils.helpers import get_project_type_class, get_selected_pages, set_selected_pages
from utils.filesystem import get_application_path
from utils.helpers import display_message, mark_primary_buttons
from utils.sql import define_table
from plugins.projects.gui.project_types.general import GeneralProject
from plugins.projects.utils.new_project_dialog import NewProjectDialog

define_table('project_collections')
define_table('project_collection_items', relations=['collection_id'])


class Page_Projects(ConfigDBTree):
    display_name = 'Projects'
    icon_path = ":/resources/icon-workspace.png"
    page_type = 'main'  # either 'settings', 'main', or 'any' ('any' means it can be pinned between main and settings)

    def __init__(self, parent):
        super().__init__(
            parent=parent,
            manager='projects',  # todo name
            query="""
                SELECT
                    name,
                    id,
                    -- COALESCE(json_extract(config, '$.cwd'), '') as cwd,
                    config,
                    folder_id
                FROM projects
                ORDER BY pinned DESC, ordr, name COLLATE NOCASE""",
            schema=[
                {
                    'text': 'Name',
                    'key': 'name',
                    'type': str,
                    'stretch': True,
                },
                {
                    'text': 'id',
                    'key': 'id',
                    'type': int,
                    'visible': False,
                },
                {
                    'text': 'config',
                    'type': str,
                    'visible': False,
                },
            ],
            layout_type='horizontal',
            config_widget=None, # GeneralProject(parent=self),
            folder_config_widget=self.Folder_Config_Widget(parent=self),
            tree_header_hidden=True,
            readonly=True,
            searchable=True,
            filterable=True,
        )
        self.splitter.setSizes([200, 800])
        define_table('project_concepts', relations=['project_id'])
    
    def on_edited(self):
        self.config_widget.widgets[1].pages['Files'].load_config()

    def add_item(self, *, parent_id=None):
        from gui import system
        projects_dir = system.manager.config.get(
            'system.default_project_directory',
        ) or '{app_dir}/projects'
        projects_dir = projects_dir.replace(
            '{app_dir}', get_application_path(),
        )
        project_types = [
            name for name, _ in system.manager.modules.get_modules_in_folder(
                module_type='Project_types', fetch_keys=('name', 'class'),
            )
        ]
        dialog = NewProjectDialog(self, projects_dir, project_types)
        dialog.accepted.connect(lambda: self.add_project(
            dialog.name, dialog.path, dialog.project_type,
        ))
        dialog.show()

    def add_project(self, name, path, project_type):
        self._editing_manager = True
        try:
            item_id = self.manager.add(name=name, config={
                'working_dir': path, '_PROJECT_TYPE': project_type,
            })
        finally:
            self._editing_manager = False
        if item_id is not None:
            self.load(select_id=item_id)

    def delete_item(self):
        item_id = self.get_selected_item_id()
        if not item_id:
            super().delete_item()
            return

        name, path = self.db_connector.get_results(
            "SELECT name, json_extract(config, '$.working_dir') FROM projects WHERE id = ?",
            (item_id,),
        )[0]
        path = os.path.realpath(path) if path else ''
        app_dir = os.path.realpath(get_application_path())
        can_delete_folder = (
            os.path.isdir(path)
            and os.path.commonpath([path, app_dir]) != path
        )

        msg = QMessageBox(
            QMessageBox.Warning,
            'Delete Project',
            f'Delete the project "{name}"?',
            QMessageBox.Ok | QMessageBox.Cancel,
            self,
        )
        msg.button(QMessageBox.Ok).setText('Delete')
        msg.setDefaultButton(QMessageBox.Cancel)
        delete_folder_chk = None
        if can_delete_folder:
            msg.setInformativeText(path)
            delete_folder_chk = QCheckBox(
                'Also delete this folder and all its files', msg,
            )
            msg.setCheckBox(delete_folder_chk)

        def on_finished():
            if msg.clickedButton() != msg.button(QMessageBox.Ok):
                return
            self.remove_item(item_id)
            if delete_folder_chk and delete_folder_chk.isChecked():
                self.delete_folder(path)

        msg.setWindowModality(Qt.NonModal)
        msg.setAttribute(Qt.WA_DeleteOnClose)
        msg.finished.connect(on_finished)
        msg.show()
        mark_primary_buttons(msg)

    @qasync.asyncSlot()
    async def delete_folder(self, path):
        try:
            await asyncio.to_thread(shutil.rmtree, path)
        except OSError as e:
            display_message(
                f'Could not delete `{path}`:\n{e}', icon=QMessageBox.Warning,
            )

    def on_item_selected(self):
        item_id = self.get_selected_item_id()
        if not item_id:
            super().on_item_selected()
            return

        # # Save current tab state before potential widget recreation
        # page_map = None
        # if self.config_widget is not None:
        #     page_map = get_selected_pages(self.config_widget.widgets[2], stop_at_tree=False)
        # print(f"[DEBUG] page_map saved: {page_map}")
        last_tab = None
        if self.config_widget is not None:
            tabs = self.config_widget.widgets[2]
            current = tabs.content.currentWidget()
            last_tab = next(
                (name for name, page in tabs.pages.items()
                 if page is current),
                None,
            )

        json_config = self.db_connector.get_scalar(
            f"SELECT config FROM `{self.table_name}` WHERE id = ?",
            (item_id,), load_json=True
        )
        project_type = json_config.get('_PROJECT_TYPE', 'general') if json_config else 'general'
        project_type_class = get_project_type_class(project_type)
        if not project_type_class:
            display_message(
                message=f"Project type module '{project_type}' not found.",
                icon=QMessageBox.Warning,
            )
            project_type_class = GeneralProject

        is_same = isinstance(self.config_widget, project_type_class)
        if not is_same:
            if self.config_widget is not None:
                self.config_layout.removeWidget(self.config_widget)
                self.config_widget.deleteLater()
            self.config_widget = project_type_class(self)
            self.config_layout.insertWidget(0, self.config_widget)
            self.config_widget.build_schema()

        super().on_item_selected()

        tabs = self.config_widget.widgets[2]
        tabs.goto_page(last_tab if last_tab in tabs.pages else 'Chat')

        # # Restore tab state
        # if page_map:
        #     set_selected_pages(self.config_widget.widgets[2], page_map)
        #     print(f"[DEBUG] tab index after restore: {self.config_widget.widgets[2].content.currentIndex() if hasattr(self.config_widget, 'widgets') and len(self.config_widget.widgets) > 2 else 'N/A'}")

    def save_config(self):
        super().save_config()
        project_type = self.config_widget.get_config().get(
            '_PROJECT_TYPE', 'general'
        )
        project_type_class = get_project_type_class(project_type)
        if not project_type_class:
            project_type_class = GeneralProject
        if not isinstance(self.config_widget, project_type_class):
            self.on_item_selected()