
import json
import logging

from PySide6.QtCore import QRegularExpression
from PySide6.QtWidgets import *
from PySide6.QtGui import Qt, QSyntaxHighlighter, QTextCharFormat, QColor, QFont

from agentpilot.gui.components.config import ConfigPages, ConfigFields, ConfigTree, ConfigTabs, \
    ConfigJoined  # , ConfigJoined
from agentpilot.utils import sql, config
from agentpilot.utils.apis import llm
from agentpilot.gui.widgets.base import BaseComboBox, BaseTableWidget, ContentPage
from agentpilot.utils.helpers import display_messagebox


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
                if match.captured(1):  # Highlight only if closing quote is present
                    self.setFormat(match.capturedStart(), match.capturedLength(), format)


# class PythonHighlighter(QSyntaxHighlighter):
#     KEYWORDS = [
#         "and", "as", "assert", "break", "class", "continue", "def", "del",
#         "elif", "else", "except", "exec", "finally", "for", "from", "global",
#         "if", "import", "in", "is", "lambda", "not", "or", "pass", "print",
#         "raise", "return", "try", "while", "with", "yield"
#     ]
#
#     OPERATORS = [
#         '=', '==', '!=', '<', '<=', '>', '>=', '\+', '-', '\*', '/', '//',
#         '\%', '\*\*', '\+=', '-=', '\*=', '/=', '\%=', '\^', '\|', '\&',
#         '\~', '>>', '<<'
#     ]
#
#     BRACKETS = [
#         '\{', '\}', '\(', '\)', '\[', '\]'
#     ]
#
#     def __init__(self, document):
#         super(PythonHighlighter, self).__init__(document)
#
#         self.highlightingRules = []
#
#         # Keyword, operator, and bracket rules
#         keywordFormat = QTextCharFormat()
#         keywordFormat.setForeground(QColor("#bf6237"))
#         keywordFormat.setFontWeight(QFont.Bold)
#         for word in PythonHighlighter.KEYWORDS:
#             pattern = r'\b{}\b'.format(word)
#             regex = QRegularExpression(pattern)
#             rule = {'pattern': regex, 'format': keywordFormat}
#             self.highlightingRules.append(rule)
#
#         # operatorFormat = QTextCharFormat()
#         # operatorFormat.setForeground(QColor("red"))
#         # for op in PythonHighlighter.OPERATORS:
#         #     pattern = r'{}'.format(op)
#         #     regex = QRegularExpression(pattern)
#         #     rule = {'pattern': regex, 'format': operatorFormat}
#         #     self.highlightingRules.append(rule)
#
#         # bracketFormat = QTextCharFormat()
#         # bracketFormat.setForeground(QColor("darkGreen"))
#         # for bracket in PythonHighlighter.BRACKETS:
#         #     pattern = r'{}'.format(bracket)
#         #     regex = QRegularExpression(pattern)
#         #     rule = {'pattern': regex, 'format': bracketFormat}
#         #     self.highlightingRules.append(rule)
#
#         # Multi-line strings (quotes)
#         self.multiLineCommentFormat = QTextCharFormat()
#         self.multiLineCommentFormat.setForeground(QColor("grey"))
#         self.commentStartExpression = QRegularExpression(r"'''|\"\"\"")
#         self.commentEndExpression = QRegularExpression(r"'''|\"\"\"")
#
#     # def set_text_to_highlight(self, text):
#     #     self.text_to_highlight = text
#     #
#     #     # This method is automatically called by the QSyntaxHighlighter base class.
#     #     # We override it to implement our custom syntax highlighting.
#     def highlightBlock(self, text):
#         # Single-line highlighting
#         for rule in self.highlightingRules:
#             expression = QRegularExpression(rule['pattern'])
#             it = expression.globalMatch(text)
#             while it.hasNext():
#                 match = it.next()
#                 self.setFormat(match.capturedStart(), match.capturedLength(), rule['format'])
#
#         # Multi-line highlighting (multi-line strings)
#         self.setCurrentBlockState(0)
#
#         startIndex = 0
#         if self.previousBlockState() != 1:
#             match = self.commentStartExpression.match(text)
#             startIndex = match.capturedStart()
#
#         while startIndex >= 0:
#             match = self.commentEndExpression.match(text, startIndex)
#             endIndex = match.capturedStart()
#             commentLength = 0
#             if endIndex == -1:
#                 self.setCurrentBlockState(1)
#                 commentLength = len(text) - startIndex
#             else:
#                 commentLength = endIndex - startIndex + match.capturedLength()
#             self.setFormat(startIndex, commentLength, self.multiLineCommentFormat)
#             startIndex = self.commentStartExpression.match(text, startIndex + commentLength).capturedStart()


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
        # name = self.config.get('general.name', 'Assistant')
        sql.execute("UPDATE `settings` SET `value` = ? WHERE `field` = 'app_config'", (json_config,))
        self.main.system.config.load()
        system_config = self.main.system.config.dict
        self.load_config(system_config)
        self.load()
        self.main.apply_stylesheet()

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
                    'text': 'Auto-title model',
                    'type': 'ModelComboBox',
                    'default': 'gpt-3.5-turbo',
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
            from agentpilot.context.base import Workflow

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

            model_name = config.get_value('system.auto_title_model', 'gpt-3.5-turbo')
            model_obj = (model_name, self.parent.main.system.models.to_dict()[model_name])

            prompt = config.get_value('system.auto_title_prompt',
                                      'Generate a brief and concise title for a chat that begins with the following message:\n\n{user_msg}')
            try:
                for context_id, msg in contexts_first_msgs.items():
                    context_prompt = prompt.format(user_msg=msg)

                    title = llm.get_scalar(context_prompt, model_obj=model_obj)
                    title = title.replace('\n', ' ').strip("'").strip('"')
                    sql.execute('UPDATE contexts SET summary = ? WHERE id = ?', (title, context_id))

            except Exception as e:
                # show error message
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
            ]

    class Page_API_Settings(ConfigTree):
        def __init__(self, parent):
            super().__init__(
                parent=parent,
                db_table='apis',
                has_config_field=False,
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
                                'label_position': 'top',
                                'default': 0.5,
                            },
                        ]

    class Page_Block_Settings(ConfigTree):
        def __init__(self, parent):
            super().__init__(
                parent=parent,
                db_table='blocks',
                db_config_field='config',
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
            # self.parent = parent

        def field_edited(self, item):
            super().field_edited(item)

            # reload blocks
            self.parent.main.system.blocks.load()

        def add_item(self):
            if not super().add_item():
                return
            # self.load()
            self.parent.main.system.blocks.load()

        def delete_item(self):
            if not super().delete_item():
                return
            # self.load()
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

            # reload blocks
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
                    {
                        'text': 'Append to',
                        'type': 'RoleComboBox',
                        'default': 'None'
                    },
                    {
                        'text': 'Visibility type',
                        'type': ('Global', 'Local',),
                        'default': 'Global',
                    },
                    {
                        'text': 'Bubble class',
                        'type': str,
                        'width': 350,
                        'num_lines': 15,
                        'label_position': 'top',
                        'highlighter': PythonHighlighter,
                        'default': '',
                    },
                ]

    class Page_Tool_Settings(ConfigTree):
        def __init__(self, parent):
            super().__init__(
                parent=parent,
                db_table='tools',
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
                layout_type=QHBoxLayout,
                config_widget=self.Tool_Config_Widget(parent=self),
                tree_width=150,  # 500,
            )
            # self.config_widget = self.Tool_Tab_Widget(parent=self)
            # self.layout.addWidget(self.config_widget)

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
                            'label_position': 'top',
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
                        # self.parent = parent
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

                class Tab_Parameters(ConfigFields):
                    def __init__(self, parent):
                        super().__init__(parent=parent)
                        # self.parent = parent
                        self.namespace = 'parameters'
                        self.schema = [
                            {
                                'text': 'Par',
                                'type': str,
                                'width': 300,
                                'num_lines': 15,
                                'label_position': None,
                                'default': '',
                            },
                        ]

    # class Page_Tool_Settings(QWidget):
    #     def __init__(self, parent):
    #         super().__init__(parent=parent)
    #         self.parent = parent
    #
    #         self.layout = QVBoxLayout(self)
    #
    #         # Function list and description
    #         self.function_layout = QVBoxLayout()
    #         self.functions_table = BaseTableWidget(self)
    #         self.functions_table.setColumnCount(4)
    #         self.functions_table.setHorizontalHeaderLabels(["ID", "Name", "Description", "On trigger"])
    #         # self.functions_table.horizontalHeader().setStretchLastSection(True)
    #         self.functions_table.setColumnWidth(3, 100)
    #         self.functions_table.setColumnHidden(0, True)
    #         self.functions_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
    #         self.functions_table.verticalHeader().setVisible(False)
    #         self.functions_table.verticalHeader().setDefaultSectionSize(20)
    #         self.functions_table.verticalHeader().setSectionResizeMode(QHeaderView.Fixed)
    #
    #         self.function_layout.addWidget(self.functions_table)
    #
    #         # Tab Widget
    #         self.tab_widget = QTabWidget(self)
    #         self.function_layout.addWidget(self.tab_widget)
    #
    #         # Code Tab
    #         self.code_tab = self.Tab_Page_Code(self.tab_widget)
    #
    #         # Parameter Tab
    #         self.parameters_tab = self.Tab_Page_Parameters(self.tab_widget)
    #
    #         # Used By Tab
    #         self.used_by_tab = QWidget(self.tab_widget)
    #         self.used_by_layout = QHBoxLayout(self.used_by_tab)
    #
    #         # Add tabs to the Tab Widget
    #         self.tab_widget.addTab(self.code_tab, "Code")
    #         self.tab_widget.addTab(self.parameters_tab, "Parameters")
    #         self.tab_widget.addTab(self.used_by_tab, "Used By")
    #
    #         # # Create a container for the model list and a button bar above
    #         # self.parameters_container = QWidget(self.models_tab)
    #         # self.models_container_layout = QVBoxLayout(self.models_container)
    #         # self.models_container_layout.setContentsMargins(0, 0, 0, 0)
    #         # self.models_container_layout.setSpacing(0)
    #
    #         # Parameters section
    #         # self.parameters_layout = QVBoxLayout(self.parameters_tab)  # Use QHBoxLayout for putting label and buttons in the same row
    #         # # self.parameters_label = QLabel("Parameters", self)
    #         # # self.parameters_label.setStyleSheet("QLabel { font-size: 15px; font-weight: bold; }")
    #         # # self.parameters_layout.addWidget(self.parameters_label)
    #         #
    #         # # Parameter buttons
    #         # self.new_parameter_button = IconButton(self, icon_path=':/resources/icon-new.png')
    #         # self.delete_parameter_button = IconButton(self, icon_path=':/resources/icon-minus.png')
    #         #
    #         # # # Add buttons to the parameters layout
    #         # # self.parameters_buttons_layout.addWidget(self.new_parameter_button)
    #         # # self.parameters_buttons_layout.addWidget(self.delete_parameter_button)
    #         # # self.parameters_buttons_layout.addStretch(1)
    #
    #         # self.parameters_table = BaseTableWidget()
    #         # self.parameters_table.setColumnCount(5)
    #         # self.parameters_table.setHorizontalHeaderLabels(
    #         #     ["ID", "Name", "Type", "Req", "Default"])
    #         # self.parameters_table.horizontalHeader().setStretchLastSection(True)
    #         # self.parameters_table.horizontalHeader().setDefaultAlignment(Qt.AlignLeft)
    #         # self.parameters_table.setColumnHidden(0, True)
    #         # self.parameters_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
    #         # self.parameters_table.verticalHeader().setVisible(False)
    #         # self.parameters_table.verticalHeader().setDefaultSectionSize(20)
    #         # self.parameters_table.verticalHeader().setSectionResizeMode(QHeaderView.Fixed)
    #         #
    #         # # self.function_layout.addLayout(self.parameters_layout)
    #         # self.parameters_layout.addWidget(self.parameters_table)
    #
    #         # Add the function layout to the main layout
    #         self.layout.addLayout(self.function_layout)
    #
    #         # # Connect signals for parameters
    #         # self.new_parameter_button.clicked.connect(self.new_parameter)
    #         # self.delete_parameter_button.clicked.connect(self.delete_parameter)
    #
    #         # Load the initial data
    #         # self.load_parameters()
    #
    #     def load(self):
    #         self.load_functions()
    #         self.parameters_tab.load()
    #
    #
    #     def load_functions(self):
    #         # Load the function list from the database or a config file
    #         # add dummy data:
    #         # id, name, description
    #         data = [
    #             [1, "Get weather", "Gets current weather for any given locations", 'Run code'],  # script
    #             [2, "Generate image", "Generate an image", ''],
    #             [3, "Create file", "Create a new file", ''],
    #         ]
    #         self.functions_table.setRowCount(len(data))
    #         for row, row_data in enumerate(data):
    #             for column, item in enumerate(row_data):
    #                 self.functions_table.setItem(row, column, QTableWidgetItem(str(item)))
    #
    #             combobox_param_type = BaseComboBox()
    #             combobox_param_type.setFixedWidth(100)
    #             combobox_param_type.addItems(['Run code'])
    #             self.functions_table.setCellWidget(row, 3, combobox_param_type)
    #             combobox_param_type.setCurrentText(row_data[3])
    #
    #     class Tab_Page_Code(QWidget):
    #         def __init__(self, parent):
    #             super().__init__(parent=parent)
    #             self.parent = parent
    #
    #             self.layout = QVBoxLayout(self)
    #
    #             self.code_text_area = QTextEdit()
    #             self.layout.addWidget(self.code_text_area)
    #
    #     class Tab_Page_Parameters(QWidget):
    #         def __init__(self, parent):
    #             super().__init__(parent=parent)
    #             self.parent = parent
    #
    #             self.layout = QVBoxLayout(self)
    #
    #             self.parameters_table = BaseTableWidget()
    #             self.parameters_table.setColumnCount(5)
    #             self.parameters_table.setHorizontalHeaderLabels(
    #                 ["ID", "Name", "Type", "Req", "Default"])
    #             self.parameters_table.horizontalHeader().setStretchLastSection(True)
    #             self.parameters_table.horizontalHeader().setDefaultAlignment(Qt.AlignLeft)
    #             self.parameters_table.setColumnHidden(0, True)
    #             self.parameters_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
    #             self.parameters_table.verticalHeader().setVisible(False)
    #             self.parameters_table.verticalHeader().setDefaultSectionSize(20)
    #             self.parameters_table.verticalHeader().setSectionResizeMode(QHeaderView.Fixed)
    #
    #             self.layout.addWidget(self.parameters_table)
    #
    #         def load(self):
    #             # Load the parameters for the selected function
    #             # add dummy data:
    #             #   id,
    #             #   name,
    #             #   description,
    #             #   type (dropdown of items ['integer', 'string', ]),,
    #             #   required (checkbox),
    #             #   hidden (checkbox)
    #             data = [
    #                 [1, "Parameter 1", "integer", True, False],
    #                 [2, "Parameter 2", "string", False, False],
    #                 [3, "Parameter 3", "integer", False, True],
    #             ]
    #             self.parameters_table.setRowCount(len(data))
    #             for row, row_data in enumerate(data):
    #                 for column, item in enumerate(row_data):
    #                     self.parameters_table.setItem(row, column, QTableWidgetItem(str(item)))
    #
    #                 # add a combobox column
    #                 combobox_param_type = BaseComboBox()
    #                 combobox_param_type.setFixedWidth(100)
    #                 combobox_param_type.addItems(['INTEGER', 'STRING', 'BOOL', 'LIST'])
    #                 combobox_param_type.setCurrentText(row_data[2])
    #                 self.parameters_table.setCellWidget(row, 2, combobox_param_type)
    #
    #                 chkBox_req = QTableWidgetItem()
    #                 chkBox_req.setFlags(chkBox_req.flags() | Qt.ItemIsUserCheckable)
    #                 chkBox_req.setCheckState(Qt.Checked if row_data[3] else Qt.Unchecked)
    #                 self.parameters_table.setItem(row, 3, chkBox_req)
    #
    #     def new_function(self):
    #         # Logic for creating a new function
    #         pass
    #
    #     def delete_function(self):
    #         # Logic for deleting the selected function
    #         pass
    #
    #     def rename_function(self):
    #         # Logic for renaming the selected function
    #         pass
    #
    #     def new_parameter(self):
    #         # Add method logic here
    #         pass
    #
    #     def delete_parameter(self):
    #         # Add method logic here
    #         pass

    # class Page_Sandboxes_Settings(QWidget):
    #     def __init__(self, parent):
    #         super().__init__(parent=parent)
    #         self.parent = parent
    #
    #         self.layout = QVBoxLayout(self)
    #
    #     def load(self):
    #         pass