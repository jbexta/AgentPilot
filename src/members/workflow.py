import asyncio
import json
from src.utils import sql  # , plugin
from src.members.base import Member
from src.utils.messages import MessageHistory
from src.members.agent import Agent

loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)


# Helper function to load behavior module dynamically todo - move to utils
def load_behaviour_module(group_key):
    from src.utils.plugin import all_plugins
    try:
        # Dynamically import the context behavior plugin based on group_key
        return all_plugins['Workflow'].get(group_key)
    except ImportError as e:
        # No module found for this group_key
        return None


def get_common_group_key(members):
    """Get all distinct group_keys and if there's only one, return it, otherwise return empty key"""
    group_keys = set(getattr(member, 'group_key', '') for member in members.values())
    if len(group_keys) == 1:
        return next(iter(group_keys))
    return ''


class Workflow(Member):
    def __init__(self, main, context_id=None, agent_id=None, inputs=None):
        super().__init__(main, workflow=None, m_id=0, inputs=inputs)
        # self.main = main
        self.system = self.main.system

        self.loop = asyncio.get_event_loop()
        self.responding = False
        self.stop_requested = False

        self.id = context_id
        self.chat_name = ''
        self.chat_title = ''
        self.leaf_id = context_id
        self.context_path = {context_id: None}
        self.members = {}
        self.member_configs = {}

        self.behaviour = None
        self.message_history = MessageHistory(self)

        self.config = {}

        # if agent_id is not None:  todo
        #     context_id = sql.get_scalar("""
        #         SELECT context_id AS id
        #         FROM contexts_members
        #         WHERE agent_id = ?
        #           AND context_id IN (
        #             SELECT context_id
        #             FROM contexts_members
        #             GROUP BY context_id
        #             HAVING COUNT(agent_id) = 1
        #           ) AND del = 0
        #         ORDER BY context_id DESC
        #         LIMIT 1""", (agent_id,))
        #     self.id = context_id

        if self.id is None:
            latest_context = sql.get_scalar('SELECT id FROM contexts WHERE parent_id IS NULL ORDER BY id DESC LIMIT 1')
            if latest_context:
                self.id = latest_context
            else:
                # # make new context
                config_json = json.dumps({
                    '_TYPE': 'workflow',
                    'members': [
                        {'id': None, 'agent_id': 0, 'loc_x': 37, 'loc_y': 30, 'config': '{}', 'del': 0}
                    ],
                    'inputs': [],
                })
                sql.execute("INSERT INTO contexts (config) VALUES (?)", (config_json,))
                c_id = sql.get_scalar('SELECT id FROM contexts ORDER BY id DESC LIMIT 1')
                # sql.execute("INSERT INTO contexts_members (context_id, agent_id, agent_config) VALUES (?, 0, '{}')", (c_id,))
                self.id = c_id

        self.load()

        # if len(self.members) == 0:  # todo remove ?
        #     raise NotImplementedError('')
        # #     sql.execute("INSERT INTO contexts_members (context_id, agent_id, agent_config) VALUES (?, 0, '{}')", (self.id,))
        # #     self.load_members()

    def load(self):
        self.config = json.loads(sql.get_scalar("SELECT config FROM contexts WHERE id = ?", (self.id,)))
        self.load_members()
        self.message_history.load()
        self.chat_title = sql.get_scalar("SELECT summary FROM contexts WHERE id = ?", (self.id,))

    def load_members(self):
        from src.utils.plugin import get_plugin_agent_class
        # Get members and inputs from the loaded json config
        members_info = self.config.get('members', [])
        inputs_info = self.config.get('inputs', [])

        self.members = {}
        self.member_configs = {}

        for member_info in members_info:
            member_id = member_info['id']
            agent_id = member_info['agent_id']
            agent_config = member_info['config']
            deleted = member_info['del']

            member_config = json.loads(agent_config)
            self.member_configs[member_id] = member_config
            if deleted == 1:
                continue

            # Extract inputs associated with the member
            member_inputs = [
                input_info['input_member_id']
                for input_info in inputs_info
                if input_info['member_id'] == member_id
            ]

            # Instantiate the agent
            use_plugin = member_config.get('info.use_plugin', None)
            kwargs = dict(main=self.main, agent_id=agent_id, member_id=member_id, config=member_config, workflow=self, wake=True, inputs=member_inputs)
            agent_class = get_plugin_agent_class(use_plugin, kwargs)
            if agent_class is not None:
                agent = agent_class  # (**kwargs)
            else:
                agent = Agent(**kwargs)

            agent.load_agent()  # Load the agent (can't be in the __init__ to make it overridable)
            self.members[member_id] = agent

        # Determine the chat name based on active members
        active_members = [member for member in members_info if not member['del']]
        if len(active_members) == 1:
            self.chat_name = json.loads(active_members[0]['config']).get('info.name', 'Assistant')
        else:
            self.chat_name = f'{len(active_members)} members'

        self.update_behaviour()

        # return
        # context_members = sql.get_results("""
        #     SELECT
        #         cm.id AS member_id,
        #         cm.agent_id,
        #         cm.agent_config,
        #         cm.del
        #     FROM contexts_members cm
        #     WHERE cm.context_id = ?
        #     ORDER BY
        #         cm.loc_x, cm.loc_y""",
        #     params=(self.id,))
        #
        # self.members = {}
        # self.member_configs = {}
        #
        # # unique_members = set()
        # for member_id, agent_id, agent_config, deleted in context_members:
        #     member_config = json.loads(agent_config)
        #     self.member_configs[member_id] = member_config
        #     if deleted == 1:
        #         continue
        #
        #     # Load participant inputs
        #     member_inputs = sql.get_results("""
        #         SELECT
        #             input_member_id
        #         FROM contexts_members_inputs
        #         WHERE member_id = ?""", params=(member_id,), return_type='list')
        #
        #     # Instantiate the agent
        #     use_plugin = member_config.get('info.use_plugin', None)
        #     kwargs = dict(main=self.main, agent_id=agent_id, member_id=member_id, workflow=self, wake=True, inputs=member_inputs)
        #     agent = plugin.get_plugin_agent_class(use_plugin, kwargs) or Agent(**kwargs)
        #     agent.load_agent()  # this can't be in the init to make it overridable
        #     # member = Member(self, member_id, agent, member_inputs)
        #     self.members[member_id] = agent  # member
        #     # unique_members.add(member_config.get('general.name', 'Assistant'))
        #
        # active_members = {m for m in context_members if not m[3] == 1}
        # if len(active_members) == 1:
        #     self.chat_name = json.loads(active_members.pop()[2]).get('info.name', 'Assistant')
        # else:
        #     self.chat_name = f'{len(active_members)} members'
        # self.update_behaviour()

    def update_behaviour(self):
        """Update the behaviour of the context based on the common key"""
        common_group_key = get_common_group_key(self.members)
        behaviour_module = load_behaviour_module(common_group_key)
        self.behaviour = behaviour_module(self) if behaviour_module else WorkflowBehaviour(self)
        # if behaviour_module:
        #     for name, obj in inspect.getmembers(behaviour_module):
        #         if inspect.isclass(obj) and issubclass(obj, WorkflowBehaviour) and obj != WorkflowBehaviour:
        #             self.behaviour = obj(self)
        #             return
        # self.behaviour = WorkflowBehaviour(self)

    def run_member(self):
        """The entry response method for the member."""
        self.behaviour.start()

    def save_message(self, role, content, member_id=None, log_obj=None):
        """Saves a message to the database and returns the message_id"""
        if role == 'output':
            content = 'The code executed without any output' if content.strip() == '' else content

        if content == '':
            return None

        # Set last_output for members, so they can be used by other members
        member = self.members.get(member_id, None)
        if member is not None:  # and role == 'assistant':
            member.last_output = content

        return self.message_history.add(role, content, member_id=member_id, log_obj=log_obj)

    def deactivate_all_branches_with_msg(self, msg_id):
        print("CALLED deactivate_all_branches_with_msg: ", msg_id)
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

    def activate_branch_with_msg(self, msg_id):
        print("CALLED activate_branch_with_msg: ", msg_id)
        sql.execute("""
            UPDATE contexts
            SET active = 1
            WHERE id = (
                SELECT context_id
                FROM contexts_messages
                WHERE id = ?
            );""", (msg_id,))


class WorkflowBehaviour:
    # Execute in order of loc_x, and when all inputs are finished
    
    def __init__(self, workflow):
        self.workflow = workflow

    def start(self):
        for member in self.workflow.members.values():
            member.response_task = self.workflow.loop.create_task(self.run_member(member))

        self.workflow.responding = True
        try:
            t = asyncio.gather(*[m.response_task for m in self.workflow.members.values()])
            self.workflow.loop.run_until_complete(t)
        except asyncio.CancelledError:
            pass  # task was cancelled, so we ignore the exception
        except Exception as e:
            # self.main.finished_signal.emit()
            raise e

    def stop(self):
        self.workflow.stop_requested = True
        for member in self.workflow.members.values():
            if member.response_task is not None:
                member.response_task.cancel()

    async def run_member(self, member):
        try:
            # todo - throw exception for circular references
            if member.inputs:
                await asyncio.gather(*[self.workflow.members[m_id].response_task
                                       for m_id in member.inputs
                                       if m_id in self.workflow.members])

            await member.run_member()
        except asyncio.CancelledError:
            pass  # task was cancelled, so we ignore the exception

