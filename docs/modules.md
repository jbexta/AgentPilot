# Modules
The codebase is highly modular and extensible, allowing anyone to extend or override almost any aspect of the app.

The following are different types of modules supported by the app, where they are used, how they interact, and how to create them.



## Core Modules:

### Controllers

_No description available._

<details>
  <summary>Implementations</summary>

- [ControllersController](src/core/controllers/controllers)

- [ActionsController](src/core/controllers/actions)

- [UtilsController](src/core/controllers/utils)

- [PagesController](src/core/controllers/pages)

- [DaemonsController](src/core/controllers/daemons)

- [GuiUtilsController](src/core/controllers/gui_utils)

- [HighlightersController](src/core/controllers/highlighters)

- [FieldsController](src/core/controllers/fields)

- [ManagersController](src/core/controllers/managers)

- [WidgetsController](src/core/controllers/widgets)

- [ConnectorsController](src/core/controllers/connectors)

- [MembersController](src/core/controllers/members)

- [AudioEffectsController](src/core/controllers/audio_effects)

- [ControllersController](src/core/controllers/finance_apis)

- [TelephoniesController](src/core/controllers/telephonies)

- [StudiosController](src/core/controllers/studios)

- [ImageEffectsController](src/core/controllers/image_effects)

- [BehaviorsController](src/core/controllers/behaviors)

- [ThreeDOperationsController](src/core/controllers/3d_operations)

- [ProvidersController](src/core/controllers/providers)

- [AudioOperationsController](src/core/controllers/audio_operations)

- [ImageToolsController](src/core/controllers/image_tools)

- [VideoOperationsController](src/core/controllers/video_operations)

- [BubblesController](src/core/controllers/bubbles)

- [EnvironmentsController](src/core/controllers/environments)

- [TextOperationsController](src/core/controllers/text_operations)

- [ImageOperationsController](src/core/controllers/image_operations)

- [ControllersController](src/core/controllers/project_types)

- [ControllersController](src/core/controllers/finance_operations)

- [WebStacksController](src/core/controllers/web_stacks)

</details>
<details>
  <summary>Create a Controller</summary>
To create a Controller module, add a new file under `src/core/controllers/` with the name of your module, for example `my_controller.py`.


This file must contain a class definition.

Note: If more than one class is declared in the file, then you must mark your controller  class with the decorator `@set_module_type('Controllers')`.

</details>

### Actions

Action modules represent discrete undo-able user actions. Each action captures the data needed to undo and redo itself, and is recorded to the app's undo history.

<details>
  <summary>Implementations</summary>

- [NavigateAction](src/core/actions/navigate)

- [SaveChatEntityAction](src/core/actions/save_chat_entity)

- [ConfigSaveAction](src/core/actions/config_save)

- [LayerStructureAction](src/core/actions/layer_structure)

- [LayerEditAction](src/core/actions/layer_edit)

</details>
<details>
  <summary>Create a Action</summary>
To create a Action module, add a new file under `src/core/actions/` with the name of your module, for example `my_action.py`.


This file must contain a class definition that inherits from `UndoableAction`.

Note: If more than one class is declared in the file, then you must mark your action  class with the decorator `@set_module_type('Actions')`.

</details>

### Connectors

Connector modules handle connections to external sources such as databases

<details>
  <summary>Implementations</summary>

- [SqliteConnector](src/core/connectors/sqlite)

- [PostgresConnector](src/core/connectors/postgres)

- [PriceFile](src/core/connectors/h5)

- [MysqlConnector](src/core/connectors/mysql)

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

- [TasksDaemon](src/core/daemons/tasks)

- [CompaniesHouseDaemon](src/core/daemons/companies_house)

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

- [DaemonManager](src/core/managers/daemons)

- [ConfigManager](src/core/managers/config)

- [ModuleManager](src/core/managers/modules)

- [AgentManager](src/core/managers/agents)

- [TelephonyManager](src/core/managers/telephony)

- [ToolManager](src/core/managers/tools)

- [VariableManager](src/core/managers/variables)

