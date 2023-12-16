import time
from openai import OpenAI
from agentpilot.agent.base import Agent


class OpenAIAssistantAgent(Agent):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.client = OpenAI()

    def wait_on_run(self, run, thread):
        while run.status == "queued" or run.status == "in_progress":
            run = self.client.beta.threads.runs.retrieve(
                thread_id=thread.id,
                run_id=run.id,
            )
            time.sleep(0.5)
        return run

    def stream(self, *args, **kwargs):
        thread = self.client.beta.threads.create()

        run = self.client.beta.threads.runs.create(
            thread_id=thread.id,
            assistant_id=assistant.id,
            instructions="Please address the user as Jane Doe. The user has a premium account."
        )

        self.wait_on_run(run, thread)

        # Retrieve all the messages added after our last user message
        messages = self.client.beta.threads.messages.list(
            thread_id=thread.id, order="asc", after=message.id
        )