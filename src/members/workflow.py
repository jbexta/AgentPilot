import asyncio
import json
from typing import Optional, Dict, List, Any

# from pydantic import TypeAdapter
from typing_extensions import override

from src.members import Member
from src.system import manager

from src.utils import sql
# from src.utils.config import WorkflowConfig, ConfigDictWrapper
from src.utils.messages import MessageHistory
from src.utils.helpers import merge_config_into_workflow_config, get_member_name_from_config, set_module_type

loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)


@set_module_type(module_type='Members', settings='workflow_settings')
class Workflow(Member):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        from src.system import manager

        self._parent_workflow = kwargs.get('workflow', None)
        self.system = manager
        self.member_type: str = 'workflow'
        self.config: Dict[str, Any] = kwargs.get('config', {})
        # config_input = kwargs.get('config', {})
        # self.config: ConfigDictWrapper = ConfigDictWrapper.from_dict(config_input) if isinstance(config_input, dict) else ConfigDictWrapper(config_input)
        self.params: Dict[str, Any] = kwargs.get('params', {}) or {}  # optional, usually only used for tool / block workflows
        self.tool_uuid: Optional[str] = kwargs.get('tool_uuid', None)  # only used for tool workflows

        self.chat_page = kwargs.get('chat_page', None)
        # Load base workflow
        if not self._parent_workflow:
            self._context_id: Optional[int] = kwargs.get('context_id', None)
            self._chat_name: str = ''
            self._chat_title: str = kwargs.get('chat_title', '')
            self._leaf_id: int = self.context_id
            self._message_history = MessageHistory(self)
            kind = kwargs.get('kind', 'CHAT')

            get_latest = kwargs.get('get_latest', False)
            if get_latest and self.context_id is not None:
                print("Warning: get_latest and context_id are both set, get_latest will be ignored.")  # todo warnings
            if get_latest and self.context_id is None:
                # Load latest context
                self.context_id = sql.get_scalar("SELECT id FROM contexts WHERE parent_id IS NULL AND kind = ? ORDER BY id DESC LIMIT 1",
                                                 (kind,))
            if self.context_id is not None:
                if self.config:
                    print("Warning: config is set, but will be ignored because an existing workflow is being loaded.")  # todo warnings
                config_str = sql.get_scalar("SELECT config FROM contexts WHERE id = ?", (self.context_id,)) or '{}'
                # self.config = ConfigDictWrapper.from_dict(json.loads(config_str))
                self.config = json.loads(config_str)

            else:
                # # Create new context
                kind_init_members = {'CHAT': 'agent'}
                if not self.config:
                    init_member_config = {'_TYPE': kind_init_members.get(kind, 'text_block')}
                    self.config = merge_config_into_workflow_config(init_member_config)
                sql.execute("INSERT INTO contexts (kind, config, name) VALUES (?, ?, ?)", (kind, json.dumps(self.config), self.chat_title))
                self.context_id = sql.get_scalar("SELECT id FROM contexts WHERE kind = ? ORDER BY id DESC LIMIT 1", (kind,))

        self.loop = asyncio.get_event_loop()
        self.responding = False
        self.stop_requested = False

        self.members: Dict[str, Member] = {}  # id: member
        self.boxes: List[set] = []

        self.autorun = True
        # from src.system.behaviors import DefaultBehavior
        self.behaviour = None

        self.load()
        self.receivable_function = self.behaviour.receive

    # class Inputs:
    #     def __init__(self, member):
    #         for k, v in member.config.get('params', {}).items():
    #             i = Input(
    #                 type='param',
    #                 description=''
    #             )
    #             setattr(self, k, i)
    #
    # # @property
    # # def INPUTS(self):
    # #     params = self.config.get('params', {})
    # #     return [
    # #         {
    # #             'type': 'MESSAGE',
    # #         }
    # #     ] + [
    # #         {
    # #             'type': 'PARAM',
    # #             'description': '',
    # #         }
    # #         for k, v in params.items()
    # #     ]
    # #
    # # @property
    # # def OUTPUTS(self):
    # #     return [
    # #         {
    # #             'type': 'MESSAGE',
    # #         }
    # #     ]
    #
    #
    # @property
    # def INPUTS(self):
    #     return {
    #         'MESSAGE': Any,
    #         'CONFIG': {
    #             'chat.sys_msg': str,
    #         },
    #         'PARAMS': {
    #             k: Any
    #             for k in self.config.get('params', {}).keys()
    #         }
    #     }
    #
    # @property
    # def OUTPUTS(self):
    #     return {  # Any  # {
    #         'OUTPUT': Any,
    #     }

    @property
    def context_id(self) -> int:
        return self.get_from_root('_context_id')

    @property
    def chat_name(self) -> str:
        return self.get_from_root('_chat_name')

    @property
    def chat_title(self) -> str:
        return self.get_from_root('_chat_title')

    @property
    def leaf_id(self) -> int:
        return self.get_from_root('_leaf_id')

    @property
    def message_history(self) -> MessageHistory:
        return self.get_from_root('_message_history')

    @context_id.setter
    def context_id(self, value):
        self._context_id = value

    @chat_name.setter
    def chat_name(self, value):
        self._chat_name = value

    @chat_title.setter
    def chat_title(self, value):
        self._chat_title = value

    @leaf_id.setter
    def leaf_id(self, value):
        self._leaf_id = value

    @message_history.setter
    def message_history(self, value):
        self._message_history = value

    def get_from_root(self, attr_name) -> Any:
        if hasattr(self, attr_name):
            return getattr(self, attr_name, None)
        return self._parent_workflow.get_from_root(attr_name)

    def load_config(self, json_config=None):
        config = {}
        if json_config is None:
            if self._parent_workflow:
                config = self._parent_workflow.members[self.member_id].config
            else:
                config = sql.get_scalar("SELECT config FROM contexts WHERE id = ?", (self.context_id,), load_json=True)
        else:
            if isinstance(json_config, str):
                config = json.loads(json_config)

        self.config = merge_config_into_workflow_config(config)

        # if json_config is None:
        #     if self._parent_workflow:
        #         member_config = self._parent_workflow.members[self.member_id].config
        #         self.config = member_config
        #     else:
        #         config_str = sql.get_scalar("SELECT config FROM contexts WHERE id = ?", (self.context_id,))
        #         self.config = json.loads(config_str) or {}
        # else:
        #     if isinstance(json_config, str):
        #         json_config = json.loads(json_config)
        #     self.config = json_config

    @override
    def load(self):
        # workflow_config = self.config.get('config', {})
        # self.autorun = workflow_config.get('autorun', True)
        workflow_options = self.config.get('options', {})
        self.autorun = workflow_options.get('autorun', True)
        self.load_members()

        if self._parent_workflow is None:
            # Load base workflow
            self.message_history.load()
            self.chat_title = sql.get_scalar("SELECT name FROM contexts WHERE id = ?", (self.context_id,))

    def load_members(self):
        from src.system import manager
        # Get members and inputs from the loaded json config
        members = self.config['members']
        # if self.config.get('_TYPE', 'agent') == 'workflow':
        #     members = self.config['members']
        # else:  # is a single entity, this allows the workflow config to contain an entity config for simplicity
        #     wf_config = merge_config_into_workflow_config(self.config)
        #     members = wf_config.get('members', [])
        inputs = self.config.get('inputs', [])

        last_member_id = None
        last_loc_x = -100
        current_box_member_ids = set()

        members = sorted(members, key=lambda x: x['loc_x'])

        self.members = {}  #!looper!#
        self.boxes = []
        iterable = iter(members)
        while len(members) > 0:
            try:
                member_dict = next(iterable)
            except StopIteration:  # todo temp make nicer
                iterable = iter(members)
                continue

            member_id = str(member_dict['id'])
            if self._parent_workflow:
                pass
            entity_id = member_dict.get('agent_id', None)
            member_config = member_dict.get('config', {})
            loc_x = member_dict.get('loc_x', 50)
            loc_y = member_dict.get('loc_y', 0)

            member_input_ids = [
                input_info['source_member_id']
                for input_info in inputs
                if input_info['target_member_id'] == member_id
                and not input_info['config'].get('looper', False)
            ]

            # Order based on the inputs
            if len(member_input_ids) > 0:
                if not all((inp_id in self.members) for inp_id in member_input_ids):
                    continue

            # Instantiate the member
            member_type = member_dict.get('config', {}).get('_TYPE', 'agent')
            kwargs = dict(main=self.main,
                          workflow=self,
                          member_id=member_id,
                          config=member_config,
                          agent_id=entity_id,
                          loc_x=loc_x,
                          loc_y=loc_y,
                          inputs=member_input_ids)

            member_class = manager.modules.get_module_class(
                module_type='Members',
                module_name=member_type,
            )
            if not member_class:
                print(f"Warning: Member module '{member_type}' not found.")  # todo clean
                members.remove(member_dict)
                iterable = iter(members)
                continue

            if member_type.upper() in manager.modules.plugins:  # todo standardise cases
                use_plugin = member_config.get('plugin_type', None)
            member = member_class(**kwargs)

            member.load()

            if member.receivable_function:
                if abs(loc_x - last_loc_x) < 10:  # 10px threshold
                    if last_member_id is not None:
                        current_box_member_ids |= {last_member_id}
                    current_box_member_ids |= {member_id}

                else:
                    if current_box_member_ids:
                        self.boxes.append(current_box_member_ids)
                        current_box_member_ids = set()

                last_loc_x = loc_x
                last_member_id = member_id

            self.members[member_id] = member
            members.remove(member_dict)
            iterable = iter(members)

        if current_box_member_ids:
            self.boxes.append(current_box_member_ids)

        del_boxes = []
        for box in self.boxes:
            for member_id in box:
                fnd = self.walk_inputs_recursive(member_id, box)
                if fnd:
                    del_boxes.append(box)
                    break
        for box in del_boxes:
            self.boxes.remove(box)

        counted_members = self.count_members()
        if counted_members == 1:
            all_members = self.get_members()  # excl_types=('user',))
            first_member = next((m for m in all_members if m.config.get('_TYPE', 'agent') != 'user'), None)
            if not first_member:
                first_member = next(iter(all_members))
            config = first_member.config
            self.chat_name = get_member_name_from_config(config)
        else:
            self.chat_name = f'{counted_members} members'

        self.update_behaviour()

    def walk_inputs_recursive(self, member_id: str, search_list: set) -> bool:  #!asyncrecdupe!#
        member = self.members[member_id]  #!params!#
        found = False
        for inp in member.inputs:
            # is_looper = self..inputs[inp].config.get('looper', False)
            if inp in search_list:
                return True
            found = found or self.walk_inputs_recursive(inp, search_list)
        return found

    def get_members(self, incl_types: Any = 'all', excl_types=None) -> List[Member]:
        if incl_types == 'all':  #!memberdiff!#
            incl_types = manager.modules.get_modules_in_folder('Members', fetch_keys=('name',))

        excl_types = excl_types or []
        excl_types = [e for e in excl_types]
        excl_types.append('node')
        incl_types = tuple(t for t in incl_types if t not in excl_types)
        matched_members = [m for m in self.members.values() if m.config.get('_TYPE', 'agent') in incl_types]
        if self._parent_workflow is not None and len(matched_members) > 1:  # todo !userbypass
            if matched_members[0].config.get('_TYPE', 'agent') == 'user':
                matched_members = matched_members[1:]
        return matched_members

    def count_members(self, incl_types='all', excl_initial_user=True) -> int:
        extra_user_count = max(len(self.get_members(incl_types=('user',))) - 1, 0)
        excl_types = ('user',) if excl_initial_user else ()
        matched_members = self.get_members(incl_types=incl_types, excl_types=excl_types)
        return len(matched_members) + (extra_user_count if excl_initial_user else 0)

    def next_expected_member(self) -> Optional[Member]:
        """Returns the next member where turn output is None"""
        next_member = next((member for member in self.get_members()
                     if member.turn_output is None),
                    None)
        return next_member

    def next_expected_is_last_member(self) -> bool:
        """Returns True if the next expected member is the last member"""
        only_one_empty = len([member for member in self.get_members() if member.turn_output is None]) == 1
        return only_one_empty  #!99!#  #!looper!#

    def get_member_async_group(self, member_id) -> Optional[List[str]]:
        for box in self.boxes:
            if member_id in box:
                return [b for b in box if self.last_output is None]
        return None  # [member_id]

    # def get_member_config(self, member_id) -> Dict[str, Any]:
    #     member = self.members.get(member_id)
    #     return member.config if member else {}

    def reset_last_outputs(self):
        """Reset the last_output and turn_output of all members."""
        for member in self.members.values():
            member.last_output = None
            member.turn_output = None
            if isinstance(member, Workflow):
                member.reset_last_outputs()

    def set_last_outputs(self, map_dict):  # {full_member_id: output}
        for k, v in map_dict.items():
            member = self.get_member_by_full_member_id(k)
            if member:
                member.last_output = v

    def set_turn_outputs(self, map_dict):  # {full_member_id: output}
        for k, v in map_dict.items():
            member = self.get_member_by_full_member_id(k)
            if member:
                member.turn_output = v

    def get_member_by_full_member_id(self, full_member_id: str) -> Optional[Member]:
        """Returns the member object based on the full member id (e.g. '1.2.3')"""
        full_split = full_member_id.split('.')
        workflow = self
        member = None
        for local_id in full_split:
            member = workflow.members.get(local_id)
            if member is None:
                return None
            workflow = member
        return member

    def save_message(
        self,
        role: str,
        content: str,
        member_id: str = None,  # '1',
        log_obj=None
    ):
        """Saves a message to the database and returns the message_id"""
        if role == 'output':
            content = 'The code executed without any output' if content.strip() == '' else content

        if content == '':
            return None

        return self.message_history.add(role, content, member_id=member_id, log_obj=log_obj)

    def deactivate_all_branches_with_msg(self, msg_id):
        sql.execute("""
            UPDATE contexts
            SET active = 0
            WHERE branch_msg_id = (
                SELECT branch_msg_id
                FROM contexts
                WHERE id = (
                    SELECT context_id
                    FROM contexts_messages
                    WHERE id = ?
                )
            );""", (msg_id,))

    # def get_active_states(self):  # todo temp helper
    #     return sql.get_results("""
    #         WITH RECURSIVE context_tree AS (
    #             -- Base case: start with the root context
    #             SELECT id, parent_id, active
    #             FROM contexts
    #             WHERE id = ?
    #
    #             UNION ALL
    #
    #             -- Recursive case: get all children
    #             SELECT c.id, c.parent_id, c.active
    #             FROM contexts c
    #             JOIN context_tree ct ON c.parent_id = ct.id
    #         )
    #         SELECT id, active
    #         FROM context_tree
    #         ORDER BY id;""", (self.context_id,), return_type='dict')

    def activate_branch_with_msg(self, msg_id):
        sql.execute("""
            UPDATE contexts
            SET active = 1
            WHERE id = (
                SELECT context_id
                FROM contexts_messages
                WHERE id = ?
            );""", (msg_id,))

    def get_common_group_key(self):
        """Get all distinct group_keys and if there's only one, return it, otherwise return empty key"""
        group_keys = set(getattr(member, 'group_key', '') for member in self.members.values())
        if len(group_keys) == 1:
            return next(iter(group_keys))
        return ''

    def update_behaviour(self):
        """Update the behaviour of the context based on the common key"""
        from src.system import manager
        from src.system.behaviors.default_behavior import DefaultBehavior
        common_group_key = self.get_common_group_key()
        behaviour = manager.modules.get_module_class(
            module_type='Behaviors',
            module_name=common_group_key,
            default=DefaultBehavior,
        )
        self.behaviour = behaviour(self)

    def get_final_message(self, filter_role='all'):
        """Returns the final output of the workflow"""
        # todo check
        matched_msgs = [m for m in self.message_history.get(base_member_id=self.full_member_id())
                        if m['role'] == filter_role or filter_role == 'all']
        return None if not matched_msgs else matched_msgs[-1]