- [TaskManager](src/core/managers/tasks)

- [JobSearchManager](src/core/managers/job_search)

- [EnvironmentManager](src/core/managers/environments)

- [BlockManager](src/core/managers/blocks)

- [OpenFoodManager](src/core/managers/open_food)

- [ProjectManager](src/core/managers/projects)

- [VenvManager](src/core/managers/venvs)

- [ProviderManager](src/core/managers/providers)

- [CompaniesHouseManager](src/core/managers/companies_house)

- [APIManager](src/core/managers/apis)

- [ModelsManager](src/core/managers/models)

- [SkillsManager](src/core/managers/skills)

- [ContactManager](src/core/managers/contacts)

- [VoiceManager](src/core/managers/voices)

- [PlansManager](src/core/managers/plans)

</details>
<details>
  <summary>Create a Manager</summary>
To create a Manager module, add a new file under `src/core/managers/` with the name of your module, for example `my_manager.py`.


This file must contain a class definition that inherits from `BaseManager`.

Note: If more than one class is declared in the file, then you must mark your manager  class with the decorator `@set_module_type('Managers')`.

</details>

### Utils

Util modules are plain collections of functions and constants - unlike every other module type they contain no class

<details>
  <summary>Implementations</summary>

</details>
<details>
  <summary>Create a Util</summary>
To create a Util module, add a new file under `src/core/utils/` with the name of your module, for example `my_util.py`.


</details>



## GUI Modules:

### Fields

Fields are QWidget modules that represent a single data field, such as a text field, a number field, a checkbox, etc.

<details>
  <summary>Implementations</summary>

- [ModelComboBox](src/gui/fields/model)

- [FontComboBox](src/gui/fields/font)

- [ModuleComboBox](src/gui/fields/module)

- [PresetMenu](src/gui/fields/preset_menu)

- [ColorPickerWidget](src/gui/fields/color_picker)

- [FilePicker](src/gui/fields/file_picker)

- [Button](src/gui/fields/button)

- [ButtonToggle](src/gui/fields/button_toggle)

- [InputSourceComboBox](src/gui/fields/input_source)

- [MemberPopupButton](src/gui/fields/popup_button)

- [EntityField](src/gui/fields/entity)

- [Float](src/gui/fields/float)

- [Text](src/gui/fields/text)

- [BaseCombo](src/gui/fields/combo)

- [List](src/gui/fields/list)

- [VenvComboBox](src/gui/fields/venv)

- [InputTargetComboBox](src/gui/fields/input_target)

- [MemberTypeMenu](src/gui/fields/member_type_menu)

- [ProjectTypeMenu](src/gui/fields/project_type_menu)

- [Image](src/gui/fields/image)

- [Boolean](src/gui/fields/boolean)

- [MediaUpload](src/gui/fields/media_upload)

- [Integer](src/gui/fields/integer)

- [ConditionPopupButton](src/gui/fields/condition_popup_button)

</details>
<details>
  <summary>Create a Field</summary>
To create a Field module, add a new file under `src/gui/fields/` with the name of your module, for example `my_field.py`.


This file must contain a class definition that inherits from `QWidget`.

Note: If more than one class is declared in the file, then you must mark your field  class with the decorator `@set_module_type('Fields')`.

</details>

### Gui_utils

Gui util modules are small reusable Qt classes - buttons, menus, dialogs, delegates and layouts - used by widgets, fields and pages

<details>
  <summary>Implementations</summary>

- [HelpIcon](src/gui/gui_utils/help_icon)

- [TextEnhancerButton](src/gui/gui_utils/text_enhancer_button)

- [LibraryDialog](src/gui/gui_utils/library_dialog)

- [BaseTreeWidget](src/gui/gui_utils/base_tree_widget)

- [EditBar](src/gui/gui_utils/edit_bar)

- [TreeButtons](src/gui/gui_utils/tree_buttons)

- [TreeDialog](src/gui/gui_utils/tree_dialog)

- [IconButton](src/gui/gui_utils/icon_button)

