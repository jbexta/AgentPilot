from typing import Any, Dict, List, Tuple, get_origin, get_args, Union, Callable, Set

import inspect
import json
import logging
import re

from openai.types import FunctionDefinition


# Define type_map to translate Python type annotations to JSON Schema types
type_map = {
    "str": "string",
    "int": "integer",
    "float": "number",
    "bool": "boolean",
    "NoneType": "null",
    "list": "array",
    "dict": "object",
}


def _map_type(annotation) -> Dict[str, Any]:
    if annotation == inspect.Parameter.empty:
        return {"type": "string"}  # Default type if annotation is missing

    origin = get_origin(annotation)

    if origin in {list, List}:
        args = get_args(annotation)
        item_type = args[0] if args else str
        return {
            "type": "array",
            "items": _map_type(item_type)
        }
    elif origin in {dict, Dict}:
        return {"type": "object"}
    elif origin is Union:
        args = get_args(annotation)
        # If Union contains None, it is an optional parameter
        if type(None) in args:
            # If Union contains only one non-None type, it is a nullable parameter
            non_none_args = [arg for arg in args if arg is not type(None)]
            if len(non_none_args) == 1:
                schema = _map_type(non_none_args[0])
                if "type" in schema:
                    if isinstance(schema["type"], str):
                        schema["type"] = [schema["type"], "null"]
                    elif "null" not in schema["type"]:
                        schema["type"].append("null")
                else:
                    schema["type"] = ["null"]
                return schema
        # If Union contains multiple types, it is a oneOf parameter
        return {"oneOf": [_map_type(arg) for arg in args]}
    elif isinstance(annotation, type):
        schema_type = type_map.get(annotation.__name__, "string")
        return {"type": schema_type}

    return {"type": "string"}  # Fallback to "string" if type is unrecognized


def is_optional(annotation) -> bool:
    origin = get_origin(annotation)
    if origin is Union:
        args = get_args(annotation)
        return type(None) in args
    return False


def _serialize_function_definition(function_def: FunctionDefinition) -> Dict[str, Any]:
    """
    Serialize a FunctionDefinition object to a dictionary.

    :param function_def: The FunctionDefinition object to serialize.
    :return: A dictionary representation of the function definition with type 'function'.
    """
    return {
        "type": "function",
        "name": function_def.name,
        "description": function_def.description,
        "parameters": function_def.parameters
    }


class FunctionTool:
    """
    A tool that executes user-defined functions.
    """

    def __init__(self, functions: Set[Callable[..., Any]]):
        """
        Initialize FunctionTool with a set of functions.

        :param functions: A set of function objects.
        """
        self._functions = self._create_function_dict(functions)
        self._definitions = self._build_function_definitions(self._functions)

    def _create_function_dict(self, functions: Set[Callable[..., Any]]) -> Dict[str, Callable[..., Any]]:
        return {func.__name__: func for func in functions}

    def _build_function_definitions(self, functions: Dict[str, Any]) -> List[FunctionDefinition]:
        specs = []
        # Flexible regex to capture ':param <name>: <description>'
        param_pattern = re.compile(
            r"""
            ^\s*                                   # Optional leading whitespace
            :param                                 # Literal ':param'
            \s+                                    # At least one whitespace character
            (?P<name>[^:\s\(\)]+)                  # Parameter name (no spaces, colons, or parentheses)
            (?:\s*\(\s*(?P<type>[^)]+?)\s*\))?     # Optional type in parentheses, allowing internal spaces
            \s*:\s*                                # Colon ':' surrounded by optional whitespace
            (?P<description>.+)                    # Description (rest of the line)
            """,
            re.VERBOSE
        )

        for name, func in functions.items():
            sig = inspect.signature(func)
            params = sig.parameters
            docstring = inspect.getdoc(func) or ""
            description = docstring.split("\n")[0] if docstring else "No description"

            param_descs = {}
            for line in docstring.splitlines():
                line = line.strip()
                match = param_pattern.match(line)
                if match:
                    groups = match.groupdict()
                    param_name = groups.get('name')
                    param_desc = groups.get('description')
                    param_desc = param_desc.strip() if param_desc else "No description"
                    param_descs[param_name] = param_desc.strip()

            properties = {}
            required = []
            for param_name, param in params.items():
                param_type_info = _map_type(param.annotation)
                param_description = param_descs.get(param_name, "No description")

                properties[param_name] = {
                    **param_type_info,
                    "description": param_description
                }

                # If the parameter has no default value and is not optional, add it to the required list
                if param.default is inspect.Parameter.empty and not is_optional(param.annotation):
                    required.append(param_name)

            function_def = FunctionDefinition(
                name=name,
                description=description,
                parameters={
                    "type": "object",
                    "properties": properties,
                    "required": required
                },
            )
            specs.append(function_def)
        return specs

    def execute(self, function_name, arguments) -> Any:
        try:
            function = self._functions[function_name]
            parsed_arguments = json.loads(arguments)
            return function(**parsed_arguments) if parsed_arguments else function()
        except TypeError as e:
            logging.error(f"Error executing function '{function_name}': {e}")
            raise

    @property
    def definitions(self) -> List[Dict[str, Any]]:
        """
        Get the function definitions serialized as dictionaries.

        :return: A list of dictionary representations of the function definitions.
        """
        return [_serialize_function_definition(fd) for fd in self._definitions]
