# import asyncio
#
# from PySide6.QtCore import QRunnable
# from PySide6.QtWidgets import QPushButton, QMessageBox
# from nio import Client, AsyncClient
#
# from src.gui.config import ConfigFields, get_widget_value, CHBoxLayout
# from src.gui.widgets import find_main_widget
# from src.utils.helpers import display_messagebox
#
#
# class Page_Settings_Matrix(ConfigFields):
#     def __init__(self, parent):
#         super().__init__(parent=parent)
#         self.parent = parent
#         self.label_width = 125
#         self.margin_left = 20
#         self.conf_namespace = 'matrix'
#
#         # self.runnable = self.RegisterRunnable(self)
#         self.schema = [
#             {
#                 'text': 'Homeserver',
#                 'type': str,
#                 'default': 'https://matrix.org',
#                 'width': 200,
#             },
#             {
#                 'text': 'Username',
#                 'type': str,
#                 'default': '',
#                 'width': 150,
#             },
#             {
#                 'text': 'Password',
#                 'type': str,
#                 'encrypt': True,
#                 'default': '',
#                 'width': 150,
#             },
#         ]
#
#     def after_init(self):
#         self.btn_login = QPushButton('Login')
#         self.btn_login.clicked.connect(self.login)
#         self.btn_register = QPushButton('Register')
#         # self.btn_register.clicked.connect(self.register)
#         # This is async now
#         self.btn_register.clicked.connect(self.register)
#         self.btn_logout = QPushButton('Logout')
#         self.btn_logout.clicked.connect(self.logout)
#
#         h_layout = CHBoxLayout()
#         h_layout.addWidget(self.btn_login)
#         h_layout.addWidget(self.btn_register)
#         h_layout.addWidget(self.btn_logout)
#
#         self.layout.insertSpacing(self.layout.count() - 1, 3)
#         self.layout.insertLayout(self.layout.count() - 1, h_layout)
#         # self.layout.insertWidget(self.layout.count() - 1, self.btn_login)
#         # self.layout.insertWidget(self.layout.count() - 1, self.btn_logout)
#         self.btn_logout.hide()
#
#     def register(self):  # , username, password):
#         homeserver = get_widget_value(self.homeserver)
#         username = get_widget_value(self.username)
#         password = get_widget_value(self.password)
#         loop = asyncio.get_event_loop()
#         client = AsyncClient(homeserver)
#         # try:
#         #     # Attempt to register the account
#         #     response = client.register(
#         #         username=username,
#         #         password=password
#         #     )
#         #     # Account created successfully
#         #     print(f"Account created successfully! User ID: {response.user_id}")
#
#         try:
#             # Attempt to register the account
#             auth_dict = {
#                 "type": "m.login.registration_token",
#                 "registration_token": "REGISTRATIONTOKEN",
#                 "session": "session-id-from-homeserver"
#             }
#             response = loop.run_until_complete(client.register(
#                 username=username,
#                 password=password,
#                 device_name="My First Device",
#             ))
#             if not response.status_code:
#                 raise Exception(response.message)
#             error_codes = ['INVALID_USERNAME', 'USER_IN_USE']
#             if any(code in response.status_code for code in error_codes):
#                 raise Exception(response.message)
#             # Account created successfully
#             print(f"Account created successfully! User ID: {response.user_id}")
#
#         except Exception as e:
#             display_messagebox(
#                 icon=QMessageBox.Warning,
#                 title='Error',
#                 text=str(e),
#             )
#
#         # load_runnable = self.RegisterRunnable(self)
#         # main = find_main_widget(self)
#         # main.page_chat.threadpool.start(load_runnable)
#         # # # Check if the username is already taken
#         # # homeserver = get_widget_value(self.homeserver)
#         # # username = get_widget_value(self.username)
#         # # password = get_widget_value(self.password)
#         # # client = AsyncClient(homeserver)
#         # # try:
#         # #     # Attempt to register the account
#         # #     response = await client.register(
#         # #         username=username,
#         # #         password=password
#         # #     )
#         # #     # Account created successfully
#         # #     print(f"Account created successfully! User ID: {response.user_id}")
#         # #
#         # # except Exception as e:
#         # #     # Handle registration errors
#         # #     if e.args[0] == 'M_USER_IN_USE':
#         # #         print("Username is already taken. Please choose another one.")
#         # #     else:
#         # #         print(f"Failed to register due to an error: {str(e)}")
#
#     # class RegisterRunnable(QRunnable):
#     #     def __init__(self, parent):
#     #         super().__init__()
#     #         self.parent = parent
#     #         self.homeserver = get_widget_value(parent.homeserver)
#     #         self.username = get_widget_value(parent.username)
#     #         self.password = get_widget_value(parent.password)
#     #         # self.page_chat = parent.main.page_chat
#     #
#     #     def run(self):
#     #         # homeserver = self.homeserver)
#     #         # username = get_widget_value(self.username)
#     #         # password = get_widget_value(self.password)
#     #         client = AsyncClient(self.homeserver)
#     #         try:
#     #             # Attempt to register the account
#     #             response = client.register(
#     #                 username=self.username,
#     #                 password=self.password
#     #             )
#     #             # Account created successfully
#     #             print(f"Account created successfully! User ID: {response.user_id}")
#     #
#     #         except Exception as e:
#     #             # Handle registration errors
#     #             if e.args[0] == 'M_USER_IN_USE':
#     #                 print("Username is already taken. Please choose another one.")
#     #             else:
#     #                 print(f"Failed to register due to an error: {str(e)}")
#
#     def login(self):
#         homeserver = get_widget_value(self.homeserver)
#         username = get_widget_value(self.username)
#         password = get_widget_value(self.password)
#         loop = asyncio.get_event_loop()
#         client = AsyncClient(homeserver, user=f'@{username}:matrix.org')
#         try:
#             response = loop.run_until_complete(client.login(
#                 password=password,
#                 device_name="My First Device",
#             ))
#             if not response.status_code:
#                 raise Exception(response.message)
#             error_codes = ['M_FORBIDDEN', 'M_UNKNOWN']
#             if any(code in response.status_code for code in error_codes):
#                 raise Exception(response.message)
#             print(f"Logged in as {response.user_id}")
#             self.btn_login.hide()
#             self.btn_register.hide()
#             self.btn_logout.show()
#         except Exception as e:
#             display_messagebox(
#                 icon=QMessageBox.Warning,
#                 title='Error',
#                 text=str(e),
#             )
#
#     def logout(self):
#         pass