- [CustomMenu](src/gui/gui_utils/custom_menu)

- [FilterWidget](src/gui/gui_utils/filter_widget)

- [TextEditorWindow](src/gui/gui_utils/text_editor_window)

- [ToggleIconButton](src/gui/gui_utils/toggle_icon_button)

- [FramelessResizeMixin](src/gui/gui_utils/frameless_resize_mixin)

- [BreadcrumbWidget](src/gui/gui_utils/breadcrumb_widget)

- [MediaIconListWidget](src/gui/gui_utils/media_icon_list_widget)

- [GitHubPublishDialog](src/gui/gui_utils/github_publish)

- [DeployTargetDialog](src/gui/gui_utils/deploy_target)

- [GitIdentityDialog](src/gui/gui_utils/git_identity)

- [AddRemoteDialog](src/gui/gui_utils/add_remote)

- [GitHubSignInDialog](src/gui/gui_utils/github_sign_in)

</details>
<details>
  <summary>Create a Gui_util</summary>
To create a Gui_util module, add a new file under `src/gui/gui_utils/` with the name of your module, for example `my_gui_util.py`.


This file must contain a class definition.

Note: If more than one class is declared in the file, then you must mark your gui_util  class with the decorator `@set_module_type('Gui_utils')`.

</details>

### Highlighters

Highlighter modules define the syntax highlighting of text areas

<details>
  <summary>Implementations</summary>

- [PythonHighlighter](src/gui/highlighters/python)

- [XMLHighlighter](src/gui/highlighters/xml)

- [JsonHighlighter](src/gui/highlighters/json)

- [CelHighlighter](src/gui/highlighters/cel)

- [HTMLHighlighter](src/gui/highlighters/html)

- [DiffHighlighter](src/gui/highlighters/diff)

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

- [Page_Daemons_Settings](src/gui/pages/daemons)

- [Page_Settings](src/gui/pages/settings)

- [Page_Tttt_Settings](src/gui/pages/tttt)

- [Page_System_Settings](src/gui/pages/system)

- [Page_Icons](src/gui/pages/icons)

- [Page_Module_Settings](src/gui/pages/modules)

- [Page_Display_Settings](src/gui/pages/display)

- [Page_ProductSearch](src/gui/pages/product_search)

- [Page_Projects](src/gui/pages/projects)

- [Page_Chat](src/gui/pages/chat)

- [Page_Embroidery](src/gui/pages/embroidery)

- [Page_Telephony_Settings](src/gui/pages/telephony)

- [Page_Jobs](src/gui/pages/jobs)

- [Page_Skill_Settings](src/gui/pages/skills)

- [Page_Entities](src/gui/pages/agents)

- [Page_OpenFood_Settings](src/gui/pages/open_food)

- [Page_Finance](src/gui/pages/finance)

- [Page_Tasks_Settings](src/gui/pages/tasks)

- [Page_Models_Settings](src/gui/pages/models)

- [Page_Videos](src/gui/pages/videos)

- [Page_CompaniesHouse_Settings](src/gui/pages/companies_house)

- [Page_Environments_Settings](src/gui/pages/environments)

- [Page_Claude_Settings](src/gui/pages/claude)

- [Page_Block_Settings](src/gui/pages/blocks)

- [Page_Slopify](src/gui/pages/slopify)

- [Page_Contexts](src/gui/pages/contexts)

- [Page_Contacts](src/gui/pages/contacts)

- [Page_Voice_Settings](src/gui/pages/voices)

- [Page_Tool_Settings](src/gui/pages/tools)

- [Page_Plan_Settings](src/gui/pages/plans)

- [Page_CompanySearch](src/gui/pages/company_search)

- [Page_Files](src/gui/pages/files)

</details>
<details>
  <summary>Create a Page</summary>
To create a Page module, add a new file under `src/gui/pages/` with the name of your module, for example `my_page.py`.


This file must contain a class definition that inherits from `QWidget`.

Note: If more than one class is declared in the file, then you must mark your page  class with the decorator `@set_module_type('Pages')`.

