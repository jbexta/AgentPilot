# 🤖 OpenAgent

![Screenshot_2023-10-16_17-46-50.png](..%2F..%2FPictures%2FScreenshot_2023-10-16_17-46-50.png) ![demo-gif.gif](..%2F..%2FVideos%2Fdemo-gif.gif)
OpenAgent is a Python GUI interface for you to create, manage and chat with AI agents, aswell as manage their voices, personality and actions.

Agents can use custom hard-coded actions, or they can be a personality wrapper for other agents like AutoGPT or Open Interpreter. Or they can be both at the same time.

With Open Interpreter enabled, an agent can run code to do what you ask it to do.

Actions can be hard-coded giving fast responses while allowing full control over action logic and dialogue integration.<br>

When both are enabled, the blend of hard-coded actions and a code interpreter allows the assistant to be fast and reliable when it can be, and more powerful when it needs to be.

### Desktop GUI:
- **Manage agents** - Create, edit and delete agents, and manage their voices, personality and actions.
- **Manage chats** - View and delete previous agent chats.
- **Run code** - Run code for open interpreter, with configurable auto run in 5 seconds.
- **Branching chats** - Messages can be deleted, editted and resubmitted, and code can be editted and re-run.


## Features

### 📄 Code Interpreter

Open-Interpreter is integrated into OpenAgent as the default code-interpreter, and can either be used as an independent agent, or it can be used only when it needs to be, saving significant costs for a general use agent.

### 📄 Tasks

For agents where actions are enabled, a task is created when one or more actions are detected, and will remain active until it completes, fails or decays. 

Actions can be detected natively or with a function call from an LLM that supports it.

Hard-coded actions are searched and sorted based on semantic similarity to the request. 
A group of the most similar actions are then fed to the action decision method.

A single action can be detected and executed on its own without using ReAct, if a request is complex enough then ReAct is used.

If ReAct fails to find an action, then the request can be passed on to the code interpreter.

### 👸 Behaviour
Agents support definition of character behaviour, allowing them to reply and sound like a celebrity or a character using TTS services that support this feature. In the future there will be support for offline TTS models.<br>

**Supported TTS services:**<br>
Amazon Polly<br>
Elevenlabs<br>
FakeYou (celebrities and characters)<br>
Uberduck (celebrities and characters) (discontinued)

### 🔓 Integrated Jailbreak
Supports DevMode Jailbreak for more unique and creative responses. <br>
To enable this change the following settings:<br>
`context > jailbreak = true`<br>
`context > prefix-all-assistant-msgs = (🔓 Developer Mode Output)`

Assistant messages are sent back to the LLM with the prefix "(🔓 Developer Mode Output)" as instructed by the jailbreak, whether the message contained it or not. This helps to keep the jailbraik _aligned_ ;)

Only the main context is jailbroken. Actions, ReAct and the code interpreter are not affected by the jailbreak.

### 🕗 Scheduler
~~Tasks can be recurring or scheduled to run at a later time with requests like _"The last weekend of every month"_, or _"Every day at 9am"_.~~
Still in development, coming soon.

