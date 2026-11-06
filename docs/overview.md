# Project Overview

This application is a modular desktop platform built with Python, PySide6 and qAsync. At its core, it features a dynamic architecture where modules—ranging from backend services to interactive GUI widgets—can be loaded and modified, even at runtime. This design empowers both developers and users to customize functionality and adapt the user interface to their evolving needs.

Beyond its modular foundation, the application ships with a powerful and extensible workflow engine, a task scheduler, project manager and block library. Together, these tools provide a robust environment for building AI agents and interactive user interfaces with ease.

## Dependencies
- Uses Poetry for dependency management (pyproject.toml)
- Python 3.11 required
- Key dependencies: PySide6, qasync, jinja2, litellm, instructor

## Architecture Overview

The application follows a modular, plugin-based architecture centered around a `SystemManager`:

- **SystemManager** (`src/gui/main.py`): Central orchestrator that dynamically loads all Manager modules, one of which is the `ModuleManager`.

- **ModuleManager** (`src/core/managers/modules.py`): A special `manager` module that loads and maintains all modules, even other `manager` modules.

All modules fall under a specific type, each of these types are defined as `controller` modules under `src/core/controllers/`.
Note that because Controllers are themselves a type of module, they have their own `controller` module (`src/core/controllers/core/controllers.py`)

The types of modules (Controllers) built in to the app are listed below:

### Core module types:

- **Controllers**:  _No description available._ 

- **Actions**: Undo-able user actions 

- **Connectors**: Database connection modules 

- **Daemons**: Background tasks or periodic jobs 

- **Managers**: System-level management modules 

- **Utils**: Shared helper functions 


### GUI module types:

- **Fields**:  Form field components 

- **Gui_utils**:  Shared GUI building blocks 

- **Highlighters**:  Syntax highlighting modules 

- **Pages**:  UI page modules for the application 

- **Widgets**:  Reusable UI widget components 


## GUI Architecture

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

### Pages

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

#### Nested Widget Classes

Pages define widget subclasses inline to configure them:

class Page_Entities(ConfigDBTree):
  def __init__(self, parent):
      super().__init__(
          config_widget=self.Entity_Config_Widget(parent=self),  # ←
      )

  class Entity_Config_Widget(ConfigJoined):  # ← Nested class
      # ... configuration ...

This keeps related configurations together while maintaining separation.

**All page modules:** Daemons, Modules, Display, Icons, System, Tttt, Settings, Tools, Embroidery, Models, Finance, Skills, Files, Slopify, Chat, Projects, Company_search, Plans, Videos, Tasks, Jobs, Agents, Companies_house, Blocks, Contacts, Telephony, Environments, Product_search, Contexts, Voices, Open_food, Claude

### Widgets

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

#### In-app tools (`@llm_tool`)

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

### Fields

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

### Schema-Driven UI

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

## Database and Persistence

- SQLite database (`data.db`) stores contexts, messages, configurations
- Message history with branching support
- Workflow state persistence and resumption

### Baking

Baking saves an item from the database into a file in the source code, so it ships with the app. Right-click an item and choose Bake. With auto-bake on, a baked item is re-baked every time it's saved in the app.

**Items** (blocks, agents, skills, tasks, …) are saved as YAML files in `src/utils/baked/`. The database copy is the real one, and the YAML is only loaded back when the app is reset. So edit items in the app, not the YAML, or your change will be overwritten.

**Modules** are saved as `.py` files in the source code. Here the file is the real one, and it's loaded into the database on every startup. So edit the `.py` file directly. Modules that aren't baked only exist in the database.

Baking isn't possible in the built app.

Block Maps are different: they write a block's output to a file, such as `docs/*.md` or `CLAUDE.md`.

## Plugins
An AgentPilot plugin is a collection of modules bundled together.

By organizing related modules into a single plugin, all modules related to a feature or integration are kept together, making development and maintenance easier.

The application automatically discovers and loads plugins from the `src/plugins` directory at startup. Each module inside a plugin is registered and made available in the app.

### Plugin Structure

Plugins are stored in a folder under `src/plugins`.
A plugin called `my_plugin` would be stored under `src/plugins/my_plugin`

Modules are organized by type, mirroring the core codebase structure
Each module type (e.g., managers, providers, widgets, etc.) has its own folder inside the plugin directory.

These module folders can optionally be grouped into `core` and `gui` folders like the main codebase. Useful if the plugin has many different types of modules.

Example structure:
```
src/
    plugins/
        my_plugin/
            __init__.py
            pages/
                __init__.py
                my_page_module.py
            widgets/
                __init__.py
                my_widget_module.py
            managers/
                __init__.py
                my_manager_module.py
            [any other type of module]/
                [my_other_module.py]
```
## Workflow Engine Overview

The Workflow Engine provides a graph-based execution environment for designing infinitely nestable, AI-driven workflows.
The underlying engine handles state management, dependency resolution, message persistence, and asynchronous execution—all while supporting real-time interaction and branching contexts.

Built-in member types:
- **Conversation:** User, Agent (an LLM), Live Agent (a live voice conversation), Claude Code, Contact.
- **Blocks:** Text, Prompt (a single LLM call), Code.
- **Flow:** Iterator, Probability (continues or stops at random).
- **Media:** Image, Audio, Video.
- **System:** Query (SQL), Set Variable, Wait, Notification.
- **Workflow:** a nested workflow.

