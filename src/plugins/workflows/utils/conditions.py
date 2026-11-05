"""CEL condition evaluation utilities for workflow conditions.

Provides safe, sandboxed expression evaluation using the Common
Expression Language (CEL) for workflow input-level conditions and
Condition members.
"""

import celpy
import celpy.celtypes


def evaluate_condition(expression, context):
    """Compile and evaluate a CEL expression against a context dict.

    Parameters
    ----------
    expression : str
        A CEL expression string to evaluate.
    context : dict
        Context variables available to the expression.

    Returns
    -------
    bool
        The boolean result of the expression, or False on any error.
    """
    try:
        env = celpy.Environment()
        ast = env.compile(expression)
        prog = env.program(ast)
        cel_context = _dict_to_cel(context)
        result = prog.evaluate(cel_context)
        return bool(result)
    except Exception:
        return False


def build_condition_context(workflow):
    """Build the CEL evaluation context from workflow state.

    Parameters
    ----------
    workflow : Workflow
        The workflow instance whose members provide context.

    Returns
    -------
    dict
        A context dict with 'members' and 'params' keys suitable
        for CEL expression evaluation.
    """
    members_ctx = {}
    for m_id, member in workflow.members.items():
        members_ctx[m_id] = {
            'output': member.last_output or '',
            'name': member.config.get('info.name', ''),
            'type': member.config.get('_TYPE', ''),
        }

    return {
        'members': members_ctx,
        'params': dict(workflow.params) if workflow.params else {},
    }


def _dict_to_cel(d):
    """Recursively convert a Python dict to CEL-compatible types."""
    cel_dict = {}
    for k, v in d.items():
        if isinstance(v, dict):
            cel_dict[k] = celpy.json_to_cel(v)
        elif isinstance(v, str):
            cel_dict[k] = celpy.celtypes.StringType(v)
        elif isinstance(v, bool):
            cel_dict[k] = celpy.celtypes.BoolType(v)
        elif isinstance(v, int):
            cel_dict[k] = celpy.celtypes.IntType(v)
        elif isinstance(v, float):
            cel_dict[k] = celpy.celtypes.DoubleType(v)
        else:
            cel_dict[k] = celpy.json_to_cel(v)
    return cel_dict
