# import pytest
# from PySide6.QtGui import Qt
# from PySide6.QtWidgets import QApplication
# from gui.main import Main
#
# @pytest.fixture
# def app(qtbot):
#     app = QApplication([])
#     app.setAttribute(Qt.AA_EnableHighDpiScaling)
#     app.setStyle("Fusion")  # Fixes macos white line issue
#     main = Main()
#     qtbot.addWidget(main)
#     yield main
#     main.close()
#
# def test_app(app, qtbot):
#     app.run_test()
#     while app.test_running:
#         qtbot.wait(100)
#         # QApplication.processEvents()
#     # qtbot.mouseClick(app.main_menu.settings_sidebar.page_buttons['Settings'], Qt.LeftButton)
#     # assert app.main_menu.pages['Settings'].isVisible()

# GUI TEST MOVED TO src/gui/demo.py
# in unit test dialogs block the test
# but in-app we cant reset app before running
import os
import shutil
import sys
import time
import unittest

from PySide6.QtGui import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from gui.main import Main
from utils import sql
from utils.reset import reset_application


class TestApp(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication(sys.argv)
        cls.app.setAttribute(Qt.AA_EnableHighDpiScaling)
        cls.app.setStyle("Fusion")  # Fixes macos white line issue
        cls.main = Main()  # test_mode=True)

    @classmethod
    def tearDownClass(cls):
        # Clean up after all tests
        cls.main.close()
        cls.app.quit()

    def setUp(self):
        self.main.show()
        self.main.raise_()
        QTest.qWait(1000)  # Wait for the window to show

        self.btn_settings = self.main.main_pages.settings_sidebar.page_buttons['settings']
        self.page_settings = self.main.main_pages.pages['settings']

    def test_app(self):
        self.main.activateWindow()
        self.main.run_test()
        while self.main.test_running:
            time.sleep(0.1)
            QApplication.processEvents()  # todo dirtyyy


if __name__ == '__main__':
    shutil.copyfile('./data.db', './test_data.db')

    db_path = os.path.join(os.path.dirname(sql.get_db_path()), 'test_data.db')
    sql.set_db_filepath(db_path)

    reset_db = True
    if reset_db:
        tos_val = sql.get_scalar('SELECT value FROM settings WHERE field = "accepted_tos"')
        if tos_val == '1':
            reset_application(force=True, preserve_audio_msgs=True)
            print("DATABASE RESET.")

        tos_val = sql.get_scalar('SELECT value FROM settings WHERE field = "accepted_tos"')
        if tos_val == '0':
            sql.execute('UPDATE settings SET value = "1" WHERE field = "accepted_tos"')

    unittest.main()

    # delete test_data.db
    if os.path.exists('./test_data.db'):
        os.remove('./test_data.db')

# # # TEST LIST
# # # - Open app with no internet/
# # # - Contexts page
# # # -   Double click context/
# # # -   Chat button/
# # # -   Delete button/
# # # -   Search/
# # # -   Filter/
# # # -   New folder/
# # # -   Right click context items/
# #
# # # - Agents page
# # # -   New agent button/
# # # -   Double click agent/
# # # -   Chat button/
# # # -   Delete button/
# # # -   Search/
# # # -   Filter/
# # # -   New folder/
# # # -     Info tab settings
# # # -       Change plugin
# # # -       Change avatar & name
# # # -     Chat tab settings
# # # -       Message tab settings
# # # -       Preload tab settings
# # # -       Group tab settings
# # # -     Tools tab settings
# # # -     Voice tab settings
# #
# # # - Chat page
# # # -   Edit title
# # # -   Navigation buttons
# # # -   Decoupled scroll
# # # -   Stop button
# # # -   Build master test
# # # -     Output placeholders
# # # -     Hide responses
# #
# # # - Open settings page
# # # -   System tab settings
# # # -     Dev mode
# # # -     Telemetry
# # # -     Always on top
# # # -     Auto run tools & code
# # # -     Default model
# # # -     Auto title
# # # -   Display tab settings
# # # -   Model tab settings
# # # -     New api
# # # -     Edit api fields & provider
# # # -     New model
# # # -     Delete model
# # # -     Edit model
# # # -     Config page
# # # - Blocks page
# # # - Tools page
# # # - Modules page
# # # - Envs page
# # # - Addons page
# # # - Page builder
# #
# # # - Plugins
# # # -   Open interpreter
# # # -   Openai assistant


#
# # import io
# # import os
# # import shutil
# # import sys
# # import threading
# # import time
# # import unittest
# # import pyautogui
# # from PySide6.QtCore import QPoint
# #
# # from PySide6.QtGui import Qt
# # from PySide6.QtWidgets import QApplication, QWidget, QGraphicsItem
# # from PySide6.QtTest import QTest
# # # from jedi.inference.imports import goto_import
# #
# # from gui.main import Main
# # from gui.util import IconButton
# # from utils import sql
# # from utils.helpers import convert_to_safe_case
# # from utils.reset import reset_application
# #
# #
# #
# # def get_widget_coords(widget):
# #     if isinstance(widget, QWidget):
# #         center = widget.rect().center()
# #         global_center = widget.mapToGlobal(center)
# #     elif isinstance(widget, QGraphicsItem):
# #         center = widget.boundingRect().center()
# #         scene_center = widget.mapToScene(center)
# #         view = widget.scene().views()[0]
# #         viewport_center = view.mapFromScene(scene_center)
# #         global_center = view.viewport().mapToGlobal(viewport_center)
# #     else:
# #         raise ValueError("Unsupported widget type")
# #     return global_center.x(), global_center.y()
# #
# #
# # def click_widget(widget, double=False, nb=False):
# #     x, y = get_widget_coords(widget)
# #     click_coords(x, y, double)
# #
# #
# # def hover_widget(widget):
# #     x, y = get_widget_coords(widget)
# #     # pyautogui.moveTo(x, y, duration=0.3)
# #     move_mouse(x, y)
# #
# #
# # def move_mouse(x, y, speed=1000):  # speed is px/s
# #     current_pos = pyautogui.position()
# #     duration = ((x - current_pos.x) ** 2 + (y - current_pos.y) ** 2) ** 0.5 / speed
# #     pyautogui.moveTo(x, y, duration=duration)
# #
# #
# # def click_coords(x, y, double=False):
# #     move_mouse(x, y)
# #     pyautogui.click(x, y)
# #     if double:
# #         QTest.qWait(30)
# #         pyautogui.click(x, y)
# #
# #     QTest.qWait(300)
# #
# #
# # def scroll_wheel(delta):
# #     pyautogui.scroll(delta)
# #     QTest.qWait(500)
# #
# #
# # def type_text(text, interval=20):
# #     for c in text:
# #         pyautogui.typewrite(c)
# #         QTest.qWait(interval)
# #
# #
# # def click_tree_item_cell(tree_widget, index, column, double=False):
# #     # If tree has a header, it is included in the index
# #     if isinstance(column, str):
# #         columns = [convert_to_safe_case(item.get('key', item['text'])) for item in tree_widget.parent.schema]
# #         if column not in columns:
# #             raise ValueError(f'Column {column} not found in tree widget')
# #         column = columns.index(column)
# #
# #         if isinstance(index, str):
# #             row_vals = [tree_widget.topLevelItem(i).text(column) for i in range(tree_widget.topLevelItemCount())]
# #             if index not in row_vals:
# #                 raise ValueError(f'Item {index} not found in column {column}')
# #             index = row_vals.index(index)
# #
# #     item_rect = tree_widget.visualRect(tree_widget.model().index(index, column))
# #     center = item_rect.center()
# #     global_center = tree_widget.mapToGlobal(center)
# #     click_coords(global_center.x(), global_center.y(), double)
# #
# #
# # class TestApp(unittest.TestCase):
# #
# #     @classmethod
# #     def setUpClass(cls):
# #         cls.app = QApplication(sys.argv)
# #         cls.app.setAttribute(Qt.AA_EnableHighDpiScaling)
# #         cls.app.setStyle("Fusion")  # Fixes macos white line issue
# #         cls.main = Main()  # test_mode=True)
# #
# #     @classmethod
# #     def tearDownClass(cls):
# #         # Clean up after all tests
# #         cls.main.close()
# #         cls.app.quit()
# #
# #     def setUp(self):
# #         self.main.show()
# #         self.main.raise_()
# #         QTest.qWait(1000)  # Wait for the window to show
# #
# #         self.btn_settings = self.main.main_menu.settings_sidebar.page_buttons['Settings']
# #         self.page_settings = self.main.main_menu.pages['Settings']
# #
# #     def get_first_chat_bubble_container(self):
# #         page_chat = self.main.page_chat
# #         first_chat_bubble_container = page_chat.message_collection.chat_bubbles[0]
# #         return first_chat_bubble_container
# #
# #     def goto_page(self, page_name, parent_page=None):
# #         if not parent_page:
# #             page_in_main = self.main.main_menu.pages.get(page_name, None)
# #             if page_in_main:
# #                 parent_page = self.main.main_menu
# #             else:
# #                 parent_page = self.main.page_settings
# #
# #         btn = parent_page.settings_sidebar.page_buttons.get(page_name, None)
# #         page = parent_page.pages.get(page_name, None)
# #         if not btn:
# #             raise ValueError(f'Page {page_name} not found')
# #
# #         # from utils.demo import click_widget
# #         click_widget(btn)
# #         return page
# #
# #     def toggle_chat_settings(self, state):
# #         page_chat = self.main.page_chat
# #         currently_visible = page_chat.workflow_settings.isVisible()
# #         if state != currently_visible:
# #             chat_icon = page_chat.top_bar.profile_pic_label
# #             click_widget(chat_icon)
# #         assert page_chat.workflow_settings.isVisible() == state
# #
# #     def send_message(self, message):
# #         message_input = self.main.message_text
# #         click_widget(message_input)
# #         type_text(message)
# #
# #         send_button = self.main.send_button
# #         click_widget(send_button)
# #
# #         while self.main.page_chat.workflow.responding:
# #             print('Waiting for response...')
# #             QTest.qWait(100)
# #
# #     def test_demo(self):
# #         enable_all = False
# #         demo_segments = {
# #             'Models': False,
# #             'Chat': False,  # + Images
# #             'Agents': False,
# #             'Blocks': False,
# #             'Workflows': True,
# #             'Tools': True,
# #             'Modules': True,
# #             'Builder': True,
# #         }
# #         if enable_all:
# #             demo_segments = {k: True for k in demo_segments.keys()}
# #
# #         if demo_segments['Models']:
# #             page_settings = self.goto_page('settings')
# #             page_models = self.goto_page('Models', page_settings)
# #             click_tree_item_cell(page_models.tree, 6, 'api_key')
# #
# #         if demo_segments['Chat']:
# #             self.goto_page('Chat')
# #             page_chat = self.goto_page('Chat')  # 2 ensure blank chat
# #             self.toggle_chat_settings(True)
# #             chat_workflow_settings = page_chat.workflow_settings
# #
# #             chat_agent_settings = chat_workflow_settings.member_config_widget.agent_settings
# #             page_chat_wf_chat = self.goto_page('Chat', chat_agent_settings)
# #             agent_model_combo = page_chat_wf_chat.pages['Messages'].model
# #             cb_x, cb_y = get_widget_coords(agent_model_combo)
# #
# #             hover_widget(agent_model_combo)  # BLOCKING
# #             # pyautogui.moveTo(cb_x, cb_y, duration=0.3)
# #             # QTest.qWait(500)
# #
# #             self.toggle_chat_settings(False)
# #
# #             self.send_message('Hello world')
# #
# #             first_chat_bubble_container = self.get_first_chat_bubble_container()  # page_chat.message_collection.chat_bubbles[0]
# #             first_chat_bubble = first_chat_bubble_container.bubble
# #             click_widget(first_chat_bubble)
# #
# #             pyautogui.press('end')
# #             type_text('!!!!!!!')
# #
# #             resend_button = getattr(first_chat_bubble_container, 'btn_resend', None)
# #             if resend_button:
# #                 click_widget(resend_button)
# #
# #             while self.main.page_chat.workflow.responding:
# #                 print('Waiting for response...')
# #                 QTest.qWait(100)
# #
# #             first_chat_bubble_container = self.get_first_chat_bubble_container()
# #             first_chat_bubble = first_chat_bubble_container.bubble
# #
# #             hover_widget(first_chat_bubble)
# #             branch_btn_back = first_chat_bubble.branch_buttons.btn_back
# #             branch_btn_next = first_chat_bubble.branch_buttons.btn_next
# #             click_widget(branch_btn_back)
# #             click_widget(branch_btn_next)
# #             click_widget(branch_btn_back)
# #             click_widget(branch_btn_next)
# #             QTest.qWait(500)
# #
# #             self.goto_page('Chat')  # New chat
# #             QTest.qWait(800)
# #
# #             self.goto_page('Contexts')
# #             QTest.qWait(800)
# #             self.goto_page('Chat')  # New chat
# #
# #             chat_save_button = chat_workflow_settings.workflow_buttons.btn_save_as
# #             click_widget(chat_save_button)  # BLOCKING
# #
# #         if demo_segments['Agents']:
# #             page_agents = self.goto_page('Agents')
# #
# #             click_tree_item_cell(page_agents.tree, 'Dev Help', 'name')
# #             click_tree_item_cell(page_agents.tree, 'Snoop Dogg', 'name', double=True)
# #
# #             self.toggle_chat_settings(True)
# #             chat_wf_settings = self.main.page_chat.workflow_settings
# #             chat_agent_settings = chat_wf_settings.member_config_widget.agent_settings
# #             page_chat_wf_chat = self.goto_page('Chat', chat_agent_settings)
# #             sys_msg = page_chat_wf_chat.pages['Messages'].sys_msg
# #             click_widget(sys_msg)
# #
# #         if demo_segments['Blocks']:
# #             page_blocks = self.goto_page('Blocks')
# #             click_tree_item_cell(page_blocks.tree, 'known-personality', 'name')
# #             click_tree_item_cell(page_blocks.tree, 'known-personality', 'name')
# #             block_settings = page_blocks.config_widget.member_config_widget.block_settings
# #             click_widget(block_settings.data)
# #             click_widget(block_settings.block_type)
# #
# #         if demo_segments['Workflows']:
# #             self.goto_page('Chat')
# #             page_chat = self.goto_page('Chat')  # dbl click
# #             self.toggle_chat_settings(True)
# #             chat_workflow_settings = page_chat.workflow_settings
# #             chat_buttons = chat_workflow_settings.workflow_buttons
# #             btn_add = chat_buttons.btn_add
# #             click_widget(btn_add)  # , nb=True)  # BLOCKING
# #             # bx, by = get_widget_coords(btn_add)
# #             # QTest.mouseClick(btn_add, Qt.RightButton, pos=QPoint(bx, by))
# #             # QTest.qWait(50)  # Short wait for menu to appear
# #
# #             x, y = get_widget_coords(page_chat.top_bar)
# #             y += 100
# #             click_coords(x, y)
# #             QTest.qWait(30)
# #             click_coords(x, y)
# #
# #             members_in_view = chat_workflow_settings.members_in_view
# #             # member_ids = list(members_in_view.keys())
# #             members = list(members_in_view.values())
# #
# #             click_widget(members[0])
# #             QTest.qWait(300)
# #             click_widget(members[1])
# #             QTest.qWait(300)
# #             click_widget(members[2])
# #             QTest.qWait(300)
# #
# #             click_widget(members[2].output_point)
# #             click_widget(members[1].input_point)
# #             QTest.qWait(300)
# #
# #             click_widget(chat_buttons.btn_member_list)
# #             QTest.qWait(300)
# #             click_widget(chat_buttons.btn_member_list)
# #
# #             hover_widget(members[0])
# #             QTest.qWait(300)
# #
# #             click_widget(members[1])
# #             QTest.qWait(300)
# #             hover_widget(members[2])
# #
# #             click_widget(list(chat_workflow_settings.inputs_in_view.values())[0])
# #             pyautogui.press('delete')  # BLOCKING
# #
# #         QTest.qWait(1000)
# #
# #         #
# #         # # page_contexts = self.goto_page('Contexts')
# #         # # tree_contexts = page_contexts.tree
# #         # # # get the first item rect in the tree efficiently
# #         # # first_item_rect = tree_contexts.visualRect(tree_contexts.model().index(0, 0))
# #         # # # get the center of the rect
# #         # # center = first_item_rect.center()
# #         # # global_center = tree_contexts.mapToGlobal(center)
# #         # # self.click_coords(global_center.x(), global_center.y(), double=True)
# #
# #
# #         # self.iterate_button_bar(page_contexts.tree_buttons)
# #
# #         #
# #         # # Check UI state
# #         # # For example, check if a label text has changed
# #         # label = self.window.findChild(QLabel, "yourLabelName")
# #         # self.assertEqual(label.text(), "Expected Text")
# #         #
# #         # # Or check if a widget is visible
# #         # widget = self.window.findChild(QWidget, "someWidgetName")
# #         # self.assertTrue(widget.isVisible())
# #         # endregion
# #
# #
# # if __name__ == '__main__':
# #     shutil.copyfile('./data.db', './test_data.db')
# #
# #     db_path = os.path.join(os.path.dirname(sql.get_db_path()), 'test_data.db')
# #     sql.set_db_filepath(db_path)
# #
# #     reset_db = True
# #     if reset_db:
# #         tos_val = sql.get_scalar('SELECT value FROM settings WHERE field = "accepted_tos"')
# #         if tos_val == '1':
# #             reset_application(force=True)
# #             print("DATABASE RESET.")
# #
# #         tos_val = sql.get_scalar('SELECT value FROM settings WHERE field = "accepted_tos"')
# #         if tos_val == '0':
# #             sql.execute('UPDATE settings SET value = "1" WHERE field = "accepted_tos"')
# #
# #     unittest.main()
# #
# #     # delete test_data.db
# #     if os.path.exists('./test_data.db'):
# #         os.remove('./test_data.db')