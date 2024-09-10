import sys
import time
import unittest
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from src.gui.main import Main

app = None

# TEST LIST
# - Open app with no internet/
# - Open convos page
# -   Double click context/
# -   Chat button/
# -   Delete button/
# -   Search bar/
# -   New folder/
# -   Right click context items/

# - Open agent page
# -   New agent button/
# -   Double click agent/
# -   Chat button/
# -   New folder/
# -   Delete button/
# -     Info tab settings
# -       Change plugin
# -       Change avatar & name
# -     Chat tab settings
# -       Message tab settings
# -       Preload tab settings
# -       Group tab settings
# -     Tools tab settings
# -     Voice tab settings

# - Open settings page
# -   System tab settings
# -     Dev mode
# -     Telemetry
# -     Always on top
# -     Default model
# -     Auto title
# -   Display tab settings
# -   Model tab settings
# -     Edit api
# -     New model
# -     Delete model
# -     Edit model
# -   Blocks tab settings
# -   Sandbox tab settings

# - Chat page
# -   Edit title
# -   Navigation buttons
# -   Openai agent
# -   Perplexity agent
# -   Multi agent mixed providers
# -   Context placeholders
# -   Hide responses
# -   Decoupled scroll
# -   Stop button

# - Plugins
# -   Open interpreter
# -   Openai assistant
# -   Memgpt
# -   Autogen agents (with and without context plugin)
# -   Autogen context plugin
#

# - Other
# -   Push/pull buttons

def setUpModule():
    global app
    app = QApplication([])


def tearDownModule():
    global app
    app.quit()


class TestApp(unittest.TestCase):

    def setUp(self):
        """Initialize before each test."""
        self.main = Main()

    def tearDown(self):
        """Clean-up after each test."""
        self.main.close()

    # region HelperFuncs
    def click_sidebar_button(self, btn_attr_name):
        """Click the specified sidebar button."""
        btn = getattr(self.main.sidebar, btn_attr_name)
        btn.click()

    def find_agent_row(self, agent_name):
        """Find the row of the specified agent."""
        for row in range(self.main.page_agents.tree.rowCount()):
            item = self.main.page_agents.tree.item(row, 3).text()
            if item == agent_name:
                return row
        return None
    # endregion

    # region UnitTests
    def test_initial_state(self):
        """Test the initial state of the app."""
        self.assertTrue(self.main.isVisible())  # Example test

    def test_agent_page(self):
        """Test the agent page."""
        start_time = time.time()  # Start timing
        self.click_sidebar_button('btn_agents')
        load_time = time.time() - start_time  # End timing

        self.assertTrue(self.main.sidebar.btn_agents.isChecked())
        self.assertLess(load_time, 0.25, "Loading the agent page took too long.")

    def test_click_where_agent_is_tupac(self):
        """Test the agent page."""
        self.click_sidebar_button('btn_agents')
        row = self.find_agent_row('Tupac Shakur')
        if row is not None:
            self.main.page_agents.tree.setCurrentCell(row, 0)
            self.assertEqual(self.main.page_agents.tree.currentRow(), row)
        else:
            self.fail('Could not find agent row.')
        # for row in range(self.main.page_agents.table_widget.rowCount()):
        #     agent_name = self.main.page_agents.table_widget.item(row, 3).text()
        #     if agent_name == 'Tupac Shakur':
        #         self.main.page_agents.table_widget.setCurrentCell(row, 0)
        #         self.assertEqual(self.main.page_agents.table_widget.currentRow(), row)
        #         break
    # endregion

    # def test_add_agent(self):
    #     """Test adding an agent."""
    #     self.main.sidebar.btn_agents.click()
    #     self.main.page_agents.btn_new_agent.click()
    #     self.assertTrue(self.main.page_agents.btn_new_agent.input_dialog.isVisible())
    #     # type 'kez'
    #     QTest.keyClicks(self.main.page_agents.btn_new_agent.input_dialog.edit_agent_name, 'kez')


if __name__ == '__main__':
    unittest.main()