# 🤖 OpenAgent

OpenAgent is a zero-shot conversational agent with a ReAct system that uses hard-coded actions as a first resort, and a code interpreter as a last resort. With full control over action logic, dialogue integration and behaviour customization.

Hard-coded actions give near instant responses and are integrated into the ReAct system.<br>
Adding a new Action is as easy as adding a new class, and instantly ready to use with ReAct.

A code interpreter is used when a task cannot be completed using explicitly defined actions. It can execute Python code, and is better suited for more difficult tasks.

## Features
### 📄 Tasks 

A Task is created when one or more Actions are detected.<br>
If a request is complex enough then ReAct is used (If enabled in the config setting `react > enabled`).<br>

By only running ReAct when necessary, the latency for single action tasks is minimised. This is the default behaviour and can be changed in the config setting `react > always-use-react`

If ReAct fails to execute the task, then the task will be passed to the code interpreter.

Actions can be categorized, allowing many more Actions to be available to the Agent and reducing token count when not using a vector db.

### 👸 Behaviour

Agents support definition of character behaviour, allowing them to reply and sound like a celebrity or a character using TTS services that support this feature. In the future there will be support for offline TTS models.<br>

**Supported TTS services:**<br>
Amazon Polly<br>
Elevenlabs<br>
FakeYou (celebrities and characters)<br>
Uberduck (celebrities and characters) (discontinued)

### 🔓 Integrated Jailbreak

Supports DevMode Jailbreak and enabled by default for more unique and creative responses. <br>
To disable this change the following settings:<br>
`context > jailbreak = False`<br>
`context > prefix-all-assistant-msgs = ''`

Assistant messages are sent back to the LLM with the prefix "(🔓 Developer Mode Output)" as instructed by the jailbreak, whether the message contained it or not.

### 🕗 Scheduler

~~Tasks can be recurring or scheduled to run at a later time with requests like _"The last weekend of every month"_, or _"Every day at 9am"_.~~
Still in development

