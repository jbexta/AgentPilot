gui.py > PageChat()
```python
    def send_message(self, message, role='user', clear_input=False):
        # check if threadpool is active
        if self.threadpool.activeThreadCount() > 0:
            return

        new_msg = self.context.save_message(role, message)
        self.last_member_msgs = {}

        if not new_msg:
            return

        self.main.send_button.update_icon(is_generating=True)

        if clear_input:
            self.main.message_text.clear()
            self.main.message_text.setFixedHeight(51)
            self.main.send_button.setFixedHeight(51)

        self.context.message_history.load_branches()  # todo - figure out a nicer way to load this only when needed
        self.refresh()
        QTimer.singleShot(5, self.after_send_message)

    def after_send_message(self):
        self.scroll_to_end()
        runnable = self.RespondingRunnable(self)
        self.threadpool.start(runnable)

    class RespondingRunnable(QRunnable):
        def __init__(self, parent):
            super().__init__()
            self.main = parent.main
            self.page_chat = parent
            self.context = self.page_chat.context

        def run(self):
            if os.environ.get('OPENAI_API_KEY', False):
                # Bubble exceptions for development
                self.context.start()
                self.main.finished_signal.emit()
            else:
                try:
                    self.context.start()
                    self.main.finished_signal.emit()
                except Exception as e:
                    self.main.error_occurred.emit(str(e))
```

context.base.py > Context() 
```python
    def start(self):
        for member in self.members.values():
            member.task = self.loop.create_task(self.run_member(member))

        self.responding = True
        try:
            # if True:  # sequential todo
            t = asyncio.gather(*[m.task for m in self.members.values()])
            self.loop.run_until_complete(t)
            # self.loop.run_until_complete(asyncio.gather(*[m.task for m in self.members.values()]))
        except asyncio.CancelledError:
            pass  # task was cancelled, so we ignore the exception
        except Exception as e:
            # self.main.finished_signal.emit()
            raise e

    async def run_member(self, member):
        try:
            if member.inputs:
                await asyncio.gather(*[self.members[m_id].task
                                       for m_id in member.inputs
                                       if m_id in self.members])

            await member.agent.respond()  # respond()  #
        except asyncio.CancelledError:
            pass  # task was cancelled, so we ignore the exception
```

agent.base.py > Agent() 
```python
    async def respond(self):
        """The entry response method for the agent. Called by the context class"""
        for key, chunk in self.receive(stream=True):
            if self.context.stop_requested:
                self.context.stop_requested = False
                break
            if key in ('assistant', 'message'):
                # todo - move this to agent class
                self.context.main.new_sentence_signal.emit(self.member_id, chunk)
                print('EMIT: ', self.member_id, chunk)
            else:
                break

    def receive(self, stream=False):
        return self.get_response_stream() if stream else self.get_response()

    def get_response_stream(self, extra_prompt='', msgs_in_system=False, check_for_tasks=True, use_davinci=False):
        """The response method for the agent. This is where Agent Pilot"""
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
        model = (model_name, self.context.main.system.models.to_dict()[model_name])  # todo make safer

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
        """The raw stream method for the agent. Override this for full"""
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
```

gui.py > PageChat()
```python
    def on_receive_finished(self):
        self.last_member_msgs = {}
        self.context.responding = False
        self.main.send_button.update_icon(is_generating=False)
        self.decoupled_scroll = False

        self.refresh()
        self.try_generate_title()
```