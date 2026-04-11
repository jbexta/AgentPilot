
from plugins.workflows.widgets.chat_widget import ChattableWorkflowWidget


class Page_Chat(ChattableWorkflowWidget):  # (ChatWidget):
    display_name = 'Chat'
    icon_path = ':/resources/icon-chat.png'
    icon_path_checked = ':/resources/icon-new-large.png'
    page_type = 'main'  # either 'settings', 'main', or 'any' ('any' means it can be pinned between main and settings)
    show_checked_background = False
    show_breadcrumbs = False

    def __init__(self, parent):
        super().__init__(
            parent=parent,
            collapsible=True,
            # show_settings=True,
        )
        self.target_when_checked = self.new_chat

    # def ensure_visible(self):
    #     # make sure chat page button is shown
    #     stacked_widget = self.main.main_pages.content
    #     index = stacked_widget.indexOf(self)
    #     current_index = stacked_widget.currentIndex()
    #     if index != current_index:
    #         self.main.main_pages.settings_sidebar.page_buttons['chat'].click()
    #         self.main.main_pages.settings_sidebar.page_buttons['chat'].setChecked(True)
