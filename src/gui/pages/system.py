import keyring
import requests
from PySide6.QtCore import Signal, QRunnable, Slot
from PySide6.QtGui import Qt
from PySide6.QtWidgets import QHBoxLayout, QLineEdit, QLabel, QPushButton, QMessageBox
from keyring.errors import PasswordDeleteError

from src.gui.widgets.config_async_widget import ConfigAsyncWidget
from src.gui.widgets.config_fields import ConfigFields
from src.gui.widgets.config_joined import ConfigJoined
from src.gui.widgets.config_pages import ConfigPages
from src.utils.helpers import display_message, set_module_type
from src.gui.util import find_main_widget
from src.utils.reset import reset_application


class Page_System_Settings(ConfigJoined):
    display_name = 'System'
    page_type = 'settings'  # either 'settings', 'main', or 'any' ('any' means it can be pinned between main and settings)

    def __init__(self, parent):
        super().__init__(parent=parent)
        # self.main = parent.main
        self.conf_namespace = 'system'
        self.widgets = [
            # self.Page_System_Login(parent=self),
            self.Page_System_Fields(parent=self),
        ]

    # class Page_System_Login(ConfigAsyncWidget):
    #     fetched_logged_in_user = Signal(str)
    #
    #     def __init__(self, parent):
    #         super().__init__(parent=parent)
    #         self.propagate = False
    #         self.fetched_logged_in_user.connect(self.load_user, Qt.QueuedConnection)
    #         self.layout = QHBoxLayout(self)
    #
    #         self.lbl_username = QLabel('username')
    #         self.lbl_username.hide()
    #         self.username = QLineEdit()
    #         self.username.setPlaceholderText('Username')
    #         self.username.setFixedWidth(150)
    #         self.password = QLineEdit()
    #         self.password.setPlaceholderText('Password')
    #         self.password.setFixedWidth(150)
    #         self.password.setEchoMode(QLineEdit.EchoMode.Password)
    #
    #         self.login_button = QPushButton('Login')
    #         self.login_button.setFixedWidth(100)
    #         self.login_button.clicked.connect(self.login)
    #
    #         self.logout_button = QPushButton('Logout')
    #         self.logout_button.setFixedWidth(100)
    #         self.logout_button.clicked.connect(self.logout)
    #         self.logout_button.hide()
    #
    #         self.layout.addWidget(self.lbl_username)
    #         self.layout.addWidget(self.username)
    #         self.layout.addWidget(self.password)
    #         self.layout.addWidget(self.login_button)
    #         self.layout.addWidget(self.logout_button)
    #         self.layout.addStretch(1)
    #
    #         self.load()
    #
    #     class LoadRunnable(QRunnable):
    #         def __init__(self, parent):
    #             super().__init__()
    #             self.parent = parent
    #
    #         def run(self):
    #             user = self.parent.validate_user()
    #             self.parent.fetched_logged_in_user.emit(user)
    #
    #     def validate_user(self):
    #         token = keyring.get_password("agentpilot", "user")
    #         url = "https://agentpilot.ai/api/auth.php"
    #         data = {
    #             'action': 'validate',
    #             'token': token
    #         }
    #         try:
    #             response = requests.post(url, data=data)
    #             response.raise_for_status()  # Raises an HTTPError for bad responses
    #             result = response.json()
    #         except requests.RequestException as e:
    #             result = {"success": False, "message": f"Request failed: {str(e)}"}
    #
    #         if not result.get('success', False) or 'username' not in result:
    #             return None
    #
    #         return result['username']
    #
    #     @Slot(str)
    #     def load_user(self, user):
    #         logged_in = user != ''
    #         self.username.setVisible(not logged_in)
    #         self.password.setVisible(not logged_in)
    #         self.login_button.setVisible(not logged_in)
    #         self.logout_button.setVisible(logged_in)
    #         self.lbl_username.setVisible(logged_in)
    #
    #         if logged_in:
    #             self.lbl_username.setText(f'Logged in as: {user}')
    #
    #     def login(self):
    #         username = self.username.text()
    #         password = self.password.text()
    #         url = "https://agentpilot.ai/api/auth.php"
    #
    #         try:
    #             if not username or not password:
    #                 raise ValueError("Username and password are required")
    #             data = {
    #                 'action': 'login',
    #                 'username': username,
    #                 'password': password
    #             }
    #
    #             response = requests.post(url, data=data)
    #             response.raise_for_status()  # Raises an HTTPError for bad responses
    #             result = response.json()
    #         except Exception as e:
    #             result = {"success": False, "message": f"Request failed: {str(e)}"}
    #
    #         if not result.get('success', False) or 'token' not in result:
    #             display_message(self, 'Login failed', 'Error', QMessageBox.Warning)
    #             return
    #
    #         token = result['token']
    #         try:
    #             keyring.set_password("agentpilot", "user", token)
    #         except Exception as e:
    #             display_message(self, f"Error logging in: {str(e)}", 'Error', QMessageBox.Warning)
    #
    #         self.load()
    #
    #     def logout(self):
    #         try:
    #             keyring.delete_password("agentpilot", "user")
    #         except PasswordDeleteError:
    #             pass
    #         except Exception as e:
    #             display_message(self, f"Error logging out: {str(e)}", 'Error', QMessageBox.Warning)
    #
    #         self.load()

    class Page_System_Fields(ConfigFields):
        def __init__(self, parent):
            super().__init__(parent=parent)
            self.parent = parent
            self.main = find_main_widget(self)
            self.label_width = 145
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
                    'text': 'Multi-window',
                    'type': bool,
                    'default': True,
                },
                {
                    'text': 'Auto-run tools',
                    'type': int,
                    'minimum': 0,
                    'maximum': 30,
                    'step': 1,
                    'default': 5,
                    'label_width': 165,
                    'has_toggle': True,
                },
                {
                    'text': 'Auto-run code',
                    'type': int,
                    'minimum': 0,
                    'maximum': 30,
                    'step': 1,
                    'default': 5,
                    'label_width': 165,
                    'tooltip': 'Auto-run code messages (where role = code)',
                    'has_toggle': True,
                },
                {
                    'text': 'Voice input method',
                    'type': ('None',),
                    'default': 'None',
                },
                {
                    'text': 'Default chat model',
                    'type': 'ModelComboBox',
                    'model_kind': 'CHAT',
                    'default': 'mistral/mistral-large-latest',
                },
                {
                    'text': 'Default voice model',
                    'type': 'ModelComboBox',
                    'model_kind': 'VOICE',
                    'default': {
                        'kind': 'VOICE',
                        'model_name': '9BWtsMINqrJLrRacOk9x',
                        # 'model_params': {},
                        'provider': 'elevenlabs',
                    },
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
                    'model_kind': 'CHAT',
                    'default': 'mistral/mistral-large-latest',
                    'row_key': 0,
                },
                {
                    'text': 'Auto-title prompt',
                    'type': str,
                    'default': 'Generate a brief and concise title for a chat that begins with the following message:\n\n{user_msg}',
                    'num_lines': 5,
                    'label_position': 'top',
                    'stretch_x': True,
                },
            ]

        def after_init(self):
            self.dev_mode.stateChanged.connect(lambda state: self.toggle_dev_mode(state))
            self.always_on_top.stateChanged.connect(self.main.toggle_always_on_top)

            # add a button 'Reset database'
            self.reset_app_btn = QPushButton('Reset Application')
            self.reset_app_btn.clicked.connect(reset_application)
            self.layout.addWidget(self.reset_app_btn)

            self.run_test_btn = QPushButton('Run Tutorial')
            self.run_test_btn.clicked.connect(self.main.run_test)
            self.layout.addWidget(self.run_test_btn)

        def toggle_dev_mode(self, state=None):
            # pass
            if state is None and hasattr(self, 'dev_mode'):
                state = self.dev_mode.isChecked()

            self.main.page_chat.top_bar.btn_info.setVisible(state)
            self.reset_app_btn.setVisible(state)
            self.run_test_btn.setVisible(state)

            for config_pages in self.main.findChildren(ConfigPages):
                for page_name, page in config_pages.pages.items():
                    page_is_dev_mode = getattr(page, 'IS_DEV_MODE', False)
                    if not page_is_dev_mode:
                        continue
                    config_pages.settings_sidebar.page_buttons[page_name].setVisible(state)

            # self.main.apply_stylesheet()
