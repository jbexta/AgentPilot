from langchain.chat_models import ChatOpenAI
from agentpilot.agent.base import Agent
from agentpilot.plugins.crewai.src.agent import Agent as CAIAgent
from agentpilot.plugins.crewai.src.task import Task as CAITask


class CrewAI_Agent(Agent):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.group_key = 'crewai'  # Must match the directory name of the context plugin
        # If all agents in a group have the same key, the corresponding context plugin will be used
        self.agent_object = None
        self.agent_task = None
        self.extra_params = [
            {
                'text': 'Role',
                'type': str,
                'default': '',
                'width': 350,
            },
            {
                'text': 'Goal',
                'type': str,
                'default': '',
                'width': 350,
            },
            {
                'text': 'Backstory',
                'type': str,
                'default': '',
                'width': 350,
                'num_lines': 2,
            },
            {
                'text': 'Memory',
                'type': bool,
                'default': True,
            },
            {
                'text': 'Allow delegation',
                'type': bool,
                'default': True,
            },
        ]

    def load_agent(self):
        super().load_agent()

        llm = ChatOpenAI(
          temperature=0.7,
          model_name="gpt-3.5-turbo-1106",
        )  # todo link to model config

        self.agent_object = CAIAgent(
            response_callback=self.response_callback,  # Custom arg
            llm=llm,
            role=self.config.get('plugin.Role', ''),
            goal=self.config.get('plugin.Goal', ''),
            backstory=self.config.get('plugin.Backstory', ''),
            memory=self.config.get('plugin.Memory', True),
            allow_delegation=self.config.get('plugin.Allow delegation', True),
        )

        sys_msg = self.system_message()
        self.agent_task = CAITask(
            description=sys_msg,
            agent=self.agent_object,
        )

    def response_callback(self, message):
        self.context.main.new_sentence_signal.emit(self.member_id, message)
        self.context.save_message('assistant', message, self.member_id)
        pass

    #
    # def stream(self, *args, **kwargs):
    #     pass
