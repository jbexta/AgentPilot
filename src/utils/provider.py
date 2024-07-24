from src.gui.config import ConfigFields


# Model provider can sync & run models under a specific API

class Provider:
    def __init__(self):
        pass

    # def sync_all(self):
    #     """Implement this method to show sync button"""
    #     pass

    # class ChatConfig(ConfigFields):
    #     """Implement this method to show custom config tab in chat tab"""
    #     def __init__(self, parent):
    #         super().__init__(parent=parent)
    #         self.label_width = 125
    #         self.schema = []

    # class ChatModelParameters(ConfigFields):
    #     """Implement this method to show custom parameters for chat models"""
    #     def __init__(self, parent):
    #         super().__init__(parent=parent)
    #         self.parent = parent
    #         self.schema = []

