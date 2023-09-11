import re
import webbrowser

from openagent.utils.apis import oai
from openagent.operations.action import BaseAction, ActionResult
from openagent.utils import helpers

# desc_prefix = 'mentions'
# desc = 'Something that involves the use of a website'

# improved desc for the LLM to better understand, and to make it more clear to the user what they can do


class Search_Site(BaseAction):
    def __init__(self, agent):
        super().__init__(agent, example='search youtube for crazy russian hacker')
        self.desc_prefix = 'requires me to'
        self.desc = 'Query a search on an arbitrary website'
        self.inputs.add('website_name', examples=['youtube'], required=False)
        self.inputs.add('search_query', examples=['crazy russian hacker'])

    def run_action(self):
        website_name = self.inputs.get('website_name').value.lower()
        search_query = self.inputs.get('search_query').value
        if website_name == '':
            google_search_url = f"https://www.google.com/search?q={'+'.join(search_query.split())}"
            # webbrowser.open_new_tab(google_search_url)
            # open_action = OpenURL()
            yield ActionResult("[SAY]you've search for `" + search_query + "`, in the style of {char_name}.")
        # print(google_search_url)
        return False


class Open_Websites(BaseAction):
    def __init__(self, agent):
        super().__init__(agent, example='open google')
        self.desc_prefix = 'requires me to'
        self.desc = 'Open one or more arbitrary website(/s)'
        self.inputs.add('website_name/s')

    # re.search("(?P<url>https?://[^\s]+)", myString).group("url")
    def run_action(self):
        return_strings = []
        try:
            inp = self.inputs.get(0).value
            if '&&&' in inp:
                input_urls = inp.split('&&&')
            else:
                input_urls = [inp]

            for input_url_or_name in input_urls:
                valid_url = helpers.is_url_valid(input_url_or_name)
                input_url = input_url_or_name
                if not valid_url:
                    res = oai.get_scalar(f"""
    Input website name: "{input_url_or_name}"
    Return the URL associated with this website as of your latest knowledge. Consider any phonetic mismatches in the transcription (eg. 'why combinator' = 'ycombinator').
    URL: """)
                    ree = re.search("(?P<url>(?:https?://|www\.)[^\s]+)", res)
                    if ree is None:
                        search = Search_Site(self.agent)
                        search.inputs.get('website_name/s').value = input_url_or_name
                        search.run_action()
                        return_strings.append(f"[SAY]that you couldn't find the website for `{input_url_or_name}`, so you searched it instead.")
                        continue
                    input_url = ree.group("url")
                    # if not helpers.is_url_valid(input_url):
                    #     return_strings.append(f"[SAY]there was an error opening the website for :{input_url_or_name}.")
                    #     continue
                    print(f'CONVERTED WEBSITE NAME {input_url_or_name}: {input_url}')

                webbrowser.open_new_tab(input_url)
                # current_url = openagent.toolkits.selenium_browser.get_current_url()
                # if current_url:
                #     if current_url.startswith(input_url):
                #         return_strings.append(f"[SAY]that '{self.inputs.get(0).value}' is already open.")
                #         continue
                # openagent.toolkits.selenium_browser.open_url(input_url)
                return_strings.append(f"[SAY]  '{self.inputs.get(0).value}' is now open")  # Make a comment about the site in the style of " + "{char_name}.")

        except Exception as e:
            return_strings.append("[SAY]there was an error opening the websites.")

        yield ActionResult('\n'.join(return_strings))


class Read_Webpage_Text(BaseAction):
    def __init__(self, agent):
        super().__init__(agent, example='read the webpage text')
        self.desc_prefix = 'requires me to'
        self.desc = 'Read the text of the current webpage'

    def run_action(self):
        try:
            text = toolkits.browser.get_page_text()
            if text is None: raise Exception()
            s = 1
            # if not valid_url:
                # res = oai.get_scalar(f"""

        except Exception as e:
            yield ActionResult("[SAY]there was an error reading the page text.")