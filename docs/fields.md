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

**All field modules:** Model, Font, Module, Preset_menu, Color_picker, File_picker, Button, Button_toggle, Input_source, Popup_button, Entity, Float, Text, Combo, List, Venv, Input_target, Member_type_menu, Project_type_menu, Image, Boolean, Media_upload, Integer, Condition_popup_button

Common field kwargs (kwargs that can be used with **any** field module):