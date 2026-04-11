# GUI Architecture

The codebase implements a three-tier abstraction system for building
hierarchical UIs, where complexity is progressively abstracted into
reusable components:

**The Hierarchy:**

**Pages:** Highest level - Widget definitions
**Widgets:** Mid level - Configurable interfaces
**Fields:** Lowest level - Input fields

The Abstraction Philosophy:
1. Fields handle their own rendering and value management
2. Widgets handle schema interpretation and config flow
3. Pages just declare "what" (data source, schema), not "how" (UI logic)

All UI logic lives in reusable Widgets and Fields. This means:
- Pages are easily maintainable
- New pages are trivial to create
- Widgets are testable in isolation
- Consistent UX across the app

## Pages

Pages are special widgets with a navigation button added to the sidebar or settings page for users to navigate to. They are typically thin widget definitions, inheritting from any ConfigWidget derived class.

Pattern: Pages instantiate re-usable Widgets with specific configurations rather than implementing UI logic themselves.

Example: Page_Tool_Settings (src/gui/pages/tools.py:28-92)
```
class Page_Tool_Settings(ConfigDBTree):  # ← Extends ConfigDBTree widget
  display_name = 'Tools'
  icon_path = ":/resources/icon-tool.png"

  def __init__(self, parent):
      super().__init__(
          parent=parent,
          manager='tools',           # ← Configuration
          query="...",              # ← What data to show
          schema=[...],             # ← Tree columns
          config_widget=self.ToolWorkflowSettings(parent=self),  # ←
Right panel
          layout_type='horizontal',
          searchable=True,
          # ... more configuration
      )

  class ToolWorkflowSettings(WorkflowSettings):  # ← Nested widget class
      pass  # Inherits all behavior, just configures it
```
The Page does almost nothing - it just:
1. Extends ConfigDBTree widget
2. Configures it with table, query, schema
3. Specifies WorkflowSettings as the config widget
4. Optionally overrides methods like on_edited()

### Nested Widget Classes

Pages define widget subclasses inline to configure them:

class Page_Entities(ConfigDBTree):
  def __init__(self, parent):
      super().__init__(
          config_widget=self.Entity_Config_Widget(parent=self),  # ←
      )

  class Entity_Config_Widget(ConfigJoined):  # ← Nested class
      # ... configuration ...

This keeps related configurations together while maintaining separation.

**All page modules:**

- **Blocks**

- **Finance**

- **Videos**

- **Slopify**

- **Modules**

- **System**

- **Models**

- **Channels**

- **Tasks**

- **Tools**

- **Agents**

- **Images**

- **Chat**

- **Youtube**

- **Display**

- **Projects**

- **Todo**

- **Job_hunter**

- **Files**

- **Settings**

- **Contexts**

- **Environments**


## Widgets

Widgets are reusable configurable components that have a specific functionality.
They can orchestrate multiple fields or other widgets
Ideally they extend ConfigWidget, or any other class derived from ConfigWidget

Key built-in Widgets:
{{ ConfigWidget }}
{{ ConfigFields }}
{{ ConfigJoined }}
{{ ConfigTabs }}
{{ ConfigPages }}
{{ ConfigDBTree }}

a) ConfigFields - Schema-driven form builder
- Takes a schema list defining fields
- Dynamically instantiates Field widgets via get_field_widget()
- Auto-binds values to/from config dict

b) ConfigDBTree - Database-backed tree view with config panel
- Left panel: Tree view of database items (with folders)
- Right panel: Configuration widget for selected item
- Handles CRUD operations, search, filtering

c) ConfigJoined - Combines multiple widgets
- Vertical or horizontal layout
- Aggregates configs from child widgets

d) WorkflowSettings - Complex workflow designer
- Visual graph editor with drag-drop
- Combines header fields + workflow canvas + member config
- A complete specialized configuration interface

e) Other specialized widgets:
- AgentSettings, InputSettings, NotifSettings, etc.
- Domain-specific configurations built from Fields/Widgets

Widget Responsibilities:

- Schema building: `build_schema()` - construct UI from schema
- Config loading: `load_config(json_config)` - populate from data source
- UI loading: `load()` - load UI from the config
- Signal an update: `update_config()` - propagates up to root, runs save_config
- Config extraction: `get_config()` - serialize current state
- Config saving: `save_config()` - persist to database

Propagation:
a) Down from root to all leaf widgets:
- `build_schema()`
-` load_config()`
- `load()`

b) Up to root from any leaf widget:
- `update_config()`

Any widget can set the boolean attribute `self.propagate_config` which allows or prevents propagation of `load_config` and `update_config`.
This is True by default for all widgets, but some widgets such as `ConfigDBTree` and `ConfigTable` have it set to False by default.

**All widget modules:**

- **Config_json_tree**

- **Config_joined**

- **Config_side_tabs**

- **Config_ext_tree**

- **Config_table**

- **Query_settings**

- **Code_settings**

- **Config_json_db_tree**

- **Config_tree**

- **Population_view**

- **Image_settings**

- **Config_pages**

- **Text_settings**

- **User_settings**

- **Multi_preview**

- **Input_settings**

- **Probability_settings**

- **Config_collection**

- **Wait_settings**

- **Overlay**

- **Workflow_settings**

- **Config_voice_tree**

- **Config_tabs**

- **Video_settings**

- **Config_db_tree**

- **Generate_widget**

- **File_tree**

- **Message_collection**

- **Chat_widget**

- **Audio_settings**

- **Prompt_settings**

- **Contact_settings**

- **Config_widget**

- **Control_panel**

- **Notif_settings**

- **Fund_map**

- **Fitness_chart**

- **Config_fields**

- **Claude_code_settings**

- **Agent_settings**

- **Media_settings**

- **Computer_use_settings**

- **Collections_widget**


## Fields

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

## Schema-Driven UI

Some widgets have a `schema` attribute, which contains a list of dictionaries.
Fields and widgets are defined by schema dictionaries:

schema = [
  {
      'text': 'Name',        # Label
      'key': 'name',         # Config key
      'type': str,           # Field type (or tuple for Combo)
      'default': '',
      'width': 150,
      'is_config_field': True,  # Save to config vs DB column
  }
]

The system automatically:
- Instantiates the correct Field class
- Binds it to the config key
- Handles value serialization