Some Text fields - such as System Message's or a Text member- can be a template.

- `{{ my_block }}` — inserts a block's output. Dashes and spaces in block names become underscores.
- `{{ my_block(topic='foo') }}` — runs a block with parameters. Always write them as `name='value'`.
- `{{ assistant_2 }}` — the output of another member in the workflow, named after the member's name and id.
- `{{ topic }}` — a param of the current workflow can also be used in the template.

Put a heading before a block, like `## {{ my_block }}`, to nest the block's own headings under it.


### Workflow Member (`src/core/members/workflow.py`)

The `Workflow` class is itself a `Member`. This implements the **Composite Pattern**, meaning a Workflow can contain other Members, including other Workflows (Nested Workflows).

#### Key Responsibilities:
1.  **Context Management:**
    *   Manages a specific `context_id` in the SQLite database.
    *   Initializes the `MessageHistory` to handle conversation retrieval.
2.  **Member Orchestration:**
    *   Dynamically instantiates child members based on the configuration (`load_members`).
    *   maintains a registry `self.members` mapping IDs to instances.
3.  **Recursive Input Resolution:**

#### Configuration & State
The workflow state is persisted in the `contexts` table. When loaded, it merges the stored JSON configuration with runtime settings:
*   **`autorun`**: Whether the workflow executes immediately upon receiving input.
*   **`members`**: A list of member configurations and their X/Y coordinates.
*   **`inputs`**: Definitions of connections (edges) between members.

### Message System (`src/utils/messages.py`)

The application uses a database-backed message history that supports branching conversations.

#### `MessageHistory`
This class abstracts the complexity of SQL recursive queries to present a given branch of the chat history.

*   **Branching:** It uses Recursive Common Table Expressions (CTEs) to traverse the `contexts` table (`parent_id` relationships) to construct the conversation thread leading to the current `leaf_id`.
*   **Context Filtering:**
    *   `get_llm_messages(calling_member_id)`: Prepares messages specifically for AI ingestion. It handles:
        *   Role filtering (User, Assistant, System, Tool).
        *   JSON parsing for Tool Calls and Results.
        *   Base64 image encoding for Vision models.
        *   Injecting "Preload" data (system prompts).
*   **Structure Mapping:**
    *   If a connection maps a specific JSON key from a source member (e.g., `{ "topic": "coding" }`), `MessageHistory` extracts that specific value and presents it as a message to the target member.

#### `Message` Object
Represents a discrete unit of communication. It tracks:
*   `role`: (user, assistant, system, tool, etc.)
*   `content`: The text payload.
*   `alt_turn`: An integer flag used to group messages into "turns" (execution cycles).

### Execution Engine (`src/core/behaviors/default.py`)

The execution logic is decoupled from the data structure and resides in `DefaultBehavior`. It implements a topological execution flow using `asyncio`.

#### The Execution Loop (`receive`)
The engine runs a continuous loop until a stop condition is met (e.g., user input required, final result produced).

1.  **Dependency Resolution (`get_async_members`):**
    *   Iterates through all members in the workflow.
    *   Checks if a member is "runnable" by verifying if all its input sources have produced a `turn_output`.
    *   **Concurrency:** If multiple members are ready simultaneously, they are executed in parallel using `asyncio.gather`.

2.  **Looping Logic:**
    *   The engine detects "Loopers" (connections marked to allow circular feedback).
    *   If a looper triggers, the engine resets the `turn_output` and `last_output` of specific members, effectively resetting their state to allow them to run again within the same turn.

3.  **Termination:**
    *   The loop breaks when no members are runnable.
    *   It checks `next_expected_is_last_member()` to determine if the final output has been generated.

### Visual Editor (`src/gui/widgets/workflow_settings.py`)

The Workflow Editor is a node-based graphical interface built on **Qt Graphics View Framework**.

#### Architecture
*   **`WorkflowSettings` (ConfigWidget):** The main container. It serializes the visual state back into the JSON configuration required by the backend.
*   **`CustomGraphicsView`:** Handles zooming, panning, and interaction events. Supports a "Mini View" (read-only overview) and an editable canvas.

#### Components
1.  **`DraggableMember` (Nodes):**
    *   Represents an Agent, Block, or Tool.
    *   Contains a `MemberProxy` which renders the specific configuration widget for that member (e.g., Model selection, Temperature).
    *   Handles resizing and visual selection states.
2.  **`ConnectionLine` (Edges):**
    *   Draws Bezier curves between nodes.
    *   **Circular Detection:** Changes visual style and logic if a line creates a loop (`looper`).
    *   **Dynamic Pathing:** Automatically adjusts curvature based on the relative positions of nodes (left/right logic).
3.  **`WorkflowButtons` (Toolbar):**
    *   Provides Copy/Paste functionality (via JSON clipboard serialization).
    *   Allows "Exploding" a nested workflow (breaking a sub-workflow into its constituent nodes on the current canvas).
    *   Manages "Group" functionality to collapse multiple nodes into a new sub-workflow.

#### Visual Abstraction
The editor implements a "Compact Mode" logic:
*   If a workflow contains only 1 Member (or User + Agent), it simplifies the view to hide the node graph, presenting it as a single member.
*   As soon as a third member or complex connection is added, it toggles to the full Graph View.