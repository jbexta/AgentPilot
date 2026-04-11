# Widgets

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
