import asyncio
from agentpilot.context.base import WorkflowBehaviour


class Autogen_Workflow(WorkflowBehaviour):
    def __init__(self, context):
        self.context = context
        self.group_key = 'autogen'

    def start(self):
        for member in self.context.members.values():
            member.response_task = self.context.loop.create_task(self.run_member(member))

        self.context.responding = True
        try:
            t = asyncio.gather(*[m.response_task for m in self.context.members.values()])
            self.context.loop.run_until_complete(t)
        except asyncio.CancelledError:
            pass  # task was cancelled, so we ignore the exception
        except Exception as e:
            raise e

    def stop(self):
        self.context.stop_requested = True
        for member in self.context.members.values():
            if member.response_task is not None:
                member.response_task.cancel()

    async def run_member(self, member):
        try:
            if member.inputs:
                await asyncio.gather(*[self.context.members[m_id].response_task
                                       for m_id in member.inputs
                                       if m_id in self.context.members])

            await member.agent.respond()
        except asyncio.CancelledError:
            pass  # task was cancelled, so we ignore the exception
