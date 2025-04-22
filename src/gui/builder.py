import ast
import inspect
from textwrap import dedent

import astor
from src.utils.helpers import convert_to_safe_case

class_param_schemas = {
    'ConfigTabs': [],
    'ConfigPages': [
        {
            'text': 'Right to Left',
            'key': 'w_right_to_left',
            'type': bool,
            'default': False,
        },
        {
            'text': 'Bottom to Top',
            'key': 'w_bottom_to_top',
            'type': bool,
            'default': False,
        }
    ],
    'ConfigDBTree': [
        {
            'text': 'Table name',
            'key': 'w_table_name',
            'type': str,
            'stretch_x': True,
            'default': '',
        },
        {
            'text': 'Query',
            'key': 'w_query',
            'type': str,
            'label_position': 'top',
            'stretch_x': True,
            'num_lines': 3,
            'default': '',
        },
        {
            'text': 'Folder key',
            'key': 'w_folder_key',
            'type': str,
            'default': '',
        },
        {
            'text': 'Layout type',
            'key': 'w_layout_type',
            'type': ('Vertical', 'Horizontal',),
            'default': 'vertical',
        },
        {
            'text': 'Readonly',
            'key': 'w_readonly',
            'type': bool,
            'default': False,
        },
        {
            'text': 'Searchable',
            'key': 'w_searchable',
            'type': bool,
            'default': False,
        },
        {
            'text': 'Versionable',
            'key': 'w_versionable',
            'type': bool,
            'default': False,
        },
        {
            'text': 'Default item icon',
            'key': 'w_default_item_icon',
            'type': str,
            'default': '',
        },
        {
            'text': 'Items pinnable',
            'key': 'w_items_pinnable',
            'type': bool,
            'default': True,
        },
        {
            'text': 'Tree header hidden',
            'key': 'w_tree_header_hidden',
            'type': bool,
            'default': False,
        },
        {
            'text': 'Tree header resizable',
            'key': 'w_tree_header_resizable',
            'type': bool,
            'default': True,
        },
        {
            'text': 'Show tree buttons',
            'key': 'w_show_tree_buttons',
            'type': bool,
            'default': True,
        },
        # {
        #     'text': 'Add item options',
        #     'type': list,
        #     'default': [],
        # },
        # {
        #     'text': 'Delete item options',
        #     'type': list,
        #     'default': [],
        # },
    ],
    'ConfigFields': [
        {
            'text': 'Field alignment',
            'key': 'w_field_alignment',
            'type': ('Left', 'Center', 'Right',),
            'default': 'left',
        },
        {
            'text': 'Label width',
            'key': 'w_label_width',
            'type': int,
            'has_toggle': True,
            'default': 150,
        },
        {
            'text': 'Margin left',
            'key': 'w_margin_left',
            'type': int,
            'default': 0,
        },
        {
            'text': 'Add stretch to end',
            'key': 'w_add_stretch_to_end',
            'type': bool,
            'default': True,
        },
    ]
}

