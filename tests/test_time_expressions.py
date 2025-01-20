# import threading
# import unittest
# from openagent.agent.base import Agent
# from unittest.mock import patch
#
#
# agent = Agent()
# agent.workflow.print_history()
#
# examples = {
#     "In 26 minutes":  "Minute[+26]",
#     "First Monday of every month":  "Day[1].Week[1].Month",
#     "First Tuesday of every year":  "Day[2].Week[1].Month[1].Year",
#     "At 11 tonight":  "Time[23:00]",
#     "At 3pm every day":  "Time[15:00].Day",
#     "Every Saturday":  "Day[6].Week",
#     "On every day that begins with an S":  "Day[5,6].Week",
#     "Second week of february":  "Week[2].Month[2]",
#     "Every friday at 4 o clock":  "Time[16:00].Day[5].Week",
#     "Last day of every month":  "Day[-1].Month",
#     "weekly":  "Day(7)",
#     "On every day that it's raining":  "Day('Is it raining?')",
#     "5 minutes before east enders starts":  "Minute[-5].{east-enders-start-time}",
#     "second to last wednesday every month":  "Day[3].Week[-2].Month",
#     "Every 5 days":  "Day(5)",
#     "the first to the fifth day of every week":  "Day[1:5].Week",
#     "3 days before the next solar eclipse":  "Day[-3].{next-solar-eclipse}",
#     "Every month":  "Month",
#     "Every 3 days for the next 90 days":  "Day(3:90)",
#     "Second week of august of every year":  "Week[2].Month[8].Year",
#     "tomorrow at 6":  "Time[18:00].Day[+1]",
#     "Every morning at 8":  "Time[08:00].Day",
#     "The day before christmas every year":  "Day[24].Month[12].Year",
#     "Every wednesday in November":  "Day[3].Week.Month[11]",
#     "Every weekday":  "Day[1:5].Week",
#     "72 hours after we get back from holiday":  "Hour[+72].{when-we-get-back-from-holiday}",
#     "the first to the fifth day of every month":  "Day[1:5].Month",
#     "Every weekday this week at 6 in the morning":  "Time[06:00].Day[1:5]",
#     "Thursday and saturday":  "Day[4,6]",
#     "Last sunday of every month":  "Day[7].Week[-1].Month",
#     "Last week of every month":  "Week[-1].Month",
#     "every wednesday for the next 7 weeks":  "Day[3].Week(1:7)",
#     "at 8 am every last wednesday of the month for the next 9 months":  "Time[08:00].Day[3].Week[-1].Month(1:9)",
#     "the second half of every month":  "Day[16:31].Month",
#     "the third quarter of this year":  "Month[7:9]",
# }
#
#
# class TestTimeExprs(unittest.TestCase):
#     def test_all(self):
#         while True:
#             agent.workflow.wait_until_current_role('user', not_equals=True)
#             user_input = input("\nUser: ")
#             if user_input:
#                 agent.save_message('user', user_input)
#
#
# if __name__ == '__main__':
#     unittest.main()
