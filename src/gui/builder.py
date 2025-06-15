import ast
import inspect
from textwrap import dedent

import astor
from src.utils.helpers import convert_to_safe_case


field_type_alias_map = {
    "Text": "str",
    "Integer": "int",
    "Float": "float",
    "Boolean": "bool",
    # "ModelComboBox": "'ModelComboBox'",
    "EnvironmentComboBox": "'EnvironmentComboBox'",
    # "RoleComboBox": "'RoleComboBox'",
    # "ModuleComboBox": "'ModuleComboBox'",
    # "ColorPickerWidget": "'ColorPickerWidget'",
}

field_options_common_schema = [
    {
        'text': 'Text',
        'key': 'f_text',
        'type': str,
        'default': '',
    },
    {
        'text': 'Key',
        'key': 'f_key',
        'type': str,
        'has_toggle': True,
        'default': '',
    },
    {
        'text': 'Label position',
        'key': 'f_label_position',
        'type': ('Left', 'Top', 'None'),
        'default': 'Left',
    },
    {
        'text': 'Label width',
        'key': 'f_label_width',
        'type': int,
        'minimum': 0,
        'maximum': 999,
        'step': 5,
        'has_toggle': True,
        'default': None,
    },
    {
        'text': 'Width',
        'key': 'f_width',
        'type': int,
        'minimum': 0,
        'maximum': 999,
        'step': 5,
        'has_toggle': True,
        'default': None,
    },
    {
        'text': 'Has toggle',
        'key': 'f_has_toggle',
        'type': bool,
        'default': False,
    },
    {
        'text': 'tooltip',
        'key': 'f_tooltip',
        'type': str,
        'has_toggle': True,
        'default': None,
    },
    {
        'text': 'Stretch X',
        'key': 'f_stretch_x',
        'type': bool,
        'default': False,
    },
    {
        'text': 'Stretch Y',
        'key': 'f_stretch_y',
        'type': bool,
        'default': False,
    },
    {
        'text': 'Default',
        'key': 'f_default',
        'type': str,
        'default': None,
    },
]


class BaseClassModifier(ast.NodeTransformer):
    """
    A base NodeTransformer that navigates to a target class defined by a path.
    Subclasses must implement the `_modify_target_node` method to perform
    their specific code transformation on the found class node.
    """

    def __init__(self, target_path):
        self.target_path = target_path
        self.current_path = []

    def visit_ClassDef(self, node):
        self.current_path.append(node.name)
        if self.current_path == self.target_path:
            self._modify_target_node(node)
        self.generic_visit(node)
        self.current_path.pop()
        return node

    def _modify_target_node(self, node):
        raise NotImplementedError("Subclasses must implement this method.")


# --- Helper for applying any AST modification (unchanged) ---

def _apply_ast_modification(module_id, modifier_class):
    """
    Applies a given AST modifier to a module's source code.
    The modifier_class is instantiated with no arguments, assuming it's a closure
    that captures its required variables from its defining scope.
    """
    from src.system import manager
    module_config = manager.modules.get(module_id, {})
    source = module_config.get('data', None)
    if not source:
        return None

    tree = ast.parse(source)
    modifier = modifier_class()  # Instantiate with no arguments
    modified_tree = modifier.visit(tree)
    modified_source = astor.to_source(modified_tree, source_generator_class=CustomSourceGenerator)

    module_config['data'] = modified_source
    manager.load()

    return modified_source


# --- Public-Facing Functions with Nested Classes using Closures ---

def modify_class_base(module_id, class_path, new_superclass):
    class BaseChangeModifier(BaseClassModifier):
        def __init__(self):
            # `class_path` is accessed directly from the outer scope
            super().__init__(class_path)

        def _modify_target_node(self, node):
            # `new_superclass` is accessed directly from the outer scope
            node.bases = [ast.Name(id=new_superclass, ctx=ast.Load())]
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == '__init__':
                    if new_superclass in ('ConfigPages', 'ConfigTabs'):
                        ensure_attribute(item, 'pages', {})
                    elif new_superclass in ('ConfigDBTree', 'ConfigFields'):
                        ensure_attribute(item, 'schema', [])
                    break

    return _apply_ast_modification(module_id, BaseChangeModifier)


