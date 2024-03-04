
import json
# import logging

from PySide6.QtCore import QRegularExpression
from PySide6.QtWidgets import *
from PySide6.QtGui import Qt, QSyntaxHighlighter, QTextCharFormat, QColor, QFont

from src.gui.components.config import ConfigPages, ConfigFields, ConfigTree, ConfigTabs, \
    ConfigJoined, ConfigJsonTree  # , ConfigJoined
from src.utils import sql  # , config
from src.utils.apis import llm
from src.gui.widgets.base import BaseComboBox, BaseTableWidget, ContentPage
from src.utils.helpers import display_messagebox


class PythonHighlighter(QSyntaxHighlighter):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.keywordFormat = QTextCharFormat()
        self.keywordFormat.setForeground(QColor('#c78953'))
        # self.keywordFormat.setFontWeight(QTextCharFormat.Bold)

        self.stringFormat = QTextCharFormat()
        self.stringFormat.setForeground(QColor('#6aab73'))

        self.keywords = [
            'and', 'as', 'assert', 'break', 'class', 'continue', 'def', 'del',
            'elif', 'else', 'except', 'finally', 'for', 'from', 'global', 'if',
            'import', 'in', 'is', 'lambda', 'nonlocal', 'not', 'or', 'pass',
            'raise', 'return', 'try', 'while', 'with', 'yield'
        ]

        # Regular expressions for python's syntax
        self.tri_single_quote = QRegularExpression("f?'''([^'\\\\]|\\\\.|'{1,2}(?!'))*(''')?")
        self.tri_double_quote = QRegularExpression('f?"""([^"\\\\]|\\\\.|"{1,2}(?!"))*(""")?')
        self.single_quote = QRegularExpression(r"'([^'\\]|\\.)*(')?")
        self.double_quote = QRegularExpression(r'"([^"\\]|\\.)*(")?')

    def highlightBlock(self, text):
        # String matching
        self.match_multiline(text, self.tri_single_quote, 1, self.stringFormat)
        self.match_multiline(text, self.tri_double_quote, 2, self.stringFormat)
        self.match_inline_string(text, self.single_quote, self.stringFormat)
        self.match_inline_string(text, self.double_quote, self.stringFormat)

        # Keyword matching
        for keyword in self.keywords:
            expression = QRegularExpression('\\b' + keyword + '\\b')
            match_iterator = expression.globalMatch(text)
            while match_iterator.hasNext():
                match = match_iterator.next()
                self.setFormat(match.capturedStart(), match.capturedLength(), self.keywordFormat)

    def match_multiline(self, text, expression, state, format):
        if self.previousBlockState() == state:
            start = 0
            length = len(text)
        else:
            start = -1
            length = 0

        # Look for the start of a multi-line string
        if start == 0:
            match = expression.match(text)
            if match.hasMatch():
                length = match.capturedLength()
                if match.captured(3):  # Closing quotes are found
                    self.setCurrentBlockState(0)
                else:
                    self.setCurrentBlockState(state)  # Continue to the next line
                self.setFormat(match.capturedStart(), length, format)
                start = match.capturedEnd()
        while start >= 0:
            match = expression.match(text, start)
            # We've got a match
            if match.hasMatch():
                # Multiline string
                length = match.capturedLength()
                if match.captured(3):  # Closing quotes are found
                    self.setCurrentBlockState(0)
                else:
                    self.setCurrentBlockState(state)  # The string is not closed
                # Apply the formatting and then look for the next possible match
                self.setFormat(match.capturedStart(), length, format)
                start = match.capturedEnd()
            else:
                # No further matches; if we are in a multi-line string, color the rest of the text
                if self.currentBlockState() == state:
                    self.setFormat(start, len(text) - start, format)
                break

    def match_inline_string(self, text, expression, format):
        match_iterator = expression.globalMatch(text)
        while match_iterator.hasNext():
            match = match_iterator.next()
            if (match.capturedLength() > 0):
                if match.captured(1):
                    self.setFormat(match.capturedStart(), match.capturedLength(), format)


