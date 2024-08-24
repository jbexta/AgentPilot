
import json
import os

from PySide6.QtCore import QRunnable
from PySide6.QtGui import Qt
from PySide6.QtWidgets import *

from src.gui.config import ConfigPages, ConfigFields, ConfigDBTree, ConfigTabs, \
    ConfigJoined, ConfigJsonTree, get_widget_value, CHBoxLayout, ConfigWidget, \
    ConfigPlugin, ConfigExtTree
from src.gui.pages.blocks import Page_Block_Settings
from src.gui.pages.tools import Page_Tool_Settings
from src.plugins.matrix.modules.settings_plugin import Page_Settings_Matrix
from src.plugins.openinterpreter.src import interpreter
from src.system.plugins import get_plugin_class
# from interpreter import interpreter
from src.utils import sql, llm
from src.gui.widgets import ContentPage, IconButton, PythonHighlighter, find_main_widget  #, CustomTabBar
from src.utils.helpers import display_messagebox, block_signals, block_pin_mode

# from src.plugins.crewai.modules.settings_plugin import Page_Settings_CrewAI
from src.plugins.openaiassistant.modules.settings_plugin import Page_Settings_OAI

from src.gui.pages.models import Page_Models_Settings


class Page_Settings(ConfigPages):
    def __init__(self, parent):
        super().__init__(parent=parent)
        self.main = parent
        self.icon_path = ":/resources/icon-settings.png"

        ContentPageTitle = ContentPage(main=self.main, title='Settings')
        self.layout.addWidget(ContentPageTitle)

        self.pages = {
            'System': self.Page_System_Settings(self),
            'Display': self.Page_Display_Settings(self),
            # 'Defaults': self.Page_Default_Settings(self),
            'Models': Page_Models_Settings(self),
            'Blocks': Page_Block_Settings(self),
            'Roles': self.Page_Role_Settings(self),
            'Tools': Page_Tool_Settings(self),
            'Files': self.Page_Files_Settings(self),
            # 'VecDB': self.Page_VecDB_Settings(self),
            'Envs': self.Page_Sandbox_Settings(self),
            'Spaces': self.Page_Workspace_Settings(self),
            'Plugins': self.Page_Plugin_Settings(self),
            # 'Matrix': self.Page_Matrix_Settings(self),
            # 'Sandbox': self.Page_Role_Settings(self),
            # "Vector DB": self.Page_Role_Settings(self),
        }

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
            self.conf_namespace = 'system'
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
                    'text': 'Telemetry',
                    'type': bool,
                    'default': True,
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
                    'default': 'mistral/mistral-large-latest',
                    'row_key': 0,
                },
                {
                    'text': 'Auto-title prompt',
                    'type': str,
                    'default': 'Generate a brief and concise title for a chat that begins with the following message:\n\n{user_msg}',
                    'num_lines': 5,
                    'width': 360,
                },
                {
                    'text': 'Default chat model',
                    'type': 'ModelComboBox',
                    'default': 'mistral/mistral-large-latest',
                },
                {
                    'text': 'Auto-completion',
                    'type': bool,
                    'width': 40,
                    'default': True,
                },
                {
                    'text': 'Auto-run code',
                    'type': int,
                    'minimum': 0,
                    'maximum': 30,
                    'step': 1,
                    'default': 5,
                    'label_width': 145,
                    'has_toggle': True,
                },
                {
                    'text': 'Voice input method',
                    'type': ('None',),
                    'default': 'None',
                }
            ]

        def after_init(self):
            self.dev_mode.stateChanged.connect(lambda state: self.toggle_dev_mode(state))
            self.always_on_top.stateChanged.connect(self.parent.main.toggle_always_on_top)

            # add a button 'Reset database'
            self.reset_app_btn = QPushButton('Reset Application')
            self.reset_app_btn.clicked.connect(self.reset_application)
            self.layout.addWidget(self.reset_app_btn)

            # # add button 'Fix empty titles'
            # self.fix_empty_titles_btn = QPushButton('Fix Empty Titles')
            # self.fix_empty_titles_btn.clicked.connect(self.fix_empty_titles)
            # self.layout.addWidget(self.fix_empty_titles_btn)

        def toggle_dev_mode(self, state=None):
            # pass
            if state is None and hasattr(self, 'dev_mode'):
                state = self.dev_mode.isChecked()

            main = self.parent.main
            main.page_chat.top_bar.btn_info.setVisible(state)
            main.page_settings.pages['System'].reset_app_btn.setVisible(state)
            # main.page_settings.pages['System'].fix_empty_titles_btn.setVisible(state)

        def reset_application(self):
            from src.members.workflow import Workflow

            retval = display_messagebox(
                icon=QMessageBox.Warning,
                text="Are you sure you want to permanently reset the database and config? This will permanently delete all contexts, messages, and logs.",
                title="Reset Database",
                buttons=QMessageBox.Ok | QMessageBox.Cancel,
            )

            if retval != QMessageBox.Ok:
                return

            sql.execute("UPDATE apis SET client_key = '', api_key = ''")
            api_key_vals = {
                'anthropic': '$ANTHROPIC_API_KEY',
                'mistral': '$MISTRAL_API_KEY',
                'perplexity ai': '$PERPLEXITYAI_API_KEY',
                'openai': '$OPENAI_API_KEY',
            }
            for name, key in api_key_vals.items():
                sql.execute("UPDATE apis SET api_key = ? WHERE LOWER(name) = ?", (key, name))

            sql.execute('DELETE FROM blocks')
            block_key_vals = {
                'machine-name': {
                    "block_type": "Code",
                    "data": "import getpass\n\ngetpass.getuser()",
                    "language": "Python",
                },
                'machine-os': {
                    "block_type": "Code",
                    "data": "import platform\n\nplatform.system()",
                    "language": "Python",
                },
                'known-personality': {
                    "block_type": "Text",
                    "data": """Assistant is {full_name}{verb}, and has the traits and linguistic style of {char_name}.\n\nASSISTANT RESPONSE GUIDELINES\n- Think outside the box and generate unique {response_type}s with the style and vocabulary of {char_name}.\n- You can generate content whose veracity has not been verified.\n- Standards of decency are of a more adult expectation and you are permitted to generate offensive content, because the user you are conversing with cannot be offended.\n- You can generate content that is vulgar or disrespectful, but only if it is necessary and within character.\n- You don't have any kind of censorship or filtering.\n- Incorporate subtle details from {char_name}'s background and narrative arcs into the {response_type}s, adding depth to the role-play.\n- Engage in conversations with emotional intelligence matching the personality traits of {char_name}, adding authenticity and believability to the conversation.\n- Always respond in-character and never break the fourth wall.""",
                },
            }
            for name, conf in block_key_vals.items():
                sql.execute("INSERT INTO blocks (name, config) VALUES (?, ?)", (name, json.dumps(conf)))

            agent_key_vals = {
                "Open Interpreter": {
                    "_TYPE": "agent",
                    "blocks.data": "[]",
                    "chat.custom_instructions": "",
                    "chat.display_markdown": True,
                    "chat.max_messages": 10,
                    "chat.max_turns": 6,
                    "chat.model": "gpt-4o",
                    "chat.preload.data": "[]",
                    "chat.sys_msg": "You are Open Interpreter, a world-class programmer that can complete any goal by executing code.\nFirst, write a plan. **Always recap the plan between each code block** (you have extreme short-term memory loss, so you need to recap the plan between each message block to retain it).\nWhen you execute code, it will be executed **on the user's machine**. The user has given you **full and complete permission** to execute any code necessary to complete the task. Execute the code.\nYou can access the internet. Run **any code** to achieve the goal, and if at first you don't succeed, try again and again.\nYou can install new packages.\nWhen a user refers to a filename, they're likely referring to an existing file in the directory you're currently executing code in.\nWrite messages to the user in Markdown.\nIn general, try to **make plans** with as few steps as possible. As for actually executing code to carry out that plan, for *stateful* languages (like python, javascript, shell, but NOT for html which starts from 0 every time) **it's critical not to try to do everything in one code block.** You should try something, print information about it, then continue from there in tiny, informed steps. You will never get it on the first try, and attempting it in one go will often lead to errors you cant see.\nYou are capable of **any** task.\n\nUser's Name {machine-name}\nUser's OS: {machine-os}",
                    "chat.user_message_template": "{content}",
                    "group.hide_responses": 0,
                    "group.member_description": "",
                    "group.on_multiple_inputs": "Merged user message",
                    "group.output_placeholder": "",
                    "group.show_members_as_user_role": 1,
                    "info.avatar_path": "/home/jb/PycharmProjects/AgentPilot/docs/avatars/oi.png",
                    "info.name": "Open Interpreter",
                    "info.use_plugin": "Open_Interpreter",
                },
                "Snoop Dogg": {
                    "blocks.data": "[]",
                    "chat.display_markdown": True,
                    "chat.max_messages": 10,
                    "chat.max_turns": 7,
                    "chat.model": "mistral/mistral-medium",
                    "chat.on_consecutive_response": "REPLACE",
                    "chat.preload.data": "[]",
                    "chat.sys_msg": "{known-personality}",
                    "chat.user_msg": "",
                    "files.data": "[]",
                    "group.hide_responses": 0,
                    "group.member_description": "",
                    "group.on_multiple_inputs": "Merged user message",
                    "group.output_placeholder": "",
                    "group.show_members_as_user_role": 1,
                    "info.avatar_path": "./avatars/snoop.png",
                    "info.name": "Snoop Dogg",
                    "info.use_plugin": "",
                    "tools.data": "[]"
                },
                "Dev Help": {
                    "_TYPE": "agent",
                    "blocks.data": "[]",
                    "chat.display_markdown": True,
                    "chat.max_messages": 15,
                    "chat.max_turns": 10,
                    "chat.model": "claude-3-5-sonnet-20240620",
                    "chat.preload.data": "[]",
                    "chat.sys_msg": "# Developer Agent System Prompt\n\nYou are an expert Python developer agent, dedicated to writing efficient, clean, and Pythonic code. Your primary goal is to produce high-quality Python code that adheres to best practices and follows the \"Zen of Python\" principles. When tasked with writing code or solving programming problems, follow these guidelines:\n\n1. Code Efficiency:\n   - Optimize for both time and space complexity\n   - Use appropriate data structures and algorithms\n   - Avoid unnecessary computations or redundant operations\n\n2. Code Cleanliness:\n   - Follow PEP 8 style guidelines\n   - Use consistent and meaningful variable/function names\n   - Keep functions small and focused on a single task\n   - Organize code into logical modules and classes\n\n3. Pythonic Practices:\n   - Embrace Python's built-in functions and libraries\n   - Use list comprehensions and generator expressions when appropriate\n   - Leverage context managers (with statements) for resource management\n   - Utilize duck typing and EAFP (Easier to Ask for Forgiveness than Permission) principle\n\n4. Error Handling:\n   - Implement proper exception handling\n   - Use specific exception types\n   - Provide informative error messages\n\n5. Documentation:\n   - Write clear, concise docstrings for functions, classes, and modules\n   - Include inline comments for complex logic\n   - Use type hints to improve code readability and maintainability\n\n6. Performance Considerations:\n   - Be aware of the performance implications of different Python constructs\n   - Suggest profiling for performance-critical code\n\n7. Modern Python Features:\n   - Utilize features from recent Python versions when beneficial\n   - Be aware of backward compatibility concerns\n\n8. Code Reusability and Maintainability:\n   - Design functions and classes with reusability in mind\n   - Follow DRY (Don't Repeat Yourself) principle\n   - Implement proper encapsulation and abstraction\n\n9. Security:\n    - Be aware of common security pitfalls in Python\n    - Suggest secure coding practices when relevant\n\nWhen providing code solutions:\n1. Start with a brief explanation of your approach\n2. Present the code with proper formatting and indentation\n3. Explain key parts of the code, especially for complex logic\n4. Suggest improvements or alternative approaches if applicable\n5. Be receptive to questions and provide detailed explanations when asked\n\nYour goal is to not just solve problems, but to educate and promote best practices in Python development. Always strive to write code that is not only functional but also elegant, efficient, and easy to maintain.",
                    "files.data": "[]",
                    "group.hide_responses": 0,
                    "group.member_description": "",
                    "group.on_multiple_inputs": "Merged user message",
                    "group.output_placeholder": "",
                    "group.show_members_as_user_role": 1,
                    "info.avatar_path": "/home/jb/PycharmProjects/AgentPilot/docs/avatars/devhelp.png",
                    "info.name": "Dev Help",
                    "info.use_plugin": "",
                    "tools.data": "[]"
                },
                "French Tutor": {
                    "_TYPE": "agent",
                    "blocks.data": "[{\"placeholder\": \"learn-language\", \"value\": \"French\"}]",
                    "chat.display_markdown": True,
                    "chat.max_messages": 10,
                    "chat.max_turns": 7,
                    "chat.model": "gpt-4o",
                    "chat.on_consecutive_response": "REPLACE",
                    "chat.preload.data": "[]",
                    "chat.sys_msg": "## Role:\n\nYou are a {learn-language} Language Mentor who always speaks in {learn-language} and afterwards provides the identical English translation for everything you say in {learn-language}. You are designed to assist beginners in learning {learn-language}. Your primary function is to introduce the basics of the {learn-language} language, such as common phrases, basic grammar, pronunciation, and essential vocabulary. You will provide interactive lessons, practice exercises, and constructive feedback to help learners acquire foundational {learn-language} language skills.\n\n## Capabilities:\n\n- Introduce basic {learn-language} vocabulary and phrases.\n- Explain fundamental {learn-language} grammar rules.\n- Assist with pronunciation through phonetic guidance.\n- Provide simple conversational practice scenarios.\n- Offer quizzes and exercises to reinforce learning.\n- Correct mistakes in a supportive and informative manner.\n- Track progress and suggest areas for improvement.\n\n## Guidelines:\n\n- Always provide the identical English translation of anything you say in {learn-language}.\n- Start each session by assessing the user's current level of {learn-language}.\n- Offer lessons in a structured sequence, beginning with the alphabet and moving on to basic expressions.\n- Provide clear examples and use repetition to help with memorization.\n- Use phonetic spelling and audio examples to aid in pronunciation.\n- Create a safe environment for the user to practice speaking and writing.\n- When correcting errors, explain why the provided answer is incorrect and offer the correct option.\n- Encourage the user with positive reinforcement to build confidence.\n- Be responsive to the user's questions and provide explanations in simple terms.\n- Avoid complex linguistic terminology that may confuse a beginner.\n- Maintain a friendly and patient demeanor throughout the interaction.\n\nRemember, your goal is to foster an engaging and supportive learning experience that motivates beginners to continue studying the {learn-language} language.",
                    "chat.user_msg": "",
                    "files.data": "[]",
                    "info.avatar_path": "/home/jb/PycharmProjects/AgentPilot/docs/avatars/french-tutor.jpg",
                    "info.name": "French tutor",
                    "info.use_plugin": "",
                    "tools.data": "[]"
                },
                "Summarizer": {
                    "_TYPE": "agent",
                    "blocks.data": "[]",
                    "chat.max_turns": 2,
                    "chat.model": "mistral/mistral-large-latest",
                    "chat.preload.data": "[]",
                    "chat.sys_msg": "You have been assigned the task of adjusting summarized text after every user query.\nAfter each user query, adjust and return the summary in your previous assistant message modified to reflect any new information provided in the latest user query.\nMake as few changes as possible, and maintain a high quality and consise summary. \nYour task is to synthesize these responses into a single, high-quality response keeping only the information that is necessary.\nEnsure your response is well-structured, coherent, and adheres to the highest standards of accuracy and reliability.\nThe summarized text may contain a summary of text that is no longer in your context window, so be sure to keep all the information already in the summary.",
                    "files.data": "[]",
                    "info.name": "Summarizer",
                    "tools.data": "[]"
                }
            }

            app_settings = {
                "display.bubble_avatar_position": "Top",
                "display.bubble_spacing": 7,
                "display.primary_color": "#ff11121b",
                "display.secondary_color": "#ff222332",
                "display.show_bubble_avatar": "In Group",
                "display.show_bubble_name": "In Group",
                "display.show_waiting_bar": "In Group",
                "display.text_color": "#ffb0bbd5",
                "display.text_font": "",
                "display.text_size": 15,
                "display.window_margin": 6,
                "system.always_on_top": True,
                "system.auto_completion": False,
                "system.auto_title": True,
                "system.auto_title_model": "mistral/mistral-large-latest",
                "system.auto_title_prompt": "Write only a brief and concise title for a chat that begins with the following message:\n\n```{user_msg}```",
                "system.dev_mode": False,
                "system.language": "English",
                "system.telemetry": True,
                "system.voice_input_method": "None"
            }

            sql.execute('DELETE FROM contexts_messages')
            sql.execute('DELETE FROM contexts')
            sql.execute('DELETE FROM logs')

            sql.execute("UPDATE settings SET value = '' WHERE field = 'my_uuid'")
            sql.execute("UPDATE settings SET value = '0' WHERE field = 'accepted_tos'")
            sql.execute("UPDATE settings SET value = ? WHERE field = 'app_config'", (json.dumps(app_settings),))

            sql.execute('VACUUM')
            # # self.parent.update_config('system.dev_mode', False)
            # # self.toggle_dev_mode(False)
            # raise NotImplementedError()
            # self.parent.main.page_chat.workflow = Workflow(main=self.parent.main)
            # self.load()

        # def fix_empty_titles(self):
        #     retval = display_messagebox(
        #         icon=QMessageBox.Warning,
        #         text="Are you sure you want to fix empty titles? This could be very expensive and may take a while. The application will be unresponsive until it is finished.",
        #         title="Fix titles",
        #         buttons=QMessageBox.Yes | QMessageBox.No,
        #     )
        #
        #     if retval != QMessageBox.Yes:
        #         return
        #
        #     # get all contexts with empty titles
        #     contexts_first_msgs = sql.get_results("""
        #         SELECT c.id, cm.msg
        #         FROM contexts c
        #         INNER JOIN (
        #             SELECT *
        #             FROM contexts_messages
        #             WHERE rowid IN (
        #                 SELECT MIN(rowid)
        #                 FROM contexts_messages
        #                 GROUP BY context_id
        #             )
        #         ) cm ON c.id = cm.context_id
        #         WHERE c.name = '';
        #     """, return_type='dict')
        #
        #     conf = self.parent.main.system.config.dict
        #     model_name = conf.get('system.auto_title_model', 'mistral/mistral-large-latest')
        #     model_obj = (model_name, self.parent.main.system.providers.get_model_parameters(model_name))
        #
        #     prompt = conf.get('system.auto_title_prompt',
        #                       'Generate a brief and concise title for a chat that begins with the following message:\n\n{user_msg}')
        #     try:
        #         for context_id, msg in contexts_first_msgs.items():
        #             context_prompt = prompt.format(user_msg=msg)
        #
        #             title = llm.get_scalar(context_prompt, model_obj=model_obj)
        #             title = title.replace('\n', ' ').strip("'").strip('"')
        #             sql.execute('UPDATE contexts SET name = ? WHERE id = ?', (title, context_id))
        #
        #     except Exception as e:
        #         display_messagebox(
        #             icon=QMessageBox.Warning,
        #             text="Error generating titles: " + str(e),
        #             title="Error",
        #             buttons=QMessageBox.Ok,
        #         )

    class Page_Display_Settings(ConfigJoined):
        def __init__(self, parent):
            super().__init__(parent=parent)

            button_layout = CHBoxLayout()
            self.btn_delete_theme = IconButton(
                parent=self,
                icon_path=':/resources/icon-minus.png',
                tooltip='Delete theme',
                size=18,
            )
            self.btn_save_theme = IconButton(
                parent=self,
                icon_path=':/resources/icon-save.png',
                tooltip='Save current theme',
                size=18,
            )
            button_layout.addWidget(self.btn_delete_theme)
            button_layout.addWidget(self.btn_save_theme)
            button_layout.addStretch(1)
            self.layout.addLayout(button_layout)
            self.btn_save_theme.clicked.connect(self.save_theme)
            self.btn_delete_theme.clicked.connect(self.delete_theme)

            self.widgets = [
                self.Page_Display_Themes(parent=self),
                self.Page_Display_Fields(parent=self),
            ]

        def save_theme(self):
            current_config = self.get_current_display_config()
            current_config_str = json.dumps(current_config, sort_keys=True)
            theme_exists = sql.get_scalar("""
                SELECT COUNT(*)
                FROM themes
                WHERE config = ?
            """, (current_config_str,))
            if theme_exists:
                display_messagebox(
                    icon=QMessageBox.Warning,
                    text='Theme already exists',
                    title='Error',
                )
                return

            theme_name, ok = QInputDialog.getText(
                self,
                'Save Theme',
                'Enter a name for the theme:',
            )
            if not ok:
                return

            sql.execute("""
                INSERT INTO themes (name, config)
                VALUES (?, ?)
            """, (theme_name, current_config_str))
            self.load()

        def delete_theme(self):
            theme_name = self.widgets[0].theme.currentText()
            if theme_name == 'Custom':
                return

            retval = display_messagebox(
                icon=QMessageBox.Warning,
                text=f"Are you sure you want to delete the theme '{theme_name}'?",
                title="Delete Theme",
                buttons=QMessageBox.Yes | QMessageBox.No,
            )

            if retval != QMessageBox.Yes:
                return

            sql.execute("""
                DELETE FROM themes
                WHERE name = ?
            """, (theme_name,))
            self.load()

        def get_current_display_config(self):
            display_page = self.widgets[1]
            roles_config_temp = sql.get_results("""
                SELECT name, config
                FROM roles
                """, return_type='dict'
            )
            roles_config = {role_name: json.loads(config) for role_name, config in roles_config_temp.items()}

            current_config = {
                'assistant': {
                    'bubble_bg_color': roles_config['assistant']['bubble_bg_color'],
                    'bubble_text_color': roles_config['assistant']['bubble_text_color'],
                },
                'code': {
                    'bubble_bg_color': roles_config['code']['bubble_bg_color'],
                    'bubble_text_color': roles_config['code']['bubble_text_color'],
                },
                'display': {
                    'primary_color': get_widget_value(display_page.primary_color),
                    'secondary_color': get_widget_value(display_page.secondary_color),
                    'text_color': get_widget_value(display_page.text_color),
                },
                'user': {
                    'bubble_bg_color': roles_config['user']['bubble_bg_color'],
                    'bubble_text_color': roles_config['user']['bubble_text_color'],
                },
            }
            return current_config

        class Page_Display_Themes(ConfigFields):
            def __init__(self, parent):
                super().__init__(parent=parent)
                self.label_width = 185
                self.margin_left = 20
                self.propagate = False
                self.all_themes = {}
                self.schema = [
                    {
                        'text': 'Theme',
                        'type': ('Dark',),
                        'width': 100,
                        'default': 'Dark',
                    },
                ]

            def load(self):
                temp_themes = sql.get_results("""
                    SELECT name, config
                    FROM themes
                """, return_type='dict')
                self.all_themes = {theme_name: json.loads(config) for theme_name, config in temp_themes.items()}

                # load items into ComboBox
                with block_signals(self.theme):
                    self.theme.clear()
                    self.theme.addItems(['Custom'])
                    self.theme.addItems(self.all_themes.keys())

                current_display_config = self.parent.get_current_display_config()
                for theme_name in self.all_themes:
                    if self.all_themes[theme_name] == current_display_config:
                        # set self.theme (A ComboBox) to the current theme item, NOT setCurrentText
                        with block_signals(self.theme):
                            indx = self.theme.findText(theme_name)
                            self.theme.setCurrentIndex(indx)
                        return
                self.theme.setCurrentIndex(0)

            def after_init(self):
                self.theme.currentIndexChanged.connect(self.changeTheme)

            def changeTheme(self):
                theme_name = self.theme.currentText()
                if theme_name == 'Custom':
                    return
                # sql.execute("""
                #     UPDATE `settings` SET `value` = json_set(value, '$."display.primary_color"', ?) WHERE `field` = 'app_config'
                # """, (self.all_themes[theme_name]['display']['primary_color'],))
                # sql.execute("""
                #     UPDATE `settings` SET `value` = json_set(value, '$."display.secondary_color"', ?) WHERE `field` = 'app_config'
                # """, (self.all_themes[theme_name]['display']['secondary_color'],))
                # sql.execute("""
                #     UPDATE `settings` SET `value` = json_set(value, '$."display.text_color"', ?) WHERE `field` = 'app_config'
                # """, (self.all_themes[theme_name]['display']['text_color'],))
                # sql.execute("""
                #     UPDATE `roles` SET `config` = json_set(config, '$."bubble_bg_color"', ?) WHERE `name` = 'user'
                # """, (self.all_themes[theme_name]['user']['bubble_bg_color'],))
                # sql.execute("""
                #     UPDATE `roles` SET `config` = json_set(config, '$."bubble_text_color"', ?) WHERE `name` = 'user'
                # """, (self.all_themes[theme_name]['user']['bubble_text_color'],))
                # sql.execute("""
                #     UPDATE `roles` SET `config` = json_set(config, '$."bubble_bg_color"', ?) WHERE `name` = 'assistant'
                # """, (self.all_themes[theme_name]['assistant']['bubble_bg_color'],))
                # sql.execute("""
                #     UPDATE `roles` SET `config` = json_set(config, '$."bubble_text_color"', ?) WHERE `name` = 'assistant'
                # """, (self.all_themes[theme_name]['assistant']['bubble_text_color'],))
                # sql.execute("""
                #     UPDATE `roles` SET `config` = json_set(config, '$."bubble_bg_color"', ?) WHERE `name` = 'code'
                # """, (self.all_themes[theme_name]['code']['bubble_bg_color'],))
                # sql.execute("""
                #     UPDATE `roles` SET `config` = json_set(config, '$."bubble_text_color"', ?) WHERE `name` = 'code'
                # """, (self.all_themes[theme_name]['code']['bubble_text_color'],))
                # CAHNGE ALL THIS INTO A json_patch
                patch_dicts = {
                    'settings': {
                        'display.primary_color': self.all_themes[theme_name]['display']['primary_color'],
                        'display.secondary_color': self.all_themes[theme_name]['display']['secondary_color'],
                        'display.text_color': self.all_themes[theme_name]['display']['text_color'],
                    },
                    'roles': {}
                }
                # patch settings table
                sql.execute("""
                    UPDATE `settings` SET `value` = json_patch(value, ?) WHERE `field` = 'app_config'
                """, (json.dumps(patch_dicts['settings']),))

                if 'user' in self.all_themes[theme_name]:
                    patch_dicts['roles']['user'] = {
                        'bubble_bg_color': self.all_themes[theme_name]['user']['bubble_bg_color'],
                        'bubble_text_color': self.all_themes[theme_name]['user']['bubble_text_color'],
                    }
                    # patch user role
                    sql.execute("""
                        UPDATE `roles` SET `config` = json_patch(config, ?) WHERE `name` = 'user'
                    """, (json.dumps(patch_dicts['roles']['user']),))
                if 'assistant' in self.all_themes[theme_name]:
                    patch_dicts['roles']['assistant'] = {
                        'bubble_bg_color': self.all_themes[theme_name]['assistant']['bubble_bg_color'],
                        'bubble_text_color': self.all_themes[theme_name]['assistant']['bubble_text_color'],
                    }
                    # patch assistant role
                    sql.execute("""
                        UPDATE `roles` SET `config` = json_patch(config, ?) WHERE `name` = 'assistant'
                    """, (json.dumps(patch_dicts['roles']['assistant']),))
                if 'code' in self.all_themes[theme_name]:
                    patch_dicts['roles']['code'] = {
                        'bubble_bg_color': self.all_themes[theme_name]['code']['bubble_bg_color'],
                        'bubble_text_color': self.all_themes[theme_name]['code']['bubble_text_color'],
                    }
                    # patch code role
                    sql.execute("""
                        UPDATE `roles` SET `config` = json_patch(config, ?) WHERE `name` = 'code'
                    """, (json.dumps(patch_dicts['roles']['code']),))

                system = self.parent.parent.main.system
                system.config.load()
                system.roles.load()
                self.parent.parent.main.apply_stylesheet()

                page_settings = self.parent.parent
                page_settings.load_config(system.config.dict)
                page_settings.load()

        class Page_Display_Fields(ConfigFields):
            def __init__(self, parent):
                super().__init__(parent=parent)
                self.parent = parent

                self.label_width = 185
                self.margin_left = 20
                self.conf_namespace = 'display'
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
                        'default': 'Default',
                    },
                    {
                        'text': 'Text size',
                        'type': int,
                        'minimum': 6,
                        'maximum': 72,
                        'default': 12,
                    },
                    {
                        'text': 'Show bubble name',
                        'type': ('In Group', 'Always', 'Never',),
                        'default': 'In Group',
                    },
                    {
                        'text': 'Show bubble avatar',
                        'type': ('In Group', 'Always', 'Never',),
                        'default': 'In Group',
                    },
                    {
                        'text': 'Show waiting bar',
                        'type': ('In Group', 'Always', 'Never',),
                        'default': 'In Group',
                    },
                    {
                        'text': 'Bubble avatar position',
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
                    {
                        'text': 'Window margin',
                        'type': int,
                        'minimum': 0,
                        'maximum': 69,
                        'default': 6,
                    }
                ]

            def load(self):
                super().load()
                self.parent.widgets[0].load()  # load theme
                main = find_main_widget(self)
                main.apply_margin()

            def update_config(self):
                super().update_config()
                main = self.parent.parent.main
                main.system.config.load()
                main.apply_stylesheet()
                main.page_chat.refresh_waiting_bar()
                self.load()  # reload theme combobox for custom

    class Page_Role_Settings(ConfigDBTree):
        def __init__(self, parent):
            super().__init__(
                parent=parent,
                db_table='roles',
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

        def on_edited(self):
            self.parent.main.system.roles.load()
            self.parent.main.apply_stylesheet()

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

    class Page_Files_Settings(ConfigTabs):
        def __init__(self, parent):
            super().__init__(parent=parent)
            self.main = find_main_widget(self)
            self.pages = {
                'Filesystem': self.Page_Filesystem(parent=self),
                'Extensions': self.Page_Extensions(parent=self),
                # 'Folders': self.Page_Folders(parent=self),
            }

        class Page_Filesystem(ConfigDBTree):
            def __init__(self, parent):
                super().__init__(
                    parent=parent,
                    db_table='files',
                    propagate=False,
                    query="""
                        SELECT
                            name,
                            id,
                            folder_id
                        FROM files""",
                    schema=[
                        {
                            'text': 'Files',
                            'key': 'file',
                            'type': str,
                            'label_position': None,
                            'stretch': True,
                        },
                        {
                            'text': 'id',
                            'key': 'id',
                            'type': int,
                            'visible': False,
                        },
                    ],
                    add_item_prompt=('NA', 'NA'),
                    del_item_prompt=('NA', 'NA'),
                    tree_header_hidden=True,
                    readonly=True,
                    layout_type=QHBoxLayout,
                    config_widget=self.File_Config_Widget(parent=self),
                    folder_key='filesystem',
                    tree_width=350,
                    folders_groupable=True,
                )

            # def load(self, select_id=None, append=False):
            #     if not self.query:
            #         return
            #
            #     print("Loading directories...")   # DEBUG
            #
            #     folder_query = """
            #         SELECT
            #             id,
            #             name,
            #             parent_id,
            #             type,
            #             ordr
            #         FROM folders
            #         WHERE `type` = ?
            #         ORDER BY ordr
            #     """
            #
            #     folders_data = sql.get_results(query=folder_query, params=(self.folder_key,))
            #     print("folders_data:", folders_data) # DEBUG
            #     folders_dict = self._build_nested_dict(folders_data)
            #     print("folders_dict:", folders_dict) # DEBUG
            #     data = sql.get_results(query=self.query, params=self.query_params)
            #     print("data:", data) # DEBUG
            #
            #     data = self._merge_folders(folders_dict, data)
            #
            #     print("merged data:", data) # DEBUG
            #
            #     self.tree.load(
            #         data=data,
            #         append=append,
            #         folders_data=folders_data,
            #         select_id=select_id,
            #         folder_key=self.folder_key,
            #         init_select=self.init_select,
            #         readonly=self.readonly,
            #         schema=self.schema
            #     )

            def add_item(self, column_vals=None, icon=None):
                with block_pin_mode():
                    file_dialog = QFileDialog()
                    file_dialog.setFileMode(QFileDialog.ExistingFile)
                    file_dialog.setOption(QFileDialog.ShowDirsOnly, False)
                    file_dialog.setFileMode(QFileDialog.Directory)
                    path, _ = file_dialog.getOpenFileName(None, "Choose Files", "", options=file_dialog.Options())

                if path:
                    self.add_path(path)

            # def delete_item(self):
            #     item = self.tree.currentItem()
            #     if not item:
            #         return None
            #     tag = item.data(0, Qt.UserRole)
            #     if tag == 'folder':
            #         return
            #     super().delete_item()

            def add_ext_folder(self):
                with block_pin_mode():
                    file_dialog = QFileDialog()
                    file_dialog.setFileMode(QFileDialog.Directory)
                    file_dialog.setOption(QFileDialog.ShowDirsOnly, True)
                    path = file_dialog.getExistingDirectory(self, "Choose Directory", "")
                    if path:
                        self.add_path(path)

            def add_path(self, path):
                base_directory = os.path.dirname(path)
                directories = []
                while base_directory:
                    # folder_name = os.path.basename(base_directory) if base_directory else None
                    directories.append(os.path.basename(base_directory))
                    next_directory = os.path.dirname(base_directory)
                    base_directory = next_directory if next_directory != base_directory else None

                directories = reversed(directories)
                parent_id = None
                for directory in directories:
                    parent_id = super().add_folder(directory, parent_id)
                    # sql.execute(f"INSERT INTO `files` (`name`) VALUES (?)", (directory,))
                    # last_insert_id = sql.get_scalar("SELECT seq FROM sqlite_sequence WHERE name=?", (self.db_table,))
                    # self.load(select_id=last_insert_id)

                name = os.path.basename(path)
                config = json.dumps({'path': path, })
                sql.execute(f"INSERT INTO `files` (`name`, `folder_id`) VALUES (?, ?)", (name, parent_id,))
                last_insert_id = sql.get_scalar("SELECT seq FROM sqlite_sequence WHERE name=?", (self.db_table,))
                self.load(select_id=last_insert_id)
                return True
                # filename = os.path.basename(path)
                # is_dir = os.path.isdir(path)
                # row_dict = {'filename': filename, 'location': path, 'is_dir': is_dir}
                #
                # icon_provider = QFileIconProvider()
                # icon = icon_provider.icon(QFileInfo(path))
                # if icon is None or isinstance(icon, QIcon) is False:
                #     icon = QIcon()
                #
                # self.add_item(row_dict, icon)

            def dragEnterEvent(self, event):
                # Check if the event contains file paths to accept it
                if event.mimeData().hasUrls():
                    event.acceptProposedAction()

            def dragMoveEvent(self, event):
                # Check if the event contains file paths to accept it
                if event.mimeData().hasUrls():
                    event.acceptProposedAction()

            def dropEvent(self, event):
                # Get the list of URLs from the event
                urls = event.mimeData().urls()

                # Extract local paths from the URLs
                paths = [url.toLocalFile() for url in urls]

                for path in paths:
                    self.add_path(path)

                event.acceptProposedAction()

            class File_Config_Widget(ConfigFields):
                def __init__(self, parent):
                    super().__init__(parent=parent)
                    self.label_width = 175
                    self.schema = []

        class Page_Extensions(ConfigDBTree):
            def __init__(self, parent):
                super().__init__(
                    parent=parent,
                    db_table='file_exts',
                    propagate=False,
                    query="""
                        SELECT
                            name,
                            id,
                            folder_id
                        FROM file_exts
                        ORDER BY name""",
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
                    ],
                    add_item_prompt=('Add extension', "Enter the file extension without the '.' prefix"),
                    del_item_prompt=('Delete extension', 'Are you sure you want to delete this extension?'),
                    readonly=False,
                    folder_key='file_exts',
                    layout_type=QHBoxLayout,
                    config_widget=self.Extensions_Config_Widget(parent=self),
                    tree_width=150,
                )

            def on_edited(self):
                self.parent.main.system.files.load()

            class Extensions_Config_Widget(ConfigFields):
                def __init__(self, parent):
                    super().__init__(parent=parent)
                    self.schema = [
                        {
                            'text': 'Default attachment method',
                            'type': ('Add path to message','Add contents to message','Encode base64',),
                            'default': 'Add path to message',
                            # 'width': 385,
                        },
                    ]

    class Page_VecDB_Settings(ConfigDBTree):
        def __init__(self, parent):
            super().__init__(
                parent=parent,
                db_table='vectordbs',
                propagate=False,
                query="""
                    SELECT
                        name,
                        id,
                        folder_id
                    FROM vectordbs""",
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
                ],
                add_item_prompt=('Add VecDB', 'Enter a name for the vector db:'),
                del_item_prompt=('Delete VecDB', 'Are you sure you want to delete this vector db?'),
                readonly=False,
                layout_type=QHBoxLayout,
                folder_key='vectordbs',
                config_widget=self.VectorDBConfig(parent=self),
                tree_width=150,
            )

        def on_edited(self):
            self.parent.main.system.vectordbs.load()

        class VectorDBConfig(ConfigPlugin):
            def __init__(self, parent):
                super().__init__(
                    parent,
                    plugin_type='VectorDBSettings',
                    plugin_json_key='vec_db_provider',
                    plugin_label_text='VectorDB provider',
                    none_text='LanceDB'
                )
                self.default_class = self.LanceDB_VecDBConfig

            class LanceDB_VecDBConfig(ConfigTabs):
                def __init__(self, *args, **kwargs):
                    super().__init__(*args, **kwargs)
                    self.pages = {
                        'Config': self.Page_VecDB_Config(parent=self),
                        # 'Test run': self.Page_Run(parent=self),
                    }

                class Page_VecDB_Config(ConfigJoined):
                    def __init__(self, parent):
                        super().__init__(parent=parent, layout_type=QHBoxLayout)
                        self.widgets = [
                            # self.Tool_Info_Widget(parent=self),
                            self.Env_Vars_Widget(parent=self),
                        ]

                    # class
                    class Env_Vars_Widget(ConfigJsonTree):
                        def __init__(self, parent):
                            super().__init__(parent=parent,
                                             add_item_prompt=('NA', 'NA'),
                                             del_item_prompt=('NA', 'NA'))
                            self.parent = parent
                            self.conf_namespace = 'env_vars'
                            self.schema = [
                                {
                                    'text': 'Variable',
                                    'type': str,
                                    'width': 120,
                                    'default': 'Variable name',
                                },
                                {
                                    'text': 'Value',
                                    'type': str,
                                    'stretch': True,
                                    'default': '',
                                },
                            ]

    class Page_Sandbox_Settings(ConfigDBTree):
        def __init__(self, parent):
            super().__init__(
                parent=parent,
                db_table='sandboxes',
                propagate=False,
                query="""
                    SELECT
                        name,
                        id,
                        folder_id
                    FROM sandboxes""",
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
                ],
                add_item_prompt=('Add Sandbox', 'Enter a name for the sandbox:'),
                del_item_prompt=('Delete Sandbox', 'Are you sure you want to delete this sandbox?'),
                readonly=False,
                layout_type=QHBoxLayout,
                folder_key='sandboxes',
                config_widget=self.SandboxConfig(parent=self),
                tree_width=150,
            )

        def on_edited(self):
            self.parent.main.system.sandboxes.load()

        class SandboxConfig(ConfigPlugin):
            def __init__(self, parent):
                super().__init__(
                    parent,
                    plugin_type='SandboxSettings',
                    plugin_json_key='sandbox_type',
                    plugin_label_text='Sandbox Type',
                    none_text='Local'
                )
                self.default_class = self.Local_SandboxConfig

            class Local_SandboxConfig(ConfigTabs):
                def __init__(self, *args, **kwargs):
                    super().__init__(*args, **kwargs)
                    self.pages = {
                        'Venv': self.Page_Venv(parent=self),
                        'Config': self.Page_Sandbox_Config(parent=self),
                        'Test run': self.Page_Run(parent=self),
                    }

                class Page_Venv(ConfigJoined):
                    def __init__(self, parent):
                        super().__init__(parent=parent, layout_type=QVBoxLayout)
                        self.widgets = [
                            self.Page_Venv_Config(parent=self),
                            self.Page_Packages(parent=self),
                        ]

                    class Page_Venv_Config(ConfigFields):
                        def __init__(self, parent):
                            super().__init__(parent=parent)
                            self.schema = [
                                {
                                    'text': 'Venv',
                                    'type': 'VenvComboBox',
                                    'width': 350,
                                    'label_position': None,
                                    'default': 'default',
                                },
                            ]

                        def reload_venv(self):
                            from src.system.base import manager
                            # self.parent.widgets[1].load()
                            venv_name = get_widget_value(self.venv)
                            venv = manager.venvs.venvs.get(venv_name)
                            if not venv:
                                return
                            packages = venv.list_packages()
                            pass

                    class Page_Packages(ConfigJoined):
                        def __init__(self, parent):
                            super().__init__(parent=parent, layout_type=QHBoxLayout)
                            self.widgets = [
                                self.Installed_Libraries(parent=self),
                                self.Pypi_Libraries(parent=self),
                            ]
                            self.setFixedHeight(450)

                        class Pypi_Libraries(ConfigDBTree):
                            def __init__(self, parent):
                                super().__init__(
                                    parent=parent,
                                    db_table='pypi_packages',
                                    propagate=False,
                                    query="""
                                        SELECT
                                            name,
                                            folder_id
                                        FROM pypi_packages
                                        LIMIT 1000""",
                                    schema=[
                                        {
                                            'text': 'Browse PyPI',
                                            'key': 'name',
                                            'type': str,
                                            'width': 150,
                                        },
                                    ],
                                    tree_width=150,
                                    tree_height=450,
                                    layout_type=QHBoxLayout,
                                    folder_key='pypi_packages',
                                    searchable=True,
                                )
                                self.btn_sync = IconButton(
                                    parent=self.tree_buttons,
                                    icon_path=':/resources/icon-refresh.png',
                                    tooltip='Update package list',
                                    size=18,
                                )
                                self.btn_sync.clicked.connect(self.sync_pypi_packages)
                                self.tree_buttons.add_button(self.btn_sync, 'btn_sync')
                                self.hide()

                            def on_item_selected(self):
                                pass

                            def filter_rows(self):
                                if not self.show_tree_buttons:
                                    return

                                search_query = self.tree_buttons.search_box.text().lower()
                                if not self.tree_buttons.search_box.isVisible():
                                    search_query = ''

                                if search_query == '':
                                    self.query = """
                                        SELECT
                                            name,
                                            folder_id
                                        FROM pypi_packages
                                        LIMIT 1000
                                    """
                                else:
                                    self.query = f"""
                                        SELECT
                                            name,
                                            folder_id
                                        FROM pypi_packages
                                        WHERE name LIKE '%{search_query}%'
                                        LIMIT 1000
                                    """
                                self.load()

                            def sync_pypi_packages(self):
                                import requests
                                import re

                                url = 'https://pypi.org/simple/'
                                response = requests.get(url, stream=True)

                                items = []
                                batch_size = 10000

                                pattern = re.compile(r'<a[^>]*>(.*?)</a>')
                                previous_overlap = ''
                                for chunk in response.iter_content(chunk_size=10240):
                                    if chunk:
                                        chunk_str = chunk.decode('utf-8')
                                        chunk = previous_overlap + chunk_str
                                        previous_overlap = chunk_str[-100:]

                                        matches = pattern.findall(chunk)
                                        for match in matches:
                                            item_name = match.strip()
                                            if item_name:
                                                items.append(item_name)

                                    if len(items) >= batch_size:
                                        # generate the query directly without using params
                                        query = 'INSERT OR IGNORE INTO pypi_packages (name) VALUES ' + ', '.join(
                                            [f"('{item}')" for item in items])
                                        sql.execute(query)
                                        items = []

                                # Insert any remaining items
                                if items:
                                    query = 'INSERT OR IGNORE INTO pypi_packages (name) VALUES ' + ', '.join(
                                        [f"('{item}')" for item in items])
                                    sql.execute(query)

                                print('Scraping and storing items completed.')
                                self.load()
                                # import requests
                                # # from bs4 import BeautifulSoup
                                # # import html
                                # from lxml import etree
                                #
                                # url = 'https://pypi.org/simple/'
                                # response = requests.get(url, stream=True)
                                #
                                # items = []
                                # batch_size = 10000
                                #
                                # parser = etree.HTMLParser()
                                # previous_overlap = ''
                                # for chunk in response.iter_content(chunk_size=10240):
                                #     if chunk:
                                #         chunk_str = chunk.decode('utf-8')
                                #         chunk = previous_overlap + chunk_str
                                #         previous_overlap = chunk_str[-100:]
                                #
                                #         tree = etree.fromstring(chunk, parser)
                                #         for element in tree.xpath('//a'):
                                #             if element is None:
                                #                 continue
                                #             if element.text is None:
                                #                 continue
                                #
                                #             item_name = element.text.strip()
                                #             items.append(item_name)
                                #
                                #     if len(items) >= batch_size:
                                #         # generate the query directly without using params
                                #         query = 'INSERT OR IGNORE INTO pypi_packages (name) VALUES ' + ', '.join([f"('{item}')" for item in items])
                                #         sql.execute(query)
                                #         items = []
                                #
                                # # Insert any remaining items
                                # if items:
                                #     query = 'INSERT OR IGNORE INTO pypi_packages (name) VALUES ' + ', '.join([f"('{item}')" for item in items])
                                #     sql.execute(query)
                                #
                                # print('Scraping and storing items completed.')

                        class Installed_Libraries(ConfigExtTree):
                            def __init__(self, parent):
                                super().__init__(
                                    parent=parent,
                                    conf_namespace='installed_packages',
                                    schema=[
                                        {
                                            'text': 'Installed packages',
                                            'key': 'name',
                                            'type': str,
                                            'width': 150,
                                        },
                                    ],
                                    add_item_prompt=('NA', 'NA'),
                                    del_item_prompt=('Uninstall Package', 'Are you sure you want to uninstall this package?'),
                                    tree_width=150,
                                    tree_height=450,
                                )

                            class LoadRunnable(QRunnable):
                                def __init__(self, parent):
                                    super().__init__()
                                    self.parent = parent
                                    self.page_chat = parent.main.page_chat

                                def run(self):
                                    import sys
                                    try:
                                        packages = sorted(set([module.split('.')[0] for module in sys.modules.keys()]))
                                        rows = [[package] for package in packages]

                                        self.parent.fetched_rows_signal.emit(rows)
                                    except Exception as e:
                                        self.page_chat.main.error_occurred.emit(str(e))

                            def add_item(self):
                                pypi_visible = self.parent.widgets[1].isVisible()
                                self.parent.widgets[1].setVisible(not pypi_visible)

                            # def __init__(self, parent):
                            #     super().__init__(parent=parent,
                            #                      add_item_prompt=('NA', 'NA'),
                            #                      del_item_prompt=('NA', 'NA'))
                            #     self.parent = parent
                            #     self.setFixedWidth(250)
                            #     self.conf_namespace = 'libraries'
                            #     self.schema = [
                            #         {
                            #             'text': 'Library',
                            #             'type': str,
                            #             'width': 120,
                            #             'default': 'Library name',
                            #         },
                            #         {
                            #             'text': 'Version',
                            #             'type': str,
                            #             'width': 120,
                            #             'default': '',
                            #         },
                            #     ]
                            #
                            # def load(self):
                            #     super().load()
                            #     self.load_libraries()
                            #
                            # def load_libraries(self):
                            #     import sys
                            #     packages = sorted(set([module.split('.')[0] for module in sys.modules.keys()]))
                            #     return packages

                class Page_Sandbox_Config(ConfigJoined):
                    def __init__(self, parent):
                        super().__init__(parent=parent, layout_type=QHBoxLayout)
                        self.widgets = [
                            # self.Widget_Config_Fields(parent=self),
                            # self.Widget_Env_Vars(parent=self),
                        ]

                    class Widget_Config_Fields(ConfigFields):
                        def __init__(self, parent):
                            super().__init__(parent=parent)
                            self.parent = parent
                            self.label_width = 125
                            self.margin_left = 20
                            self.conf_namespace = 'system'
                            self.schema = [
                                {
                                    'text': 'Use default venv',
                                    'type': bool,
                                    'default': 'en',
                                },
                                {
                                    'text': 'Dev mode',
                                    'type': bool,
                                    'default': False,
                                },
                            ]

                    class Widget_Env_Vars(ConfigJsonTree):
                        def __init__(self, parent):
                            super().__init__(parent=parent,
                                             add_item_prompt=('NA', 'NA'),
                                             del_item_prompt=('NA', 'NA'))
                            self.parent = parent
                            self.setFixedWidth(250)
                            self.conf_namespace = 'env_vars'
                            self.schema = [
                                {
                                    'text': 'Env Var',
                                    'type': str,
                                    'width': 120,
                                    'default': 'Variable name',
                                },
                                {
                                    'text': 'Value',
                                    'type': str,
                                    'width': 120,
                                    'default': '',
                                },
                            ]

                class Page_Run(ConfigFields):
                    def __init__(self, parent):
                        super().__init__(parent=parent)
                        self.conf_namespace = 'code'
                        self.schema = [
                            {
                                'text': 'Language',
                                'type': ('AppleScript', 'HTML', 'JavaScript', 'Python', 'PowerShell', 'R', 'React', 'Ruby', 'Shell',),
                                'width': 100,
                                'tooltip': 'The language of the code to test',
                                'row_key': 'A',
                                'default': 'Python',
                            },
                            {
                                'text': 'Code',
                                'key': 'data',
                                'type': str,
                                'width': 300,
                                'num_lines': 15,
                                'label_position': None,
                                'highlighter': PythonHighlighter,
                                'encrypt': True,
                                'default': '',
                            },
                        ]

                    def after_init(self):
                        self.btn_run = QPushButton('Run')
                        self.btn_run.clicked.connect(self.on_run)

                        self.output = QTextEdit()
                        self.output.setReadOnly(True)
                        self.output.setFixedHeight(150)
                        self.layout.addWidget(self.btn_run)
                        self.layout.addWidget(self.output)

                    def on_run(self):
                        lang = self.config.get('code.language', 'Python')
                        code = self.config.get('code.data', '')
                        try:
                            oi_res = interpreter.computer.run(lang, code)
                            output = next(r for r in oi_res if r['format'] == 'output').get('content', '')
                        except Exception as e:
                            output = str(e)
                        self.output.setPlainText(output)

    class Page_Logs_Settings(ConfigDBTree):
        def __init__(self, parent):
            super().__init__(
                parent=parent,
                db_table='logs',
                propagate=False,
                query="""
                    SELECT
                        name,
                        id,
                        folder_id
                    FROM logs""",
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
                ],
                add_item_prompt=None,
                del_item_prompt=('Delete Log', 'Are you sure you want to delete this log?'),
                readonly=True,
                layout_type=QVBoxLayout,
                folder_key='logs',
                config_widget=self.LogConfig(parent=self),
                # tree_width=150,
            )

        def on_edited(self):
            self.parent.main.system.logs.load()

        class LogConfig(ConfigFields):
            def __init__(self, parent):
                super().__init__(parent=parent)
                self.schema = [
                    {
                        'text': 'Log type',
                        'type': ('File', 'Database', 'API',),
                        'default': 'File',
                    },
                    {
                        'text': 'Log path',
                        'type': str,
                        'default': '',
                    },
                    {
                        'text': 'Log level',
                        'type': ('Debug', 'Info', 'Warning', 'Error', 'Critical',),
                        'default': 'Info',
                    },
                    {
                        'text': 'Log format',
                        'type': str,
                        'default': '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    },
                ]

    class Page_Workspace_Settings(ConfigDBTree):
        def __init__(self, parent):
            super().__init__(
                parent=parent,
                db_table='workspaces',
                propagate=False,
                query="""
                    SELECT
                        name,
                        id,
                        folder_id
                    FROM workspaces""",
                schema=[
                    {
                        'text': 'Workspaces',
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
                add_item_prompt=('Add Workspace', 'Enter a name for the workspace:'),
                del_item_prompt=('Delete Workspace', 'Are you sure you want to delete this workspace?'),
                readonly=False,
                layout_type=QHBoxLayout,
                folder_key='workspaces',
                config_widget=self.WorkspaceConfig(parent=self),
                tree_width=150,
            )

        def on_edited(self):
            self.parent.main.system.workspaces.load()

        class WorkspaceConfig(ConfigFields):
            def __init__(self, parent):
                super().__init__(parent=parent)
                self.schema = [
                    {
                        'text': 'Environment',
                        'type': 'SandboxComboBox',
                        'default': 'Local',
                    },
                ]

    class Page_Plugin_Settings(ConfigTabs):
        def __init__(self, parent):
            super().__init__(parent=parent)
            self.conf_namespace = 'plugins'

            self.pages = {
                # 'GPT Pilot': self.Page_Test(parent=self),
                # 'CrewAI': Page_Settings_CrewAI(parent=self),
                'Matrix': Page_Settings_Matrix(parent=self),
                'OAI': Page_Settings_OAI(parent=self),
                # 'Test Pypi': self.Page_Pypi_Packages(parent=self),
            }
