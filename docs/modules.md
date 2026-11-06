# Modules
The codebase is highly modular and extensible, allowing anyone to extend or override almost any aspect of the app.

The following are different types of modules supported by the app, where they are used, how they interact, and how to create them.



## Core Modules:

### Controllers

_No description available._

<details>
  <summary>Implementations</summary>

- [HighlightersController](src/core/controllers/highlighters)

- [ControllersController](src/core/controllers/controllers)

- [WidgetsController](src/core/controllers/widgets)

- [DaemonsController](src/core/controllers/daemons)

- [FieldsController](src/core/controllers/fields)

- [ManagersController](src/core/controllers/managers)

- [GuiUtilsController](src/core/controllers/gui_utils)

- [ActionsController](src/core/controllers/actions)

- [UtilsController](src/core/controllers/utils)

- [ConnectorsController](src/core/controllers/connectors)

- [PagesController](src/core/controllers/pages)

- [AudioEffectsController](src/core/controllers/audio_effects)

- [BubblesController](src/core/controllers/bubbles)

- [WebStacksController](src/core/controllers/web_stacks)

- [TextOperationsController](src/core/controllers/text_operations)

- [BehaviorsController](src/core/controllers/behaviors)

- [ProvidersController](src/core/controllers/providers)

- [EnvironmentsController](src/core/controllers/environments)

- [ImageToolsController](src/core/controllers/image_tools)

- [ControllersController](src/core/controllers/finance_operations)

- [ImageOperationsController](src/core/controllers/image_operations)

- [MembersController](src/core/controllers/members)

- [ThreeDOperationsController](src/core/controllers/3d_operations)

- [VideoOperationsController](src/core/controllers/video_operations)

- [ImageEffectsController](src/core/controllers/image_effects)

- [ControllersController](src/core/controllers/finance_apis)

- [TelephoniesController](src/core/controllers/telephonies)

- [StudiosController](src/core/controllers/studios)

- [AudioOperationsController](src/core/controllers/audio_operations)

- [ControllersController](src/core/controllers/project_types)

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

- [PriceFile](src/core/connectors/h5)

- [MysqlConnector](src/core/connectors/mysql)

- [PostgresConnector](src/core/connectors/postgres)

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

- [ConfigManager](src/core/managers/config)

- [ModuleManager](src/core/managers/modules)

- [DaemonManager](src/core/managers/daemons)

- [ContactManager](src/core/managers/contacts)

- [ModelsManager](src/core/managers/models)

- [OpenFoodManager](src/core/managers/open_food)

- [SkillsManager](src/core/managers/skills)

- [VariableManager](src/core/managers/variables)

- [PlansManager](src/core/managers/plans)

- [BlockManager](src/core/managers/blocks)

- [ProjectManager](src/core/managers/projects)

- [TelephonyManager](src/core/managers/telephony)

- [APIManager](src/core/managers/apis)

- [VenvManager](src/core/managers/venvs)

- [AgentManager](src/core/managers/agents)

- [EnvironmentManager](src/core/managers/environments)

- [CompaniesHouseManager](src/core/managers/companies_house)

- [TaskManager](src/core/managers/tasks)

- [VoiceManager](src/core/managers/voices)

- [JobSearchManager](src/core/managers/job_search)

- [ProviderManager](src/core/managers/providers)

- [ToolManager](src/core/managers/tools)

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

- [InputSourceComboBox](src/gui/fields/input_source)

- [MemberTypeMenu](src/gui/fields/member_type_menu)

- [Text](src/gui/fields/text)

- [BaseCombo](src/gui/fields/combo)

- [Button](src/gui/fields/button)

- [List](src/gui/fields/list)

- [InputTargetComboBox](src/gui/fields/input_target)

- [MemberPopupButton](src/gui/fields/popup_button)

- [ProjectTypeMenu](src/gui/fields/project_type_menu)

- [ButtonToggle](src/gui/fields/button_toggle)

- [ModuleComboBox](src/gui/fields/module)

- [Image](src/gui/fields/image)

- [ConditionPopupButton](src/gui/fields/condition_popup_button)

