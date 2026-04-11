# Modules
The codebase is highly modular and extensible, allowing anyone to extend or override almost any aspect of the app.

This document describes the different types of modules supported by the app, where they are used, how they interact, and how to create them.



## Core Modules:

### Controllers

_No description available._

<details>
  <summary>Implementations</summary>

- [{{ no such element: dict object['__name__'] }}](src/core/controllers/daemons)

- [{{ no such element: dict object['__name__'] }}](src/core/controllers/controllers)

- [{{ no such element: dict object['__name__'] }}](src/core/controllers/audio_operations)

- [{{ no such element: dict object['__name__'] }}](src/core/controllers/primitives)

- [{{ no such element: dict object['__name__'] }}](src/core/controllers/managers)

- [{{ no such element: dict object['__name__'] }}](src/core/controllers/project_types)

- [{{ no such element: dict object['__name__'] }}](src/core/controllers/providers)

- [{{ no such element: dict object['__name__'] }}](src/core/controllers/bubbles)

- [{{ no such element: dict object['__name__'] }}](src/core/controllers/finance_apis)

- [{{ no such element: dict object['__name__'] }}](src/core/controllers/image_effects)

- [{{ no such element: dict object['__name__'] }}](src/core/controllers/ga_type)

- [{{ no such element: dict object['__name__'] }}](src/core/controllers/video_operations)

- [{{ no such element: dict object['__name__'] }}](src/core/controllers/image_operations)

- [{{ no such element: dict object['__name__'] }}](src/core/controllers/3d_operations)

- [{{ no such element: dict object['__name__'] }}](src/core/controllers/pages)

- [{{ no such element: dict object['__name__'] }}](src/core/controllers/fields)

- [{{ no such element: dict object['__name__'] }}](src/core/controllers/highlighters)

- [{{ no such element: dict object['__name__'] }}](src/core/controllers/behaviors)

- [{{ no such element: dict object['__name__'] }}](src/core/controllers/text_operations)

- [{{ no such element: dict object['__name__'] }}](src/core/controllers/connectors)

- [{{ no such element: dict object['__name__'] }}](src/core/controllers/widgets)

- [{{ no such element: dict object['__name__'] }}](src/core/controllers/studios)

- [{{ no such element: dict object['__name__'] }}](src/core/controllers/members)

- [{{ no such element: dict object['__name__'] }}](src/core/controllers/environments)

- [{{ no such element: dict object['__name__'] }}](src/core/controllers/audio_effects)

</details>
<details>
  <summary>Create a Controller</summary>
To create a Controller module, add a new file under `src/core/controllers/` with the name of your module, for example `my_controller.py`.


</details>

### Connectors

Connector modules handle connections to external sources such as databases

<details>
  <summary>Implementations</summary>

- [{{ no such element: dict object['__name__'] }}](src/core/connectors/h5)

- [{{ no such element: dict object['__name__'] }}](src/core/connectors/mysql)

- [{{ no such element: dict object['__name__'] }}](src/core/connectors/postgres)

- [{{ no such element: dict object['__name__'] }}](src/core/connectors/sqlite)

</details>
<details>
  <summary>Create a Connector</summary>
To create a Connector module, add a new file under `src/core/connectors/` with the name of your module, for example `my_connector.py`.


This file must contain a class definition.

Note: If more than one class is declared in the file, then you must mark your connector  class with the decorator `@set_module_type('Connectors')`.

</details>

### Daemons

Daemon modules are background processes that run continuously

<details>
  <summary>Implementations</summary>

- [{{ no such element: dict object['__name__'] }}](src/core/daemons/tasks)

</details>
<details>
  <summary>Create a Daemon</summary>
To create a Daemon module, add a new file under `src/core/daemons/` with the name of your module, for example `my_daemon.py`.


This file must contain a class definition.

Note: If more than one class is declared in the file, then you must mark your daemon  class with the decorator `@set_module_type('Daemons')`.

</details>

### Managers

Manager modules are initialized on startup, these often load and save data to a specific database table.

<details>
  <summary>Implementations</summary>

