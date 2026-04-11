# Fields

Fields are atomic, reusable input field, typically used from a ConfigFields or ConfigTree derived widget.

- Purpose: Individual form controls (text inputs, combos, buttons, color
pickers, etc.)
- Examples: Text, Combo, Boolean, FilePicker, ModelField
- Key traits:
- Extend Qt base widgets (QWidget, QLineEdit, etc.)
- Implement get_value() and set_value() methods
- Self-contained with their own validation and styling
- Have an option_schema defining how they themselves can be configured

**All field modules:**

- **Font**

- **Module**

- **Boolean**

- **Member_type_menu**

- **Button_toggle**

- **Condition_popup_button**

- **Entity**

- **List**

- **Image**

- **Input_target**

- **Button**

- **Model**

- **Float**

- **Project_type_menu**

- **Input_source**

- **Integer**

- **Combo**

- **File_picker**

- **Media_upload**

- **Color_picker**

- **Venv**

- **Text**

- **Popup_button**


Common field kwargs (kwargs that can be used with **any** field module):