from PySide6.QtWidgets import QMessageBox
from gui.widgets.config_db_tree import ConfigDBTree
from gui.util import get_project_type_class, get_selected_pages, set_selected_pages
from utils.helpers import display_message
from utils.sql import define_table
from plugins.projects.gui.project_types.general import GeneralProject


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
        self.config_widget.widgets[1].load_config()
    
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
        print(f"[DEBUG] is_same={is_same}, widget={type(self.config_widget)}, class={project_type_class}")
        if not is_same:
            print("Not same")
            if self.config_widget is not None:
                self.config_layout.removeWidget(self.config_widget)
                self.config_widget.deleteLater()
            self.config_widget = project_type_class(self)
            self.config_layout.insertWidget(0, self.config_widget)
            self.config_widget.build_schema()

        super().on_item_selected()

        print(f"[DEBUG] tab index after super: {self.config_widget.widgets[2].content.currentIndex() if hasattr(self.config_widget, 'widgets') and len(self.config_widget.widgets) > 2 else 'N/A'}")

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