- [{{ no such element: dict object['__name__'] }}](src/core/managers/blocks)

- [{{ no such element: dict object['__name__'] }}](src/core/managers/tools)

- [{{ no such element: dict object['__name__'] }}](src/core/managers/modules)

- [{{ no such element: dict object['__name__'] }}](src/core/managers/config)

- [{{ no such element: dict object['__name__'] }}](src/core/managers/projects)

- [{{ no such element: dict object['__name__'] }}](src/core/managers/apis)

- [{{ no such element: dict object['__name__'] }}](src/core/managers/models)

- [{{ no such element: dict object['__name__'] }}](src/core/managers/agents)

- [{{ no such element: dict object['__name__'] }}](src/core/managers/providers)

- [{{ no such element: dict object['__name__'] }}](src/core/managers/roles)

- [{{ no such element: dict object['__name__'] }}](src/core/managers/venvs)

- [{{ no such element: dict object['__name__'] }}](src/core/managers/daemons)

- [{{ no such element: dict object['__name__'] }}](src/core/managers/environments)

</details>
<details>
  <summary>Create a Manager</summary>
To create a Manager module, add a new file under `src/core/managers/` with the name of your module, for example `my_manager.py`.


This file must contain a class definition that inherits from `BaseManager`.

Note: If more than one class is declared in the file, then you must mark your manager  class with the decorator `@set_module_type('Managers')`.

</details>



## GUI Modules:

### Fields

Fields are QWidget modules that represent a single data field, such as a text field, a number field, a checkbox, etc.

<details>
  <summary>Implementations</summary>

- [{{ no such element: dict object['__name__'] }}](src/gui/fields/font)

- [{{ no such element: dict object['__name__'] }}](src/gui/fields/module)

- [{{ no such element: dict object['__name__'] }}](src/gui/fields/boolean)

- [{{ no such element: dict object['__name__'] }}](src/gui/fields/member_type_menu)

- [{{ no such element: dict object['__name__'] }}](src/gui/fields/button_toggle)

- [{{ no such element: dict object['__name__'] }}](src/gui/fields/condition_popup_button)

- [{{ no such element: dict object['__name__'] }}](src/gui/fields/entity)

- [{{ no such element: dict object['__name__'] }}](src/gui/fields/list)

- [{{ no such element: dict object['__name__'] }}](src/gui/fields/image)

- [{{ no such element: dict object['__name__'] }}](src/gui/fields/input_target)

- [{{ no such element: dict object['__name__'] }}](src/gui/fields/button)

- [{{ no such element: dict object['__name__'] }}](src/gui/fields/model)

- [{{ no such element: dict object['__name__'] }}](src/gui/fields/float)

- [{{ no such element: dict object['__name__'] }}](src/gui/fields/project_type_menu)

- [{{ no such element: dict object['__name__'] }}](src/gui/fields/input_source)

- [{{ no such element: dict object['__name__'] }}](src/gui/fields/integer)

- [{{ no such element: dict object['__name__'] }}](src/gui/fields/combo)

- [{{ no such element: dict object['__name__'] }}](src/gui/fields/file_picker)

- [{{ no such element: dict object['__name__'] }}](src/gui/fields/media_upload)

- [{{ no such element: dict object['__name__'] }}](src/gui/fields/color_picker)

- [{{ no such element: dict object['__name__'] }}](src/gui/fields/venv)

- [{{ no such element: dict object['__name__'] }}](src/gui/fields/text)

- [{{ no such element: dict object['__name__'] }}](src/gui/fields/popup_button)

</details>
<details>
  <summary>Create a Field</summary>
To create a Field module, add a new file under `src/gui/fields/` with the name of your module, for example `my_field.py`.


This file must contain a class definition that inherits from `QWidget`.

Note: If more than one class is declared in the file, then you must mark your field  class with the decorator `@set_module_type('Fields')`.

</details>

### Highlighters

Highlighter modules define the syntax highlighting of text areas

<details>
  <summary>Implementations</summary>

- [{{ no such element: dict object['__name__'] }}](src/gui/highlighters/python)

