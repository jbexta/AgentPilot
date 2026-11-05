# GUI Architecture

The codebase implements a three-tier abstraction system for building hierarchical UIs, where complexity is progressively abstracted into reusable components:

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

**All page modules:** Daemons, Settings, Tttt, System, Icons, Modules, Display, Product_search, Projects, Chat, Embroidery, Telephony, Jobs, Skills, Agents, Open_food, Finance, Tasks, Models, Videos, Companies_house, Environments, Claude, Blocks, Slopify, Contexts, Contacts, Voices, Tools, Plans, Company_search, Files

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

Any widget can set the boolean attribute `self.propagate_config`, which allows or prevents propagation of `load_config` and `update_config`.
It is **off by default**. Each widget takes its parent's value when it is constructed, and `update_config` checks the flag at every hop. A subtree that must save sets `self.propagate_config = True` in its root's `__init__`, **before** it builds any child widgets (see `MediaSettings.__init__`). Setting it on a leaf does nothing. If it's missing anywhere in the chain, `save_config` never runs.

### In-app tools (`@llm_tool`)

Any widget or page method can be exposed to agents as a tool that controls the UI, by decorating it with `@llm_tool` from `utils.helpers`:

```python
@llm_tool(
    name='add',
    description='Add a new item to the tree',
    params={'name': 'Name of the new item'},
)
def add_item(self, name: str = None):
    ...
```

- `name`: tool name, defaults to the method name. It is prefixed with the snake-cased defining class, e.g. `config_db_tree_add`.
- `description`: defaults to the method docstring.
- `params`: maps exposed parameter names to descriptions. When omitted, every signature parameter is exposed. `params={}` exposes none.
- `confirm=True`: the user must approve each call before it runs (honoured by Claude Code agents).
- Annotations `str`, `int`, `float` and `bool` map to JSON schema types, anything else is a string. Parameters without a default are required.
- The return value is sent back to the agent as the tool output (`None` -> `Done`). Raise an exception to return an error.

Tools are discovered automatically from every loaded class, listed on the Tools page under the `Application/<module>` folder, and selected in an agent's tool list like workflow tools (selecting a folder selects all tools in it).

**Widget references**

Because a widget class can be on screen many times, a non-root tool takes an extra required `widget` argument, e.g. `w3`. The agent gets these references from `view_ui`, which walks the visible UI with `get_agent_visualisation(refs)` and prints a `Tools [wN]:` block for each widget that has tools. A call fails if the referenced widget is no longer in view, so the agent calls `view_ui` again.

- Mark a class with `_ap_llm_tool_root = True` to make the tools it defines unprefixed and called without a `widget` argument. `MainPages` does this for `view_ui` and `restart_app`. Inherited tools are unaffected, so `switch_page` (from `ConfigPages`) is still `config_pages_switch_page` and takes a `widget`.
- Override `agent_visualisation()` to describe a widget's state to the agent (see `VideoStudio`). Override `get_agent_visualisation(refs)` to control which children are walked (see `FileTree`).
- A tool taking a `refs` parameter receives the caller's reference list, cleared, to number widgets itself (only `view_ui` needs this).

**All widget modules:** Config_db_tree, Config_json_db_tree, Config_table, Config_widget, Config_side_tabs, Config_fields, Config_tabs, Filter_builder, Config_json_tree, Config_pages, Config_tree, Config_collection, Config_joined, Config_ext_tree, Config_voice_tree, Wait_settings, File_tree_deploy, Prompt_settings, Generate_widget, Overlay, Agent_settings, Computer_use_settings, Chat_widget, Github_account, Vcs_panel, Audio_settings, Input_settings, Text_settings, Fund_map, Claude_context, User_settings, Git_diff_settings, Multi_preview, Notif_settings, Video_settings, File_tree, Deploy_panel, Media_settings, Live_agent_settings, Git_checkpoint_settings, Workflow_settings, Code_settings, Contact_settings, Workflow_popup, Message_collection, Set_variable_settings, Query_settings, Image_settings, Cc_user_settings, Probability_settings, File_tree_vcs, Claude_code_settings

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

**All field modules:** Model, Font, Module, Preset_menu, Color_picker, File_picker, Button, Button_toggle, Input_source, Popup_button, Entity, Float, Text, Combo, List, Venv, Input_target, Member_type_menu, Project_type_menu, Image, Boolean, Media_upload, Integer, Condition_popup_button

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