import sys
import time
import unittest
import pyautogui

from PySide6.QtGui import Qt
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from src.gui.main import Main
from src.gui.widgets import IconButton
from src.utils.helpers import convert_to_safe_case


# TEST LIST
# - Open app with no internet/
# - Contexts page
# -   Double click context/
# -   Chat button/
# -   Delete button/
# -   Search/
# -   Filter/
# -   New folder/
# -   Right click context items/

# - Agents page
# -   New agent button/
# -   Double click agent/
# -   Chat button/
# -   Delete button/
# -   Search/
# -   Filter/
# -   New folder/
# -     Info tab settings
# -       Change plugin
# -       Change avatar & name
# -     Chat tab settings
# -       Message tab settings
# -       Preload tab settings
# -       Group tab settings
# -     Tools tab settings
# -     Voice tab settings

# - Chat page
# -   Edit title
# -   Navigation buttons
# -   Decoupled scroll
# -   Stop button
# -   Build master test
# -     Output placeholders
# -     Hide responses

# - Open settings page
# -   System tab settings
# -     Dev mode
# -     Telemetry
# -     Always on top
# -     Auto run tools & code
# -     Default model
# -     Auto title
# -   Display tab settings
# -   Model tab settings
# -     New api
# -     Edit api fields & provider
# -     New model
# -     Delete model
# -     Edit model
# -     Config page
# - Blocks page
# - Tools page
# - Modules page
# - Envs page
# - Addons page
# - Page builder

# - Plugins
# -   Open interpreter
# -   Openai assistant


