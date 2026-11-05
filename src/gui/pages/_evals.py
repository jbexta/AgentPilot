"""
Evals Page Module.

This module provides the evals management page for the Agent Pilot GUI interface.
Evals enable users to create, organize, and manage evaluation sets for agents,
workflows, or models, supporting systematic testing and benchmarking of AI
capabilities. The page facilitates organization, execution, and review of
evaluation runs and results.

Key Features:
- Eval creation, editing, and deletion
- Organization of evals into folders or categories
- Eval-specific configuration and settings
- Search and filtering capabilities
- Integrated configuration widget for detailed eval setup
- Management and review of eval results and runs

The page extends ConfigDBTree to provide database-backed eval management with
an interface for organizing, configuring, and reviewing evaluation sets and outcomes.
"""

from typing_extensions import override
from gui.widgets.config_db_tree import ConfigDBTree
from plugins.workflows.widgets.workflow_settings import WorkflowSettings
from utils import sql


class Page_Evals(ConfigDBTree):
    display_name = 'Evals'
    icon_path = ":/resources/icon-workspace.png"
    page_type = 'settings'  # either 'settings', 'main', or 'any' ('any' means it can be pinned between main and settings)

    def __init__(self, parent):
        super().__init__(
            parent=parent,
            table_name='projects',  # todo name
            query="""
                SELECT
                    name,
                    id,
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
                    'image_key': 'config',
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
            layout_type='vertical',
            # config_widget=self.Project_Config_Widget(parent=self),
            folder_config_widget=self.Folder_Config_Widget(parent=self),
            tree_header_hidden=True,
            add_item_options={'title': 'New Project', 'prompt': 'Enter a name for the project:'},
            del_item_options={'title': 'Delete Project',
                              'prompt': 'Are you sure you want to delete this project?'},
            readonly=True,
            searchable=True,
            filterable=True,
            folder_key='projects',
        )
        self.splitter.setSizes([500, 500])

    # class Project_Config_Widget(