def modify_class_add_page(module_id, class_path, new_page_name):
    class AddPageModifier(BaseClassModifier):
        def __init__(self):
            super().__init__(class_path)
            # It can be useful to still set instance attributes for use in other methods
            self.safe_page_name = convert_to_safe_case(new_page_name)

        def _modify_target_node(self, node):
            new_page_class = ast.parse(dedent(f"""
                class Page_{self.safe_page_name}(ConfigWidget):
                    def __init__(self, parent):
                        super().__init__(parent)
            """)).body[0]
            node.body.append(new_page_class)

            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == '__init__':
                    self._modify_init(item)
                    return

        def _modify_init(self, init_node):
            # `new_page_name` is accessed directly from the outer scope
            for stmt in init_node.body:
                if (isinstance(stmt, ast.Assign) and isinstance(stmt.targets[0], ast.Attribute) and
                        stmt.targets[0].attr == 'pages' and isinstance(stmt.value, ast.Dict)):
                    new_key = ast.Str(s=new_page_name)
                    new_value = ast.Call(
                        func=ast.Attribute(value=ast.Name(id='self', ctx=ast.Load()),
                                           attr=f'Page_{self.safe_page_name}', ctx=ast.Load()),
                        args=[ast.Name(id='self', ctx=ast.Load())], keywords=[]
                    )
                    stmt.value.keys.append(new_key)
                    stmt.value.values.append(new_value)
                    return

            new_pages_assign = \
            ast.parse(f"self.pages = {{{new_page_name!r}: self.Page_{self.safe_page_name}(self)}}").body[0]
            init_node.body.append(new_pages_assign)

    return _apply_ast_modification(module_id, AddPageModifier)


def modify_class_delete_page(module_id, class_path, page_name):
    """
    Deletes a nested page class and its entry from the `self.pages` dictionary
    within a target class.
    """

    class DeletePageModifier(BaseClassModifier):
        def __init__(self):
            # Access `class_path` from the closure for the base class
            super().__init__(class_path)

        def _modify_target_node(self, node):
            """
            This method is called by the base class when the target class is found.
            It orchestrates the deletion of the page.
            """
            class_name_to_remove = None

            # 1. Find the __init__ method and remove the page from the `self.pages` dict.
            #    This helper method will return the name of the class associated with the page.
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == '__init__':
                    class_name_to_remove = self._remove_page_from_init(item)
                    break

            # 2. If we found and removed the page entry, now remove the class definition itself.
            if class_name_to_remove:
                # We use a list comprehension to create a new body without the target class.
                # This is a safer way to modify a list while iterating over it.
                node.body[:] = [
                    item for item in node.body
                    if not (isinstance(item, ast.ClassDef) and item.name == class_name_to_remove)
                ]

        def _remove_page_from_init(self, init_node):
            """
            Finds the `self.pages` dictionary in the __init__ method, removes the
            entry corresponding to `page_name`, and returns the class name that was removed.
            """
            # Access `page_name` from the closure
            for stmt in init_node.body:
                # Check if this statement is `self.pages = ...`
                if not (isinstance(stmt, ast.Assign) and
                        isinstance(stmt.targets[0], ast.Attribute) and
                        stmt.targets[0].attr == 'pages'):
                    continue

                # Check if the value is a dictionary
                if not isinstance(stmt.value, ast.Dict):
                    continue

                # Find the key-value pair to remove from the dictionary
                for i, key in enumerate(stmt.value.keys):
                    if isinstance(key, (ast.Constant, ast.Str)) and key.s == page_name:
                        # Get the name of the class from the value, e.g., self.Page_MyPage -> "Page_MyPage"
                        class_name = stmt.value.values[i].func.attr

                        # Delete the key and value from the dictionary AST nodes
                        del stmt.value.keys[i]
                        del stmt.value.values[i]

                        return class_name

            return None

    # Call the main helper to apply this modification
    return _apply_ast_modification(module_id, DeletePageModifier)


