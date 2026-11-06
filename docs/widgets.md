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

Any widget can set the boolean attribute `self.propagate_config`, which allows or prevents propagation of `load_config` and `update_config`.
It is **off by default**. Each widget takes its parent's value when it is constructed, and `update_config` checks the flag at every hop. A subtree that must save sets `self.propagate_config = True` in its root's `__init__`, **before** it builds any child widgets (see `MediaSettings.__init__`). Setting it on a leaf does nothing. If it's missing anywhere in the chain, `save_config` never runs.

## In-app tools (`@llm_tool`)

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

**All widget modules:** Config_table, Config_voice_tree, Config_pages, Config_tree, Config_side_tabs, Config_db_tree, Config_json_tree, Config_widget, Config_collection, Config_ext_tree, Filter_builder, Config_tabs, Config_json_db_tree, Config_joined, Config_fields, Computer_use_settings, Live_agent_settings, Git_diff_settings, Workflow_popup, Generate_widget, Input_settings, Code_settings, Notif_settings, Video_settings, Cc_user_settings, Audio_settings, Contact_settings, File_tree_vcs, Chat_widget, Fund_map, Image_settings, Prompt_settings, Probability_settings, Git_checkpoint_settings, Wait_settings, Set_variable_settings, Claude_context, Workflow_settings, Text_settings, Claude_code_settings, Multi_preview, Agent_settings, Github_account, Deploy_panel, Overlay, Message_collection, User_settings, File_tree, File_tree_deploy, Vcs_panel, Media_settings, Query_settings