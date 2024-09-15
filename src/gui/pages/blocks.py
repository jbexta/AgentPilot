import json
import sqlite3

from PySide6.QtWidgets import QHBoxLayout, QMessageBox

from src.gui.config import ConfigDBTree
from src.members.workflow import WorkflowSettings
from src.utils import sql
from src.utils.helpers import display_messagebox


class Page_Block_Settings(ConfigDBTree):
    def __init__(self, parent):
        super().__init__(
            parent=parent,
            db_table='blocks',
            propagate=False,
            query="""
                SELECT
                    name,
                    id,
                    folder_id
                FROM blocks""",
            schema=[
                {
                    'text': 'Blocks',
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
            ],
            add_item_prompt=('Add Block', 'Enter a placeholder tag for the block:'),
            del_item_prompt=('Delete Block', 'Are you sure you want to delete this block?'),
            folder_key='blocks',
            readonly=False,
            layout_type=QHBoxLayout,
            tree_header_hidden=True,
            config_widget=self.Block_Config_Widget(parent=self),
            tree_height=665,
            # tree_width=150,
        )
        self.icon_path = ":/resources/icon-blocks.png"
        self.try_add_breadcrumb_widget(root_title='Blocks')

    def on_edited(self):
        self.parent.main.system.blocks.load()

    class Block_Config_Widget(WorkflowSettings):
        def __init__(self, parent):
            super().__init__(parent=parent)  # ,
                             # compact_mode=True)
            self.setFixedWidth(450)
            pass

        def save_config(self):
            """Saves the config to database when modified"""
            json_config_dict = self.get_config()
            json_config = json.dumps(json_config_dict)

            entity_id = self.parent.get_selected_item_id()
            if not entity_id:
                raise NotImplementedError()

            try:
                sql.execute("UPDATE blocks SET config = ? WHERE id = ?", (json_config, entity_id))
            except sqlite3.IntegrityError as e:
                display_messagebox(
                    icon=QMessageBox.Warning,
                    title='Error',
                    text='Name already exists',
                )  # todo

            self.load_config(json_config)  # reload config
            self.parent.reload_current_row()


        # def load_config(self, json_config=None):
        #     pass

        # def update_config(self):
        #     pass

        # def load(self):
        #     pass

        # def save_config(self):
        #     """Saves the config to database when modified"""
        #     json_config_dict = self.get_config()
        #     json_config = json.dumps(json_config_dict)
        #
        #     entity_id = self.parent.tree_config.get_selected_item_id()
        #     if not entity_id:
        #         raise NotImplementedError()
        #
        #     sql.execute("UPDATE blocks SET config = ? WHERE id = ?", (json_config, entity_id))
        #
        #     self.load_config(json_config)  # reload config
        #     self.parent.reload_current_row()

    # class Block_Config_Widget(ConfigFields):  # _OLD(ConfigFields):
    #     def __init__(self, parent):
    #         super().__init__(parent=parent)
    #         # self.main = find_main_widget(self)
    #         self.schema = [
    #             {
    #                 'text': 'Type',
    #                 'key': 'block_type',
    #                 'type': ('Text', 'Prompt', 'Code', 'Metaprompt'),
    #                 'width': 100,
    #                 'default': 'Text',
    #                 'row_key': 0,
    #             },
    #             {
    #                 'text': 'Model',
    #                 'key': 'prompt_model',
    #                 'type': 'ModelComboBox',
    #                 'label_position': None,
    #                 'default': 'default',
    #                 'row_key': 0,
    #             },
    #             {
    #                 'text': 'Language',
    #                 'type':
    #                 ('AppleScript', 'HTML', 'JavaScript', 'Python', 'PowerShell', 'R', 'React', 'Ruby', 'Shell',),
    #                 'width': 100,
    #                 'tooltip': 'The language of the code, to be passed to open interpreter',
    #                 'label_position': None,
    #                 'row_key': 0,
    #                 'default': 'Python',
    #             },
    #             {
    #                 'text': 'Data',
    #                 'type': str,
    #                 'default': '',
    #                 'num_lines': 23,
    #                 'stretch_x': True,
    #                 # 'stretch_y': True,
    #                 'label_position': None,
    #                 # 'exec_type_field': 'block_type',
    #                 # 'lang_field': 'language',
    #                 # 'model_field': 'prompt_model',
    #             },
    #         ]
    #
    #     def after_init(self):
    #         self.refresh_model_visibility()
    #
    #         self.btn_run = QPushButton('Test output')
    #         self.btn_run.clicked.connect(self.on_run)
    #
    #         self.output = QTextEdit()
    #         self.output.setReadOnly(True)
    #         self.output.setFixedHeight(150)
    #         self.layout.addWidget(self.btn_run)
    #         # add spacing
    #         self.layout.addSpacing(3)
    #         self.layout.addWidget(self.output)
    #
    #     def on_run(self):
    #         name = self.parent.tree.get_column_value(0)
    #         try:
    #             output = self.parent.parent.main.system.blocks.compute_block(name=name)  # , source_text=source_text)
    #         except RecursionError as e:
    #             display_messagebox(
    #                 icon=QMessageBox.Warning,
    #                 title="Error",
    #                 text=str(e),
    #                 buttons=QMessageBox.Ok
    #             )
    #             return
    #         self.output.setPlainText(output)
    #         # self.output.setVisible(True)
    #         self.toggle_run_box(visible=True)
    #
    #     def toggle_run_box(self, visible):
    #         self.data.setFixedHeight(482 if visible else 632)
    #         self.output.setVisible(visible)
    #         if not visible:
    #             self.output.setPlainText('')
    #         # window_height = self.data
    #         # if visible:
    #         #     window_height -= 150
    #         # self.data.setFixedHeight(window_height)
    #
    #     def load(self):
    #         super().load()
    #         self.refresh_model_visibility()
    #
    #     def update_config(self):
    #         super().update_config()
    #         self.refresh_model_visibility()
    #
    #     def refresh_model_visibility(self):
    #         block_type = get_widget_value(self.block_type)
    #         model_visible = block_type == 'Prompt' or block_type == 'Metaprompt'
    #         lang_visible = block_type == 'Code'
    #         self.prompt_model.setVisible(model_visible)
    #         self.language.setVisible(lang_visible)
    #         if lang_visible:
    #             # set syntax highlighting
    #             lang = get_widget_value(self.language)
