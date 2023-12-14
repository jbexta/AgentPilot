import json
import re
import time
import string
import asyncio
from queue import Queue
import agentpilot.agent.speech as speech
# from agentpilot.plugins.memgpt.modules.agent_plugin import MemGPT_AgentPlugin
from agentpilot.operations import task
from agentpilot.utils import sql, logs, helpers
# from agentpilot.plugins.openinterpreter.modules.agent_plugin import *
from agentpilot.utils.apis import llm


class Agent:
    def __init__(self, agent_id=0, member_id=None, context=None, wake=False):
        self.context = context
        self.id = agent_id
        self.member_id = member_id
        self.name = ''
        self.desc = ''
        self.speaker = None
        self.blocks = {}
        self.active_plugin = None
        self.actions = None
        self.voice_data = None
        self.config = {}

        self.load_agent()

        self.intermediate_task_responses = Queue()
        self.speech_lock = asyncio.Lock()
        # self.listener = Listener(self.speaker.is_speaking, lambda response: self.save_message('assistant', response))

        self.logging_obj = None
        self.active_task = None

        self.new_bubble_callback = None

        self.latest_analysed_msg_id = 0

        self.bg_task = None
        if wake:
            self.bg_task = self.context.loop.create_task(self.wake())

    async def wake(self):
        bg_tasks = [
            self.speaker.download_voices(),
            self.speaker.speak_voices(),
            self.__intermediate_response_thread(),
            # self.loop.create_task(self.listener.listen())
        ]
        await asyncio.gather(*bg_tasks)
        # self.loop.run_until_complete(asyncio.gather(*bg_tasks))

    def __del__(self):
        if self.bg_task:
            self.bg_task.cancel()

    async def __intermediate_response_thread(self):
        while True:
            await asyncio.sleep(0.03)
            if self.speech_lock.locked():
                continue
            if self.intermediate_task_responses.empty():
                continue

            async with self.speech_lock:
                response_str = self.format_message(self.intermediate_task_responses.get())
                self.get_response(extra_prompt=response_str,
                                  check_for_tasks=False)

    def load_agent(self):
        if self.member_id:
            agent_data = sql.get_results("""
                SELECT
                    a.`desc`,
                    cm.`agent_config`,
                    s.`value` AS `global_config`
                FROM contexts_members cm
                LEFT JOIN agents a
                    ON a.id = cm.agent_id
                LEFT JOIN settings s ON s.field = 'global_config'
                WHERE cm.id = ? """, (self.member_id,))[0]
        elif self.id > 0:
            agent_data = sql.get_results("""
                SELECT
                    a.`desc`,
                    a.`config`,
                    s.`value` AS `global_config`
                FROM agents a
                LEFT JOIN settings s ON s.field = 'global_config'
                WHERE a.id = ? """, (self.id,))[0]
        else:
            agent_data = sql.get_results("""
                SELECT
                    '',
                    '{}',
                    s.`value` AS `global_config`
                FROM settings s
                WHERE s.field = 'global_config' """)[0]

        self.desc = agent_data[0]
        agent_config = json.loads(agent_data[1])
        global_config = json.loads(agent_data[2])

        self.name = agent_config.get('general.name', 'Assistant')
        self.config = {**global_config, **agent_config}

        self.active_plugin = self.config.get('general.use_plugin', None)
        # use_plugin =
        # if use_plugin:
        #     raise NotImplementedError()
        #     # if use_plugin == 'openinterpreter':
        #     #     self.active_plugin = OpenInterpreterAgent(self)
        #     # # elif use_plugin == 'memgpt':
        #     # #     self.active_plugin = MemGPT_AgentPlugin(self)
        #     # else:
        #     #     raise Exception(f'Plugin "{use_plugin}" not recognised')

        voice_id = self.config.get('voice.current_id', None)
        if voice_id is not None and str(voice_id) != '0':  # todo dirty
            self.voice_data = sql.get_results("""
                SELECT
                    v.id,
                    v.api_id,
                    v.uuid,
                    v.display_name,
                    v.known_from,
                    v.creator,
                    v.lang,
                    v.verb
                FROM voices v
                WHERE v.id = ? """, (voice_id,))[0]
        else:
            self.voice_data = None

        if self.speaker is not None: self.speaker.kill()
        self.speaker = speech.Stream_Speak(self)

        source_dir = self.config.get('actions.source_directory', '.')
        # self.actions = retrieval.ActionCollection(source_dir)

    def get_global_config(self):
        global_config = sql.get_scalar("""
            SELECT
                s.`value` AS `global_config`
            FROM settings s
            WHERE s.field = 'global_config' """)
        return json.loads(global_config)

    def system_message(self, msgs_in_system=None, response_instruction='', msgs_in_system_len=0):
        date = time.strftime("%a, %b %d, %Y", time.localtime())
        time_ = time.strftime("%I:%M %p", time.localtime())
        timezone = time.strftime("%Z", time.localtime())
        location = "Sheffield, UK"

        member_names = {k: v.get('general.name', 'Assistant') for k, v in self.context.member_configs.items()}
        member_placeholders = {k: v.get('group.output_context_placeholder', f'{member_names[k]}_{str(k)}')
                               for k, v in self.context.member_configs.items()}
        member_last_outputs = {member.m_id: member.last_output for k, member in self.context.members.items() if member.last_output != ''}
        member_blocks_dict = {member_placeholders[k]: v for k, v in member_last_outputs.items()}
        context_blocks_dict = {k: v for k, v in self.context.blocks.items()}

        blocks_dict = helpers.SafeDict({**member_blocks_dict, **context_blocks_dict})

        semi_formatted_sys_msg = string.Formatter().vformat(
            self.config.get('context.sys_msg', ''), (), blocks_dict,
        )

        agent_name = self.config.get('general.name', 'Assistant')
        if self.voice_data:
            char_name = re.sub(r'\([^)]*\)', '', self.voice_data[3]).strip()
            full_name = f"{char_name} from {self.voice_data[4]}" if self.voice_data[4] != '' else char_name
            verb = self.voice_data[7]
            if verb != '': verb = ' ' + verb
        else:
            char_name = agent_name
            full_name = agent_name
            verb = ''

        # ungrouped_actions = [fk for fk, fv in retrieval.all_category_files['_Uncategorised'].all_actions_data.items()]
        # action_groups = [k for k, v in retrieval.all_category_files.items() if not k.startswith('_')]
        all_actions = []  # ungrouped_actions + action_groups

        response_type = self.config.get('context.response_type', 'response')

        # Use the SafeDict class to format the text to gracefully allow non existent keys
        final_formatted_sys_msg = string.Formatter().vformat(
            semi_formatted_sys_msg, (), helpers.SafeDict(
                agent_name=agent_name,
                char_name=char_name,
                full_name=full_name,
                verb=verb,
                actions=', '.join(all_actions),
                response_instruction=response_instruction.strip(),
                date=date,
                time=time_,
                timezone=timezone,
                location=location,
                response_type=response_type
            )
        )

        message_str = ''
        if msgs_in_system:
            if msgs_in_system_len > 0:
                msgs_in_system = msgs_in_system[-msgs_in_system_len:]
            message_str = "\n".join(
                f"""{msg['role']}: \"{msg['content'].strip().strip('"')}\"""" for msg in msgs_in_system)
            message_str = f"\n\nCONVERSATION:\n\n{message_str}\nassistant: "
        if response_instruction != '':
            response_instruction = f"\n\n{response_instruction}\n\n"

        return final_formatted_sys_msg + response_instruction + message_str

    def format_message(self, message):
        dialogue_placeholders = {
            '[RES]': '[ITSOC] very briefly respond to the user in no more than [3S] ',
            '[INF]': '[ITSOC] very briefly inform the user in no more than [3S] ',
            '[ANS]': '[ITSOC] very briefly respond to the user considering the following information: ',
            '[Q]': '[ITSOC] Ask the user the following question: ',
            '[SAY]': '[ITSOC], say: ',
            '[MI]': '[ITSOC] Ask for the following information: ',
            '[ITSOC]': 'In the style of {char_name}{verb}, spoken like a genuine dialogue ',
            '[WOFA]': 'Without offering any further assistance, ',
            '[3S]': 'Three sentences',
        }
        for k, v in dialogue_placeholders.items():
            message = message.replace(k, v)

        if message != '':
            message = f"[INSTRUCTIONS-FOR-NEXT-RESPONSE]\n{message}\n[/INSTRUCTIONS-FOR-NEXT-RESPONSE]"
        return message

    # def send(self, message):
    #     new_msg = self.save_message('user', message)
    #     return new_msg
    #
    # def send_and_receive(self, message, stream=True):
    #     self.send(message)
    #     return self.receive(stream=stream)

    def receive(self, stream=False):
        return self.get_response_stream() if stream else self.get_response()

    def get_response(self, extra_prompt='', msgs_in_system=False, check_for_tasks=True):
        full_response = ''
        for sentence in self.get_response_stream(extra_prompt, msgs_in_system, check_for_tasks):
            full_response += sentence
        return full_response

    def get_response_stream(self, extra_prompt='', msgs_in_system=False, check_for_tasks=True, use_davinci=False):
        messages = self.context.message_history.get(llm_format=True, calling_member_id=self.member_id)
        last_role = self.context.message_history.last_role()

        check_for_tasks = self.config.get('actions.enable_actions', False) if check_for_tasks else False
        if check_for_tasks and last_role == 'user':
            replace_busy_action_on_new = self.config.get('actions.replace_busy_action_on_new')
            if self.active_task is None or replace_busy_action_on_new:

                new_task = task.Task(self)

                if new_task.status != task.TaskStatus.CANCELLED:
                    self.active_task = new_task

            if self.active_task:
                assistant_response = ''
                try:
                    task_finished, task_response = self.active_task.run()
                    if task_response != '':
                        extra_prompt = self.format_message(task_response)
                        for sentence in self.get_response_stream(extra_prompt=extra_prompt, check_for_tasks=False):
                            assistant_response += sentence
                            print(f'YIELDED: {sentence}  - FROM GetResponseStream')
                            yield sentence
                    else:
                        task_finished = True

                    if task_finished:
                        self.active_task = None

                except Exception as e:
                    logs.insert_log('TASK ERROR', str(e))
                    extra_prompt = self.format_message(
                        f'[SAY] "I failed the task" (Task = `{self.active_task.objective}`)')
                    for sentence in self.get_response_stream(extra_prompt=extra_prompt, check_for_tasks=False):
                        assistant_response += sentence
                        print(f'YIELDED: {sentence}  - FROM GetResponseStream')
                        yield sentence
                return assistant_response

        if extra_prompt != '' and len(messages) > 0:
            raise NotImplementedError()
            # messages[-1]['content'] += '\nsystem: ' + extra_prompt

        use_msgs_in_system = messages if msgs_in_system else None
        system_msg = self.system_message(msgs_in_system=use_msgs_in_system,
                                         response_instruction=extra_prompt)
        initial_prompt = ''
        model_name = self.config.get('context.model', 'gpt-3.5-turbo')
        model = (model_name, self.context.models[model_name])

        kwargs = dict(messages=messages, msgs_in_system=msgs_in_system, system_msg=system_msg, model=model)
        stream = self.stream(**kwargs)

        response = ''

        language, code = None, None
        for key, chunk in self.speaker.push_stream(stream):
            if key == 'CONFIRM':
                language, code = chunk
                break
            if key == 'PAUSE':
                break

            if key == 'assistant':
                response += chunk

            print(f'YIELDED: {str(key)}, {str(chunk)}  - FROM GetResponseStream')
            yield key, chunk

        logs.insert_log('PROMPT', f'{initial_prompt}\n\n--- RESPONSE ---\n\n{response}',
                        print_=False)

        if response != '':
            self.context.save_message('assistant', response, self.member_id, self.logging_obj)
        if code:
            self.context.save_message('code', self.combine_lang_and_code(language, code), self.member_id)

    def stream(self, messages, msgs_in_system=False, system_msg='', model=None):
        stream = llm.get_chat_response(messages if not msgs_in_system else [],
                                       system_msg,
                                       model_obj=model)
        self.logging_obj = stream.logging_obj
        for resp in stream:
            delta = resp.choices[0].get('delta', {})
            if not delta:
                continue
            text = delta.get('content', '')
            yield 'assistant', text

    def combine_lang_and_code(self, lang, code):
        return f'```{lang}\n{code}\n```'

    # def save_message(self, role, content):
    #     if role == 'user':
    #         if self.context.message_history.last_role() == 'user':
    #             # return None  # Don't allow double user messages
    #             pass  # Allow for now
    #     elif role == 'assistant':
    #         content = content.strip().strip('"').strip()  # hack to clean up the assistant's messages from FB and DevMode
    #     elif role == 'output':
    #         content = 'The code executed without any output' if content.strip() == '' else content
    #
    #     if content == '':
    #         return None
    #     return self.context.message_history.add(role, content)

    def __wait_until_finished_speaking(self):
        while True:
            if not self.speaker.speaking: break
            time.sleep(0.05)
