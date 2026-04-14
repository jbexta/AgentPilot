from PySide6.QtWidgets import QWidget, QPushButton, QHBoxLayout

from gui.util import CVBoxLayout, get_field_widget
from utils.helpers import set_module_type


@set_module_type('Fields')
class List(QWidget):
    """
    A list field widget that manages multiple instances of a specified field type.

    This widget creates a dynamic list where users can add and remove field items.
    Each item is an instance of the field type specified by `of_type`, initialized
    with the parameters from `of_type_default_params`.

    Parameters (via kwargs):
        parent (QWidget): The parent widget.
        of_type (str or type): The type of field to contain (e.g., 'text', str, int).
        of_type_default_params (dict, optional): Default parameters for each field instance.
        default (list, optional): Default list of values.
        min_items (int, optional): Minimum number of items (fields cannot be removed below this).
        max_items (int, optional): Maximum number of items (add button disabled above this).

    Methods:
        get_value(): Returns a list of values from all field items.
        set_value(value): Sets the list values by creating fields for each item.
        clear_value(): Removes all fields and resets to empty list.

    The widget emits changes via the parent's `update_config` method when items are added or removed.
    """

    option_schema = [
        {
            'text': 'Of type',
            'key': 'f_of_type',
            'type': str,
            'default': 'text',
            'tooltip': 'The type of field this list contains',
        },
        {
            'text': 'Min items',
            'key': 'f_min_items',
            'type': int,
            'minimum': 0,
            'maximum': 999,
            'has_toggle': True,
            'default': None,
            'tooltip': 'Minimum number of items allowed',
        },
        {
            'text': 'Max items',
            'key': 'f_max_items',
            'type': int,
            'minimum': 1,
            'maximum': 999,
            'has_toggle': True,
            'default': None,
            'tooltip': 'Maximum number of items allowed',
        },
    ]

    def __init__(self, parent, **kwargs):
        super().__init__(parent)
        self.parent = parent

        # Configuration parameters
        self.of_type = kwargs.get('of_type', 'text')
        self.of_type_default_params = kwargs.get('of_type_default_params', {})
        self.min_items = kwargs.get('min_items', None)
        self.max_items = kwargs.get('max_items', None)
        default_value = kwargs.get('default', [])

        # Store field widgets
        self.field_widgets = []

        # Main layout
        self.main_layout = CVBoxLayout(self)

        # Container for field items
        self.items_layout = CVBoxLayout()
        self.main_layout.addLayout(self.items_layout)

        # Add button
        self.add_button = QPushButton('+')
        self.add_button.setFixedSize(30, 25)
        self.add_button.clicked.connect(self.add_field)

        add_button_container = QHBoxLayout()
        add_button_container.setContentsMargins(0, 5, 0, 0)
        add_button_container.addWidget(self.add_button)
        add_button_container.addStretch()
        self.main_layout.addLayout(add_button_container)

        # Set default values if provided
        if default_value:
            self.set_value(default_value)

    def add_field(self, value=None):
        """Add a new field to the list."""
        # Check max items limit
        if self.max_items is not None and len(self.field_widgets) >= self.max_items:
            self.add_button.setEnabled(False)
            return

        # Create row container
        row_widget = QWidget()
        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(0, 2, 0, 2)
        row_layout.setSpacing(5)

        # Create field schema
        field_schema = {
            'type': self.of_type,
            **self.of_type_default_params
        }

        # Create field widget
        field_widget = get_field_widget(field_schema, parent=self)
        if not field_widget:
            return

        # Set field value if provided
        if value is not None:
            if hasattr(field_widget, 'set_value'):
                field_widget.set_value(value)

        # Create remove button
        remove_button = QPushButton('-')
        remove_button.setFixedSize(25, 25)
        remove_button.clicked.connect(lambda: self.remove_field(row_widget, field_widget))

        # Add widgets to row
        row_layout.addWidget(field_widget, stretch=1)
        row_layout.addWidget(remove_button)

        # Add row to items layout
        self.items_layout.addWidget(row_widget)

        # Store references
        self.field_widgets.append(field_widget)

        # Update button states
        self.update_button_states()

        # Notify parent of config change
        if self.parent and hasattr(self.parent, 'update_config'):
            self.parent.update_config()

    def remove_field(self, row_widget, field_widget):
        """Remove a field from the list."""
        # Check min items limit
        if self.min_items is not None and len(self.field_widgets) <= self.min_items:
            return

        # Remove from field widgets list
        if field_widget in self.field_widgets:
            self.field_widgets.remove(field_widget)

        # Remove row widget
        self.items_layout.removeWidget(row_widget)
        row_widget.deleteLater()

        # Update button states
        self.update_button_states()

        # Notify parent of config change
        if self.parent and hasattr(self.parent, 'update_config'):
            self.parent.update_config()

    def update_config(self):
        """Implements same method as ConfigWidget, as a workaround to avoid inheriting from it"""
        if hasattr(self.parent, 'update_config'):
            self.parent.update_config()

    def update_button_states(self):
        """Update the enabled state of add button based on limits."""
        # Update add button
        if self.max_items is not None:
            self.add_button.setEnabled(len(self.field_widgets) < self.max_items)
        else:
            self.add_button.setEnabled(True)

    def get_value(self):
        """Get list of values from all field widgets."""
        values = []
        for field_widget in self.field_widgets:
            if hasattr(field_widget, 'get_value'):
                values.append(field_widget.get_value())
        return values

    def set_value(self, value):
        """Set the list values by creating fields for each item."""
        if not isinstance(value, (list, tuple)):
            value = [value] if value else []

        # Clear existing fields
        self.clear_value()

        # Add a field for each value
        for item in value:
            self.add_field(value=item)

    def clear_value(self):
        """Clear all field widgets."""
        # Remove all field widgets
        while self.field_widgets:
            field_widget = self.field_widgets[0]
            # Find the row widget containing this field
            for i in range(self.items_layout.count()):
                item = self.items_layout.itemAt(i)
                if item and item.widget():
                    row_widget = item.widget()
                    # Check if this row contains our field
                    row_layout = row_widget.layout()
                    if row_layout:
                        for j in range(row_layout.count()):
                            row_item = row_layout.itemAt(j)
                            if row_item and row_item.widget() == field_widget:
                                self.field_widgets.remove(field_widget)
                                self.items_layout.removeWidget(row_widget)
                                row_widget.deleteLater()
                                break
                    break

        # Update button states
        self.update_button_states()