def modify_class_add_field(module_id, class_path, field_name, field_type):
    class AddFieldModifier(BaseClassModifier):
        def __init__(self):
            super().__init__(class_path)

        def _modify_target_node(self, node):
            # `field_name` and `field_type` are accessed from the closure
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == '__init__':
                    self._modify_init(item)
                    break

        def _modify_init(self, init_node):
            type_from_alias = field_type_alias_map.get(field_type, field_type)
            new_entry_dict = ast.parse(f"{{'text': {field_name!r}, 'type': {type_from_alias}}}").body[0].value

            for stmt in init_node.body:
                if (isinstance(stmt, ast.Assign) and isinstance(stmt.targets[0], ast.Attribute) and
                        stmt.targets[0].attr == 'schema' and isinstance(stmt.value, ast.List)):
                    stmt.value.elts.append(new_entry_dict)
                    return

            new_schema_assign = ast.parse(f"self.schema = []").body[0]
            new_schema_assign.value.elts.append(new_entry_dict)
            init_node.body.append(new_schema_assign)

    return _apply_ast_modification(module_id, AddFieldModifier)


# def modify_class_base(module_id, class_path, new_superclass):
#     class ClassModifier(ast.NodeTransformer):
#         def __init__(self, target_path, new_superclass):
#             self.target_path = target_path
#             self.current_path = []
#             self.new_superclass = new_superclass
#
#         def visit_ClassDef(self, node):
#             self.current_path.append(node.name)
#             if self.current_path == self.target_path:
#                 new_bases = [ast.Name(id=self.new_superclass, ctx=ast.Load())]
#                 node.bases = new_bases
#
#                 if self.new_superclass == 'ConfigPages' or self.new_superclass == 'ConfigTabs':
#                     for item in node.body:
#                         if isinstance(item, ast.FunctionDef) and item.name == '__init__':
#                             ensure_attribute(item, 'pages', {})
#                             # comment_attributes(item, ['schema'])
#                             break
#                 elif self.new_superclass == 'ConfigDBTree' or self.new_superclass == 'ConfigFields':
#                     for item in node.body:
#                         if isinstance(item, ast.FunctionDef) and item.name == '__init__':
#                             ensure_attribute(item, 'schema', [])  # , reset_value=True)
#                             # comment_attributes(item, ['pages'])
#                             break
#
#             self.generic_visit(node)
#             self.current_path.pop()
#             return node
#
#     from src.system import manager
#     module_config = manager.modules.get(module_id, {})
#     source = module_config.get('data', None)
#     if not source:
#         return None
#
#     tree = ast.parse(source)
#     modifier = ClassModifier(class_path, new_superclass)
#     modified_tree = modifier.visit(tree)
#     modified_source = astor.to_source(modified_tree, source_generator_class=CustomSourceGenerator)  # astor.to_source(modified_tree)
#
#     # Update the module data with the modified source
#     module_config['data'] = modified_source
#     # manager.modules[module_id] = module_config
#     manager.load()
#
#     return modified_source
#
#
# def modify_class_add_page(module_id, class_path, new_page_name):
#     class ClassModifier(ast.NodeTransformer):
#         def __init__(self, target_path, new_page_name):
#             self.target_path = target_path
#             self.current_path = []
#             self.new_page_name = new_page_name
#             self.safe_page_name = convert_to_safe_case(new_page_name)
#
#         def visit_ClassDef(self, node):
#             self.current_path.append(node.name)
#             if self.current_path == self.target_path:
#                 new_page = ast.parse(dedent(f"""
#                     class Page_{self.safe_page_name}(ConfigWidget):
#                         def __init__(self, parent):
#                             super().__init__(parent)
#                 """))
#                 node.body.append(new_page.body[0])
#
#                 for item in node.body:
#                     if isinstance(item, ast.FunctionDef) and item.name == '__init__':
#                         self.modify_init(item)
#                         break
#
#             self.generic_visit(node)
#             self.current_path.pop()
#             return node
#
#         def modify_init(self, init_node):
#             for stmt in init_node.body:
#                 if not (isinstance(stmt, ast.Assign) and isinstance(stmt.targets[0], ast.Attribute) and stmt.targets[0].attr == 'pages'):
#                     continue
#                 if not isinstance(stmt.value, ast.Dict):
#                     continue
#
#                 # Add new page to existing dictionary  # args is  `parent=self`
#                 new_key = ast.Str(s=self.new_page_name)
#                 new_value = ast.Call(
#                     func=ast.Attribute(value=ast.Name(id='self', ctx=ast.Load()), attr=f'Page_{self.safe_page_name}',
#                                        ctx=ast.Load()),
#                     args=[ast.Name(id='self', ctx=ast.Load())],
#                     keywords=[]
#                 )
#                 stmt.value.keys.append(new_key)
#                 stmt.value.values.append(new_value)
#                 return
#
#             # If we didn't find and modify an existing self.pages, create a new one
#             new_pages = ast.parse(f"self.pages = {{{self.new_page_name!r}: self.{self.safe_page_name}(self)}}").body[0]
#
#             init_node.body.append(new_pages)
#
#     from src.system import manager
#     module_config = manager.modules.get(module_id, {})
#     source = module_config.get('data', None)
#     if not source:
#         return None
#
#     tree = ast.parse(source)
#     modifier = ClassModifier(class_path, new_page_name)
#     modified_tree = modifier.visit(tree)
#     modified_source = astor.to_source(modified_tree, source_generator_class=CustomSourceGenerator)
#
#     # Update the module data with the modified source
#     module_config['data'] = modified_source
#     # manager.modules[module_id] = module_config
#     manager.load()
#
#     return modified_source
#
#
# def modify_class_delete_page(module_id, class_path, page_name):
#     class ClassModifier(ast.NodeTransformer):
#         def __init__(self, target_path, page_name):
#             self.target_path = target_path
#             self.current_path = []
#             self.page_name = page_name
#
#         def visit_ClassDef(self, node):
#             self.current_path.append(node.name)
#             if self.current_path == self.target_path:
#                 class_name = None
#                 for item in node.body:
#                     if isinstance(item, ast.FunctionDef) and item.name == '__init__':
#                         class_name = self.modify_init(item)
#                         break
#                 if class_name:
#                     for item in node.body:
#                         if isinstance(item, ast.ClassDef) and item.name == class_name:
#                             node.body.remove(item)
#                             break
#
#             self.generic_visit(node)
#             self.current_path.pop()
#             return node
#
#         def modify_init(self, init_node):
#             for stmt in init_node.body:
#                 if not (isinstance(stmt, ast.Assign) and isinstance(stmt.targets[0], ast.Attribute) and stmt.targets[0].attr == 'pages'):
#                     continue
#                 if not isinstance(stmt.value, ast.Dict):
#                     continue
#
#                 for i, key in enumerate(stmt.value.keys):
#                     if key.s == self.page_name:
#                         class_name = stmt.value.values[i].func.attr
#                         del stmt.value.keys[i]
#                         del stmt.value.values[i]
#
#                         return class_name
#
#             return None
#
#     from src.system import manager
#     module_config = manager.modules.get(module_id, {})
#     source = module_config.get('data', None)
#     if not source:
#         return None
#
#     tree = ast.parse(source)
#     modifier = ClassModifier(class_path, page_name)
#     modified_tree = modifier.visit(tree)
#     modified_source = astor.to_source(modified_tree, source_generator_class=CustomSourceGenerator)
#
#     # Update the module data with the modified source
#     module_config['data'] = modified_source
#     # manager.modules[module_id] = module_config
#     manager.load()
#
#     return modified_source

