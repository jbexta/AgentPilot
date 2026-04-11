# Plugins
An **AgentPilot plugin** is a collection of modules bundled together and placed in the `src/plugins` directory.

By organizing related modules into a single plugin, all modules related to a feature or integration are kept together, making development and maintenance easier.

The application automatically discovers and loads plugins from the `src/plugins` directory at startup. Each module inside a plugin is registered and made available in the app.

## Plugin Structure

To create a plugin:

1. **Create a directory for your plugin under `src/plugins`**
   For example, if your plugin is called `my_plugin`, create the directory `src/plugins/my_plugin` with the following structure:
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
            [any other type of module]/
                [my_other_module.py]
   ```

2. **Organize your modules by type, mirroring the core codebase structure**
   Each module type (e.g., managers, providers, widgets, etc.) should have its own folder inside your plugin directory.
   These module folders can optionally be grouped into `core` and `gui` folders like the main codebase. Only do this if the plugin has many different types of modules.
   Place your module files (Python files containing classes that inherit from the appropriate base class, such as `BaseManager`, `Provider`, etc.) in the corresponding folder.

3. **(Optional) Add extra source code**
   If your plugin needs additional code, you can add other files inside your plugin directory without needing them to be declared as modules.

4. **Ensure each folder has an `__init__.py` file**
   This makes sure Python recognizes it as a standard package.