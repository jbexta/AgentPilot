
from src.utils.helpers import WorkflowManagerController


class AgentManager(WorkflowManagerController):
    def __init__(self, system):
        super().__init__(
            system,
            table_name='entities',
            # query="""
            #     SELECT
            #         COALESCE(json_extract(config, '$."info.name"'), name) AS name,
            #         id,
            #         config,
            #         '' AS chat_button,
            #         folder_id
            #     FROM entities
            #     WHERE kind = :kind
            #     ORDER BY pinned DESC, ordr, name""",
            # load_columns=['uuid', 'name', 'config', 'folder_id'],
            folder_key='agents',
            load_columns=['uuid', 'config'],
            default_fields={
                'kind': 'AGENT',
            },
            add_item_options={'title': 'Add Agent', 'prompt': 'Enter a name for the agent:'},
            del_item_options={'title': 'Delete Agent', 'prompt': 'Are you sure you want to delete this agent?'},
        )  # todo rename back to agents

    # def on_edited(self):
    #     main = self.system._main_gui
    #     if not main:
    #         return
    #     main.main_menu.build_custom_pages()
    #     main.page_settings.build_schema()
    #     main.main_menu.settings_sidebar.toggle_page_pin(text, True)