- [FilePicker](src/gui/fields/file_picker)

- [MediaUpload](src/gui/fields/media_upload)

- [ColorPickerWidget](src/gui/fields/color_picker)

- [Integer](src/gui/fields/integer)

- [Float](src/gui/fields/float)

- [Boolean](src/gui/fields/boolean)

- [EntityField](src/gui/fields/entity)

- [FontComboBox](src/gui/fields/font)

- [ModelComboBox](src/gui/fields/model)

- [PresetMenu](src/gui/fields/preset_menu)

- [VenvComboBox](src/gui/fields/venv)

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

- [TextEditorWindow](src/gui/gui_utils/text_editor_window)

- [EditBar](src/gui/gui_utils/edit_bar)

- [TreeButtons](src/gui/gui_utils/tree_buttons)

- [TextEnhancerButton](src/gui/gui_utils/text_enhancer_button)

- [CustomMenu](src/gui/gui_utils/custom_menu)

- [MediaIconListWidget](src/gui/gui_utils/media_icon_list_widget)

- [LibraryDialog](src/gui/gui_utils/library_dialog)

- [TreeDialog](src/gui/gui_utils/tree_dialog)

- [IconButton](src/gui/gui_utils/icon_button)

- [ToggleIconButton](src/gui/gui_utils/toggle_icon_button)

- [FramelessResizeMixin](src/gui/gui_utils/frameless_resize_mixin)

- [HelpIcon](src/gui/gui_utils/help_icon)

- [BreadcrumbWidget](src/gui/gui_utils/breadcrumb_widget)

- [FilterWidget](src/gui/gui_utils/filter_widget)

- [BaseTreeWidget](src/gui/gui_utils/base_tree_widget)

- [AddRemoteDialog](src/gui/gui_utils/add_remote)

- [GitHubSignInDialog](src/gui/gui_utils/github_sign_in)

- [GitIdentityDialog](src/gui/gui_utils/git_identity)

- [DeployTargetDialog](src/gui/gui_utils/deploy_target)

- [GitHubPublishDialog](src/gui/gui_utils/github_publish)

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

- [XMLHighlighter](src/gui/highlighters/xml)

- [HTMLHighlighter](src/gui/highlighters/html)

- [PythonHighlighter](src/gui/highlighters/python)

- [CelHighlighter](src/gui/highlighters/cel)

- [JsonHighlighter](src/gui/highlighters/json)

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

- [Page_Module_Settings](src/gui/pages/modules)

- [Page_Display_Settings](src/gui/pages/display)

- [Page_Icons](src/gui/pages/icons)

- [Page_System_Settings](src/gui/pages/system)

- [Page_Tttt_Settings](src/gui/pages/tttt)

- [Page_Settings](src/gui/pages/settings)

- [Page_Tool_Settings](src/gui/pages/tools)

- [Page_Embroidery](src/gui/pages/embroidery)

- [Page_Models_Settings](src/gui/pages/models)

- [Page_Finance](src/gui/pages/finance)

- [Page_Skill_Settings](src/gui/pages/skills)

- [Page_Files](src/gui/pages/files)

- [Page_Slopify](src/gui/pages/slopify)

- [Page_Chat](src/gui/pages/chat)

- [Page_Projects](src/gui/pages/projects)

- [Page_CompanySearch](src/gui/pages/company_search)

- [Page_Plan_Settings](src/gui/pages/plans)

- [Page_Videos](src/gui/pages/videos)

- [Page_Tasks_Settings](src/gui/pages/tasks)

- [Page_Jobs](src/gui/pages/jobs)

- [Page_Entities](src/gui/pages/agents)

- [Page_CompaniesHouse_Settings](src/gui/pages/companies_house)

- [Page_Block_Settings](src/gui/pages/blocks)

- [Page_Contacts](src/gui/pages/contacts)

- [Page_Telephony_Settings](src/gui/pages/telephony)

- [Page_Environments_Settings](src/gui/pages/environments)

- [Page_ProductSearch](src/gui/pages/product_search)

