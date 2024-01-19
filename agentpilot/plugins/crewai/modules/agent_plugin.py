from agentpilot.agent.base import Agent


class CrewAI_Agent(Agent):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # If all agents in a group have the same key, the corresponding context plugin will be used
        self.group_key = 'crewai'
        self.extra_params = [
            {
                'text': 'Executor',
                'type': ('Sequential',),
                'default': 'Sequential',
            },
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
        # We need to link to an orchestrator agent here if there is one, to get the appropriate stream object
        pass

    def stream(self, *args, **kwargs):
        pass
