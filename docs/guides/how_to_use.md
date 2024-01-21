# How to use

This is unfinished, parts that are crossed out are not implemented yet.

## Settings page

This is for configuring the app and global settings.
<br>Set your api keys and configure models in the `API` tab.

## Agents page

The agents page is where you can view, manage and create agents.
<br>The settings for each agent are the default settings for when the agent is used in a chat.
<br>Start a chat with an agent by double clicking it or clicking the chat button.

## Chat page

### Member settings

Clicking the member name at the top of the chat will open the member settings.
<br>Changing these settings will only affect this specific member.

### Multi-agent chat

Agent Pilot supports group chats natively as well as CrewAI, ~~Autogen~~ or a [custom plugin]().

Add a member to the chat by clicking the `+` button.
<br>In the multi-agent view, you can connect agent outputs to other agent inputs.
<br>Clicking on a member bubble will open its member settings.
<br>Clicking on a connection will display the input type field, there are 2 types of inputs:
- `message` - The receiving agent will use the output as a message input, if there are multiple message inputs we will see soon the different ways you can handle this
- `context` - The agent can use the response in it's system or user message, use this in the same way as a context block, using the input agent setting `Output context placeholder`.

~~For a full guide to the native group chat functionality, see [Native group chat](#native-group-chat).~~

### Native Behaviour


### Plugin Behaviour

A context plugin like CrewAI or Autogen will only be used if **all** members of the chat are one of these types of agents.

### CrewAI

<b>Expensive to use and only supports OpenAI.</b>

For CrewAI, each instance of a CrewAI agent is a `task` in the terms of CrewAI terminology, and the `System message` of the agent is the `task` description.
<br>The agents don't use your typed message, so just type anything and press enter.
<br>Even though messages are persisted in Agent Pilot, they are not persisted in CrewAI, so the agents won't be able to see messages of previous turns.
<br>Each time you type something the same workflow will be executed, so it is not conversational.

| Functionality        |           |
|----------------------|-----------|
| Persistance          | Yes       |
| Voice                | Yes       |
| Context blocks       | Yes       |
| Model selection      | Yes       |
| Native member inputs | Yes       |
| Branching            | Yes       |
| Streaming            | No        |
| Call logging         | No        |
| Conversational       | No        |




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