from PySide6.QtGui import QFont, Qt
from PySide6.QtWidgets import QDialog, QLabel, QPlainTextEdit, QVBoxLayout, QWidget

from gui.gui_utils.layouts import CHBoxLayout
from gui.gui_utils.helpers import find_main, get_selected_pages
from gui.gui_utils.icon_button import IconButton


class BreadcrumbWidget(QWidget):
    def __init__(self, parent, root_title=None):
        super().__init__(parent=parent)

        self.setFixedHeight(45)
        self.parent = parent
        self.root_title = root_title

        self.title_layout = CHBoxLayout(self)
        self.title_layout.setSpacing(20)
        self.title_layout.setContentsMargins(20, 0, 10, 0)

        self.label = QLabel(root_title)
        self.font = QFont()
        self.font.setPointSize(15)
        self.label.setFont(self.font)

        self.title_layout.addWidget(self.label)

        # self.edit_btn = IconButton(
        #     parent=self,
        #     icon_path=':/resources/icon-edit.png',
        #     tooltip='Edit this page'
        # )
        # self.edit_btn.setFixedSize(25, 25)
        # self.edit_btn.clicked.connect(self.edit_page)
        # self.edit_btn.hide()
        #
        # self.finish_btn = IconButton(
        #     parent=self,
        #     icon_path=':/resources/icon-tick.svg',
        #     tooltip='Finish editing'
        # )
        # self.finish_btn.setFixedSize(25, 25)
        # self.finish_btn.clicked.connect(self.finish_edit)
        # self.finish_btn.hide()

        self.viz_btn = IconButton(
            parent=self,
            icon_path=':/resources/icon-eye.png',
            tooltip='Show agent visualisation'
        )  # temp: preview agent visualisation
        self.viz_btn.setFixedSize(25, 25)
        self.viz_btn.clicked.connect(self.show_page_visualisation)
        self.viz_btn.hide()

        # self.title_layout.addWidget(self.edit_btn)
        self.title_layout.addWidget(self.viz_btn)
        # self.title_layout.addWidget(self.finish_btn)

    def load(self):
        sel_pages = get_selected_pages(self.parent, incl_objects=True, stop_at_tree=True)
        sel_page_tuples = list(sel_pages.values())
        page_names = [getattr(p, 'display_name', p_name) for p_name, p in sel_page_tuples if p is not None]
        page_names.insert(0, self.root_title)
        breadcrumb_text = '   >   '.join(page_names)
        if breadcrumb_text:
            self.label.setText(breadcrumb_text)

    # def edit_page(self):  # todo
    #     main = find_main()
    #     page_widget = self.parent
    #     module_name = None
    #     for name, page in main.main_pages.pages.items():
    #         if page is page_widget:
    #             module_name = name
    #             break
    #     if not module_name:
    #         return
    #
    #     if hasattr(page_widget, 'toggle_widget_edit'):
    #         page_widget.toggle_widget_edit(True)
    #
    #     from gui.pages.modules import PageEditor
    #     if getattr(main, 'module_popup', None):
    #         main.module_popup.close()
    #         main.module_popup = None
    #     main.module_popup = PageEditor(main, module_name)
    #     main.module_popup.load()
    #     main.module_popup.show()
    #     self.edit_btn.hide()
    #     self.finish_btn.show()
    #
    # def finish_edit(self):
    #     page_widget = self.parent
    #     if hasattr(page_widget, 'toggle_widget_edit'):
    #         page_widget.toggle_widget_edit(False)
    #
    #     main = find_main()
    #     if getattr(main, 'module_popup', None):
    #         main.module_popup.close()
    #         main.module_popup = None
    #
    #     edit_bar = getattr(self.parent, 'edit_bar', None)
    #     if edit_bar:
    #         edit_bar.hide()
    #
    #     self.finish_btn.hide()
    #     self.edit_btn.show()

    def enterEvent(self, event):
        # user_editing = find_attribute(self.parent, 'user_editing', False)
        # if user_editing:
        #     self.finish_btn.show()
        #     return
        #
        # allow_db = sql.get_scalar("""
        #     SELECT json_extract(value, '$."system.allow_importing_db_modules"')
        #     FROM settings WHERE field = 'app_config'
        # """)
        # module_id = find_attribute(self.parent, 'module_id')
        # can_edit = module_id is not None and allow_db
        # if can_edit:
        #     self.edit_btn.show()
        #     self.finish_btn.hide()
        self.viz_btn.show()

    def leaveEvent(self, event):
        # self.edit_btn.hide()
        self.viz_btn.hide()

    def show_page_visualisation(self):  # temp: preview agent visualisation
        dialog = QDialog(self)
        dialog.setWindowFlags(
            Qt.Window
            | Qt.WindowTitleHint
            | Qt.WindowSystemMenuHint
            | Qt.WindowCloseButtonHint
            | Qt.WindowStaysOnTopHint
        )
        dialog.setWindowTitle('Agent visualisation')
        layout = QVBoxLayout(dialog)
        text_box = QPlainTextEdit(dialog)
        text_box.setReadOnly(True)
        text_box.setPlainText(find_main().main_pages.get_agent_visualisation([]))
        layout.addWidget(text_box)
        dialog.resize(600, 500)
        dialog.exec()