### ~~Useful commands for CLI~~ Rewrite broke CLI for now
~~`^c` - Clears the context messages<br>
`^3` - Deletes the previous (n) messages permenantly<br>
`-v` - Toggle Verbose mode (Shows information about the Agent's decisions)<br>
`-e` - ~~Toggle Eval mode (Saves prompts as valid unless marked otherwise)~~<br>
`-t [request]` ~~- Enforces a task<br>~~
`-re [request]` ~~- Enforces a ReAct task<br>~~
`-ci [request]` ~~- Enforces a code interpreter task<br>~~~~

## Action Overview
Agents support regular 
```python
# Example Action
class GenerateImage(BaseAction):
    def __init__(self, agent):
        super().__init__(agent)
        # DEFINE THE ACTION DESCRIPTION
        self.desc_prefix = 'requires me to'
        self.desc = "Do something like Generate/Create/Make/Draw/Design something like an Image/Picture/Photo/Drawing/Illustration etc."
        # DEFINE THE ACTION INPUT PARAMETERS
        self.inputs.add('description-of-what-to-create')
        self.inputs.add('should-assistant-augment-improve-or-enhance-the-user-image-prompt', 
                        required=False, 
                        hidden=True, 
                        fvalue=BoolFValue)

    def run_action(self):
        """
        Starts or resumes the action on every user message
        Responses can be yielded instead of returned to allow for continuous execution
        """
        
        # USE self.add_response() TO SEND A RESPONSE WITHOUT PAUSING THE ACTION
        self.add_response('[SAY] "Ok, give me a moment to generate the image"')

        # GET THE INPUT VALUES
        prompt = self.inputs.get('description-of-what-to-create').value
        augment_prompt = self.inputs.get('should-assistant-augment-improve-or-enhance-the-user-image-prompt').value.lower().strip() == 'true'

        # STABLE DIFFUSION PROMPT GENERATOR
        num_words = len(prompt.split(' '))
        if num_words < 7:
            augment_prompt = True

        if augment_prompt:
            conv_str = self.agent.context.message_history.get_conversation_str(msg_limit=4)
            sd_prompt = llm.get_scalar(f"""
Act as a stable diffusion image prompt augmenter. I will give the base prompt request and you will engineer a prompt for stable diffusion that would yield the best and most desirable image from it. The prompt should be detailed and should build on what I request to generate the best possible image. You must consider and apply what makes a good image prompt.
Here is the requested content to augment: `{prompt}`
This was based on the following conversation: 
{conv_str}

Now after I say "GO", write the stable diffusion prompt without any other text. I will then use it to generate the image.
GO: """)
        else:
            sd_prompt = prompt

        # USE REPLICATE API TO GENERATE THE IMAGE
        cl = replicate.Client(api_token=api.apis['replicate']['priv_key'])
        image_paths = cl.run(
            "stability-ai/sdxl:2b017d9b67edd2ee1401238df49d75da53c523f36e363881e057f5dc3ed3c5b2",
            input={"prompt": sd_prompt}
        )
        
        if len(image_paths) == 0:
            # YIELD AN ActionError() TO STOP THE ACTION AND RETURN AN ERROR RESPONSE
            yield ActionError('There was an error generating the image')

        # DOWNLOAD THE IMAGE
        req_path = image_paths[0]
        file_extension = req_path.split('.')[-1]
        response = requests.get(req_path)
        response.raise_for_status()
        image_bytes = io.BytesIO(response.content)
        img = Image.open(image_bytes)
        img_path = tempfile.NamedTemporaryFile(suffix=f'.{file_extension}').name
        img.save(img_path)
        
        # ASK THE USER FOR CONFIRMATION TO OPEN THE IMAGE (FOR THE SAKE OF THIS EXAMPLE)
        # 1. ADD A NEW INPUT
        # 2. YIELD MissingInputs(), THIS IS EQUIVELANT TO `ActionResponse('[MI]')`
        open_image = self.inputs.add('do-you-want-to-open-the-image', BoolFValue)
        yield MissingInputs() 
        # EXECUTION WILL NOT RESUME UNTIL THE INPUT HAS BEEN DETECTED
            
        # OPEN THE IMAGE
        if open_image.value():
            if platform.system() == 'Darwin':  # MAC
                subprocess.Popen(['open', img_path], stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
            elif platform.system() == 'Windows':  # WINDOWS
                subprocess.Popen(['start', img_path], shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
            else:  # LINUX
                subprocess.Popen(['xdg-open', img_path], stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)

        # YIELD AN ActionSuccess() TO STOP THE ACTION AND RETURN A RESPONSE
        # PASS ANY OUTPUT VARIABLES IN PARENTHESES "()"
        yield ActionSuccess(f'[SAY] "The image has been successfuly generated." (path = {img_path})')
```

Every action must contain the variables: <br>
```desc_prefix``` (A prefix for the description for when the Agent is detecting actions from the users' message Eg. 'requires me to') <br>
```desc``` (A description of what the action does Eg. 'Get the current time')

Any action category (.py file under ```openagent/operations/actions```) can also contain these variables, but are optional.
If these aren't given, then by default the category will be formatted like this:<br> ```The user's request mentions something related to [category]```

Each action must contain a ```run_action()``` method.
This is called when a Task decides to run the Action. <br>
This method can be a generator, meaning ```ActionResponses``` can be **'yielded' instead of 'returned'**, allowing the action logic to continue sequentially from where it left off (After each user message).<br>

This method will not run unless all _**required**_ inputs have been given.
If there are missing inputs the Agent will ask for them until the task decays. <br>
This is useful for confirmation prompts, or to ask the user additional questions based on programatic execution flow.

### Action Input Parameters
`input_name`: _A descriptive name for the input_<br>
`required`: _A Boolean representing whether the input is required before executing_<br>
`time_based`: _A Boolean representing whether the input is time based_<br>
`hidden`: _A Boolean representing whether the input is hidden and won't be asked for by the agent_<br>
`default`: _A default value for the input_<br>
`examples`: _A list of example values, unused but may be used in the future_<br>
`fvalue`: _Any FValue (Default: TextFValue)_<br>

### Action Responses
When an ```ActionResponse``` is yielded, it's injected into the main context to guide the agent's next response.<br>
Unless the Action was created from within a ReAct context, then it is only usually used for the React instance.

An ```ActionResponse``` can contain dialogue placeholders, by default these are available: <br>

    '[RES]' = '[WOFA][ITSOC] very briefly respond to the user '
    '[INF]' = '[WOFA][ITSOC] very briefly inform the user '
    '[ANS]' = '[WOFA][ITSOC] very briefly respond to the user considering the following information: '
    '[Q]' = '[ITSOC] Ask the user the following question: '
    '[SAY]', '[ITSOC] Say: '
    '[MI]' = '[ITSOC] Ask for the following information: '
    '[WOFA]' = 'Without offering any further assistance, '
    '[ITSOC]' = 'In the style of {char_name}{verb}, spoken like a genuine dialogue, ' if self.voice_id else ''
    '[3S]', 'Three sentences'

`ActionResponse's` from within a ReAct class ignore all dialogue placeholders. So it's important to word the `ActionResponse` properly, for example:<br>
ImageGen response = `f"[SAY] 'The image has been successfuly generated.' (path = {img_path})"`<br>

Notice how the dialogue placeholders are only used for instructions that relate to how the response is relayed to the user, and not the actual response itself.

Also notice the information in parenthesis "( )" is only output values.

The response is seen by the main context including the dialogue placeholders but not the output values.<br>
And is seen by a ReAct context including the output values but not the dialogue placeholders.

### Creating an Action Category
Actions can be categorized, allowing many more Actions to be available to the Agent while improving speed.

Categories and Actions are stored in the directory ```openagent/operations/actions```

New categories can be made by adding a new file to this directory, the Agent will use the filename as the category name, unless it contains a `desc` variable.

### Creating an Action
Creating a new action is straightforward, simply add a new class that inherits ```BaseAction``` to any category file under the actions directory.<br>

An action can be uncategorized by adding it to the `_Uncategorized.py` file. Categories that begin with an underscore will not be treated as a category, and the actions within this file will always be included in the decision.

Ensure the action makes sense in the context of the category it is being added to, or the Agent will likely have trouble finding it.

## Task Overview

A Task is created when one or more Actions are detected, and will remain active until it completes, fails or decays. 

Actions can be detected by the following methods:<br>
- **Native** - Native decision prompt that doesn't rely on function calling.
- **Function Call** - Function call from an LLM that supports it.

Hard-coded actions are searched and sorted based on semantic similarity to the request. A group of the most similar actions are then fed to one of the detection methods above, depending on the config setting: `use-function-call`

If the config setting `try-single-action = true` then a validation prompt is used to determine if the single action is sufficient, and if not, then ReAct is used. (If enabled in the config)

This validator can be disabled with the config setting: `use-validator`

If the config setting `try-single-action = false` then the validator is skipped, since the validator is only used to determine if the single action is sufficient.<br>

This default behaviour of not always using ReAct is faster for single actions, but introduces a problem where for complex requests it may forget to initiate a ReAct.
This could be solved by fine-tuning a validator model.

Explicit ReAct is used to seperate different instructions verbatim from the user request, to execute them independently. Implicit ReAct is work in progress.

If ReAct fails to perform an action, then the request can be passed on to the code interpreter.

An action will not run until all required inputs have been given, and the parent task will decay if the inputs are not given within a certain number of messages (Config setting `decay_at_idle_count`)<br>
This is also true when actions are performed inside a ReAct, then the ReAct will hang on the action until the input is given or decays.

### **Current actions that can be chained together:**

**Web_Browser_and_Website <br>**
	Open_Websites <br>
	Search_Site <br>
<br>
**Audio_Playback <br>**
	GetNameOfCurrentlyPlayingTrack <br>
	NextTrack <br>
	PauseMusic <br>
	PlayMusic <br>
	PreviousTrack <br>
	RepeatTrack <br>
	SearchPlayMusic <br>
	SwitchPlaybackToDesktop <br>
	SwitchPlaybackToSmartphone <br>
	ToggleShuffle <br>
<br>
**Image_And_Video_Production <br>**
	GenerateImage (Replicate API) <br>
	UpscaleImage (Replicate API) <br>
<br>
**Desktop_Management <br>**
	CloseWindow <br>
	MinimizeWindow <br>
	Set_Desktop_Background <br>
<br>
**Desktop_Software_Apps <br>**
	Open_Desktop_Software <br>
<br>
**Email_OR_SMS_OR_Messaging <br>**
	Send_SMS_Or_Text_Message (Twilio API) <br>
<br>
**Clipboard_Operations <br>**
	Copy_To_Clipboard <br>
	Cut_To_Clipboard <br>
	Paste_From_Clipboard <br>
<br>
**RemindersAndEvents <br>**
	~~Set_Reminder~~ <br>
<br>
**Lists <br>**
	Add_Item_To_List <br>
	Create_A_New_List <br>
	DeleteOrRemove_A_List <br>
	DeleteOrRemove_Item_From_List <br>
	ViewOrRead_Existing_List <br>
<br>
**Files_and_Directories <br>**
    DeleteFile <br>
	Open_Directory_Or_File <br>
	~~UnzipFile~~ <br>
<br>
**_Uncategorised <br>**
	Clear_Assistant_Context_Messages <br>
	Date <br>
	~~Modify_Assistant_Responses~~ <br>
	~~Modify_Assistant_Voice~~ <br>
	~~MouseClick~~ <br>
	Sync_Available_Voices <br>
	Time <br>
	Type_Text <br>
<br>

### **Example of different ways to execute Tasks:**

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

## Warning
- Do not paste a block of text into the CLI, as it will run each separate line as a separate command. Use the GUI instead.

## ~~Finetuning~~

~~Each component of the Agent can be fine-tuned independently on top of the zero-shot instructions to improve the accuracy of the Agent.~~

- [Action Decision](https://github.com/jbexta/OpenAgent/blob/6c06eef739b6cf6788961535aeee75474965b778/openagent/operations/task.py#L250)<br>
- [Action Validator](https://github.com/jbexta/OpenAgent/blob/6c06eef739b6cf6788961535aeee75474965b778/openagent/operations/task.py#L175)<br>
- [Input Extractor](https://github.com/jbexta/OpenAgent/blob/6c06eef739b6cf6788961535aeee75474965b778/openagent/operations/action.py#L85)<br>
- [ReAct Requests](https://github.com/jbexta/OpenAgent/blob/6c06eef739b6cf6788961535aeee75474965b778/openagent/operations/task.py#L359)

~~Fine-tuning data can be found in utils/finetuning.~~

~~When eval mode is turned on with `-e`, prompts are saved to the 'valid' directory, and a popup will appear for each task with a "Wrong" button. When a task is marked as wrong, you will be asked to specify which prompts were wrong, and to provide the correct response.~~

~~To fine-tune a GPT 3.5 model with the data, use the following command:<br>
`-finetune` or just ask the Agent to fine-tune itself.~~<br>

~~You will be told how much it will cost to fine-tune a model, and asked to confirm the action.~~

~~Fine tuned model metadata is stored in the database, and each~~ 

## Contributions

Contributions to OpenAgent are welcome and appreciated. Please feel free to submit a pull request.