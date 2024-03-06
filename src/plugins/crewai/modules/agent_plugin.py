from langchain.chat_models import ChatOpenAI
from src.agent.base import Agent
from crewai import Agent as CAIAgent
from crewai import Task as CAITask


class CrewAI_Agent(Agent):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.group_key = 'crewai'  # Must match the directory name of the context plugin
        # If all agents in a group have the same key, the corresponding context plugin will be used
        self.agent_object = None
        self.agent_task = None
        self.schema = [
            {
                'text': 'Role',
                'type': str,
                'label_width': 75,
                'width': 450,
                'default': '',
            },
            {
                'text': 'Goal',
                'type': str,
                'label_width': 75,
                'width': 450,
                'default': '',
            },
            {
                'text': 'Backstory',
                'type': str,
                'label_position': 'top',
                'label_width': 110,
                'width': 525,
                'num_lines': 4,
                'default': '',
            },
            {
                'text': 'Memory',
                'type': bool,
                'label_width': 75,
                'row_key': 'X',
                'default': True,
            },
            {
                'text': 'Allow delegation',
                'type': bool,
                'label_width': 100,
                # 'label_text_alignment': Qt.AlignRight,
                'row_key': 'X',
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
            step_callback=self.step_callback,
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
            expected_output='Full analysis report in bullet points',  # todo link
            agent=self.agent_object,
        )

    def step_callback(self, callback_object):
        pass

    # def response_callback(self, message):
    #     self.workflow.main.new_sentence_signal.emit(self.member_id, message)
    #     self.workflow.save_message('assistant', message, self.member_id)
    #     pass

    #
    # def stream(self, *args, **kwargs):
    #     pass
