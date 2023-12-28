import sys
import unittest
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from agentpilot.gui import Main

app = None


def setUpModule():
    global app
    app = QApplication([])


def tearDownModule():
    global app
    app.quit()


class TestApp(unittest.TestCase):

    def setUp(self):
        """Initialize before each test."""
        self.main = Main()  # Assuming Main is your main window class

    def tearDown(self):
        """Clean-up after each test."""
        self.main.close()

    def test_initial_state(self):
        """Test the initial state of the app."""
        self.assertTrue(self.main.isVisible())  # Example test

    def test_agent_page(self):
        """Test the agent page."""
        self.main.sidebar.btn_agents.click()
        self.assertTrue(self.main.sidebar.btn_agents.isChecked())

    def test_click_where_agent_is_tupac(self):
        """Test the agent page."""
        self.main.sidebar.btn_agents.click()
        for row in range(self.main.page_agents.table_widget.rowCount()):
            agent_name = self.main.page_agents.table_widget.item(row, 3).text()
            if agent_name == 'Tupac Shakur':
                self.main.page_agents.table_widget.setCurrentCell(row, 0)
                self.assertEqual(self.main.page_agents.table_widget.currentRow(), row)
                break

    # def test_add_agent(self):
    #     """Test adding an agent."""
    #     self.main.sidebar.btn_agents.click()
    #     self.main.page_agents.btn_new_agent.click()
    #     self.assertTrue(self.main.page_agents.btn_new_agent.input_dialog.isVisible())
    #     # type 'kez'
    #     QTest.keyClicks(self.main.page_agents.btn_new_agent.input_dialog.edit_agent_name, 'kez')


if __name__ == '__main__':
    unittest.main()