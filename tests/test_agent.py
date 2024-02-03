import threading
import unittest
from openagent.agent.base import Agent
from unittest.mock import patch


agent = Agent()
agent.workflow.print_history()

main_thread = threading.Thread(target=agent.run)
main_thread.start()

# * = requires info gathering
# $ = requires knowledge retrieval
# % = requires smarter logic
# + = requires action logic
# @ = requires a web search
# - = time based

# LEVEL 1
time_examples = [
    "-In 15 minutes, play a relaxing playlist for my meditation session"
    "-in 10 minutes set a timer for 4 minutes"
    "-every morning I want you to tell me a philosophical quote"
    "-tell me a motivating quote just before I sleep every night"
    "-Share a new word and its meaning every day."
    "-Share a joke every afternoon to lighten up my day."
    "-read my reading list every morning"
    "-Help me learn a new language by teaching me a few phrases each day."
    "-Give me a historical fact every day."
    "-Every Saturday, recommend a DIY craft project I can do over the weekend"
    "-Teach me a new scientific concept every week."
    "-every day remind me to do exercise"
    "-read the news every morning"
    "-set a reminder on the first thursday of every month called event"
    "-there's an event that happens on the first friday of every month that i always forget about, can you let me know the day before so i dont forget"
    "$-what are the settings for alarm/reminder/task at ten thirty"
    "@-*set an alarm for n minutes before east enders starts"
]

info_examples = [
    "*Play tracy chapmans version of this song",
    "*Send me an sms with the name of this song",  # #
    "*who covers this song",
    "*What's the weather forecast for my location this weekend?",
    "*Add this website to my reading list",
    "*send an sms of a summary of this website in a message to darren",
    "*send an email of a summary of this youtube video in an email to darren",
    "*what year was this song released",
    "*Set my desktop background to a picture of a dog",
    "$*add milk to whichever list has cocoa powder in",
    "$*play that song that i said made me feel good yesterday",
]

examples = [
    "@Provide a daily brief on the stock market."
    "$which list has cocoa powder in it"
    "$what tasks have you done recently"
    "$what alarms do you have set"
    "$what tasks are you doing"
    "$Provide a recap of my main tasks from last week."
    "$How many times did I ask about exercise routines this month"
    "Give me a summary of the latest research in artificial intelligence"
    "Suggest a healthy meal plan for next week."
    "%set a reminder every day with the meal plan for that day"
    "Suggest an exercise routine for weight loss."
    "Suggest a weekend getaway based on my interest in hiking."
    "+Find me a recipe that uses the ingredients I have in my fridge."
    "+Help me prepare for my job interview by asking me common interview questions."
    "+Quiz me on capital cities of the world."
    "teach me a new scientific concept"
    "play stone roses"  # #
    "Add celery and oil to my shopping list and my garage list"  # #
    "set an alarm for 20 minutes in 5 minutes"
]

"generate an image of a cat and a dog and set it as my wallpaper"  # #
"Sql query of a file"
"open this file and analyse it"
"analyse this folder"
"read this file and tell me x"


class TestAgent(unittest.TestCase):
    def test_level1(self):
        while True:
            agent.workflow.wait_until_current_role('user', not_equals=True)
            user_input = input("\nUser: ")
            if user_input:
                agent.save_message('user', user_input)


if __name__ == '__main__':
    unittest.main()
