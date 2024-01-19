import asyncio
import importlib
import inspect
import json
from agentpilot.utils import sql, plugin
from agentpilot.context.member import Member
from agentpilot.context.messages import MessageHistory
from agentpilot.agent.base import Agent

loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)


# Helper function to load behavior module dynamically todo - move to utils
def load_behaviour_module(group_key):
    try:
        # Dynamically import the context behavior plugin based on group_key
        module_name = f"agentpilot.plugins.{group_key}.modules.context_plugin"
        behavior_module = importlib.import_module(module_name)
        return behavior_module
    except ImportError as e:
        # No module found for this group_key
        return None


def get_common_group_key(members):
    """Get all distinct group_keys and if there's only one, return it, otherwise return empty key"""
    group_keys = set(getattr(member.agent, 'group_key', '') for member in members.values())
    if len(group_keys) == 1:
        return next(iter(group_keys))
    return ''


class Context:
    def __init__(self, main, context_id=None, agent_id=None):
        self.main = main
        self.system = self.main.system

        self.loop = asyncio.get_event_loop()
        self.responding = False
        self.stop_requested = False

        self.id = context_id
        self.chat_name = ''
        self.chat_title = ''
        self.leaf_id = context_id
        self.context_path = {context_id: None}
        self.members = {}  # {member_id: Member()}
        self.member_configs = {}  # {member_id: config}

        self.behaviour = None

        self.config = {}

        self.message_history = MessageHistory(self)
        if agent_id is not None:
            context_id = sql.get_scalar("""
                SELECT context_id AS id 
                FROM contexts_members 
                WHERE agent_id = ? 
                  AND context_id IN (
                    SELECT context_id 
                    FROM contexts_members 
                    GROUP BY context_id 
                    HAVING COUNT(agent_id) = 1
                  ) AND del = 0
                ORDER BY context_id DESC 
                LIMIT 1""", (agent_id,))
            self.id = context_id

        if self.id is None:
            latest_context = sql.get_scalar('SELECT id FROM contexts WHERE parent_id IS NULL ORDER BY id DESC LIMIT 1')
            if latest_context:
                self.id = latest_context
            else:
                # # make new context
                sql.execute("INSERT INTO contexts (id) VALUES (NULL)")
                c_id = sql.get_scalar('SELECT id FROM contexts ORDER BY id DESC LIMIT 1')
                sql.execute("INSERT INTO contexts_members (context_id, agent_id, agent_config) VALUES (?, 0, '{}')", (c_id,))
                self.id = c_id

        self.load()

        if len(self.members) == 0:
            sql.execute("INSERT INTO contexts_members (context_id, agent_id, agent_config) VALUES (?, 0, '{}')", (self.id,))
            self.load_members()

    def load(self):
        self.load_members()
        self.message_history.load()
        self.chat_title = sql.get_scalar("SELECT summary FROM contexts WHERE id = ?", (self.id,))

    def load_members(self):
        # Fetch the participants associated with the context
        context_members = sql.get_results("""
            SELECT 
                cm.id AS member_id,
                cm.agent_id,
                cm.agent_config,
                cm.del
            FROM contexts_members cm
            WHERE cm.context_id = ?
            ORDER BY 
                cm.ordr""",
            params=(self.id,))

        self.members = {}
        self.member_configs = {}

        unique_members = set()
        for member_id, agent_id, agent_config, deleted in context_members:
            member_config = json.loads(agent_config)
            self.member_configs[member_id] = member_config
            if deleted == 1:
                continue

            # Load participant inputs
            member_inputs = sql.get_results("""
                SELECT 
                    input_member_id
                FROM contexts_members_inputs
                WHERE member_id = ?""", params=(member_id,), return_type='list')

            # Instantiate the agent
            use_plugin = member_config.get('general.use_plugin', None)
            kwargs = dict(agent_id=agent_id, member_id=member_id, context=self, wake=True)
            agent = plugin.get_plugin_agent_class(use_plugin, kwargs) or Agent(**kwargs)
            agent.load_agent()  # this can't be in the init to make it overridable
            member = Member(self, member_id, agent, member_inputs)
            self.members[member_id] = member
            unique_members.add(member_config.get('general.name', 'Assistant'))

        self.chat_name = ', '.join(unique_members)
        self.update_behaviour()

    def update_behaviour(self):
        """Update the behaviour of the context based on the common key"""
        common_group_key = get_common_group_key(self.members)
        behaviour_module = load_behaviour_module(common_group_key)
        if behaviour_module:
            for name, obj in inspect.getmembers(behaviour_module):
                if inspect.isclass(obj) and issubclass(obj, ContextBehaviour) and obj != ContextBehaviour:
                    self.behaviour = obj(self)
                    return
        self.behaviour = ContextBehaviour(self)

    def save_message(self, role, content, member_id=None, log_obj=None):
        if role == 'output':
            content = 'The code executed without any output' if content.strip() == '' else content

        if content == '':
            return None

        member = self.members.get(member_id, None)
        if member is not None and role == 'assistant':
            member.last_output = content

        return self.message_history.add(role, content, member_id=member_id, log_obj=log_obj)

    def deactivate_all_branches_with_msg(self, msg_id):  # todo - get these into a transaction
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


class ContextBehaviour:
    def __init__(self, context):
        self.context = context

    def start(self):
        for member in self.context.members.values():
            member.task = self.context.loop.create_task(self.run_member(member))

        self.context.responding = True
        try:
            # if True:  # sequential todo
            t = asyncio.gather(*[m.task for m in self.context.members.values()])
            self.context.loop.run_until_complete(t)
            # self.loop.run_until_complete(asyncio.gather(*[m.task for m in self.members.values()]))
        except asyncio.CancelledError:
            pass  # task was cancelled, so we ignore the exception
        except Exception as e:
            # self.main.finished_signal.emit()
            raise e

    def stop(self):
        self.context.stop_requested = True
        for member in self.context.members.values():
            if member.task is not None:
                member.task.cancel()

    async def run_member(self, member):
        try:
            if member.inputs:
                await asyncio.gather(*[self.context.members[m_id].task
                                       for m_id in member.inputs
                                       if m_id in self.context.members])

            member.agent.respond()  # respond()  #
        except asyncio.CancelledError:
            pass  # task was cancelled, so we ignore the exception

