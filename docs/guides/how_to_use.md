# How to use

This is unfinished, parts that are crossed out are not implemented yet.

## Settings page

This is for configuring the app and global settings.<br>

### API page

<p>
  <img src="../Screenshot4.png" align="left" height="400px" alt="AgentPilot API page" style="margin-right: 20px;" />

Set your API keys and configure models in the `API` page. 

Model parameters can be set for each model in the `Models` tab, or set provider wide in the `Config` tab.

The parameters in `Models` are prioritized over the `Config` provider parameters.
</p>

<br clear="left">

### Blocks page

<p>
  <img src="../Screenshot5.png" align="left" height="400px" alt="AgentPilot Blocks page" style="margin-right: 20px;" />

The `Blocks` page is where you can create and edit context blocks.<br>

Context blocks can be used in the system message of any agents, allowing re-usability and consistency across multiple agents.<br>

</p>

<br clear="left">


## Agents page

<p>
  <img src="../Screenshot1.png" align="left" height="400px" alt="AgentPilot API page" style="margin-right: 20px;" />

Here, you can view, manage and create agents.

These settings are the default agent settings when the agent is used in a chat.

Start a chat with an agent by double clicking it or clicking the chat button.

The `Info` 

</p>

<br clear="left">

## Chat page

<p>
  <img src="../Screenshot2.png" align="left" height="400px" alt="AgentPilot API page" style="margin-right: 20px;" />

This is where you chat with agents or workflows (multi member chat).

Clicking on the name at the top of the chat will open the workflow settings, which can be a single agent or a multi member workflow.

It's important to note that the workflow settings will only affect the workflow, **not** the default agent settings shown in the agents page above.

And vice versa, the default agent settings will **not** affect the workflow settings.

**When the `+` button is clicked in the bottom right corner, a copy of the current workflow will be created and will **not** use the default agent settings.**
</p>

<br clear="left">

### Multi-agent chat

Agent Pilot supports group chats natively as well as CrewAI, ~~Autogen~~ or a [custom plugin]().

Add a member to the chat by clicking the `+` button.
<br>In the multi-agent view, you can connect agent outputs to other agent inputs.
<br>Clicking on a member bubble will open its member settings.
<br>Clicking on a connection will display the input type field, there are 2 types of inputs:
- `message` - The receiving agent will use the output as a message input, ~~if there are multiple message inputs we will see soon the different ways we can handle this~~
- `context` - The agent can use the response in it's system or user message, use this in the same way as a context block, using the input agent setting `Output context placeholder`.

~~For a full guide to the native group chat functionality, see [Native group chat](#native-group-chat).~~

### Native Behaviour


### Plugin Behaviour

A context integration like CrewAI or Autogen will only be used if **all** members of the chat are one of these types of agents.

### CrewAI

The CrewAI plugin uses LiteLLM langchain chat models to generate responses. 

Each instance of a CrewAI agent is a task, the `System message` of the agent is the CrewAI `task description`, and the `User message` is the task `Expected output`.
This is a dirty workaround for now for more space.

The tasks are a predefined workflow, so the agents don't use your typed message, just type anything and press enter.

Even though messages are persisted in Agent Pilot, they are not persisted in CrewAI, so the agents won't be able to see messages of previous turns.

Each time you type something the same workflow will be executed, so it is not conversational.



### Autogen

## Agent Plugins

### Open Interpreter

### MemGPT

### OpenAI Assistant

This is a wrapper for a CrewAI agent, see their documentation for more info.

### CrewAI Agent

This is a wrapper for a CrewAI agent, see their documentation for more info.

### Autogen Agent

This is a wrapper for AutoGen agents, see their documentation for more info.



<details>
<summary>Agents</summary>
<details>
<summary> - Agent settings</summary>

</details>
</details>

<details>
<summary>Contexts</summary>

</details>

<details>
<summary>Settings</summary>

</details>