from setuptools import setup, find_packages

# requirements.txt:
# ------------------
# aiohttp~=3.9.1
# appdirs~=1.4.4
# boto3~=1.28.19
# botocore~=1.31.19
# html2image~=2.0.4.3
# inquirer~=3.2.0
# jupyter-client~=8.6.0
# langchain~=0.1.1
# langchain-openai~=0.0.3
# litellm~=1.16.18
# matplotlib~=3.8.2
# mistune~=3.0.2
# numpy~=1.25.0
# openai~=1.7.1
# opencv-python~=4.9.0.80
# packaging~=23.1
# pillow~=10.2.0
# posthog~=3.1.0
# psutil~=5.9.7
# PyAutoGUI~=0.9.54
# pydantic~=2.5.2
# pyperclip~=1.8.2
# PySide6~=6.2.4
# python-dotenv~=1.0.0
# PyYAML~=6.0
# regex~=2023.10.3
# requests~=2.31.0
# setuptools~=65.5.1
# tiktoken~=0.4.0
# tokentrim~=0.1.13
# toml~=0.10.2
# tqdm~=4.66.1
# open-interpreter~=0.2.0

setup(
    name='agentpilot',
    version='0.2.0',
    description='A framework to create, manage, and chat with AI agents',
    author='jbexta',
    author_email='agentpilotinfo@gmail.com',
    packages=find_packages(),
    install_requires=[
        "aiohttp~=3.9.1",
        "appdirs~=1.4.4",
        "boto3~=1.28.19",
        "botocore~=1.31.19",
        "html2image~=2.0.4.3",
        "inquirer~=3.2.0",
        "jupyter-client~=8.6.0",
        "langchain~=0.1.1",
        "langchain-openai~=0.0.3",
        "litellm~=1.16.18",
        "matplotlib~=3.8.2",
        "mistune~=3.0.2",
        "numpy~=1.25.0",
        "openai~=1.7.1",
        "packaging~=23.1",
        "pillow~=10.2.0",
        "posthog~=3.1.0",
        "psutil~=5.9.7",
        "PyAutoGUI~=0.9.54",
        "pydantic~=2.5.2",
        "pyperclip~=1.8.2",
        "PySide6~=6.2.4",
        "python-dotenv~=1.0.0",
        "PyYAML~=6.0",
        "regex~=2023.10.3",
        "requests~=2.31.0",
        "setuptools~=65.5.1",
        "tiktoken~=0.4.0",
        "tokentrim~=0.1.13",
        "toml~=0.10.2",
        "tqdm~=4.66.1",
        "open-interpreter~=0.2.0",
    ],
    python_requires='>=3.10',
)


#         "setuptools~=65.5.1",
#         "openai~=0.27.8",
#         "tiktoken~=0.4.0",
#         "pyttsx3~=2.90",
#         "requests~=2.31.0",
#         "spotipy~=2.23.0",
#         "pynput~=1.7.6",
#         "selenium~=4.10.0",
#         "sounddevice~=0.4.6",
#         "firetv~=1.0.9",
#         "PyAutoGUI~=0.9.54",
#         "twilio~=8.4.0",
#         "termcolor~=2.3.0",
#         "typer~=0.9.0",
#         "replicate~=0.10.0",
#         "Pillow~=9.5.0",
#         "matplotlib~=3.7.2",
#     ],
#     python_requires='>=3.10',
# )