field_type_alias_map = {
    "Text": "str",
    "Integer": "int",
    "Float": "float",
    "Boolean": "bool",
    "ModelComboBox": "'ModelComboBox'",
    "EnvironmentComboBox": "'EnvironmentComboBox'",
    "RoleComboBox": "'RoleComboBox'",
    "ModuleComboBox": "'ModuleComboBox'",
    "ColorPickerWidget": "'ColorPickerWidget'",
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

field_option_schemas = {
    str: [
        {
            'text': 'Num lines',
            'key': 'f_num_lines',
            'type': int,
            'minimum': 1,
            'maximum': 999,
            'step': 1,
            'has_toggle': True,
            'default': None,
        },
        {
            'text': 'Text size',
            'key': 'f_text_size',
            'type': int,
            'minimum': 0,
            'maximum': 99,
            'step': 5,
            'has_toggle': True,
            'default': None,
        },
        {
            'text': 'Text alignment',
            'key': 'f_text_alignment',
            'type': ('Left', 'Center', 'Right',),
            'default': 'Left',
        },
        {
            'text': 'Highlighter',
            'key': 'f_highlighter',
            'type': ('None', 'XML', 'Python',),
            'default': 'None',
        },
        {
            'text': 'Monospaced',
            'key': 'f_monospaced',
            'type': bool,
            'default': False,
        },
        {
            'text': 'Transparent',
            'key': 'f_transparent',
            'type': bool,
            'default': False,
        },
        {
            'text': 'Placeholder text',
            'key': 'f_placeholder_text',
            'type': str,
            'default': None,
        },
    ],
    int: [
        {
            'text': 'Minimum',
            'key': 'f_minimum',
            'type': int,
            'minimum': -2147483647,
            'maximum': 2147483647,
            'step': 5,
            'default': 0,
        },
        {
            'text': 'Maximum',
            'key': 'f_maximum',
            'type': int,
            'minimum': -2147483647,
            'maximum': 2147483647,
            'step': 5,
            'default': 100,
        },
        {
            'text': 'Step',
            'key': 'f_step',
            'type': int,
            'minimum': -2147483647,
            'maximum': 2147483647,
            'step': 1,
            'default': 1,
        }
    ],
    float: [
        {
            'text': 'Minimum',
            'key': 'f_minimum',
            'type': float,
            'minimum': -3.402823466e+38,
            'maximum': 3.402823466e+38,
            'step': 0.1,
            'default': 0.0,
        },
        {
            'text': 'Maximum',
            'key': 'f_maximum',
            'type': float,
            'minimum': -3.402823466e+38,
            'maximum': 3.402823466e+38,
            'step': 0.1,
            'default': 1.0,
        },
        {
            'text': 'Step',
            'key': 'f_step',
            'type': float,
            'minimum': -3.402823466e+38,
            'maximum': 3.402823466e+38,
            'step': 0.1,
            'default': 0.1,
        }
    ],
}


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


def modify_class_base(module_id, class_path, new_superclass):
    class ClassModifier(ast.NodeTransformer):
        def __init__(self, target_path, new_superclass):
            self.target_path = target_path
            self.current_path = []
            self.new_superclass = new_superclass

        def visit_ClassDef(self, node):
            self.current_path.append(node.name)
            if self.current_path == self.target_path:
                new_bases = [ast.Name(id=self.new_superclass, ctx=ast.Load())]
                node.bases = new_bases

                if self.new_superclass == 'ConfigPages' or self.new_superclass == 'ConfigTabs':
                    for item in node.body:
                        if isinstance(item, ast.FunctionDef) and item.name == '__init__':
                            ensure_attribute(item, 'pages', {})
                            # comment_attributes(item, ['schema'])
                            break
                elif self.new_superclass == 'ConfigDBTree' or self.new_superclass == 'ConfigFields':
                    for item in node.body:
                        if isinstance(item, ast.FunctionDef) and item.name == '__init__':
                            ensure_attribute(item, 'schema', [])  # , reset_value=True)
                            # comment_attributes(item, ['pages'])
                            break

            self.generic_visit(node)
            self.current_path.pop()
            return node

    from src.system.base import manager
    module_config = manager.get_manager('modules').modules.get(module_id, {})
    source = module_config.get('data', None)
    if not source:
        return None

    tree = ast.parse(source)
    modifier = ClassModifier(class_path, new_superclass)
    modified_tree = modifier.visit(tree)
    modified_source = astor.to_source(modified_tree, source_generator_class=CustomSourceGenerator)  # astor.to_source(modified_tree)

    # Update the module data with the modified source
    module_config['data'] = modified_source
    manager.get_manager('modules').modules[module_id] = module_config

    return modified_source


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


def modify_class_add_page(module_id, class_path, new_page_name):
    class ClassModifier(ast.NodeTransformer):
        def __init__(self, target_path, new_page_name):
            self.target_path = target_path
            self.current_path = []
            self.new_page_name = new_page_name
            self.safe_page_name = convert_to_safe_case(new_page_name)

        def visit_ClassDef(self, node):
            self.current_path.append(node.name)
            if self.current_path == self.target_path:
                new_page = ast.parse(dedent(f"""
                    class Page_{self.safe_page_name}(ConfigWidget):
                        def __init__(self, parent):
                            super().__init__(parent)
                """))
                node.body.append(new_page.body[0])

                for item in node.body:
                    if isinstance(item, ast.FunctionDef) and item.name == '__init__':
                        self.modify_init(item)
                        break

            self.generic_visit(node)
            self.current_path.pop()
            return node

        def modify_init(self, init_node):
            for stmt in init_node.body:
                if not (isinstance(stmt, ast.Assign) and isinstance(stmt.targets[0], ast.Attribute) and stmt.targets[0].attr == 'pages'):
                    continue
                if not isinstance(stmt.value, ast.Dict):
                    continue

                # Add new page to existing dictionary  # args is  `parent=self`
                new_key = ast.Str(s=self.new_page_name)
                new_value = ast.Call(
                    func=ast.Attribute(value=ast.Name(id='self', ctx=ast.Load()), attr=f'Page_{self.safe_page_name}',
                                       ctx=ast.Load()),
                    args=[ast.Name(id='self', ctx=ast.Load())],
                    keywords=[]
                )
                stmt.value.keys.append(new_key)
                stmt.value.values.append(new_value)
                return

            # If we didn't find and modify an existing self.pages, create a new one
            new_pages = ast.parse(f"self.pages = {{{self.new_page_name!r}: self.{self.safe_page_name}(self)}}").body[0]

            init_node.body.append(new_pages)

    from src.system.base import manager
    module_config = manager.get_manager('modules').modules.get(module_id, {})
    source = module_config.get('data', None)
    if not source:
        return None

    tree = ast.parse(source)
    modifier = ClassModifier(class_path, new_page_name)
    modified_tree = modifier.visit(tree)
    modified_source = astor.to_source(modified_tree, source_generator_class=CustomSourceGenerator)

    # Update the module data with the modified source
    module_config['data'] = modified_source
    manager.get_manager('modules').modules[module_id] = module_config

    return modified_source


def modify_class_delete_page(module_id, class_path, page_name):
    class ClassModifier(ast.NodeTransformer):
        def __init__(self, target_path, page_name):
            self.target_path = target_path
            self.current_path = []
            self.page_name = page_name

        def visit_ClassDef(self, node):
            self.current_path.append(node.name)
            if self.current_path == self.target_path:
                class_name = None
                for item in node.body:
                    if isinstance(item, ast.FunctionDef) and item.name == '__init__':
                        class_name = self.modify_init(item)
                        break
                if class_name:
                    for item in node.body:
                        if isinstance(item, ast.ClassDef) and item.name == class_name:
                            node.body.remove(item)
                            break

            self.generic_visit(node)
            self.current_path.pop()
            return node

        def modify_init(self, init_node):
            for stmt in init_node.body:
                if not (isinstance(stmt, ast.Assign) and isinstance(stmt.targets[0], ast.Attribute) and stmt.targets[0].attr == 'pages'):
                    continue
                if not isinstance(stmt.value, ast.Dict):
                    continue

                for i, key in enumerate(stmt.value.keys):
                    if key.s == self.page_name:
                        class_name = stmt.value.values[i].func.attr
                        del stmt.value.keys[i]
                        del stmt.value.values[i]

                        return class_name

            return None

    from src.system.base import manager
    module_config = manager.get_manager('modules').modules.get(module_id, {})
    source = module_config.get('data', None)
    if not source:
        return None

    tree = ast.parse(source)
    modifier = ClassModifier(class_path, page_name)
    modified_tree = modifier.visit(tree)
    modified_source = astor.to_source(modified_tree, source_generator_class=CustomSourceGenerator)

    # Update the module data with the modified source
    module_config['data'] = modified_source
    manager.get_manager('modules').modules[module_id] = module_config

    return modified_source


def modify_class_add_field(module_id, class_path, field_name, field_type):
    class ClassModifier(ast.NodeTransformer):
        def __init__(self, target_path, field_name, field_type):
            self.target_path = target_path
            self.current_path = []
            self.field_name = field_name
            self.field_type = field_type

        def visit_ClassDef(self, node):
            self.current_path.append(node.name)
            if self.current_path == self.target_path:
                for item in node.body:
                    if isinstance(item, ast.FunctionDef) and item.name == '__init__':
                        self.modify_init(item)
                        break

            self.generic_visit(node)
            self.current_path.pop()
            return node

        def modify_init(self, init_node):
            type_from_alias = field_type_alias_map.get(self.field_type, self.field_type)
            new_entry = ast.parse(f"{{'text': {self.field_name!r}, 'type': {type_from_alias}}}")
            for stmt in init_node.body:
                if not (isinstance(stmt, ast.Assign) and isinstance(stmt.targets[0], ast.Attribute) and stmt.targets[0].attr == 'schema'):
                    continue
                if not isinstance(stmt.value, ast.List):
                    continue

                stmt.value.elts.append(new_entry.body[0].value)
                return

            # If we didn't find and modify an existing self.schema, create a new one
            new_schema = ast.parse(f"self.schema = [{new_entry.body[0].value}]").body[0]
            init_node.body.append(new_schema)

    from src.system.base import manager
    module_config = manager.get_manager('modules').modules.get(module_id, {})
    source = module_config.get('data', None)
    if not source:
        return None

    tree = ast.parse(source)
    modifier = ClassModifier(class_path, field_name, field_type)
    modified_tree = modifier.visit(tree)
    modified_source = astor.to_source(modified_tree, source_generator_class=CustomSourceGenerator)

    # Update the module data with the modified source
    module_config['data'] = modified_source
    manager.get_manager('modules').modules[module_id] = module_config

    return modified_source


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
