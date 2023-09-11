# from openagent.utils.apis import tts
# from openagent.agent.base import Agent
# from openagent.utils import sql, apis


# Agent()
# Agent.edit_base_prompt()
# set settings
# get_voices
# Agent.set_voice

# if __name__ == '__main__':
#     engine = pyttsx3.init()
#     voices = engine.getProperty('voices')
#
#     agent = Agent()
#     agent.context.print_history()
#
#     main_thread = threading.Thread(target=agent.run)
#     main_thread.start()
#
#     while True:
#         agent.context.wait_until_current_role('user', not_equals=True)
#         user_input = input("User: ")
#         if user_input:
#             agent.save_message('user', user_input)


# def scan_commands(user_input):
#     if user_input.startswith('/sync_voices'):
#         tts.sync_all()
#