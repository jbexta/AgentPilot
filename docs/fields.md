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

**All field modules:** Input_source, Member_type_menu, Text, Combo, Button, List, Input_target, Popup_button, Project_type_menu, Button_toggle, Module, Image, Condition_popup_button, File_picker, Media_upload, Color_picker, Integer, Float, Boolean, Entity, Font, Model, Preset_menu, Venv

Common field kwargs (kwargs that can be used with **any** field module):