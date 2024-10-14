<h1 align="center">💬 Agent Pilot</h1>


<p align="center">️
  <img src="docs/demo.png" width="600px" alt="AgentPilot desktop demo" />
<br><br>
Create, manage, and chat with AI agents using your own keys, models and local data.
<br><br>
Agent Pilot provides a seamless experience, whether you want to chat with a single LLM, or a complex multi-member workflow.
<br><br>
Branching conversations are supported, edit and resend messages as needed.
<br><br>
Combine models from different providers under one chat, and configure their interaction with each other in a low-code environment.
<br><br>
</p>

<div align="center">

[![Discord](https://img.shields.io/discord/1169291612816420896?style=flat)](https://discord.gg/ge2ZzDGu9e)
[![X (formerly Twitter) Follow](https://img.shields.io/twitter/follow/AgentPilotAI)](https://twitter.com/AgentPilotAI)
</div>

> [!NOTE]  
> This project is under development, each release is stableish but may contain unfinished features or bugs, and this readme may not be accurate.

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
		
<b>Mirror:</b> <a href="https://sourceforge.net/projects/agentpilot/files/v0.3.2/AgentPilot_0.3.2_Linux_Portable.tar.gz/download" target="_blank">AgentPilot_0.3.2_Linux_Portable.tar.gz</a><br>
<b>MD5:</b>  66038195e76473997dec655e95bd7d62<br>
<b>SHA1:</b> e04749481fdff79dde6ab2e1ecb453809902471e<br>
	</td>
  </tr>
  <tr>
	<td>Windows</td>
	<td>
<b>Mirror:</b> <a href="https://sourceforge.net/projects/agentpilot/files/v0.3.2/AgentPilot_0.3.2_Windows_Portable.zip/download" target="_blank">AgentPilot_0.3.2_Windows_Portable.zip</a><br>
<b>MD5:</b> 034c1ecfda52ecdba6f560515e36232f<br>
<b>SHA1:</b> c2904d0adffd43421ce8498c90d5545758389904<br>
	</td>
  </tr>
</table>


Building from source: [How to build from source](docs/guides/how_to_build.md) <br>

> [!TIP]
> You can migrate your old database to the new version by replacing your executable with the new one before starting the application.

## Features

###  👤 Create Agents
Create new agents, edit their configuration and organise them into folders.<br>
Multi-member workflows can be saved as a single agent ~~and nested infinitely (coming soon)~~.

### 📝 Manage Chats
View, continue and delete previous workflow chats and organise them into folders.<br>

### 🌱 Branching Workflows
Messages, tools and code can be edited and re-run, allowing a more practical way to chat with your workflow.<br>
Branching works with all plugins and multi-member chats.<br>

### 👥 Graph Workflows
Seamlessly add other members or blocks to a workflow and configure how they interact with each other.<br>
Members aligned vertically are executed in parallel.
Workflow behaviour can be modified with a plugin.

### 📦 Blocks
Manage a collection of nestable blocks available to use in any workflow or text field, 
allowing reusability and consistency.<br>
Blocks can be workflows themselves, fully interoperable with chat workflows.<br>
You can use blocks in text (such as system message) by using the block name in curly braces, e.g. `{block-name}`.

Block types:
- **Text** - A simple text block that can nest other blocks.
- **Code** - A code block that is executed and gets the output.
- **Prompt** - A prompt block that gets an LLM response.
- **Workflow** - Any number of the above types connected together.

### 🔨 Tools 
Create, edit and delete tools, configure their parameters, code, language and environment.<br>
These can be added to an agent to let the LLM call them automatically.<br>
By default they use a single code block, but they can also be a workflow containing multiple blocks,
this allows the LLM to not only run code but run an entire workflow.

### 💻 Code Interpreter
Open Interpreter is integrated into Agent Pilot, and can either be used standalone as a plugin 
or used to execute code in 9 languages (Python, Shell, AppleScript, HTML, JavaScript, PowerShell, R, React, Ruby)

Code can be executed in multiple ways:
- From a block set as type 'Code'
- From a tool (which uses a block)
- From a message with the role 'Code'

You should always understand the code that is being run, any code you execute is your own responsibility.

For code messages, auto-run can be enabled in the settings.
To see code messages in action talk to the pre-configured Open Interpreter agent.

### 🪄 AI Generation
Blocks under the 'System Blocks' folder are used for generating or enhancing fields.
Claude's prompt generator is included by default, you can tweak it or create your own.
- **Prompt** - An AI generated prompt replaces the initial prompt.
- **System message** - AI generated system message.

### 🔌 Plugins
Agent Pilot supports the following plugins:
- **Agent** - Create custom agent behaviour.
- - [Open Interpreter](https://github.com/KillianLucas/open-interpreter)
- - [OpenAI Assistant](/)
- - [CrewAI Agent](/) (Currently disabled)
- **Workflow** - Create workflow behaviour.
- - [CrewAI Workflow](/) (Currently disabled)
- **Provider** - Add support for a model provider.
- - [Litellm (100+ models)](/)

- [Create a plugin](/)

### 👄 Voice
**Coming back soon**<br>
~~Agents can be linked to a text-to-speech service, combine with a personality context block and make your agent come to life!~~<br>

### 🔠 Models
LiteLLM is integrated and supports the following providers:<br>

- AI21
- AWS Bedrock
- AWS Sagemaker
- Aleph Alpha
- Anthropic
- Anyscale
- Azure OpenAI
- Baseten
- Cloudflare
- Cohere
- Custom API Servers
- DeepInfra
- DeepSeek
- Gemini
- Github
- Groq
- Huggingface
- Mistral
- NLP Cloud
- Nvidia NIM
- Ollama
- OpenAI
- OpenRouter
- PaLM API Google
- Perplexity AI
- Petals
- Replicate
- Together AI
- VLLM
- VertexAI Google
- Voyage

(Anthropic, Mistral, Perplexity, OpenRouter & OpenAI have been tested)

## Contributions
Contributions to Agent Pilot are welcome and appreciated. Please feel free to submit a pull request.

## Known Issues
- Changing the config of an OpenAI Assistant won't reload the assistant, for now close and reopen the chat.
- Some others
- Be careful using auto run code and open interpreter, any chat you open, if code is the last message it will start auto running, I'll add a flag to remember if the countdown has been stopped.
- Flickering when response is generating and scrolled up the page.
- Sometimes the scroll position jumps if the user is scrolled up and an AI response has finished generating.
- Windows exe must have console visible due to a strange bug.
- Issue on linux, creating venv does not install pip 
- Numeric tool parameters get stuck at -99999 
- When editing a previous message with markdown, to resend you have to press the resend button twice (because the first click makes the bubble lose focus, which blocks the event button click event)
- Multiple async groups (vertically aligned members) in the same workflow causes an issue.

If you find this project useful please consider showing support by giving a star or leaving a tip :)
<br><br>
BTC:<br> 
ETH: <br>
