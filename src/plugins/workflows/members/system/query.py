"""Query System Member Module.

Executes SQL queries against the application database within workflows.
Supports execute, get_scalar, and get_results methods with configurable
return types for result sets.
"""

from plugins.workflows.members import Member
from utils import sql
from utils.helpers import set_module_type


RETURN_TYPE_MAP = {
    'Rows': 'rows',
    'List': 'list',
    'Dict': 'dict',
    'Hdict': 'hdict',
    'Tuple': 'tuple',
}


@set_module_type(module_type='Members', settings='query_settings')
class Query(Member):
    default_role = 'block'
    default_avatar = ':/resources/icon-blocks.png'
    default_name = 'Query'
    workflow_insert_mode = 'single'
    OUTPUT = str

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.receivable_function = self.receive

    async def receive(self):
        try:
            query = await self.format_config_value('query')
            method = self.config.get('method', 'Get results')

            if method == 'Execute':
                lastrowid = sql.execute(query)
                result = str(lastrowid)
            elif method == 'Scalar':
                scalar = sql.get_scalar(query)
                result = str(scalar)
            else:
                rt_key = self.config.get('return_type', 'Rows')
                return_type = RETURN_TYPE_MAP.get(rt_key, 'rows')
                rows = sql.get_results(
                    query, return_type=return_type,
                )
                result = str(rows)

            self.workflow.save_message(
                'sys', result, self.full_member_id(),
            )
            yield self.default_role, result
        except Exception as e:
            error_msg = str(e)
            self.workflow.save_message(
                'error', error_msg, self.full_member_id(),
            )
            yield 'error', error_msg