#
# def modify_class_add_field(module_id, class_path, field_name, field_type):
#     class ClassModifier(ast.NodeTransformer):
#         def __init__(self, target_path, field_name, field_type):
#             self.target_path = target_path
#             self.current_path = []
#             self.field_name = field_name
#             self.field_type = field_type
#
#         def visit_ClassDef(self, node):
#             self.current_path.append(node.name)
#             if self.current_path == self.target_path:
#                 for item in node.body:
#                     if isinstance(item, ast.FunctionDef) and item.name == '__init__':
#                         self.modify_init(item)
#                         break
#
#             self.generic_visit(node)
#             self.current_path.pop()
#             return node
#
#         def modify_init(self, init_node):
#             type_from_alias = field_type_alias_map.get(self.field_type, self.field_type)
#             new_entry = ast.parse(f"{{'text': {self.field_name!r}, 'type': {type_from_alias}}}")
#             for stmt in init_node.body:
#                 if not (isinstance(stmt, ast.Assign) and isinstance(stmt.targets[0], ast.Attribute) and stmt.targets[0].attr == 'schema'):
#                     continue
#                 if not isinstance(stmt.value, ast.List):
#                     continue
#
#                 stmt.value.elts.append(new_entry.body[0].value)
#                 return
#
#             # If we didn't find and modify an existing self.schema, create a new one
#             new_schema = ast.parse(f"self.schema = [{new_entry.body[0].value}]").body[0]
#             init_node.body.append(new_schema)
#
#     from src.system import manager
#     module_config = manager.modules.get(module_id, {})
#     source = module_config.get('data', None)
#     if not source:
#         return None
#
#     tree = ast.parse(source)
#     modifier = ClassModifier(class_path, field_name, field_type)
#     modified_tree = modifier.visit(tree)
#     modified_source = astor.to_source(modified_tree, source_generator_class=CustomSourceGenerator)
#
#     # Update the module data with the modified source
#     module_config['data'] = modified_source
#     # manager.modules[module_id] = module_config
#     manager.load()
#
#     return modified_source

