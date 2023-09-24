import os
import sys
import threading
import pyttsx3
from termcolor import colored

from utils.apis import llm
from agent.base import Agent
from utils import sql, api, config

from cli import CLI
from gui import GUI

# d = llm.get_scalar("""
# You are completing a task by breaking it down into smaller actions that are explicitly expressed in the task.
# You have access to a wide range of actions, which you will search through and select after each thought message, unless the task is complete or can not complete.
#
# If all elements of the task have been completed then return the thought: "TASK COMPLETED"
# Conversely, if an element of the task can not be completed then return the thought: "CAN NOT COMPLETE"
# Otherwise, return a thought that is a description of the next action to take verbatim from the task Assistant.
#
# -- EXAMPLE OUTPUTS --
#
# Task: what is the x
# Thought: I need to get the x
# Action: Get the x
# Result: The x is [x_val]
# Thought: TASK COMPLETED
# END
#
#
# Task: what is x
# Thought: I need to get x
# Action: Get x
# Result: There is no x
# Thought: CAN NOT COMPLETE
# END
#
#
# Task: set x to y
# Thought: First, I need to get y
# Action: Get y
# Result: y is [y_val]
# Thought: Now, I need to set x to [y_val]
# Action: Set x to [y_val]
# Result: I have set x to [y_val]
# Thought: TASK COMPLETED
# END
#
#
# Task: do x and y
# Thought: First, I need to do x
# Action: Do x
# Result: I have done x
# Thought: Now, I need to do y
# Action: Do y
# Result: There was an error doing y
# Thought: CAN NOT COMPLETE
# END
#
#
# Task: send a x with the y of z
# Thought: First, I need to get the y of z
# Action Get the y of z
# Result: The y of z is [yz_val]
# Thought: Now, I need to send a x with [yz_val]
# Action: Send a x with [yz_val]
# Result: I have sent a x with [yz_val]
# Thought: TASK COMPLETED
# END
#
# Use the following conversation as context. The last user message (denoted with arrows ">> ... <<") is the message that triggered the task.
# The preceding assistant messages are provided to give you context for the last user message.
#
# CONVERSATION:
# user: `ok`
# assistant: `Ah, mon ami! Voilà, the task has been completed! I have conjured a delightful image of a dashing French mouse and a charming cat, ready to grace your wallpaper. Enjoy the whimsical scene!`
# >> user: `open bbc news youtube why combinator and reddit` <<
#
# Only return the next thought message. The Action and Result will be returned automatically.
#
# Task: open bbc news youtube and reddit
# Thought: First, I need to open bbc news, youtube, reddit
# Action: Open one or more website(/s)
# Result: Action complete. Bbc news, youtube, reddit are now open
# Thought: """)
# print(d)
# dd = 1

# d = llm.get_scalar("""Analyze the provided messages and actions/detections list and return a selection based on the last message. If none are valid then return "0".
#
# ACTIONS/DETECTIONS LIST:
# ID: Description
# ____________________
# 0: NO ACTION TO TAKE AND NOTHING DETECTED
# 1: ACTION TO TAKE BUT IS NOT IN THE BELOW ACTIONS
# 2: Add something to a list,
# 3: Get the current time,
# 4: Syncronise the available voices of the assistant,
# 5: Create a new list,
# 6: Click/Press A mouse button/On the screen,
# 7: Upscale/Enhance/Increase the Resolution/Quality of an Image/Picture/Photo/Drawing/Illustration,
# 8: Change the desktop background,
# 9: Do something like Generate/Create/Make/Draw/Design something like an Image/Picture/Photo/Drawing/Illustration etc
#
# Use the following messages to guide your analysis. The last message (denoted with arrows ">> ... <<") is the message you will use to determine the valid ID.
# The preceding assistant messages are provided to give you context for the last message, to determine whether an action/detection is valid.
# The higher the ID, the more probable that this is the correct action/detection, however this may not always be the case.
# To identify the primary action in the last request, focus on the main verb that indicates the current or next immediate action to take.
# Consider the tense of each verb to disregard actions that are completed or auxiliary.
#
# CONTEXT:
#
# >> request: `Now, I need to display the images.` <<
#
# TASK:
# Examine the messages in detail, applying logic and reasoning to ascertain the valid ID based on the latest message.
# If no actions or detections from the list are valid based on the last message, simply output "0".
#
# (Give an explanation of your decision after on the same line in parenthesis)
# ID: """)
# print(d)
# dd = 1
# (Give an explanation of your decision after on the same line in parenthesis)