class Page_Settings(ConfigPages):
    def __init__(self, main):
        super().__init__(parent=main)
        self.main = main

        ContentPageTitle = ContentPage(main=main, title='Settings')
        self.layout.addWidget(ContentPageTitle)

        self.pages = {
            'System': self.Page_System_Settings(self),
            'API': self.Page_API_Settings(self),
            'Display': self.Page_Display_Settings(self),
            'Blocks': self.Page_Block_Settings(self),
            'Roles': self.Page_Role_Settings(self),
            'Tools': self.Page_Tool_Settings(self),
            'Sandbox': self.Page_Role_Settings(self),
            "Vector DB": self.Page_Role_Settings(self),
        }
        self.build_schema()
        self.settings_sidebar.layout.addStretch(1)

    def save_config(self):
        """Saves the config to database when modified"""
        json_config = json.dumps(self.get_config())
        sql.execute("UPDATE `settings` SET `value` = ? WHERE `field` = 'app_config'", (json_config,))
        self.main.system.config.load()
        system_config = self.main.system.config.dict
        self.load_config(system_config)

    class Page_System_Settings(ConfigFields):
        def __init__(self, parent):
            super().__init__(parent=parent)
            self.parent = parent
            self.label_width = 125
            self.margin_left = 20
            self.namespace = 'system'
            self.schema = [
                {
                    'text': 'Language',
                    'type': 'LanguageComboBox',
                    'default': 'en',
                },
                {
                    'text': 'Dev mode',
                    'type': bool,
                    'default': False,
                },
                {
                    'text': 'Always on top',
                    'type': bool,
                    'default': True,
                },
                {
                    'text': 'Auto title',
                    'type': bool,
                    'width': 40,
                    'default': True,
                    'row_key': 0,
                },
                {
                    'text': 'Auto-title model',
                    'label_position': None,
                    'type': 'ModelComboBox',
                    'default': 'gpt-3.5-turbo',
                    'row_key': 0,
                },
                {
                    'text': 'Auto-title prompt',
                    'type': str,
                    'default': 'Generate a brief and concise title for a chat that begins with the following message:\n\n{user_msg}',
                    'num_lines': 4,
                    'width': 300,
                },
            ]

        def after_init(self):
            self.dev_mode.stateChanged.connect(lambda state: self.toggle_dev_mode(state))

            self.always_on_top.stateChanged.connect(self.parent.main.toggle_always_on_top)

            # add a button 'Reset database'
            self.reset_app_btn = QPushButton('Reset Application')
            self.reset_app_btn.clicked.connect(self.reset_application)
            self.layout.addWidget(self.reset_app_btn)

            # add button 'Fix empty titles'
            self.fix_empty_titles_btn = QPushButton('Fix Empty Titles')
            self.fix_empty_titles_btn.clicked.connect(self.fix_empty_titles)
            self.layout.addWidget(self.fix_empty_titles_btn)

        def toggle_dev_mode(self, state=None):
            # pass
            if state is None and hasattr(self, 'dev_mode'):
                state = self.dev_mode.isChecked()

            main = self.parent.main
            main.page_chat.topbar.btn_info.setVisible(state)
            main.page_chat.topbar.group_settings.group_topbar.btn_clear.setVisible(state)
            main.page_settings.pages['System'].reset_app_btn.setVisible(state)
            main.page_settings.pages['System'].fix_empty_titles_btn.setVisible(state)

        def reset_application(self):
            from src.context.base import Workflow

            retval = display_messagebox(
                icon=QMessageBox.Warning,
                text="Are you sure you want to permanently reset the database and config? This will permanently delete all contexts, messages, and logs.",
                title="Reset Database",
                buttons=QMessageBox.Ok | QMessageBox.Cancel,
            )

            if retval != QMessageBox.Ok:
                return

            sql.execute('DELETE FROM contexts_messages')
            sql.execute('DELETE FROM contexts_members')
            sql.execute('DELETE FROM contexts')
            sql.execute('DELETE FROM embeddings WHERE id > 1984')
            sql.execute('DELETE FROM logs')
            sql.execute('VACUUM')
            self.parent.update_config('system.dev_mode', False)
            self.toggle_dev_mode(False)
            self.parent.main.page_chat.workflow = Workflow(main=self.parent.main)
            self.load()

        def fix_empty_titles(self):
            retval = display_messagebox(
                icon=QMessageBox.Warning,
                text="Are you sure you want to fix empty titles? This could be very expensive and may take a while. The application will be unresponsive until it is finished.",
                title="Fix titles",
                buttons=QMessageBox.Yes | QMessageBox.No,
            )

            if retval != QMessageBox.Yes:
                return

            # get all contexts with empty titles
            contexts_first_msgs = sql.get_results("""
                SELECT c.id, cm.msg
                FROM contexts c
                INNER JOIN (
                    SELECT *
                    FROM contexts_messages
                    WHERE rowid IN (
                        SELECT MIN(rowid)
                        FROM contexts_messages
                        GROUP BY context_id
                    )
                ) cm ON c.id = cm.context_id
                WHERE c.summary = '';
            """, return_type='dict')

            conf = self.parent.main.system.config.dict
            model_name = conf.get('system.auto_title_model', 'gpt-3.5-turbo')
            model_obj = (model_name, self.parent.main.system.models.to_dict()[model_name])

            prompt = conf.get('system.auto_title_prompt',
                              'Generate a brief and concise title for a chat that begins with the following message:\n\n{user_msg}')
            try:
                for context_id, msg in contexts_first_msgs.items():
                    context_prompt = prompt.format(user_msg=msg)

                    title = llm.get_scalar(context_prompt, model_obj=model_obj)
                    title = title.replace('\n', ' ').strip("'").strip('"')
                    sql.execute('UPDATE contexts SET summary = ? WHERE id = ?', (title, context_id))

            except Exception as e:
                display_messagebox(
                    icon=QMessageBox.Warning,
                    text="Error generating titles: " + str(e),
                    title="Error",
                    buttons=QMessageBox.Ok,
                )

    class Page_Display_Settings(ConfigFields):
        def __init__(self, parent):
            super().__init__(parent=parent)
            self.parent = parent

            self.label_width = 185
            self.margin_left = 20
            self.namespace = 'display'
            self.schema = [
                {
                    'text': 'Primary color',
                    'type': 'ColorPickerWidget',
                    'default': '#ffffff',
                },
                {
                    'text': 'Secondary color',
                    'type': 'ColorPickerWidget',
                    'default': '#ffffff',
                },
                {
                    'text': 'Text color',
                    'type': 'ColorPickerWidget',
                    'default': '#ffffff',
                },
                {
                    'text': 'Text font',
                    'type': 'FontComboBox',
                    'default': 'Arial',
                },
                {
                    'text': 'Text size',
                    'type': int,
                    'minimum': 6,
                    'maximum': 72,
                    'default': 12,
                },
                {
                    'text': 'Show agent bubble avatar',
                    'type': ('In Group', 'Always', 'Never',),
                    'default': 'In Group',
                },
                {
                    'text': 'Agent bubble avatar position',
                    'type': ('Top', 'Middle',),
                    'default': 'Top',
                },
                {
                    'text': 'Bubble spacing',
                    'type': int,
                    'minimum': 0,
                    'maximum': 10,
                    'default': 5,
                },
            ]

        def update_config(self):
            super().update_config()
            self.parent.main.apply_stylesheet()

    class Page_API_Settings(ConfigTree):
        def __init__(self, parent):
            super().__init__(
                parent=parent,
                db_table='apis',
                has_config_field=False,
                propagate=False,
                query="""
                    SELECT
                        name,
                        id,
                        client_key,
                        priv_key
                    FROM apis
                    ORDER BY name""",
                schema=[
                    {
                        'text': 'Name',
                        'key': 'name',
                        'type': str,
                        'width': 120,
                    },
                    {
                        'text': 'id',
                        'key': 'id',
                        'type': int,
                        'visible': False,
                    },
                    {
                        'text': 'Client Key',
                        'key': 'client_key',
                        'type': str,
                        'width': 100,
                    },
                    {
                        'text': 'API Key',
                        'key': 'priv_key',
                        'type': str,
                        'stretch': True,
                    },
                ],
                add_item_prompt=('Add API', 'Enter a name for the API:'),
                del_item_prompt=('Delete API', 'Are you sure you want to delete this API?'),
                readonly=False,
                layout_type=QVBoxLayout,
                # config_widget=self.API_Tab_Widget(parent=self),
                tree_width=500,
            )
            self.config_widget = self.API_Tab_Widget(parent=self)
            self.layout.addWidget(self.config_widget)

        class API_Tab_Widget(ConfigTabs):
            def __init__(self, parent):
                super().__init__(parent=parent)

                self.pages = {
                    'Models': self.Tab_Models(parent=self),
                }

            class Tab_Models(ConfigTree):
                def __init__(self, parent):
                    super().__init__(
                        parent=parent,
                        db_table='models',
                        db_config_field='model_config',
                        query="""
                            SELECT
                                alias,
                                id
                            FROM models
                            WHERE api_id = ?
                            ORDER BY alias""",
                        query_params=(parent.parent,),
                        schema=[
                            {
                                'text': 'Name',
                                'key': 'name',
                                'type': str,
                                'width': 150,
                            },
                            {
                                'text': 'id',
                                'key': 'id',
                                'type': int,
                                'visible': False,
                            },
                        ],
                        add_item_prompt=('Add Model', 'Enter a name for the model:'),
                        del_item_prompt=('Delete Model', 'Are you sure you want to delete this model?'),
                        layout_type=QHBoxLayout,
                        config_widget=self.Model_Config_Widget(parent=self),
                        tree_header_hidden=True,
                        tree_width=150,
                    )

                class Model_Config_Widget(ConfigFields):
                    def __init__(self, parent):
                        super().__init__(parent=parent)
                        self.parent = parent
                        self.schema = [
                            {
                                'text': 'Alias',
                                'type': str,
                                'width': 300,
                                'label_position': 'top',
                                # 'is_db_field': True,
                                'default': '',
                            },
                            {
                                'text': 'Model name',
                                'type': str,
                                'width': 300,
                                'label_position': 'top',
                                # 'is_db_field': True,
                                'default': '',
                            },
                            {
                                'text': 'Api Base',
                                'type': str,
                                'width': 300,
                                'label_position': 'top',
                                'default': '',
                            },
                            {
                                'text': 'Custom provider',
                                'type': str,
                                'label_position': 'top',
                                'default': '',
                            },
                            {
                                'text': 'Temperature',
                                'type': float,
                                'minimum': 0.0,
                                'maximum': 1.0,
                                'step': 0.05,
                                # 'label_position': 'top',
                                'default': 0.6,
                                'row_key': 'A',
                            },
                            {
                                'text': 'Top P',
                                'type': float,
                                'minimum': 0.0,
                                'maximum': 1.0,
                                'step': 0.05,
                                # 'label_position': 'top',
                                'default': 1.0,
                                'row_key': 'A',
                            },
                        ]

    class Page_Block_Settings(ConfigTree):
        def __init__(self, parent):
            super().__init__(
                parent=parent,
                db_table='blocks',
                db_config_field='config',
                propagate=False,
                query="""
                    SELECT
                        name,
                        id
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
                        # 'readonly': True,
                    },
                ],
                add_item_prompt=('Add Block', 'Enter a placeholder tag for the block:'),
                del_item_prompt=('Delete Block', 'Are you sure you want to delete this block?'),
                readonly=False,
                layout_type=QHBoxLayout,
                config_widget=self.Block_Config_Widget(parent=self),
                tree_width=150,
            )

        def field_edited(self, item):
            super().field_edited(item)
            self.parent.main.system.blocks.load()

        def add_item(self):
            if not super().add_item():
                return
            self.parent.main.system.blocks.load()

        def delete_item(self):
            if not super().delete_item():
                return
            self.parent.main.system.blocks.load()

        class Block_Config_Widget(ConfigFields):
            def __init__(self, parent):
                super().__init__(parent=parent)
                self.schema = [
                    {
                        'text': 'Data',
                        'type': str,
                        'default': '',
                        'num_lines': 20,
                        'width': 450,
                        'label_position': 'top',
                    },
                ]

    class Page_Role_Settings(ConfigTree):
        def __init__(self, parent):
            super().__init__(
                parent=parent,
                db_table='roles',
                db_config_field='config',
                propagate=False,
                query="""
                    SELECT
                        name,
                        id
                    FROM roles""",
                schema=[
                    {
                        'text': 'Roles',
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
                add_item_prompt=('Add Role', 'Enter a name for the role:'),
                del_item_prompt=('Delete Role', 'Are you sure you want to delete this role?'),
                readonly=False,
                layout_type=QHBoxLayout,
                config_widget=self.Role_Config_Widget(parent=self),
                tree_width=150,
            )

        def field_edited(self, item):
            super().field_edited(item)
            self.parent.main.system.roles.load()

        def add_item(self):
            if not super().add_item():
                return
            self.parent.main.system.roles.load()

        def delete_item(self):
            if not super().delete_item():
                return
            self.parent.main.system.roles.load()

        class Role_Config_Widget(ConfigFields):
            def __init__(self, parent):
                super().__init__(parent=parent)
                self.label_width = 175
                self.schema = [
                    {
                        'text': 'Bubble bg color',
                        'type': 'ColorPickerWidget',
                        'default': '#3b3b3b',
                    },
                    {
                        'text': 'Bubble text color',
                        'type': 'ColorPickerWidget',
                        'default': '#c4c4c4',
                    },
                    {
                        'text': 'Bubble image size',
                        'type': int,
                        'minimum': 3,
                        'maximum': 100,
                        'default': 25,
                    },
                    # {
                    #     'text': 'Append to',
                    #     'type': 'RoleComboBox',
                    #     'default': 'None'
                    # },
                    # {
                    #     'text': 'Visibility type',
                    #     'type': ('Global', 'Local',),
                    #     'default': 'Global',
                    # },
                    # {
                    #     'text': 'Bubble class',
                    #     'type': str,
                    #     'width': 350,
                    #     'num_lines': 15,
                    #     'label_position': 'top',
                    #     'highlighter': PythonHighlighter,
                    #     'default': '',
                    # },
                ]

    class Page_Tool_Settings(ConfigTree):
        def __init__(self, parent):
            super().__init__(
                parent=parent,
                db_table='tools',
                propagate=False,
                query="""
                    SELECT
                        name,
                        id
                    FROM tools""",
                schema=[
                    {
                        'text': 'Name',
                        'key': 'name',
                        'type': str,
                        'width': 120,
                    },
                    {
                        'text': 'id',
                        'key': 'id',
                        'type': int,
                        'visible': False,
                    },
                ],
                add_item_prompt=('Add Tool', 'Enter a name for the tool:'),
                del_item_prompt=('Delete Tool', 'Are you sure you want to delete this tool?'),
                readonly=False,
                layout_type=QVBoxLayout,
                config_widget=self.Tool_Config_Widget(parent=self),
                tree_width=150,  # 500,
            )

        class Tool_Config_Widget(ConfigJoined):
            def __init__(self, parent):
                super().__init__(parent=parent)
                self.widgets = [
                    self.Tool_Info_Widget(parent=self),
                    self.Tool_Tab_Widget(parent=self),
                ]

            class Tool_Info_Widget(ConfigFields):
                def __init__(self, parent):
                    super().__init__(parent=parent)
                    self.schema = [
                        {
                            'text': 'Description',
                            'type': str,
                            'num_lines': 2,
                            'width': 350,
                            'default': '',
                        },
                        {
                            'text': 'Method',
                            'type': ('Function call', 'Prompt based',),
                            'default': 'Native',
                        },
                    ]

            class Tool_Tab_Widget(ConfigTabs):
                def __init__(self, parent):
                    super().__init__(parent=parent)

                    self.pages = {
                        'Code': self.Tab_Code(parent=self),
                        'Parameters': self.Tab_Parameters(parent=self),
                        # 'Prompt': self.Tab_Prompt(parent=self),
                    }

                class Tab_Code(ConfigFields):
                    def __init__(self, parent):
                        super().__init__(parent=parent)
                        self.namespace = 'code'
                        self.schema = [
                            {
                                'text': 'Type',
                                'type': ('Native', 'Langchain',),
                                'default': 'Native',
                            },
                            {
                                'text': 'Code',
                                'type': str,
                                'width': 350,
                                'num_lines': 15,
                                'label_position': None,
                                'highlighter': PythonHighlighter,
                                'default': '',
                            },
                        ]

                # class Tab_Parameters(ConfigJoined):
                #     def __init__(self, parent):
                #         super().__init__(parent=parent)
                #         self.widgets = [
                #             self.Tab_Parameters_Tree(parent=self),
                #             self.Tab_Parameters_Info(parent=self),
                #         ]

                class Tab_Parameters(ConfigJsonTree):
                    def __init__(self, parent):
                        super().__init__(parent=parent,
                                         add_item_prompt=('NA', 'NA'),
                                         del_item_prompt=('NA', 'NA'))
                        self.parent = parent
                        self.namespace = 'parameters'
                        self.schema = [
                            {
                                'text': 'Name',
                                'type': str,
                                'width': 120,
                                'default': '< Enter a parameter name >',
                            },
                            {
                                'text': 'Description',
                                'type': str,
                                'stretch': True,
                                'default': '< Enter a parameter name >',
                            },
                            {
                                'text': 'Type',
                                'type': ('String', 'Integer', 'Float', 'Bool', 'List',),
                                'width': 100,
                                'default': 'String',
                            },
                            {
                                'text': 'Req',
                                'type': bool,
                                'default': True,
                            },
                            {
                                'text': 'Default',
                                'type': str,
                                'default': '',
                            },
                        ]

                    # class Tab_Parameters_Info(ConfigFields):
                    #     def __init__(self, parent):
                    #         super().__init__(parent=parent)
                    #         self.schema = [
                    #             {
                    #                 'text': 'Description',
                    #                 'type': str,
                    #                 'num_lines': 2,
                    #                 'width': 350,
                    #                 'default': '',
                    #             },
                    #         ]