def get_class_path(module, class_name):
    if not module:
        return None

    def find_class_name_recursive(obj, path):
        """Recursively find the class name and return the path to it."""
        if not inspect.isclass(obj):
            return None

        current_path = path + [obj.__name__]

        if obj.__name__ == class_name:
            obj_superclass = obj.__bases__[0] if obj.__bases__ else None
            return current_path, obj_superclass

        # Check for nested classes
        for name, member in inspect.getmembers(obj):
            if inspect.isclass(member) and member.__module__ == obj.__module__:
                result = find_class_name_recursive(member, current_path)
                if result:
                    return result
        return None

    # Search for the class in the loaded module
    for name, obj in inspect.getmembers(module):
        if inspect.isclass(obj) and obj.__module__ == module.__name__ and obj.__name__.lower().startswith('page_'):
            return find_class_name_recursive(obj, [])

    return None


class CustomSourceGenerator(astor.code_gen.SourceGenerator):
    def visit_Dict(self, node):
        if not node.keys:
            self.write('{}')
            return

        self.write('{')
        self.indentation += 1
        for key, value in zip(node.keys, node.values):
            self.fill()
            self.visit(key)
            self.write(': ')
            self.visit(value)
            self.write(',')
        self.indentation -= 1
        self.fill()
        self.write('}')

    def fill(self, text=""):
        self.write('\n' + self.indent_with * self.indentation + text)



def ensure_attribute(node, attr_name, attr_value, reset_value=False):
    rem_node = None
    for item in node.body:
        if isinstance(item, ast.Assign) and isinstance(item.targets[0], ast.Attribute) and item.targets[0].attr == attr_name:
            if not reset_value:
                return
            # node.body.remove(item)
            rem_node = item

    if rem_node:
        node.body.remove(rem_node)

    if isinstance(attr_value, dict):
        new_attr = ast.Assign(
            targets=[ast.Attribute(value=ast.Name(id='self', ctx=ast.Load()), attr=attr_name, ctx=ast.Store())],
            value=ast.Dict(keys=[ast.Str(s=k) for k in attr_value.keys()],
                           values=[ast.Str(s=str(v)) for v in attr_value.values()])
        )
    else:
        new_attr = ast.Assign(
            targets=[ast.Attribute(value=ast.Name(id='self', ctx=ast.Load()), attr=attr_name, ctx=ast.Store())],
            value=ast.Str(s=attr_value)
        )

    node.body.append(new_attr)


# def comment_attributes(node, attributes):
#     # import astor
#     new_body = []
#     for stmt in node.body:
#         if (isinstance(stmt, ast.Assign) and
#             isinstance(stmt.targets[0], ast.Attribute) and
#             stmt.targets[0].attr in attributes):
#             # Convert the assignment node back to source code.
#             # This may span multiple lines if the assignment is complex.
#             try:
#                 original_code = astor.to_source(stmt)
#             except Exception:
#                 original_code = ""  # Fallback in case conversion fails.
#             # Prepend each line with a comment symbol.
#             commented_lines = []
#             for line in original_code.splitlines():
#                 commented_lines.append("# " + line)
#             commented_code = "\n".join(commented_lines)
#             # Replace the assignment with an expression node containing a string literal.
#             # The CustomSourceGenerator can then handle outputting this literal as a comment.
#             comment_node = ast.Expr(value=ast.Str(s=commented_code))
#             new_body.append(comment_node)
#         else:
#             new_body.append(stmt)
#     node.body = new_body