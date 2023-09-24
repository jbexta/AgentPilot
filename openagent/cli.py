from termcolor import colored

from agent.base import Agent
from utils import config
from utils.sql import check_database


class CLI:
    def __init__(self):
        self.agent = None

    def run(self):
        # Check if the database is available
        if not check_database():
            # If not, prompt the user to enter the database location
            database_location = input("Database not found. Please enter the database location: ")

            if not database_location:
                print("Database location not provided. Application will exit.")
                return

            # Set the database location in the agent
            config.set_value('system.db-path', database_location)

        tcolor = config.get_value('system.termcolor-assistant')
        self.agent = Agent()
        self.agent.context.print_history(12)
        while True:
            self.agent.context.wait_until_current_role('user', not_equals=True)
            user_input = input("\nUser: ")
            if user_input:
                for sentence in self.agent.send_and_receive(user_input, stream=True):
                    print(colored(sentence, tcolor), end='')