class TestApp(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication(sys.argv)
        cls.main = Main()

    @classmethod
    def tearDownClass(cls):
        # Clean up after all tests
        cls.main.close()
        cls.app.quit()

    def setUp(self):
        self.main.show()
        self.main.raise_()
        QTest.qWait(1000)  # Wait for the window to show

        self.btn_settings = self.main.main_menu.settings_sidebar.page_buttons['Settings']
        self.page_settings = self.main.main_menu.pages['Settings']

    def click_widget(self, widget, double=False):
        x, y = self.get_widget_coords(widget)
        self.click_coords(x, y)

    def hover_widget(self, widget):
        x, y = self.get_widget_coords(widget)
        pyautogui.moveTo(x, y, duration=0.3)

    def click_coords(self, x, y, double=False):
        pyautogui.moveTo(x, y, duration=0.3)
        pyautogui.click(x, y)
        if double:
            pyautogui.click(x, y)
        QTest.qWait(300)

    def scroll_wheel(self, delta):
        pyautogui.scroll(delta)
        QTest.qWait(500)

    def type_text(self, text, interval=42):
        for c in text:
            pyautogui.typewrite(c)
            QTest.qWait(interval)

    # def click_tree_item_at_index(self, tree_widget, index):
    #     # If tree has a header, it is included in the index
    #     first_item_rect = tree_widget.visualRect(tree_widget.model().index(index, 0))
    #     center = first_item_rect.center()
    #     global_center = tree_widget.mapToGlobal(center)
    #     self.click_coords(global_center.x(), global_center.y(), double=True)

    def click_tree_item_cell(self, tree_widget, index, column):
        # If tree has a header, it is included in the index
        if isinstance(column, str):
            columns = [convert_to_safe_case(item.get('key', item['text'])) for item in tree_widget.parent.schema]
            if column not in columns:
                raise ValueError(f'Column {column} not found in tree widget')
            column = columns.index(column)

        item_rect = tree_widget.visualRect(tree_widget.model().index(index, column))
        center = item_rect.center()
        global_center = tree_widget.mapToGlobal(center)
        self.click_coords(global_center.x(), global_center.y(), double=True)

    def goto_page(self, page_name, parent_page=None):
        if not parent_page:
            page_in_main = self.main.main_menu.pages.get(page_name, None)
            if page_in_main:
                parent_page = self.main.main_menu
            else:
                parent_page = self.page_settings

        btn = parent_page.settings_sidebar.page_buttons.get(page_name, None)
        page = parent_page.pages.get(page_name, None)
        if not btn:
            raise ValueError(f'Page {page_name} not found')

        self.click_widget(btn)
        return page

    def get_widget_coords(self, widget):
        center = widget.rect().center()
        global_center = widget.mapToGlobal(center)
        return global_center.x(), global_center.y()

    def get_first_chat_bubble_container(self):
        page_chat = self.main.page_chat
        first_chat_bubble_container = page_chat.message_collection.chat_bubbles[0]
        return first_chat_bubble_container

    def test_demo(self):
        demo_segments = {
            'Reset': True,
            'Models': True,
            'Chat': True,
            'Agents': True,
        }

        if demo_segments['Models']:
            page_settings = self.goto_page('Settings')
            page_models = self.goto_page('Models', page_settings)
            self.click_tree_item_cell(page_models.tree, 6, 'api_key')

        if demo_segments['Chat']:
            page_chat = self.goto_page('Chat')
            chat_icon = page_chat.top_bar.profile_pic_label
            self.click_widget(chat_icon)
            chat_workflow_settings = page_chat.workflow_settings
            assert chat_workflow_settings.isVisible()

            chat_agent_settings = chat_workflow_settings.member_config_widget.agent_settings
            page_chat_wf_chat = self.goto_page('Chat', chat_agent_settings)
            agent_model_combo = page_chat_wf_chat.pages['Messages'].model
            cb_x, cb_y = self.get_widget_coords(agent_model_combo)

            pyautogui.moveTo(cb_x, cb_y, duration=0.3)
            QTest.qWait(500)
            # close the combo box
            # agent_model_combo.close()

            message_input = self.main.message_text
            self.click_widget(message_input)
            self.type_text('Hello world')

            send_button = self.main.send_button
            self.click_widget(send_button)

            while self.main.page_chat.workflow.responding:
                print('Waiting for response...')
                QTest.qWait(100)

            first_chat_bubble_container = self.get_first_chat_bubble_container()  # page_chat.message_collection.chat_bubbles[0]
            first_chat_bubble = first_chat_bubble_container.bubble
            self.click_widget(first_chat_bubble)

            pyautogui.press('end')
            self.type_text('!!!!!!!')

            resend_button = getattr(first_chat_bubble_container, 'btn_resend', None)
            if resend_button:
                self.click_widget(resend_button)

            while self.main.page_chat.workflow.responding:
                print('Waiting for response...')
                QTest.qWait(100)

            first_chat_bubble_container = self.get_first_chat_bubble_container()
            first_chat_bubble = first_chat_bubble_container.bubble

            self.hover_widget(first_chat_bubble)
            branch_btn_back = first_chat_bubble.branch_buttons.btn_back
            branch_btn_next = first_chat_bubble.branch_buttons.btn_next
            self.click_widget(branch_btn_back)
            self.click_widget(branch_btn_next)
            self.click_widget(branch_btn_back)
            self.click_widget(branch_btn_next)
            QTest.qWait(500)

            self.goto_page('Chat')  # New chat
            QTest.qWait(800)

            self.goto_page('Contexts')
            QTest.qWait(800)
            self.goto_page('Chat')  # New chat

            chat_save_button = chat_workflow_settings.workflow_buttons.btn_save_as
            self.click_widget(chat_save_button)

        if demo_segments['Agents']:
            page_agents = self.goto_page('Agents')

        QTest.qWait(1000)

        #
        # # page_contexts = self.goto_page('Contexts')
        # # tree_contexts = page_contexts.tree
        # # # get the first item rect in the tree efficiently
        # # first_item_rect = tree_contexts.visualRect(tree_contexts.model().index(0, 0))
        # # # get the center of the rect
        # # center = first_item_rect.center()
        # # global_center = tree_contexts.mapToGlobal(center)
        # # self.click_coords(global_center.x(), global_center.y(), double=True)


        # self.iterate_button_bar(page_contexts.tree_buttons)

        #
        # # Check UI state
        # # For example, check if a label text has changed
        # label = self.window.findChild(QLabel, "yourLabelName")
        # self.assertEqual(label.text(), "Expected Text")
        #
        # # Or check if a widget is visible
        # widget = self.window.findChild(QWidget, "someWidgetName")
        # self.assertTrue(widget.isVisible())
        # endregion


if __name__ == '__main__':
    unittest.main()