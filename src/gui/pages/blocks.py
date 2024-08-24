from PySide6.QtWidgets import QHBoxLayout, QPushButton, QTextEdit

from src.gui.config import ConfigDBTree, ConfigFields, get_widget_value


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
            config_widget=self.Block_Config_Widget(parent=self),
            tree_width=150,
        )

    def on_edited(self):
        self.parent.main.system.blocks.load()

    def on_item_selected(self):
        super().on_item_selected()
        # self.config_widget.output.setPlainText('')
        # self.config_widget.output.setVisible(True)
        self.config_widget.toggle_run_box(visible=False)

    class Block_Config_Widget(ConfigFields):
        def __init__(self, parent):
            super().__init__(parent=parent)
            # self.main = find_main_widget(self)
            self.schema = [
                {
                    'text': 'Type',
                    'key': 'block_type',
                    'type': ('Text', 'Prompt', 'Code'),
                    'width': 90,
                    'default': 'Text',
                    'row_key': 0,
                },
                {
                    'text': 'Model',
                    'key': 'prompt_model',
                    'type': 'ModelComboBox',
                    'label_position': None,
                    'default': 'mistral/mistral-large-latest',
                    'row_key': 0,
                },
                {
                    'text': 'Language',
                    'type':
                    ('AppleScript', 'HTML', 'JavaScript', 'Python', 'PowerShell', 'R', 'React', 'Ruby', 'Shell',),
                    'width': 100,
                    'tooltip': 'The language of the code, to be passed to open interpreter',
                    'label_position': None,
                    'row_key': 0,
                    'default': 'Python',
                },
                {
                    'text': 'Data',
                    'type': str,
                    'default': '',
                    'num_lines': 23,
                    'width': 385,
                    'label_position': None,
                },
            ]

        def after_init(self):
            self.refresh_model_visibility()

            self.btn_run = QPushButton('Run')
            self.btn_run.clicked.connect(self.on_run)

            self.output = QTextEdit()
            self.output.setReadOnly(True)
            self.output.setFixedHeight(150)
            self.layout.addWidget(self.btn_run)
            self.layout.addWidget(self.output)

        def on_run(self):
            name = self.parent.get_column_value(0)
            output = self.parent.parent.main.system.blocks.compute_block(name=name)  # , source_text=source_text)
            self.output.setPlainText(output)
            # self.output.setVisible(True)
            self.toggle_run_box(visible=True)

        def toggle_run_box(self, visible):
            self.output.setVisible(visible)
            if not visible:
                self.output.setPlainText('')
            self.data.setFixedHeight(443 if visible else 593)

        def load(self):
            super().load()
            self.refresh_model_visibility()

        def update_config(self):
            super().update_config()
            self.refresh_model_visibility()

        def refresh_model_visibility(self):
            block_type = get_widget_value(self.block_type)
            model_visible = block_type == 'Prompt'
            lang_visible = block_type == 'Code'
            self.prompt_model.setVisible(model_visible)
            self.language.setVisible(lang_visible)