- [{{ no such element: dict object['__name__'] }}](src/gui/highlighters/xml)

- [{{ no such element: dict object['__name__'] }}](src/gui/highlighters/cel)

- [{{ no such element: dict object['__name__'] }}](src/gui/highlighters/json)

</details>
<details>
  <summary>Create a Highlighter</summary>
To create a Highlighter module, add a new file under `src/gui/highlighters/` with the name of your module, for example `my_highlighter.py`.


This file must contain a class definition that inherits from `QSyntaxHighlighter`.

Note: If more than one class is declared in the file, then you must mark your highlighter  class with the decorator `@set_module_type('Highlighters')`.

</details>

### Pages

Pages are QWidget modules that can be composed of Widget modules

<details>
  <summary>Implementations</summary>

- [{{ no such element: dict object['__name__'] }}](src/gui/pages/blocks)

- [{{ no such element: dict object['__name__'] }}](src/gui/pages/finance)

- [{{ no such element: dict object['__name__'] }}](src/gui/pages/videos)

- [{{ no such element: dict object['__name__'] }}](src/gui/pages/slopify)

- [{{ no such element: dict object['__name__'] }}](src/gui/pages/modules)

- [{{ no such element: dict object['__name__'] }}](src/gui/pages/system)

- [{{ no such element: dict object['__name__'] }}](src/gui/pages/models)

- [{{ no such element: dict object['__name__'] }}](src/gui/pages/channels)

- [{{ no such element: dict object['__name__'] }}](src/gui/pages/tasks)

- [{{ no such element: dict object['__name__'] }}](src/gui/pages/tools)

- [{{ no such element: dict object['__name__'] }}](src/gui/pages/agents)

- [{{ no such element: dict object['__name__'] }}](src/gui/pages/images)

- [{{ no such element: dict object['__name__'] }}](src/gui/pages/chat)

- [{{ no such element: dict object['__name__'] }}](src/gui/pages/youtube)

- [{{ no such element: dict object['__name__'] }}](src/gui/pages/display)

- [{{ no such element: dict object['__name__'] }}](src/gui/pages/projects)

- [{{ no such element: dict object['__name__'] }}](src/gui/pages/todo)

- [{{ no such element: dict object['__name__'] }}](src/gui/pages/job_hunter)

- [{{ no such element: dict object['__name__'] }}](src/gui/pages/files)

- [{{ no such element: dict object['__name__'] }}](src/gui/pages/settings)

- [{{ no such element: dict object['__name__'] }}](src/gui/pages/contexts)

- [{{ no such element: dict object['__name__'] }}](src/gui/pages/environments)

</details>
<details>
  <summary>Create a Page</summary>
To create a Page module, add a new file under `src/gui/pages/` with the name of your module, for example `my_page.py`.


This file must contain a class definition that inherits from `QWidget`.

Note: If more than one class is declared in the file, then you must mark your page  class with the decorator `@set_module_type('Pages')`.

</details>

### Studios

Studio modules define editors for creating and modifying different types of content.

<details>
  <summary>Implementations</summary>

- [{{ no such element: dict object['__name__'] }}](src/gui/studios/h5_studio)

- [{{ no such element: dict object['__name__'] }}](src/gui/studios/text_studio)

- [{{ no such element: dict object['__name__'] }}](src/gui/studios/video_studio)

- [{{ no such element: dict object['__name__'] }}](src/gui/studios/image_studio)

</details>
<details>
  <summary>Create a Studio</summary>
To create a Studio module, add a new file under `src/gui/studios/` with the name of your module, for example `my_studio.py`.


This file must contain a class definition.

Note: If more than one class is declared in the file, then you must mark your studio  class with the decorator `@set_module_type('Studios')`.

</details>

### Widgets

Widgets are QWidget modules that can be used within pages or linked as a Member settings widget.

<details>
  <summary>Implementations</summary>

- [{{ no such element: dict object['__name__'] }}](src/gui/widgets/config_json_tree)

- [{{ no such element: dict object['__name__'] }}](src/gui/widgets/config_joined)

- [{{ no such element: dict object['__name__'] }}](src/gui/widgets/config_side_tabs)

