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
                'label_width': 110,
                'width': 350,
                'default': '',
            },
            {
                'text': 'Goal',
                'type': str,
                'label_width': 110,
                'width': 350,
                'default': '',
            },
            {
                'text': 'Backstory',
                'type': str,
                'label_width': 110,
                'width': 350,
                'num_lines': 2,
                'default': '',
            },
            {
                'text': 'Memory',
                'type': bool,
                'label_width': 110,
                'default': True,
            },
            {
                'text': 'Allow delegation',
                'type': bool,
                'label_width': 110,
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
            role=self.config.get('plugin.role', ''),
            goal=self.config.get('plugin.goal', ''),
            backstory=self.config.get('plugin.backstory', ''),
            memory=self.config.get('plugin.memory', True),
            allow_delegation=self.config.get('plugin.allow_delegation', True),
        )

        sys_msg = self.system_message()
        self.agent_task = CAITask(
            description=sys_msg,
            agent=self.agent_object,
        )

    def response_callback(self, message):
        self.workflow.main.new_sentence_signal.emit(self.member_id, message)
        self.workflow.save_message('assistant', message, self.member_id)
        pass

    #
    # def stream(self, *args, **kwargs):
    #     pass
