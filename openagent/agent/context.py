import threading
import time
import tiktoken
from termcolor import cprint

from utils import sql, config


class Context:
    def __init__(self, messages=None, behaviour=''):
        self.message_history = MessageHistory(messages)
        self.behaviour = behaviour
        self.recent_actions = []

    def system_message(self, msgs_in_system=None, extra_prompt='', msgs_in_system_len=0, format_func=None):
        date = time.strftime("%a, %b %d, %Y", time.localtime())
        time_ = time.strftime("%I:%M %p", time.localtime())
        timezone = time.strftime("%Z", time.localtime())
        location = "Sheffield, UK"
        metadata = """
Date: {date}
Time: {time}
Location: {location}
""".format(date=date, time=time_, timezone=timezone, location=location)

        if extra_prompt != '':
            extra_prompt = f"\n{extra_prompt.strip()}\n"
        if self.behaviour != '':
            self.behaviour = f"\n{self.behaviour.strip()}\n"

        message_str = ''
        if msgs_in_system:
            if msgs_in_system_len > 0:
                msgs_in_system = msgs_in_system[-msgs_in_system_len:]
            message_str = "\n".join(f"""{msg['role']}: \"{msg['content'].strip().strip('"')}\"""" for msg in msgs_in_system)
            message_str = f"\nCONVERSATION:\n\n{message_str}\nassistant: "

        # attachments_str = '\n\n'.join([f'{att.name}\n{att.text}' for att in self.attachments])
        # attachments_str = f"\n\n{attachments_str}\n\n" if attachments_str != '' else ''

        actions_str = '\n'.join([action_res for action_res in self.recent_actions])
        actions_str = f"\n\n'RECENT ACTIONS PERFORMED BY THE ASSISTANT:'\n\n{actions_str}\n\n" if actions_str != '' else ''

        full_prompt = metadata + self.behaviour + actions_str + extra_prompt + message_str
        return format_func(full_prompt) if format_func else full_prompt

    def wait_until_current_role(self, role, not_equals=False):
        while True:
            last_msg = self.message_history.last()
            if not last_msg: break

            if (last_msg['role'] == role and not not_equals) or (last_msg['role'] != role and not_equals):
                break
            else:
                time.sleep(0.05)
                continue

    def print_history(self, num_msgs=30):
        for msg in self.message_history.get()[-num_msgs:]:
            tcolor = config.get_value('system.termcolor-assistant') if msg['role'] == 'assistant' else None
            cprint(f"{msg['role'].upper()}: > {msg['content']}", tcolor)


class MessageHistory:
    def __init__(self, messages=None):
        self.context_id = None
        self._messages = [Message(m['id'], m['role'], m['content']) for m in (messages or [])]
        self.thread_lock = threading.Lock()

    def load_context_messages(self):
        if sql.get_scalar("SELECT COUNT(*) FROM contexts") == 0:
            sql.execute("INSERT INTO contexts (id) VALUES (NULL)")

        self.context_id = sql.get_scalar("SELECT MAX(id) FROM contexts")

        msg_log = sql.get_results("""
            SELECT * FROM ( SELECT id, role, msg FROM contexts_messages WHERE del = 0 ORDER BY id DESC LIMIT ? ) ORDER BY id
        """, (config.get_value('context.max-messages'),))
        msgs = [Message(msg_id, role, content) for msg_id, role, content in msg_log]
        with self.thread_lock:
            self._messages = msgs

    def new_context(self):
        sql.execute("INSERT INTO contexts (id) VALUES (NULL)")
        self.load_context_messages()

    def add(self, role, content):
        with self.thread_lock:
            if len(self._messages) > 0:
                max_id = max([msg.id for msg in self._messages])
            else:
                max_id = sql.get_scalar("SELECT COALESCE(MAX(id), 0) FROM contexts_messages")
            new_msg = Message(max_id + 1, role, content)

            same_role = self.last_role() == new_msg.role
            if same_role:
                if self.context_id is not None:
                    sql.execute("UPDATE contexts_messages SET msg = ? WHERE id = ?", (new_msg.content, self.last_id()))
                self._messages[-1].content += '\n\n' + new_msg.content
                return

            if self.context_id is not None:
                sql.execute("INSERT INTO contexts_messages (id, context_id, role, msg) VALUES (?, ?, ?, ?)", (new_msg.id, self.context_id, role, content))
                self._messages.append(new_msg)

            if len(self._messages) > config.get_value('context.max-messages'):
                self._messages.pop(0)

    def remove(self, n):
        with self.thread_lock:
            if len(self._messages) > 0:
                sql.execute(
                    'DELETE FROM contexts_messages WHERE id IN (SELECT id FROM contexts_messages ORDER BY id DESC LIMIT ?)',
                    (n,))
                self._messages = self._messages[:-n]

    def get(self, incl_ids=False, incl_roles=('user', 'assistant'), incl_assistant_prefix=False):
        assistant_msg_prefix = config.get_value('context.prefix-all-assistant-msgs')
        formatted_msgs = []
        for msg in self._messages:
            if msg.role not in incl_roles: continue

            if msg.role == 'assistant' and incl_assistant_prefix:
                msg_content = f"{assistant_msg_prefix} {msg.content}"
            else:
                msg_content = msg.content

            last_seen_role = formatted_msgs[-1]['role'] if len(formatted_msgs) > 0 else ''
            if msg.role == last_seen_role:
                formatted_msgs[-1]['content'] += '\n' + msg_content
            else:
                formatted_msgs.append({'id': msg.id, 'role': msg.role, 'content': msg_content})

        if incl_ids:
            return formatted_msgs
        else:
            return [{'role': msg['role'], 'content': msg['content']}
                    for msg in formatted_msgs]

    def get_conversation_str(self, msg_limit=4, prefix='CONVERSATION:\n\n'):
        msgs = self.get()[-msg_limit:]
        formatted_context = [f"{msg['role']}: `{msg['content'].strip()}`" for msg in msgs]
        formatted_context[-1] = f""">> {formatted_context[-1]} <<"""
        return prefix + '\n'.join(formatted_context)

    def get_react_str(self, msg_limit=8, prefix='THOUGHTS:\n\n'):
        msgs = self.get(incl_roles=('thought', 'observation'))[-msg_limit:]
        formatted_context = [f"{msg['role']}: `{msg['content'].strip()}`" for msg in msgs]
        return prefix + '\n'.join(formatted_context)

    def last(self, incl_roles=('user', 'assistant')):
        msgs = self.get(incl_roles=incl_roles, incl_ids=True)
        return msgs[-1] if len(msgs) > 0 else None

    def last_role(self):
        last = self.last()
        if last is None:
            return ''
        return last['role']

    def last_id(self):
        last = self.last()
        if last is None:
            return 0
        return last['id']


class Message:
    def __init__(self, msg_id, role, content, unix_time=None):
        self.id = msg_id
        self.role = role
        self.content = content
        self.token_count = len(tiktoken.encoding_for_model("gpt-3.5-turbo").encode(content))
        self.unix_time = unix_time or int(time.time())
