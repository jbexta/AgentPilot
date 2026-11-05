# Plugins
An AgentPilot plugin is a collection of modules bundled together.

By organizing related modules into a single plugin, all modules related to a feature or integration are kept together, making development and maintenance easier.

The application automatically discovers and loads plugins from the `src/plugins` directory at startup. Each module inside a plugin is registered and made available in the app.

## Plugin Structure

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