### Useful commands
`clear context` - Clears the context messages<br>
`^3` - Deletes the previous 3 messages permenantly<br>
`-t [request]` - Forces the Agent to start a task<br>
`-v` - Toggle Verbose mode (Shows information about the Agent's decisions)<br>
`-d` - Toggle Debug mode (Shows full information about the Agent)

## Action Overview

```python
# Example Action
class DeleteFile(BaseAction):
    def __init__(self, agent):
        super().__init__(agent)
        self.desc_prefix = 'requires me to'
        self.desc = "Delete a file"
        # Define the action input parameters
        self.inputs = ActionInputCollection([
            ActionInput('path-of-file-to-delete')
        ])

    def run_action(self):  # Called on every user message
        filepath = self.inputs.get('path-of-file-to-delete').value
        if not os.path.exists(filepath):
            yield ActionError('File does not exist')
        else:
            # Ask the user to confirm the action via an input
            ays = self.inputs.add('are-you-sure-you-want-to-delete', BoolFValue)
            yield MissingInputs()  # This is equivelant to ActionResponse('[MI]')
            # Execution will not resume until the input has been detected
            
            if ays.value == True:
                try:
                    os.remove(filepath)
                    yield ActionResult('[INF] File was deleted')
                except Exception as e:
                    yield ActionError('[INF] There was an error deleting the file')
            else:
                yield ActionResult('[INF] Deletion was cancelled')
```

Every action must contain the variables: <br>
```desc_prefix``` (A prefix for the description for when the Agent is detecting actions from the users' message Eg. 'requires me to') <br>
```desc``` (A description of what the action does Eg. 'Get the current time')

Any action category (.py file under ```openagent/operations/actions```) can also contain these variables, but are optional.
If these aren't given, then by default the category will be formatted like this:<br> ```The user's request mentions something related to [category]```

Each action must contain a ```run_action()``` method.
This is called when a Task decides to run the Action. <br>
This method is a generator, meaning ```ActionResponses``` are **'yielded' instead of 'returned'**, allowing the action logic to continue sequentially from where it left off (After each user message).<br>
However, this method will not run unless all _**required**_ inputs have been given.
If there are missing inputs the Agent will ask for them until the task decays.

### Action Input Parameters
`input_name`: _A descriptive name for the input_<br>
`required`: _A Boolean representing whether the input is required before executing_<br>
`time_based`: _A Boolean representing whether the input is time based_<br>
`hidden`: _A Boolean representing whether the input is hidden and won't be asked for by the agent_<br>
`fvalue`: _Any FValue (Default: TextFValue)_<br>
`default`: _A default value for the input_<br>
`examples`: _A list of example values, unused but may be used in the future_<br>

### Action Responses

When an ```ActionResponse``` is yielded, it's injected into the system prompt to guide the agent's next response.<br>
Unless the Action was created from within a React class, then it is only usually used for the React instance.

An ```ActionResponse``` can contain placeholders, by default these are available: <br>

    '[RES]' = '[WOFA][ITSOC] very briefly respond to the user '
    '[INF]' = '[WOFA][ITSOC] very briefly inform the user '
    '[ANS]' = '[WOFA][ITSOC] very briefly respond to the user considering the following information: '
    '[Q]' = '[ITSOC] Ask the user the following question: '
    '[SAY]', '[ITSOC] Say: '
    '[MI]' = '[ITSOC] Ask for the following information: '
    '[WOFA]' = 'Without offering any further assistance, '
    '[ITSOC]' = 'In the style of {char_name}{verb}, spoken like a genuine dialogue, ' if self.__voice_id else ''
    '[3S]', 'Three sentences'

`ActionResponse's` from within a React class ignore all placeholders. So it's important to word the `ActionResponse` properly, for example:<br>
GetTime response = `f"[SAY] it is {time}"`<br>
Notice how the placeholders are only used for instructions that relate to how the response is relayed to the user, and not the actual response itself.

### Creating an Action

Creating a new action is straightforward, simply add a new class that inherits the ```BaseAction``` class to any category file under the directory: ```openagent/operations/actions```.<br>

_Note: Ensure that the action makes sense in the context of the category it is being added to, or else the Agent will have trouble finding it. New categories can be made by adding a new file to this directory, the agent will use the filename as the category name. File names that begin with an underscore will not be treated as a category, and the actions within this file will be shown to the agent alongside the action categories._

## Task Overview
A Task is created when one or more Actions are detected, and will remain active until it completes, fails or decays.
<br>

The task will not run until all required inputs have been given, and will decay if the inputs are not given within a certain number of messages (Config setting `actions > input-decay-after-idle-msg-count`)<br>

If a request is complex enough then ReAct is used (If enabled in the config setting `react > enabled`).<br>

By default the ReAct will only do what you explicitly tell it to do. Task decomposition is not yet implemented, however I think it might not be necessary with an integrated code interpreter.

If a ReAct thought is unable to detect a hardcoded action, then it will try to use a code interpreter.

**Example of different ways to execute a Task:**

User: **"Generate an image of a cat and a dog and set it as my wallpaper"**<br>
_Assistant: "Ok, give me a moment to generate the image"<br>
Assistant: "Wallpaper set successfully"_

User: **"Generate an image of a cat and a dog"**<br>
_Assistant: "Ok, give me a moment to generate the image"<br>
Assistant: "Here is the image"<br>_
User: **"Set it as my wallpaper"**<br>
_Assistant: "Wallpaper set successfully"_

User: **"Generate an image"**<br>
_Assistant: "Ok, what do you want me to generate?"<br>_
User: **"A cat and a dog"**<br>
_Assistant: "Ok, give me a moment to generate the image"<br>
Assistant: "Here is the image"<br>_
User: **"Set it as my wallpaper"**<br>
_Assistant: "Wallpaper set successfully"_


## Roadmap
- Exciting things to come!

## Contributions

Contributions to OpenAgent are welcome and appreciated. Please feel free to submit a pull request.