# test_query = 'Set my wallpaper'
# test_embedding = llm.gen_embedding(test_query)
# all_embeddings = sql.get_results('SELECT original_text, embedding FROM embeddings', return_type='dict')
#
# for original_text, embedding in all_embeddings.items():
#     cs = semantic.cosine_similarity(test_embedding, [float(x) for x in embedding.split(',')])
#     print(original_text, cs)
# d = llm.get_scalar("""Analyze the provided requests and actions/detections list and if appropriate, return the ID of the most valid Action/Detection based on the last request. If none are valid then return "0".
# Note: To identify the primary action in the last request, focus on the main verb that indicates the current or next immediate action the speaker intends to take. Consider the verb's tense to prioritize actions that are planned or ongoing over those that are completed or auxiliary. Disregard actions that are merely described or implied without being the central focus of the current intention.
#
# ACTIONS/DETECTIONS LIST:
# ID: Description
# ____________________
# 0: NO ACTION TO TAKE AND NOTHING DETECTED
# 1: Change the desktop background,
# 2: Search and Play a specific song/album/artist/playlist/genre,
# 3: Do something like Generate/Create/Make/Draw/Design something like an Image/Picture/Photo/Drawing/Illustration etc,
# 4: Play music / resume playback where what to play is unspecified,
# 5: Switch music playback to smartphone for current music streaming
#
# Use the following requests to guide your analysis. The last request (denoted with arrows ">> ... <<") is the request you will use to determine the most valid ID.
# The preceding assistant messages are provided to give you context for the last request, to determine whether an action/detection is valid.
#
# CONTEXT:
# Task: `generate an image of a duck and set it as my background`
# Request: I need to generate an image of a duck.
# Result: "The image has been successfuly generated." (path = /tmp/tmpfy0f7m0o.png)
# >> Request: `I need to set the Image(`/tmp/tmpfy0f7m0o.png`) as the background.` <<
#
# TASK:
# Examine the requests in detail, applying logic and reasoning to ascertain the most valid ID based on the latest request.
# The verb expressing the main action in the sentence is crucial to making the right choice. If a secondary action or condition is described, it should not take precedence over the main action indicated in the last request. Focusing particularly on the tense to identify the valid - yet to be performed - action.
# If no actions or detections from the list are valid based on the last request, simply output "0".
#
# ID (with reasoning): """)
# print(d)
# d = llm.get_scalar("""
# You are completing a task by breaking it down into smaller actions that are explicitly expressed in the task.
# You have access to a wide range of actions, which you will search through and select after each request, unless the task is complete or can not complete.
#
# Only return the inferred Task request.
#
# -- EXAMPLE OUTPUTS --
#
# Task: what is the x
# Request: I need to get the x
# Action: Get the x
# Result: The x is [x_val]
# Request: TASK COMPLETED
# END
#
#
# Task: what is x
# Request: I need to get x
# Action: Get x
# Result: There is no x
# Request: CAN NOT COMPLETE
# END
#
#
# Task: do x and y
# Request: First, I need to do x
# Action: Do x
# Result: I have done x
# Request: Now, I need to do y
# Action: Do y
# Result: I have done y
# Request: TASK COMPLETED
# END
#
#
# Task: do x and y
# Request: First, I need to do x
# Action: Do x
# Result: I have done x
# Request: Now, I need to do y
# Action: Do y
# Result: There was an error doing y
# Request: CAN NOT COMPLETE
# END
#
#
# Task: set x to y
# Request: First, I need to get y
# Action: Get y
# Result: y is [y_val]
# Request: Now, I need to set x to [y_val]
# Action: Set x to [y_val]
# Result: I have set x to [y_val]
# Request: TASK COMPLETED
# END
#
#
# Task: send a x with the y of z
# Request: First, I need to get the y of z
# Action Get the y of z
# Result: The y of z is [yz_val]
# Request: Now, I need to send a x with [yz_val]
# Action: Send a x with [yz_val]
# Result: I have sent a x with [yz_val]
# Request: TASK COMPLETED
# END
#
# Use the following conversation as context. The last user message (denoted with arrows ">> ... <<") is the message that triggered the task.
# The preceding assistant messages are provided to give you context for the task request if necessary.
#
# CONVERSATION:
# assistant: `Ah, my dear interlocutor, I have conjured a delightful image of a cat and a dog frolicking together. Allow me to set it as your wallpaper, so you may bask in their adorable companionship every time you glance at your screen. The task has been completed. Enjoy!`
# >> user: `what time is it` <<
#
# Task: """)
# print(d)
# dd = 1


# Return the next request.
# If the task is completed then return "TASK COMPLETED.",
# If the task can not be completed then return "CAN NOT COMPLETE task.".
# Otherwise, return a request that is a description of the next action to take verbatim from the task request.

# test_popup = show_popup(message='Test popup',
#                         backcolor='#8fb7f7',
#                         tick_button_func=None,
#                         cross_button_func=lambda x: print(''))

# engine = pyttsx3.init()
# voices = engine.getProperty('voices')

# oai_api_exists = api.apis['openai']['priv_key'] != ''
# if not oai_api_exists:
#     environ_key = os.environ.get('OPENAI_API_KEY')
#     if environ_key:
#         print('Found OpenAI API key in environment variables')
#     user_input = input(f"Enter your OpenAI API key: {'(press enter to use env variable)' if environ_key else ''}")
#     if not user_input: user_input = environ_key
#
#     sql.execute(f"UPDATE apis SET priv_key = '{user_input.strip()}' WHERE name = 'OpenAI'")
#     api.apis['openai']['priv_key'] = user_input.strip()
#     oai.openai.api_key = api.apis['openai']['priv_key']

def main():
    mode = 'GUI'  # DEFAULT
    if '--cli' in sys.argv:
        mode = 'CLI'

    if mode == 'GUI':
        app = GUI()
    else:
        app = CLI()

    app.run()


if __name__ == '__main__':
    main()
