from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget

from src.gui.fields.combo import BaseCombo
from src.gui.util import find_input_key, CVBoxLayout, find_workflow_widget  # , BaseComboBox
from src.utils import sql
from src.utils.helpers import convert_model_json_to_obj, block_signals


class InputSourceComboBox(QWidget):
    currentIndexChanged = Signal(int)
    def __init__(self, parent, **kwargs):
        super().__init__(parent)
        self.parent = parent
        self.source_member_id, _ = find_input_key(self)

        self.layout = CVBoxLayout(self)

        self.main_combo = self.SourceTypeComboBox(self)
        self.output_combo = self.SourceOutputOptions(self)
        self.structure_combo = self.SourceStructureOptions(self)

        # self.main_combo.setCur

        self.layout.addWidget(self.main_combo)
        self.layout.addWidget(self.output_combo)
        self.layout.addWidget(self.structure_combo)

        self.main_combo.currentIndexChanged.connect(self.on_main_combo_index_changed)
        self.output_combo.currentIndexChanged.connect(self.on_main_combo_index_changed)
        self.structure_combo.currentIndexChanged.connect(self.on_main_combo_index_changed)

        # # add a small dot to the left of the comboboxes
        # dot = QLabel(self.parent)
        # dot.setFixedSize(5, 5)
        # dot.setStyleSheet("background-color: red; border-radius: 2px;")
        # # get position of the comboboxes middle (bottom of the first combobox) relative to the parent
        # main_combo_pos = self.main_combo.mapToParent(self.main_combo.rect().center())
        # dot.move(0, main_combo_pos.y() - 2)

        self.load()

    def on_main_combo_index_changed(self):
        # Emit our own signal when the main_combo's index changes
        index = self.main_combo.currentIndex()
        self.currentIndexChanged.emit(index)
        self.update_visibility()

    def load(self):
        with block_signals(self):
            self.main_combo.load()
            self.output_combo.load()
        self.update_visibility()
        self.currentIndexChanged.emit(self.currentIndex())

    def update_visibility(self):
        source_type = self.main_combo.currentText()
        self.output_combo.setVisible(False)
        self.structure_combo.setVisible(False)
        if source_type == 'Output':
            self.output_combo.setVisible(True)
        elif source_type == 'Structure':
            self.structure_combo.setVisible(True)

    def get_structure_sources(self):
        workflow = find_workflow_widget(self)
        source_member = workflow.members_in_view[self.source_member_id]
        source_member_config = source_member.member_config
        source_member_type = source_member_config.get('_TYPE', 'agent')

        structure = []
        if source_member_type == 'agent':
            model_obj = convert_model_json_to_obj(source_member_config.get('chat.model', {}))
            source_member_model_params = model_obj.get('model_params', {})
            structure_data = source_member_model_params.get('structure.data', [])
            structure.extend([p['attribute'] for p in structure_data])

        elif source_member_type == 'prompt_block':
            # block_type = source_member_config.get('_TYPE_PLUGIN', 'Text')
            # if block_type == 'Prompt':
            model_obj = convert_model_json_to_obj(source_member_config.get('prompt_model', {}))
            source_member_model_params = model_obj.get('model_params', {})
            structure_data = source_member_model_params.get('structure.data', [])
            structure.extend([p['attribute'] for p in structure_data])

        return structure

    def setCurrentIndex(self, index):
        self.main_combo.setCurrentIndex(index)
        self.update_visibility()

    def currentIndex(self):
        return self.main_combo.currentIndex()

    def currentData(self):
        return self.main_combo.currentText()

    def itemData(self, index):
        return self.main_combo.itemData(index)

    def findData(self, data):
        return self.main_combo.findData(data)

    def current_options(self):
        if self.output_combo.isVisible():
            return self.output_combo.currentData()
        else:
            return self.structure_combo.currentData()

    def set_options(self, source_type, options):
        if source_type == 'Output':
            index = self.output_combo.findData(options)
            if index != -1:
                self.output_combo.setCurrentIndex(index)
            else:
                self.output_combo.setCurrentIndex(0)
                self.on_main_combo_index_changed()
        elif source_type == 'Structure':
            index = self.structure_combo.findData(options)
            if index != -1:
                self.structure_combo.setCurrentIndex(index)
            else:
                self.structure_combo.setCurrentIndex(0)
                self.on_main_combo_index_changed()

    class SourceTypeComboBox(Combo):
        def __init__(self, parent):
            super().__init__(parent)
            self.parent = parent
            self.load()

        def load(self):
            allowed_outputs = ['Output']
            structure = self.parent.get_structure_sources()
            if len(structure) > 0:
                allowed_outputs.append('Structure')

            with block_signals(self):
                self.clear()
                for output in allowed_outputs:
                    # if not already in the combobox
                    if output not in [self.itemText(i) for i in range(self.count())]:
                        self.addItem(output, output)

    class SourceOutputOptions(BaseCombo):
        def __init__(self, parent):
            super().__init__(parent)
            self.parent = parent
            self.load()

        def showPopup(self):
            # self.load()
            super().showPopup()

        def load(self):
            roles = sql.get_results("SELECT name FROM roles", return_type='list')
            with block_signals(self):
                self.clear()
                self.addItem('  Any role', '<ANY>')
                for role in roles:
                    self.addItem(f'  {role.title()}', role)

    class SourceStructureOptions(BaseCombo):
        def __init__(self, parent):
            super().__init__(parent)
            self.parent = parent
            self.load()

        def showPopup(self):
            # self.load()
            super().showPopup()

        def load(self):
            structure = self.parent.get_structure_sources()
            with block_signals(self):
                self.clear()
                for s in structure:
                    self.addItem(f'  {s}', s)