- [{{ no such element: dict object['__name__'] }}](src/gui/widgets/config_ext_tree)

- [{{ no such element: dict object['__name__'] }}](src/gui/widgets/config_table)

- [{{ no such element: dict object['__name__'] }}](src/gui/widgets/query_settings)

- [{{ no such element: dict object['__name__'] }}](src/gui/widgets/code_settings)

- [{{ no such element: dict object['__name__'] }}](src/gui/widgets/config_json_db_tree)

- [{{ no such element: dict object['__name__'] }}](src/gui/widgets/config_tree)

- [{{ no such element: dict object['__name__'] }}](src/gui/widgets/population_view)

- [{{ no such element: dict object['__name__'] }}](src/gui/widgets/image_settings)

- [{{ no such element: dict object['__name__'] }}](src/gui/widgets/config_pages)

- [{{ no such element: dict object['__name__'] }}](src/gui/widgets/text_settings)

- [{{ no such element: dict object['__name__'] }}](src/gui/widgets/user_settings)

- [{{ no such element: dict object['__name__'] }}](src/gui/widgets/multi_preview)

- [{{ no such element: dict object['__name__'] }}](src/gui/widgets/input_settings)

- [{{ no such element: dict object['__name__'] }}](src/gui/widgets/probability_settings)

- [{{ no such element: dict object['__name__'] }}](src/gui/widgets/config_collection)

- [{{ no such element: dict object['__name__'] }}](src/gui/widgets/wait_settings)

- [{{ no such element: dict object['__name__'] }}](src/gui/widgets/overlay)

- [{{ no such element: dict object['__name__'] }}](src/gui/widgets/workflow_settings)

- [{{ no such element: dict object['__name__'] }}](src/gui/widgets/config_voice_tree)

- [{{ no such element: dict object['__name__'] }}](src/gui/widgets/config_tabs)

- [{{ no such element: dict object['__name__'] }}](src/gui/widgets/video_settings)

- [{{ no such element: dict object['__name__'] }}](src/gui/widgets/config_db_tree)

- [{{ no such element: dict object['__name__'] }}](src/gui/widgets/generate_widget)

- [{{ no such element: dict object['__name__'] }}](src/gui/widgets/file_tree)

- [{{ no such element: dict object['__name__'] }}](src/gui/widgets/message_collection)

- [{{ no such element: dict object['__name__'] }}](src/gui/widgets/chat_widget)

- [{{ no such element: dict object['__name__'] }}](src/gui/widgets/audio_settings)

- [{{ no such element: dict object['__name__'] }}](src/gui/widgets/prompt_settings)

- [{{ no such element: dict object['__name__'] }}](src/gui/widgets/contact_settings)

- [{{ no such element: dict object['__name__'] }}](src/gui/widgets/config_widget)

- [{{ no such element: dict object['__name__'] }}](src/gui/widgets/control_panel)

- [{{ no such element: dict object['__name__'] }}](src/gui/widgets/notif_settings)

- [{{ no such element: dict object['__name__'] }}](src/gui/widgets/fund_map)

- [{{ no such element: dict object['__name__'] }}](src/gui/widgets/fitness_chart)

- [{{ no such element: dict object['__name__'] }}](src/gui/widgets/config_fields)

- [{{ no such element: dict object['__name__'] }}](src/gui/widgets/claude_code_settings)

- [{{ no such element: dict object['__name__'] }}](src/gui/widgets/agent_settings)

- [{{ no such element: dict object['__name__'] }}](src/gui/widgets/media_settings)

- [{{ no such element: dict object['__name__'] }}](src/gui/widgets/computer_use_settings)

- [{{ no such element: dict object['__name__'] }}](src/gui/widgets/collections_widget)

</details>
<details>
  <summary>Create a Widget</summary>
To create a Widget module, add a new file under `src/gui/widgets/` with the name of your module, for example `my_widget.py`.


This file must contain a class definition that inherits from `QWidget`.

Note: If more than one class is declared in the file, then you must mark your widget  class with the decorator `@set_module_type('Widgets')`.

</details>

