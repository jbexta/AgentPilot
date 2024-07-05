<h1 align="center">💬 Agent Pilot</h1>


<p align="center">️
  <img src="docs/demo.png" width="600px" alt="AgentPilot desktop demo" />
<br><br>
Agent Pilot is an open source desktop app to create, manage, and chat with AI agents.
<br><br>
Using your own keys, models and local data.
<br><br>
Features multi-agent, branching chats with dozens of providers through LiteLLM.
<br><br>
Combine models from different providers under one context, and
configure their interaction with each other in a low-code environment.
<br><br>
Open Interpreter comes built-in as the applications code interpreter, let it run code to
do whatever you ask it to do.
<br>
</p>

<div align="center">

[![Discord](https://img.shields.io/discord/ge2ZzDGu9e?style=flat-square&logo=discord&label=Discord&color=5865F2&link=https%3A%2F%2Fdiscord.gg%2Fge2ZzDGu9e)](https://discord.gg/ge2ZzDGu9e)
[![X (formerly Twitter) Follow](https://img.shields.io/twitter/follow/AgentPilotAI)](https://twitter.com/AgentPilotAI)
</div>

<h3 align="center">Version 0.3.X </h3>
<p align="center">
<b>How to migrate your data to 0.3.0</b><br>
Copy your old database (data.db) to the new application folder before you start the app.<br><br>
</p>

<p align="center">
  <img src="docs/demo.gif" align="center" height="255px" alt="AgentPilot gif demo" style="margin-right: 20px;" />
  <img src="docs/Screenshot3.png" align="center" height="250px" alt="AgentPilot gif demo" style="margin-right: 20px;" />
  <img src="docs/Screenshot1.png" align="center" height="250px" alt="AgentPilot gif demo" style="margin-right: 20px;" />
</p>
<p align="center">
  <img src="docs/Screenshot2.png" align="center" height="250px" alt="AgentPilot gif demo" style="margin-right: 20px;" />
  <img src="docs/Screenshot4.png" align="center" height="250px" alt="AgentPilot gif demo" style="margin-right: 20px;" />
</p>

## Quickstart

### Binaries
<table>
  <tr>
	<th>Platform</th>
	<th>Downloads</th>
  </tr>
  <tr>
	<td>Linux</td>
	<td>
		
<b>Mirror:</b> <a href="https://sourceforge.net/projects/agentpilot/files/v0.3.0/AgentPilot_0.3.0_Linux_Portable.tar.xz/download" target="_blank">AgentPilot_0.3.0_Linux_Portable.tar.gz</a><br>
<b>MD5:</b>  d06b3f9c1439dc0cbf9180584e19d966<br>
<b>SHA1:</b> 63725237fe76016ac91b0bf743b4565164415dc7<br>
	</td>
  </tr>
  <tr>
	<td>Windows</td>
	<td>
<b>Mirror:</b> <a href="https://sourceforge.net/projects/agentpilot/files/v0.3.0/AgentPilot_0.3.0_Windows_Portable.zip/download" target="_blank">AgentPilot_0.3.0_Windows_Portable.zip</a><br>
<b>MD5:</b> 255c088034017b07674c4ec1207cd2a9<br>
<b>SHA1:</b> f39a3f9a162cf524b2d97bdc1c52458d2708a3c6<br>
	</td>
  </tr>
</table>


Building from source: [How to build from source](docs/guides/how_to_build.md) <br>

### Python
```bash
$ pip install agentpilot
```


### Documentation
[Python docs](/)<br>
[How to use](/)<br>
[Create a plugin](/)

## Features

###  👤 Create Agents
Create new agents, edit their configuration and organise them into folders.<br>
Multi-member workflows can be saved as a composite agent and nested infinitely.

### 📝 Manage Chats
View, continue and delete previous workflow chats and organise them into folders.<br>
Chats can be exported and imported as .<br>

### 👥 Multi-Agent Workflows
Seamlessly add multiple agents (or users), and configure how they interact with each other.<br>
Agent pilot supports group chat natively, but can be modified with a plugin:<br>
[CrewAI](/) *(All workflow agents **must** be a CrewAI agent, or else native will be used)*
<br>
[Create a workflow plugin](/)

### 🌱 Branching Workflows
Messages can be edited and resubmitted, and code can be edited and re-run.<br>
Allowing for a more practical way to chat with your workflow.<br>
Branching works with all plugins and multi-agent chats.<br>

### 🔠 Context Blocks
Manage a list of context blocks available to use in any agent system message.<br>
Allowing reusability and consistency across multiple agents.<br>
Block types:
- **Text** - A simple text block that can nest other blocks.
- **Code** - A code block that is executed and gets the output.
- **Prompt** - A prompt block that gets an LLM response.

### 🔨 Tools
Create, edit and delete tools, configure their parameters, code, language and environment.<br>
Tools can be added to an Agent or used individually as a workflow component.<br>

### 🔌 Plugins
Agent Pilot supports the following plugin types:
- **Agent** - Override the default agent behaviour.
- **Workflow** - Override the default workflow behaviour.

These agent plugins are built-in and ready to use:<br>
[Open Interpreter](https://github.com/KillianLucas/open-interpreter) 
<br>
[OpenAI Assistant](/)
<br>
[CrewAI Agent](/)
<br>
[Create an agent plugin](/)


### 💻 Code Interpreter
Open Interpreter is integrated into Agent Pilot, and can either be used standalone as a plugin 
or utilised by any Agent or context block to execute code.
<br>
Code auto-run can be enabled in the settings, but use this with caution, you should always
understand the code that is being run, any code you execute is your own responsibility.<br>
Try something like "Split this image into quarters" and see the power of Open Interpreter

### 📄 Tasks
~~Tasks are being reimplemented, coming soon!~~

### 🕗 Scheduler
~~Tasks can be recurring or scheduled to run at a later time with requests like _"The last weekend of every month"_, or _"Every day at 9am"_.~~
Still in development, coming soon.

### 👄 Voice
Agents can be linked to a text-to-speech service, combine with a personality context block and make your agent come to life!<br>

**Supported TTS services:**<br>
- Amazon Polly<br>
- Elevenlabs (expensive)<br>
- FakeYou (celebrities and characters but too slow for realtime)<br>
- Uberduck (celebrities and characters are discontinued)

**Supported LLM providers using LiteLLM:**<br>
- Anthropic
- Mistral
- Perplexity AI
- Groq
- OpenAI
- Replicate
- Azure OpenAI
- Huggingface
- Ollama
- VertexAI Google
- PaLM API Google
- Voyage
- AWS Sagemaker
- AWS Bedrock
- Anyscale
- VLLM
- DeepInfra
- AI21
- NLP Cloud
- Cohere
- Together AI
- Cloudflare
- Aleph Alpha
- Baseten
- OpenRouter
- Custom API Server
- Petals<br>
(Anthropic, Mistral, Perplexity, OpenRouter & OpenAI have been tested)

## Contributions
Contributions to Agent Pilot are welcome and appreciated. Please feel free to submit a pull request.

## Known Issues

- Custom user message isn't functional yet

## Notes
If you find this project useful please consider showing support by giving a star or leaving a tip :)
<br><br>
BTC:<br> 
ETH: <br>
