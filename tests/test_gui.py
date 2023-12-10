import unittest
from unittest import TestCase
from gui import GUI


class TestApp(TestCase):
    """Tests the pyside app."""

    def test_app_run(self):
        """Tests if app opens
        """
        app = GUI()
        app.run()


if __name__ == '__main__':
    unittest.main()
