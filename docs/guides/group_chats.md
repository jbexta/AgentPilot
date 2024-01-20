# Native group chat

Agent Pilot supports group chats natively, with the ability to use an agents output in other agents.

| Functionality        |              |
|----------------------|--------------|
| Persistance          | Yes          |
| Voice                | Yes          |
| Context blocks       | Yes          |
| Model selection      | Yes          |
| Native member inputs | Yes          |
| Branching            | Yes          |
| Streaming            | No           |
| Call logging         | No           |
| Conversational       | No           |

## Creating a group chat

To create a group chat, you must first create a context plugin


# Plugin group chats

When all agents in a group chat are of the same agent plugin and share a common `group_key` attribute, 
the group chat functionality is inherited from the corresponding context plugin that matches the `group_key`.

## CrewAI

For CrewAI, each instance of a CrewAI agent is a `task` in the terms of CrewAI terminology, and the `System message` of the agent is the `task` description.
<br>The agents don't use your typed message, so just type anything and press enter.
<br>Even though messages are persisted in Agent Pilot, they are not persisted in CrewAI, so the agents won't be able to see messages of previous turns.
<br>Each time you type something the same workflow will be executed, so it is not conversational.

| Functionality        |                    |
|----------------------|--------------------|
| Persistance          | Yes                |
| Voice                | Yes                |
| Context blocks       | Yes                |
| Model selection      | Yes -- Only OpenAI |
| Native member inputs | Yes                |
| Branching            | Yes                |
| Streaming            | No                 |
| Call logging         | No                 |
| Conversational       | No                 |



## Autogen