- [Page_Contexts](src/gui/pages/contexts)

- [Page_Voice_Settings](src/gui/pages/voices)

- [Page_OpenFood_Settings](src/gui/pages/open_food)

- [Page_Claude_Settings](src/gui/pages/claude)

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

- [ConfigTable](src/gui/widgets/config_table)

- [ConfigVoiceTree](src/gui/widgets/config_voice_tree)

- [ConfigPages](src/gui/widgets/config_pages)

- [ConfigTree](src/gui/widgets/config_tree)

- [ConfigSideTabs](src/gui/widgets/config_side_tabs)

- [ConfigDBTree](src/gui/widgets/config_db_tree)

- [ConfigJsonTree](src/gui/widgets/config_json_tree)

- [ConfigWidget](src/gui/widgets/config_widget)

- [ConfigCollection](src/gui/widgets/config_collection)

- [ConfigExtTree](src/gui/widgets/config_ext_tree)

- [FilterBuilder](src/gui/widgets/filter_builder)

- [ConfigTabs](src/gui/widgets/config_tabs)

- [ConfigJsonDBTree](src/gui/widgets/config_json_db_tree)

- [ConfigJoined](src/gui/widgets/config_joined)

- [ConfigFields](src/gui/widgets/config_fields)

- [ComputerUseSettings](src/gui/widgets/computer_use_settings)

- [LiveAgentSettings](src/gui/widgets/live_agent_settings)

- [GitDiffSettings](src/gui/widgets/git_diff_settings)

- [RunWorkflowPopup](src/gui/widgets/workflow_popup)

- [GenerateWidget](src/gui/widgets/generate_widget)

- [InputSettings](src/gui/widgets/input_settings)

- [CodeSettings](src/gui/widgets/code_settings)

- [NotifSettings](src/gui/widgets/notif_settings)

- [VideoSettings](src/gui/widgets/video_settings)

- [CC_User_Settings](src/gui/widgets/cc_user_settings)

- [AudioSettings](src/gui/widgets/audio_settings)

- [ContactSettings](src/gui/widgets/contact_settings)

- [FileTreeVcs](src/gui/widgets/file_tree_vcs)

- [ChattableWorkflowWidget](src/gui/widgets/chat_widget)

- [FundMapWidget](src/gui/widgets/fund_map)

- [ImageSettings](src/gui/widgets/image_settings)

- [PromptSettings](src/gui/widgets/prompt_settings)

- [ProbabilitySettings](src/gui/widgets/probability_settings)

- [GitCheckpointSettings](src/gui/widgets/git_checkpoint_settings)

- [WaitSettings](src/gui/widgets/wait_settings)

- [SetVariableSettings](src/gui/widgets/set_variable_settings)

- [ClaudeContext](src/gui/widgets/claude_context)

- [WorkflowSettings](src/gui/widgets/workflow_settings)

- [TextSettings](src/gui/widgets/text_settings)

- [ClaudeCodeSettings](src/gui/widgets/claude_code_settings)

- [MultiPreview](src/gui/widgets/multi_preview)

- [AgentSettings](src/gui/widgets/agent_settings)

- [GitHubAccount](src/gui/widgets/github_account)

- [DeployPanel](src/gui/widgets/deploy_panel)

- [ComputerUseOverlay](src/gui/widgets/overlay)

- [MessageCollection](src/gui/widgets/message_collection)

- [UserSettings](src/gui/widgets/user_settings)

- [FileTree](src/gui/widgets/file_tree)

- [FileTreeDeploy](src/gui/widgets/file_tree_deploy)

- [VcsPanel](src/gui/widgets/vcs_panel)

- [MediaSettings](src/gui/widgets/media_settings)

- [QuerySettings](src/gui/widgets/query_settings)

</details>
<details>
  <summary>Create a Widget</summary>
To create a Widget module, add a new file under `src/gui/widgets/` with the name of your module, for example `my_widget.py`.


This file must contain a class definition that inherits from `QWidget`.

Note: If more than one class is declared in the file, then you must mark your widget  class with the decorator `@set_module_type('Widgets')`.

</details>

