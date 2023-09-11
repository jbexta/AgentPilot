import requests

from openagent.utils.apis import oai
from openagent.operations.action import ActionResult, BaseAction
from openagent.utils import api

api_config = api.apis.get('openweathermap')
priv_key = api_config['priv_key']

desc_prefix = 'requires me to'
desc = 'Find out what the weather is going to be like or what the weather is like right now'


class Weather(BaseAction):
    def __init__(self, agent):
        super().__init__(agent, example='will it be sunny today?')
        self.desc_prefix = 'requires me to'
        self.desc = 'Get the weather forecast'
        self.inputs.add('weather-location', default='sheffield, uk')

    def run_action(self):
        try:
            base_url = "http://api.openweathermap.org/data/2.5/forecast?"
            location = self.inputs.get('weather-location').value
            complete_url = base_url + "appid=" + priv_key + "&q=" + location + "&units=metric"
            response = requests.get(complete_url)
            x = response.json()
            if x["cod"] != "200":
                raise Exception('Weather Error')
            data = x["list"]

            output = []

            for record in data:
                dt_txt = record.get('dt_txt', '')
                temp = record['main']['temp']
                feels_like = record['main']['feels_like']
                weather_main = record['weather'][0]['main']
                weather_desc = record['weather'][0]['description']
                wind_speed = record['wind']['speed']
                wind_deg = record['wind']['deg']

                formatted_record = f"{dt_txt} | Temp: {temp}°C | Feels Like: {feels_like}°C | Weather: {weather_main} ({weather_desc}) | Wind: {wind_speed}m/s at {wind_deg}°"

                output.append(formatted_record)

            full_output = '\n'.join(output)
            
            res = oai.get_scalar('weather')


            yield ActionResult(f"[ANS] {full_output}")

        except Exception as e:
            yield ActionResult("[SAY] There was an error getting the weather.")