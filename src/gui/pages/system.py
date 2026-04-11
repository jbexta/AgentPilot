"""System Page Module.

This module provides the system-level configuration and management page for the
Agent Pilot GUI interface. The page enables administrators to configure core
system settings, manage system resources, monitor application performance,
and handle system-level operations.

Key Features:
- System configuration and administration
- Performance monitoring and resource management
- System security and authentication settings
- Integration with external services and APIs
- System maintenance and diagnostic tools
- Backup and recovery operations
- Logging and audit trail management
- Advanced system troubleshooting capabilities

The page provides comprehensive system administration tools for maintaining
and optimizing the Agent Pilot installation and infrastructure.
"""

import json
import re

import keyring
import requests
from PySide6.QtCore import Signal
from PySide6.QtGui import Qt
from PySide6.QtWidgets import QHBoxLayout, QLineEdit, QLabel, QPushButton, QMessageBox
from keyring.errors import PasswordDeleteError

# from gui.widgets.config_async_widget import ConfigAsyncWidget
from gui.widgets.config_fields import ConfigFields
from gui.widgets.config_joined import ConfigJoined
from gui.widgets.config_pages import ConfigPages
from utils.helpers import display_message, set_module_type  # , clone_specific_subdirectory
from gui.util import find_main
from utils.reset import reset_application, bootstrap_modules, bootstrap_entities, run_bake_block_maps

