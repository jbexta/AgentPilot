import time

import openai
from openai import OpenAI
from agentpilot.agent.base import Agent


class OpenAI_Assistant(Agent):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.client = OpenAI()
        self.external_params = {
            'code_interpreter': bool,
        }
        # self.extra_config = {
        #     'assistant.id'
        # }
        self.instance_config = {
            'assistant_id': None
        }
        # self.last_msg_id = ''

    def load_agent(self):
        super().load_agent()

        # ADD CHECK FOR CHANGED CONFIG, IF INVALID, RECREATE ASSISTANT

        name = self.config.get('general.name', 'Assistant')
        model_name = self.config.get('context.model', 'gpt-3.5-turbo')
        system_msg = self.system_message()

        assistant = openai.beta.assistants.create(
            name=name,
            instructions=system_msg,
            model=model_name,
        )

        self.update_instance_config('assistant_id', assistant.id)

    # DEAD ENDED WITH THIS, NOT POSSIBLE UNTIL 0.2.0 BREAKING RELEASE ? UNLESS CLEAN MERGE INTO config
    # WRONG IT IS POSSIBLE,
    # - IGNORE INSTANCE PARAMS WHEN update_agent_config IS CALLED
    # - IGNORE AGENT PARAMS WHEN update_instance_config IS CALLED
    # THINK WHAT HAPPENS WHEN YOU MODIFY THE PLUGIN CONFIG, IT SHOULD RELOAD THE AGENT
    def update_instance_config(self, field, value):
        self.instance_config['assistant_id'] = value
        self.save_config()

    def stream(self, *args, **kwargs):
        thread = self.client.beta.threads.create()
        # get msgs arg
        messages = kwargs.get('messages', [])
        for msg in messages:
            new_msg = self.client.beta.threads.messages.create(
                thread_id=thread.id,
                role=msg['role'],
                content=msg['content'],
            )
            self.last_msg_id = new_msg.id

        run = self.client.beta.threads.runs.create(
            thread_id=thread.id,
            assistant_id=self.assistant_id,
            instructions="Please address the user as Jane Doe. The user has a premium account."
        )

        run = self.wait_on_run(run, thread)

        # Retrieve all the messages added after our last user message
        messages = self.client.beta.threads.messages.list(
            thread_id=thread.id, order="asc", after=self.last_msg_id
        )
        for msg in messages:
            msg_content = msg.content[0].text.value
            yield 'assistant', msg_content

        kk = 0

    def wait_on_run(self, run, thread):
        while run.status == "queued" or run.status == "in_progress":
            run = self.client.beta.threads.runs.retrieve(
                thread_id=thread.id,
                run_id=run.id,
            )
            time.sleep(0.5)
        return run
