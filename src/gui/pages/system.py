import re

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
from src.utils.helpers import display_message, set_module_type  # , clone_specific_subdirectory
from src.gui.util import find_main_widget
from src.utils.reset import reset_application

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
                    'text': 'Allow importing db modules',
                    'type': bool,
                    'default': False,
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
            try:
                self.dev_mode.stateChanged.connect(lambda state: self.toggle_dev_mode(state))
                self.always_on_top.stateChanged.connect(self.main.toggle_always_on_top)

                # add a button 'Reset database'
                self.reset_app_btn = QPushButton('Reset Application')
                self.reset_app_btn.clicked.connect(reset_application)
                self.layout.addWidget(self.reset_app_btn)

                self.scrape_agpt_btn = QPushButton('Scrape AutoGPT')
                self.scrape_agpt_btn.clicked.connect(self.scrape_autogpt)
                self.layout.addWidget(self.scrape_agpt_btn)

                self.run_test_btn = QPushButton('Run Tutorial')
                self.run_test_btn.clicked.connect(self.main.run_test)
                self.layout.addWidget(self.run_test_btn)
            except Exception as e:
                pass

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

        # def scrape_autogpt(self):
        #     # Ensure Git is installed and in your PATH.
        #
        #     repo_to_clone_1 = "https://github.com/Significant-Gravitas/AutoGPT.git"
        #     subdirectory_to_get_1 = "autogpt_platform/backend"
        #     destination_folder_1 = "src/plugins/agpt"
        #     full_destination_folder_1 = os.path.join(os.getcwd(), destination_folder_1)
        #
        #     print(
        #         f"\nAttempting to clone subdirectory '{subdirectory_to_get_1}' from '{repo_to_clone_1}' into '{full_destination_folder_1}'")
        #     self.clone_specific_subdirectory(repo_to_clone_1, subdirectory_to_get_1, full_destination_folder_1,
        #                                      branch="master")
        #
        #     old_import_root_name = os.path.basename(subdirectory_to_get_1.strip('/'))
        #
        #     # MODIFIED: Correctly determine the new import prefix
        #     new_import_prefix = ""
        #     if destination_folder_1:  # Ensure it's not empty
        #         path_parts = destination_folder_1.split(os.sep)
        #         # This will create "src.plugins.agpt.backend"
        #         new_import_prefix = '.'.join(filter(None, path_parts))
        #
        #     if new_import_prefix and old_import_root_name:
        #         self._rewrite_imports_in_directory(full_destination_folder_1, old_import_root_name, new_import_prefix)
        #     else:
        #         print(
        #             f"Warning: Could not determine import rewrite parameters (old: '{old_import_root_name}', new: '{new_import_prefix}'). Skipping import rewrite.")
        #
        # def clone_specific_subdirectory(self, repo_url: str, limit_to_subdirectory: str, target_directory: str,
        #                                 branch: str = "main"):
        #     temp_clone_dir = "temp_repo_sparse_clone"
        #
        #     try:
        #         if os.path.exists(temp_clone_dir):
        #             shutil.rmtree(temp_clone_dir)
        #         os.makedirs(temp_clone_dir)
        #
        #         subprocess.run(["git", "init"], cwd=temp_clone_dir, check=True, capture_output=True, text=True)
        #         subprocess.run(["git", "remote", "add", "origin", repo_url], cwd=temp_clone_dir, check=True,
        #                        capture_output=True, text=True)
        #         subprocess.run(["git", "config", "core.sparsecheckout", "true"], cwd=temp_clone_dir, check=True,
        #                        capture_output=True, text=True)
        #
        #         sparse_checkout_file_path = os.path.join(temp_clone_dir, ".git", "info", "sparse-checkout")
        #         with open(sparse_checkout_file_path, "w") as f:
        #             f.write(f"{limit_to_subdirectory.strip('/')}/\n")
        #
        #         print(f"Fetching branch '{branch}' from '{repo_url}' (sparse, depth=1)...")
        #         fetch_command = ["git", "fetch", "--depth=1", "origin", branch]
        #         result = subprocess.run(fetch_command, cwd=temp_clone_dir, check=True, capture_output=True, text=True)
        #         # print(f"Fetch successful: {result.stdout.strip()}") # Can be noisy
        #         # if result.stderr.strip(): print(f"Fetch stderr: {result.stderr.strip()}")
        #
        #         print(f"Checking out '{branch}' sparsely from FETCH_HEAD...")
        #         checkout_command = ["git", "checkout", "-B", branch, "FETCH_HEAD"]
        #         result = subprocess.run(checkout_command, cwd=temp_clone_dir, check=True, capture_output=True,
        #                                 text=True)
        #         # print(f"Checkout successful: {result.stdout.strip()}") # Can be noisy
        #         # if result.stderr.strip(): print(f"Checkout stderr: {result.stderr.strip()}")
        #
        #         source_path_in_temp_clone = os.path.join(temp_clone_dir, limit_to_subdirectory.strip('/'))
        #
        #         os.makedirs(target_directory, exist_ok=True)
        #
        #         if os.path.exists(source_path_in_temp_clone) and os.path.isdir(source_path_in_temp_clone):
        #             for item_name in os.listdir(source_path_in_temp_clone):
        #                 source_item_path = os.path.join(source_path_in_temp_clone, item_name)
        #                 destination_item_path = os.path.join(target_directory, item_name)
        #                 shutil.move(source_item_path, destination_item_path)
        #             print(f"Successfully moved contents of '{limit_to_subdirectory}' to '{target_directory}'")
        #         elif os.path.exists(source_path_in_temp_clone) and os.path.isfile(source_path_in_temp_clone):
        #             destination_file_path = os.path.join(target_directory,
        #                                                  os.path.basename(limit_to_subdirectory.strip('/')))
        #             shutil.move(source_path_in_temp_clone, destination_file_path)
        #             print(f"Successfully moved file '{limit_to_subdirectory}' to '{destination_file_path}'")
        #         else:
        #             print(
        #                 f"Error: Subdirectory or file '{source_path_in_temp_clone}' not found after sparse checkout.")
        #             # ... (error details) ...
        #
        #     except subprocess.CalledProcessError as e:
        #         print(f"Git command failed with exit code {e.returncode}:")
        #         if e.stdout: print(f"Stdout: {e.stdout.strip()}")
        #         if e.stderr: print(f"Stderr: {e.stderr.strip()}")
        #     except Exception as e:
        #         print(f"An unexpected error occurred: {e}")
        #     finally:
        #         if os.path.exists(temp_clone_dir):
        #             shutil.rmtree(temp_clone_dir)
        #             # print(f"Cleaned up temporary directory: {temp_clone_dir}") # Can be noisy
        #
        # def _rewrite_imports_in_directory(self, directory_path: str, old_module_name: str, new_package_path: str):
        #     print(f"Rewriting imports in '{directory_path}': changing '{old_module_name}' to '{new_package_path}'")
        #
        #     from_pattern = re.compile(
        #         r"(^\s*from\s+)(" + re.escape(old_module_name) + r")((?:\.\w+)*)(\s+import\s+.*)$"
        #     )
        #     import_pattern = re.compile(
        #         r"(^\s*import\s+)(" + re.escape(old_module_name) + r")((?:\.\w+)*)(\s*as\s+\w+)?(.*)$"
        #     )
        #
        #     for root, _, files in os.walk(directory_path):
        #         for filename in files:
        #             if filename.endswith(".py"):
        #                 filepath = os.path.join(root, filename)
        #                 try:
        #                     with open(filepath, 'r', encoding='utf-8') as f:
        #                         lines = f.readlines()
        #
        #                     new_lines = []
        #                     modified = False
        #                     for line_from_file in lines:
        #                         # Determine if line originally had a newline and strip it for processing
        #                         has_newline = line_from_file.endswith('\n')
        #                         processed_line = line_from_file[:-1] if has_newline else line_from_file
        #
        #                         # Store the current state of processed_line for comparison
        #                         current_processed_line_state = processed_line
        #
        #                         match = from_pattern.match(processed_line)
        #                         if match:
        #                             # Groups do not contain the newline as we matched on 'processed_line'
        #                             processed_line = f"{match.group(1)}{new_package_path}{match.group(3)}{match.group(4)}"
        #                         else:
        #                             match = import_pattern.match(processed_line)
        #                             if match:
        #                                 alias_part = match.group(4) if match.group(4) else ""
        #                                 # Group 5 (rest_part) also does not contain newline here
        #                                 rest_part = match.group(5) if match.group(5) else ""
        #                                 processed_line = f"{match.group(1)}{new_package_path}{match.group(3)}{alias_part}{rest_part}"
        #
        #                         final_line_to_append = processed_line
        #                         if has_newline:
        #                             final_line_to_append += '\n'
        #
        #                         if line_from_file != final_line_to_append:
        #                             modified = True
        #                         new_lines.append(final_line_to_append)
        #
        #                     if modified:
        #                         with open(filepath, 'w', encoding='utf-8') as f:
        #                             f.writelines(new_lines)
        #                         # print(f"    Rewrote imports in: {filepath}")
        #                 except Exception as e:
        #                     print(f"    Error processing file {filepath} for import rewrite: {e}")
        #     print(f"Import rewriting in '{directory_path}' completed.")
        #
        # # def scrape_autogpt(self):
        # #
        # #     # Ensure Git is installed and in your PATH.
        # #
        # #     # Example 1: Clone a subdirectory
        #     # This repo has a folder 'autogpt_platform/backend' we want to clone
        #     repo_to_clone_1 = "https://github.com/Significant-Gravitas/AutoGPT.git"
        #     subdirectory_to_get_1 = "autogpt_platform/backend"  # Path relative to repo root
        #     destination_folder_1 = "src/plugins/agpt"  # Relative to current project root
        #     full_destination_folder_1 = os.path.join(os.getcwd(), destination_folder_1)
        #     pass
        #
        #     print(f"\nAttempting to clone subdirectory '{subdirectory_to_get_1}' from '{repo_to_clone_1}' into '{full_destination_folder_1}'")
        #     self.clone_specific_subdirectory(repo_to_clone_1, subdirectory_to_get_1, full_destination_folder_1, branch="master")
        #
        # def clone_specific_subdirectory(self, repo_url: str, limit_to_subdirectory: str, target_directory: str,
        #                                 branch: str = "main"):
        #     """
        #     Clones a specific subdirectory (and its contents) from a Git repository
        #     into a target directory using sparse checkout.
        #
        #     Args:
        #         repo_url: The URL of the Git repository.
        #         limit_to_subdirectory: The relative path of the subdirectory to clone (e.g., "docs/features").
        #         target_directory: The local path where the subdirectory contents should be placed.
        #         branch: The branch to clone from (defaults to "main").
        #     """
        #     temp_clone_dir = "temp_repo_sparse_clone"  # Temporary directory for the sparse checkout
        #
        #     try:
        #         # Clean up any pre-existing temporary directory
        #         if os.path.exists(temp_clone_dir):
        #             shutil.rmtree(temp_clone_dir)
        #         os.makedirs(temp_clone_dir)
        #
        #         # Initialize Git, add remote, and enable sparse checkout
        #         subprocess.run(["git", "init"], cwd=temp_clone_dir, check=True, capture_output=True, text=True)
        #         subprocess.run(["git", "remote", "add", "origin", repo_url], cwd=temp_clone_dir, check=True,
        #                        capture_output=True, text=True)
        #         subprocess.run(["git", "config", "core.sparsecheckout", "true"], cwd=temp_clone_dir, check=True,
        #                        capture_output=True, text=True)
        #
        #         # Define the subdirectory for sparse checkout.
        #         sparse_checkout_file_path = os.path.join(temp_clone_dir, ".git", "info", "sparse-checkout")
        #         with open(sparse_checkout_file_path, "w") as f:
        #             f.write(f"{limit_to_subdirectory.strip('/')}\n")
        #
        #         # Fetch the specified branch shallowly (only the latest commit)
        #         print(f"Fetching branch '{branch}' from '{repo_url}' (sparse, depth=1)...")
        #         fetch_command = ["git", "fetch", "--depth=1", "origin", branch]
        #         result = subprocess.run(fetch_command, cwd=temp_clone_dir, check=True, capture_output=True, text=True)
        #         print(f"Fetch successful: {result.stdout.strip()}")
        #         if result.stderr.strip():
        #             print(f"Fetch stderr: {result.stderr.strip()}")
        #
        #         # Checkout the fetched branch. This step populates the working directory
        #         # according to sparse-checkout rules. FETCH_HEAD points to the commit just fetched.
        #         # Using '-B' creates the branch if it doesn't exist or resets it if it does, then checks it out.
        #         print(f"Checking out '{branch}' sparsely from FETCH_HEAD...")
        #         checkout_command = ["git", "checkout", "-B", branch, "FETCH_HEAD"]
        #         result = subprocess.run(checkout_command, cwd=temp_clone_dir, check=True, capture_output=True,
        #                                 text=True)
        #         print(f"Checkout successful: {result.stdout.strip()}")
        #         if result.stderr.strip():
        #             print(f"Checkout stderr: {result.stderr.strip()}")
        #
        #         # Path to the desired subdirectory within the temporary clone
        #         # limit_to_subdirectory should not have leading slashes for os.path.join in this context if temp_clone_dir is the root.
        #         # Example: if limit_to_subdirectory is "foo/bar", source_path_in_temp_clone becomes "temp_repo_sparse_clone/foo/bar"
        #         source_path_in_temp_clone = os.path.join(temp_clone_dir, limit_to_subdirectory.strip('/'))
        #
        #         if os.path.exists(source_path_in_temp_clone) and os.path.isdir(source_path_in_temp_clone):
        #             os.makedirs(target_directory, exist_ok=True)
        #             for item_name in os.listdir(source_path_in_temp_clone):
        #                 source_item_path = os.path.join(source_path_in_temp_clone, item_name)
        #                 destination_item_path = os.path.join(target_directory, item_name)
        #                 shutil.move(source_item_path, destination_item_path)
        #             print(f"Successfully moved contents of '{limit_to_subdirectory}' to '{target_directory}'")
        #         elif os.path.exists(source_path_in_temp_clone) and os.path.isfile(source_path_in_temp_clone):
        #             os.makedirs(target_directory, exist_ok=True)
        #             destination_file_path = os.path.join(target_directory,
        #                                                  os.path.basename(limit_to_subdirectory.strip('/')))
        #             shutil.move(source_path_in_temp_clone, destination_file_path)
        #             print(f"Successfully moved file '{limit_to_subdirectory}' to '{destination_file_path}'")
        #         else:
        #             print(
        #                 f"Error: Subdirectory or file '{source_path_in_temp_clone}' (derived from '{limit_to_subdirectory}') not found in the repository after sparse checkout.")
        #             print(f"Contents of temporary clone directory '{temp_clone_dir}': {os.listdir(temp_clone_dir)}")
        #             # Also list contents of .git/info/sparse-checkout for debugging
        #             if os.path.exists(sparse_checkout_file_path):
        #                 with open(sparse_checkout_file_path, "r") as f:
        #                     print(f"Contents of '.git/info/sparse-checkout':\n{f.read()}")
        #             else:
        #                 print("'.git/info/sparse-checkout' file not found.")
        #
        #         self._rewrite_imports_in_directory(full_destination_folder_1, old_import_root_name, new_import_prefix)
        #
        #     except subprocess.CalledProcessError as e:
        #         print(f"Git command failed with exit code {e.returncode}:")
        #         if e.stdout:
        #             print(f"Stdout: {e.stdout.strip()}")
        #         if e.stderr:
        #             print(f"Stderr: {e.stderr.strip()}")
        #     except Exception as e:
        #         print(f"An unexpected error occurred: {e}")
        #     finally:
        #         # Clean up the temporary clone directory
        #         if os.path.exists(temp_clone_dir):
        #             shutil.rmtree(temp_clone_dir)
        #             print(f"Cleaned up temporary directory: {temp_clone_dir}")
        #
        # # def clone_specific_subdirectory(self, repo_url: str, limit_to_subdirectory: str, target_directory: str, branch: str = "main"):
        # #     """
        # #     Clones a specific subdirectory (and its contents) from a Git repository
        # #     into a target directory using sparse checkout.
        # #
        # #     Args:
        # #         repo_url: The URL of the Git repository.
        # #         limit_to_subdirectory: The relative path of the subdirectory to clone (e.g., "docs/features").
        # #         target_directory: The local path where the subdirectory contents should be placed.
        # #         branch: The branch to clone from (defaults to "main").
        # #     """
        # #     temp_clone_dir = "temp_repo_sparse_clone" # Temporary directory for the sparse checkout
        # #
        # #     try:
        # #         # Clean up any pre-existing temporary directory
        # #         if os.path.exists(temp_clone_dir):
        # #             shutil.rmtree(temp_clone_dir)
        # #         os.makedirs(temp_clone_dir)
        # #
        # #         # Initialize Git, add remote, and enable sparse checkout
        # #         subprocess.run(["git", "init"], cwd=temp_clone_dir, check=True, capture_output=True)
        # #         subprocess.run(["git", "remote", "add", "origin", repo_url], cwd=temp_clone_dir, check=True, capture_output=True)
        # #         subprocess.run(["git", "config", "core.sparsecheckout", "true"], cwd=temp_clone_dir, check=True, capture_output=True)
        # #
        # #         # Define the subdirectory for sparse checkout.
        # #         # Writing the directory path (e.g., "path/to/folder") will include all its contents.
        # #         sparse_checkout_file_path = os.path.join(temp_clone_dir, ".git", "info", "sparse-checkout")
        # #         with open(sparse_checkout_file_path, "w") as f:
        # #             # Ensure the path in sparse-checkout correctly targets the directory and its contents.
        # #             # A common way is to just list the directory. Git will include its children.
        # #             # If limit_to_subdirectory is "foo/bar", writing "foo/bar\n" is usually sufficient.
        # #             # Adding a trailing "/*" (e.g. "foo/bar/*") can be more explicit for some Git versions/cases
        # #             # but often isn't necessary for directories. Let's keep it simple.
        # #             f.write(f"{limit_to_subdirectory.strip('/')}\n")
        # #
        # #         # Pull the specified branch using a shallow clone
        # #         print(f"Pulling '{limit_to_subdirectory}' from branch '{branch}' of '{repo_url}' (sparse)...")
        # #         pull_command = ["git", "pull", "--depth=1", "origin", branch]
        # #         result = subprocess.run(pull_command, cwd=temp_clone_dir, check=True, capture_output=True, text=True)
        # #         print(f"Pull successful: {result.stdout.strip()}")
        # #
        # #         # Path to the desired subdirectory within the temporary clone
        # #         source_path_in_temp_clone = os.path.join(temp_clone_dir, limit_to_subdirectory.strip('/'))
        # #
        # #         if os.path.exists(source_path_in_temp_clone) and os.path.isdir(source_path_in_temp_clone):
        # #             # Create target directory if it doesn't exist
        # #             os.makedirs(target_directory, exist_ok=True)
        # #
        # #             # Move contents from the sparsely checked-out subdirectory to the target directory
        # #             for item_name in os.listdir(source_path_in_temp_clone):
        # #                 source_item_path = os.path.join(source_path_in_temp_clone, item_name)
        # #                 destination_item_path = os.path.join(target_directory, item_name)
        # #                 shutil.move(source_item_path, destination_item_path)
        # #             print(f"Successfully cloned contents of '{limit_to_subdirectory}' to '{target_directory}'")
        # #         elif os.path.exists(source_path_in_temp_clone) and os.path.isfile(source_path_in_temp_clone):
        # #              # Handle case where limit_to_subdirectory is a single file
        # #             os.makedirs(target_directory, exist_ok=True)
        # #             destination_file_path = os.path.join(target_directory, os.path.basename(limit_to_subdirectory.strip('/')))
        # #             shutil.move(source_path_in_temp_clone, destination_file_path)
        # #             print(f"Successfully cloned file '{limit_to_subdirectory}' to '{destination_file_path}'")
        # #         else:
        # #             print(f"Error: Subdirectory or file '{limit_to_subdirectory}' not found in the repository after sparse checkout.")
        # #             print(f"Contents of '{temp_clone_dir}': {os.listdir(temp_clone_dir)}")
        # #             print(f"Contents of '.git/info/sparse-checkout':")
        # #             with open(sparse_checkout_file_path, "r") as f:
        # #                 print(f.read())
        # #
        # #     except subprocess.CalledProcessError as e:
        # #         print(f"Git command failed with exit code {e.returncode}:")
        # #         if e.stdout:
        # #             print(f"Stdout: {e.stdout.strip()}")
        # #         if e.stderr:
        # #             print(f"Stderr: {e.stderr.strip()}")
        # #     except Exception as e:
        # #         print(f"An unexpected error occurred: {e}")
        # #     finally:
        # #         # Clean up the temporary clone directory
        # #         if os.path.exists(temp_clone_dir):
        # #             shutil.rmtree(temp_clone_dir)


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