import subprocess
import os
import shutil

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
    #             display_message('Login failed', 'Error', QMessageBox.Warning)
    #             return
    #
    #         token = result['token']
    #         try:
    #             keyring.set_password("agentpilot", "user", token)
    #         except Exception as e:
    #             display_message(f"Error logging in: {str(e)}", 'Error', QMessageBox.Warning)
    #
    #         self.load()
    #
    #     def logout(self):
    #         try:
    #             keyring.delete_password("agentpilot", "user")
    #         except PasswordDeleteError:
    #             pass
    #         except Exception as e:
    #             display_message(f"Error logging out: {str(e)}", 'Error', QMessageBox.Warning)
    #
    #         self.load()

    class Page_System_Fields(ConfigFields):
        def __init__(self, parent):
            super().__init__(parent=parent)
            self.parent = parent
            self.main = find_main()
            self.auto_label_width = True
            self.margin_left = 20
            self.conf_namespace = 'system'
            self.schema = [
                {
                    'text': 'Language',
                    'type': ('English',),
                    'default': 'English',
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
                # {
                #     'text': 'Backup database',
                #     'type': bool,
                #     'default': True,
                #     'tooltip': 'Save a rolling backup of the database to a file in the same directory as the application.',
                # },
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
                    'text': 'Allow importing db modules',
                    'type': bool,
                    'default': False,
                },
                {
                    'text': 'Auto-bake',
                    'type': bool,
                    'tooltip': 'Automatically bake changes to source code when modified. This only applies for items that are already baked.',
                    'default': True,
                },
                {
                    'text': 'Auto-run tools',
                    'type': int,
                    'minimum': 0,
                    'maximum': 30,
                    'step': 1,
                    'default': 5,
                    'has_toggle': True,
                },
                {
                    'text': 'Auto-run code',
                    'type': int,
                    'minimum': 0,
                    'maximum': 30,
                    'step': 1,
                    'default': 5,
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
                    'type': 'model',
                    'popup_params': True,
                    'model_kind': 'CHAT',
                    'default': 'mistral/mistral-large-latest',
                },
                {
                    'text': 'Default voice model',
                    'type': 'model',
                    'popup_params': True,
                    'model_kind': 'AUDIO',
                    'default': '',
                },
                {
                    'text': 'Default image model',
                    'type': 'model',
                    'popup_params': True,
                    'model_kind': 'IMAGE',
                    'default': '',
                },
                {
                    'text': 'Default video model',
                    'type': 'model',
                    'popup_params': True,
                    'model_kind': 'VIDEO',
                    'default': '',
                },
                {
                    'text': 'Default audio model',
                    'type': 'model',
                    'popup_params': True,
                    'model_kind': 'AUDIO',
                    'default': '',
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
                    'type': 'model',
                    'popup_params': True,
                    'model_kind': 'CHAT',
                    'default': 'mistral/mistral-large-latest',
                    'visibility_predicate': lambda self: self.auto_title_wgt.isChecked(),
                    'row_key': 0,
                },
                {
                    'text': 'Auto-title prompt',
                    'type': str,
                    'default': 'Generate a brief and concise title for a chat that begins with the following message:\n\n{user_msg}',
                    'num_lines': 5,
                    'label_position': 'top',
                    'stretch_x': True,
                    'visibility_predicate': lambda self: self.auto_title_wgt.isChecked(),
                },
                {
                    'text': 'Default project entity',
                    'type': 'entity',
                    'default': '',
                },
            ]

        def after_init(self):
            try:
                self.dev_mode_wgt.stateChanged.connect(lambda state: self.toggle_dev_mode(state))
                self.always_on_top_wgt.stateChanged.connect(self.main.toggle_always_on_top)

                self.bootstrap_modules_btn = QPushButton('Bootstrap baked Modules')
                self.bootstrap_modules_btn.clicked.connect(bootstrap_modules)
                self.layout.addWidget(self.bootstrap_modules_btn)

                self.bootstrap_entities_btn = QPushButton('Bootstrap baked Entities')
                self.bootstrap_entities_btn.clicked.connect(bootstrap_entities)
                self.layout.addWidget(self.bootstrap_entities_btn)

                self.reset_app_btn = QPushButton('Reset Application')
                self.reset_app_btn.clicked.connect(reset_application)
                self.layout.addWidget(self.reset_app_btn)

                self.scrape_agpt_btn = QPushButton('Scrape AutoGPT')
                self.scrape_agpt_btn.clicked.connect(self.scrape_autogpt)
                self.layout.addWidget(self.scrape_agpt_btn)

                self.bake_docs_btn = QPushButton('Bake Docs')
                self.bake_docs_btn.clicked.connect(self.on_bake_docs)
                self.layout.addWidget(self.bake_docs_btn)

                self.run_demo_btn = QPushButton('Run Demo')
                self.run_demo_btn.clicked.connect(self.main.run_demo)
                self.layout.addWidget(self.run_demo_btn)
            except Exception as e:
                pass

        def toggle_dev_mode(self, state=None):
            # pass
            if state is None and hasattr(self, 'dev_mode_wgt'):
                state = self.dev_mode_wgt.isChecked()

            self.main.page_chat.workflow_settings.header_widget.widgets[1].btn_info.setVisible(state)
            self.reset_app_btn.setVisible(state)
            self.bake_docs_btn.setVisible(state)
            self.run_demo_btn.setVisible(state)

            for config_pages in self.main.findChildren(ConfigPages):
                for page_name, page in config_pages.pages.items():
                    page_is_dev_mode = getattr(page, 'IS_DEV_MODE', False)
                    if not page_is_dev_mode:
                        continue
                    config_pages.settings_sidebar.page_buttons[page_name].setVisible(state)

            # self.main.apply_stylesheet()
        
        def on_bake_docs(self):
            from utils import sql

            row = sql.get_results(
                "SELECT config FROM projects WHERE json_extract(config, '$._PROJECT_TYPE') = 'application' LIMIT 1",
                return_type='tuple',
            )
            if not row:
                display_message('No application project found.')
                return

            config = json.loads(row[0])
            run_bake_block_maps(config, self.bake_docs_btn)

        def scrape_autogpt(self):
            # dialog to confirm scraping
            reply = QMessageBox.question(self, 'Scrape AutoGPT',
                                         'This will erase any existing AutoGPT backend files in the src/plugins/agpt folder.\n'
                                         'Do you want to continue?',
                                         QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply != QMessageBox.Yes:
                return

            # delete existing AutoGPT backend files
            destination_folder_1 = "src/plugins/agpt"
            full_destination_folder_1 = os.path.join(os.getcwd(), destination_folder_1)
            if os.path.exists(full_destination_folder_1):
                print(f"Deleting existing AutoGPT backend files in '{full_destination_folder_1}'")
                shutil.rmtree(full_destination_folder_1)

            repo_to_clone_1 = "https://github.com/Significant-Gravitas/AutoGPT.git"
            subdirectory_to_get_1 = "autogpt_platform/backend"

            # CRITICAL: For imports 'src.plugins.agpt.backend.module', files MUST be in this folder.
            destination_folder_1 = "src/plugins/agpt"
            full_destination_folder_1 = os.path.join(os.getcwd(), destination_folder_1)

            print(
                f"\nAttempting to clone contents of '{subdirectory_to_get_1}' from '{repo_to_clone_1}' into '{full_destination_folder_1}'")
            self.clone_specific_subdirectory(repo_to_clone_1, subdirectory_to_get_1, full_destination_folder_1,
                                             branch="master")

            old_import_root_name = os.path.basename(subdirectory_to_get_1.strip('/'))  # Should be "backend"

            new_import_prefix = ""
            if destination_folder_1:
                path_parts = destination_folder_1.split(os.sep)
                # If destination_folder_1 is "src/plugins/agpt/backend",
                # new_import_prefix becomes "src.plugins.agpt.backend"
                new_import_prefix = '.'.join(filter(None, path_parts))

            if new_import_prefix and old_import_root_name:
                print(f"INFO: Rewriting imports from '{old_import_root_name}.module' to '{new_import_prefix}.module'")
                self._rewrite_imports_in_directory(full_destination_folder_1, old_import_root_name, new_import_prefix + f".{old_import_root_name}")
            else:
                print(
                    f"Warning: Could not determine import rewrite parameters (old: '{old_import_root_name}', new: '{new_import_prefix}'). Skipping import rewrite.")

        def clone_specific_subdirectory(self, repo_url: str, limit_to_subdirectory: str, target_directory: str,
                                        branch: str = "main"):
            temp_clone_dir = "temp_repo_sparse_clone"

            try:
                if os.path.exists(temp_clone_dir):
                    shutil.rmtree(temp_clone_dir)
                os.makedirs(temp_clone_dir)

                subprocess.run(["git", "init"], cwd=temp_clone_dir, check=True, capture_output=True, text=True)
                subprocess.run(["git", "remote", "add", "origin", repo_url], cwd=temp_clone_dir, check=True,
                               capture_output=True, text=True)
                subprocess.run(["git", "config", "core.sparsecheckout", "true"], cwd=temp_clone_dir, check=True,
                               capture_output=True, text=True)

                sparse_checkout_file_path = os.path.join(temp_clone_dir, ".git", "info", "sparse-checkout")
                with open(sparse_checkout_file_path, "w") as f:
                    f.write(f"{limit_to_subdirectory.strip('/')}/\n")

                print(f"Fetching branch '{branch}' from '{repo_url}' (sparse, depth=1)...")
                subprocess.run(["git", "fetch", "--depth=1", "origin", branch], cwd=temp_clone_dir, check=True,
                               capture_output=True, text=True)

                print(f"Checking out '{branch}' sparsely from FETCH_HEAD...")
                subprocess.run(["git", "checkout", "-B", branch, "FETCH_HEAD"], cwd=temp_clone_dir, check=True,
                               capture_output=True, text=True)

                source_path_in_temp_clone = os.path.join(temp_clone_dir, limit_to_subdirectory.strip('/'))

                os.makedirs(target_directory, exist_ok=True)

                if os.path.exists(source_path_in_temp_clone) and os.path.isdir(source_path_in_temp_clone):
                    for item_name in os.listdir(source_path_in_temp_clone):
                        source_item_path = os.path.join(source_path_in_temp_clone, item_name)
                        destination_item_path = os.path.join(target_directory, item_name)
                        shutil.move(source_item_path, destination_item_path)
                    print(f"Successfully moved contents of '{limit_to_subdirectory}' to '{target_directory}'")
                elif os.path.exists(source_path_in_temp_clone) and os.path.isfile(source_path_in_temp_clone):
                    destination_file_path = os.path.join(target_directory,
                                                         os.path.basename(limit_to_subdirectory.strip('/')))
                    shutil.move(source_path_in_temp_clone, destination_file_path)
                    print(f"Successfully moved file '{limit_to_subdirectory}' to '{destination_file_path}'")
                else:
                    print(
                        f"Error: Source path '{source_path_in_temp_clone}' (from '{limit_to_subdirectory}') not found or not a directory after sparse checkout.")
                    # ... (additional error details from previous versions can be added if needed) ...

            except subprocess.CalledProcessError as e:
                print(f"Git command failed with exit code {e.returncode}:")
                if e.stdout: print(f"Stdout: {e.stdout.strip()}")
                if e.stderr: print(f"Stderr: {e.stderr.strip()}")
            except Exception as e:
                print(f"An unexpected error occurred: {e}")
            finally:
                if os.path.exists(temp_clone_dir):
                    shutil.rmtree(temp_clone_dir)

        def _rewrite_imports_in_directory(self, directory_path: str, old_module_name: str, new_package_path: str):
            print(f"Rewriting imports in '{directory_path}': changing '{old_module_name}' to '{new_package_path}'")

            from_pattern = re.compile(
                r"(^\s*from\s+)(" + re.escape(old_module_name) + r")((?:\.\w+)*)(\s+import\s+.*)$"
            )
            import_pattern = re.compile(
                r"(^\s*import\s+)(" + re.escape(old_module_name) + r")((?:\.\w+)*)(\s*as\s+\w+)?(.*)$"
            )

            for root, _, files in os.walk(directory_path):
                for filename in files:
                    if filename.endswith(".py"):
                        filepath = os.path.join(root, filename)
                        try:
                            with open(filepath, 'r', encoding='utf-8') as f:
                                lines = f.readlines()

                            new_lines = []
                            modified = False
                            for line_from_file in lines:
                                has_newline = line_from_file.endswith('\n')
                                processed_line = line_from_file[:-1] if has_newline else line_from_file

                                current_processed_line_state = processed_line  # For comparison if no change

                                match = from_pattern.match(processed_line)
                                if match:  # from backend.module import ...
                                    # G1="from ", G2=old_module_name, G3=".module" or "", G4=" import ..."
                                    processed_line = f"{match.group(1)}{new_package_path}{match.group(3)}{match.group(4)}"
                                else:
                                    match = import_pattern.match(processed_line)  # import backend.module ...
                                    if match:
                                        # G1="import ", G2=old_module_name, G3=".module" or "", G4=" as alias" or None, G5="comment" or ""
                                        alias_part = match.group(4) if match.group(4) else ""
                                        rest_part = match.group(5) if match.group(5) else ""
                                        processed_line = f"{match.group(1)}{new_package_path}{match.group(3)}{alias_part}{rest_part}"

                                final_line_to_append = processed_line
                                if has_newline:
                                    final_line_to_append += '\n'

                                if line_from_file != final_line_to_append:
                                    modified = True
                                new_lines.append(final_line_to_append)

                            if modified:
                                with open(filepath, 'w', encoding='utf-8') as f:
                                    f.writelines(new_lines)
                                # print(f"    Rewrote imports in: {filepath}") # Optional verbose logging
                        except Exception as e:
                            print(f"    Error processing file {filepath} for import rewrite: {e}")
            print(f"Import rewriting in '{directory_path}' completed.")