</details>

### Widgets

Widgets are QWidget modules that can be used within pages or linked as a Member settings widget.

<details>
  <summary>Implementations</summary>

- [ConfigDBTree](src/gui/widgets/config_db_tree)

- [ConfigJsonDBTree](src/gui/widgets/config_json_db_tree)

- [ConfigTable](src/gui/widgets/config_table)

- [ConfigWidget](src/gui/widgets/config_widget)

- [ConfigSideTabs](src/gui/widgets/config_side_tabs)

- [ConfigFields](src/gui/widgets/config_fields)

- [ConfigTabs](src/gui/widgets/config_tabs)

- [FilterBuilder](src/gui/widgets/filter_builder)

- [ConfigJsonTree](src/gui/widgets/config_json_tree)

- [ConfigPages](src/gui/widgets/config_pages)

- [ConfigTree](src/gui/widgets/config_tree)

- [ConfigCollection](src/gui/widgets/config_collection)

- [ConfigJoined](src/gui/widgets/config_joined)

- [ConfigExtTree](src/gui/widgets/config_ext_tree)

- [ConfigVoiceTree](src/gui/widgets/config_voice_tree)

- [WaitSettings](src/gui/widgets/wait_settings)

- [FileTreeDeploy](src/gui/widgets/file_tree_deploy)

- [PromptSettings](src/gui/widgets/prompt_settings)

- [GenerateWidget](src/gui/widgets/generate_widget)

- [ComputerUseOverlay](src/gui/widgets/overlay)

- [AgentSettings](src/gui/widgets/agent_settings)

- [ComputerUseSettings](src/gui/widgets/computer_use_settings)

- [ChattableWorkflowWidget](src/gui/widgets/chat_widget)

- [GitHubAccount](src/gui/widgets/github_account)

- [VcsPanel](src/gui/widgets/vcs_panel)

- [AudioSettings](src/gui/widgets/audio_settings)

- [InputSettings](src/gui/widgets/input_settings)

- [TextSettings](src/gui/widgets/text_settings)

- [FundMapWidget](src/gui/widgets/fund_map)

- [ClaudeContext](src/gui/widgets/claude_context)

- [UserSettings](src/gui/widgets/user_settings)

- [GitDiffSettings](src/gui/widgets/git_diff_settings)

- [MultiPreview](src/gui/widgets/multi_preview)

- [NotifSettings](src/gui/widgets/notif_settings)

- [VideoSettings](src/gui/widgets/video_settings)

- [FileTree](src/gui/widgets/file_tree)

- [DeployPanel](src/gui/widgets/deploy_panel)

- [MediaSettings](src/gui/widgets/media_settings)

- [LiveAgentSettings](src/gui/widgets/live_agent_settings)

- [GitCheckpointSettings](src/gui/widgets/git_checkpoint_settings)

- [WorkflowSettings](src/gui/widgets/workflow_settings)

- [CodeSettings](src/gui/widgets/code_settings)

- [ContactSettings](src/gui/widgets/contact_settings)

- [RunWorkflowPopup](src/gui/widgets/workflow_popup)

- [MessageCollection](src/gui/widgets/message_collection)

- [SetVariableSettings](src/gui/widgets/set_variable_settings)

- [QuerySettings](src/gui/widgets/query_settings)

- [ImageSettings](src/gui/widgets/image_settings)

- [CC_User_Settings](src/gui/widgets/cc_user_settings)

- [ProbabilitySettings](src/gui/widgets/probability_settings)

- [FileTreeVcs](src/gui/widgets/file_tree_vcs)

- [ClaudeCodeSettings](src/gui/widgets/claude_code_settings)

</details>
<details>
  <summary>Create a Widget</summary>
To create a Widget module, add a new file under `src/gui/widgets/` with the name of your module, for example `my_widget.py`.


This file must contain a class definition that inherits from `QWidget`.

Note: If more than one class is declared in the file, then you must mark your widget  class with the decorator `@set_module_type('Widgets')`.

</details>

