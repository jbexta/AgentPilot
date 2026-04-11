# Pages

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

## Nested Widget Classes

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
