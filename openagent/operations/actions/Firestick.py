import firetv
import subprocess

cli = firetv.AdbClient()

#         'Turn_On_Tv': {
#             'user_prefix': 'requires me to',
#             'description': 'Turn on the TV',
#         },
#         'Turn_Off_Tv': {
#             'user_prefix': 'requires me to',
#             'description': 'Turn off the TV',
#         },
#         'Go_To_Home': {
#             'user_prefix': 'requires me to',
#             'description': 'Go to the home screen',
#         },
#         'Media_Play': {
#             'user_prefix': 'requires me to',
#             'description': 'Play media',
#         },
#         'Media_Pause': {
#             'user_prefix': 'requires me to',
#             'description': 'Pause media',
#         },
#         'Media_Previous': {
#             'user_prefix': 'requires me to',
#             'description': 'Go to the previous media',
#         },
#         'Media_Next': {
#             'user_prefix': 'requires me to',
#             'description': 'Skip to the next media',
#         },
#         'Volume_Up': {
#             'user_prefix': 'requires me to',
#             'description': 'Turn the volume up',
#         },
#         'Volume_Down': {
#             'user_prefix': 'requires me to',
#             'description': 'Turn the volume down',
#         },


def go():
    push_adb("adb disconnect")
    push_adb("adb connect xx.xx")

def push_adb(msg):
    # cli.
    cmd = subprocess.Popen(msg)