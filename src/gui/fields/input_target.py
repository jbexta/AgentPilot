from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget

from src.gui.fields.combo import BaseCombo
from src.gui.util import find_workflow_widget, CVBoxLayout, find_input_key
from src.utils.helpers import block_signals


class InputTargetComboBox(QWidget):
    currentIndexChanged = Signal(int)
    def __init__(self, parent, **kwargs):
        super().__init__(parent)
        self.parent = parent
        _, self.target_member_id = find_input_key(self)

        self.layout = CVBoxLayout(self)
        self.main_combo = self.TargetTypeComboBox(self)
        self.layout.addWidget(self.main_combo)

        self.main_combo.currentIndexChanged.connect(self.on_main_combo_index_changed)

        self.load()

    def on_main_combo_index_changed(self, index):
        # Emit our own signal when the main_combo's index changes
        self.currentIndexChanged.emit(index)
        self.update_visibility()

    def load(self):
        with block_signals(self):
            self.main_combo.load()
        self.update_visibility()
        self.currentIndexChanged.emit(self.currentIndex())

    def update_visibility(self):
        pass

    def setCurrentIndex(self, index):
        self.main_combo.setCurrentIndex(index)

    def currentIndex(self):
        return self.main_combo.currentIndex()

    def currentData(self):
        return self.main_combo.currentText()

    def itemData(self, index):
        return self.main_combo.itemData(index)

    def findData(self, data):
        return self.main_combo.findData(data)

    def current_options(self):
        return None

    class TargetTypeComboBox(BaseCombo):
        def __init__(self, parent):
            super().__init__(parent)
            self.parent = parent
            self.load()

        def showPopup(self):
            # self.load()
            super().showPopup()

        def load(self):
            workflow = find_workflow_widget(self)
            target_member = workflow.members_in_view[self.parent.target_member_id]
            target_member_config = target_member.member_config
            target_member_type = target_member_config.get('_TYPE', 'agent')

            allowed_inputs = []
            if target_member_type == 'workflow':
                target_workflow_first_member = next(iter(sorted(target_member_config.get('members', []),
                                                 key=lambda x: x['loc_x'])),
                                               None)
                if target_workflow_first_member:
                    first_member_is_user = target_workflow_first_member['config'].get('_TYPE', 'agent') == 'user'
                    if first_member_is_user:  # todo de-dupe
                        allowed_inputs = ['Message']

            elif target_member_type == 'agent' or target_member_type == 'user':
                allowed_inputs = ['Message']

            with block_signals(self):
                self.clear()
                for inp in allowed_inputs:
                    if inp not in [self.itemText(i) for i in range(self.count())]:
                        self.addItem(inp, inp)