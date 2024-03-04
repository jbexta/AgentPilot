import io
import platform
import subprocess
import tempfile
import replicate
import requests
from src.utils.apis import llm
from src.operations.action import BaseAction, ActionSuccess
from src.operations.parameters import *
from src.utils import api


class UpscaleImage(BaseAction):
    def __init__(self, agent):
        super().__init__(agent, example='upscale this image')
        self.desc_prefix = 'requires me to'
        self.desc = "Upscale/Enhance/Increase the Resolution/Quality of an Image/Picture/Photo/Drawing/Illustration."
        self.inputs.add('image-to-modify', fvalue=ImageFValue)
        self.inputs.add('upscale-factor', required=False)

    def run_action(self):
        cl = replicate.Client(api_token=api.apis['replicate']['priv_key'])
        image_paths = cl.run(
            "nightmareai/real-esrgan:42fed1c4974146d4d2414e2be2c5277c7fcf05fcc3a73abf41610695738c1d7b",
            input={"image": None}
        )


class GenerateImage(BaseAction):
    def __init__(self, agent):
        super().__init__(agent, example='generate an image of a dog', return_ftype=ImageFValue)
        self.desc_prefix = 'requires me to'
        self.desc = "Do something like Generate/Create/Make/Draw/Design something like an Image/Picture/Photo/Drawing/Illustration etc."
        # self.inputs.add('full-description-of-what-to-create', required=True))
        self.inputs.add('description-of-what-to-create')
        self.inputs.add('should-assistant-augment-improve-or-enhance-the-user-image-prompt', required=False, hidden=True, format='Boolean (True/False)')

    def run_action(self):
        self.add_response('[SAY] "Ok, give me a moment to generate the image"')

        augment_prompt = self.inputs.get('should-assistant-augment-improve-or-enhance-the-user-image-prompt').value.lower().strip() == 'true'
        prompt = self.inputs.get('description-of-what-to-create').value

        num_words = len(prompt.split(' '))
        if num_words < 7:
            augment_prompt = True

        if augment_prompt:
            conv_str = self.agent.workflow.message_history.get_conversation_str(msg_limit=4)  # .last()
            sd_prompt = llm.get_scalar(f"""
Act as a stable diffusion image prompt augmenter. I will give the base prompt request and you will engineer a prompt for stable diffusion that would yield the best and most desirable image from it. The prompt should be detailed and should build on what I request to generate the best possible image. You must consider and apply what makes a good image prompt.
Here is the requested content to augment: `{prompt}`
This was based on the following conversation: 
{conv_str}

Now after I say "GO", write the stable diffusion prompt without any other text. I will then use it to generate the image.
GO: """)
        else:
            sd_prompt = prompt

        cl = replicate.Client(api_token=api.apis['replicate']['priv_key'])
        image_paths = cl.run(
            "stability-ai/sdxl:2b017d9b67edd2ee1401238df49d75da53c523f36e363881e057f5dc3ed3c5b2",
            input={"prompt": sd_prompt}
        )
        if len(image_paths) == 0:
            return ActionSuccess('[SAY] "Sorry, I was unable to generate the image"')

        req_path = image_paths[0]
        file_extension = req_path.split('.')[-1]
        response = requests.get(req_path)
        response.raise_for_status()

        image_bytes = io.BytesIO(response.content)

        img = Image.open(image_bytes)
        img_path = tempfile.NamedTemporaryFile(suffix=f'.{file_extension}').name
        img.save(img_path)

        if platform.system() == 'Darwin':  # macOS
            subprocess.Popen(['open', img_path], stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
        elif platform.system() == 'Windows':  # Windows
            subprocess.Popen(['start', img_path], shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
        else:  # linux variants
            subprocess.Popen(['xdg-open', img_path], stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)

        yield ActionSuccess(f'[SAY] "The image has been successfuly generated." (Image = `{img_path}`)')
        #                    output=f"Path the generated image was saved to: `{', '.join([p for p in local_image_paths])}`")
