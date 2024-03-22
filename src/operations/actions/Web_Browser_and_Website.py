import re
import webbrowser

from src.operations.action import BaseAction, ActionSuccess, ActionError
from src.utils import helpers, llm


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
        # return False
        website_name = self.inputs.get('website_name').value.lower()
        search_query = self.inputs.get('search_query').value
        if website_name == '':
            google_search_url = f"https://www.google.com/search?q={'+'.join(search_query.split())}"
            webbrowser.open_new_tab(google_search_url)
            yield ActionSuccess("[SAY]you've search for `" + search_query + "`, in the style of {char_name}.")
        else:
            res = llm.get_scalar(f"""
Input website name: "{website_name}"
Search query: "{search_query}"
Return the url when you search for the query on the given website as of your latest knowledge. Consider any phonetic mismatches in the transcription (eg. 'why combinator' = 'ycombinator').
URL: """)
            ree = re.search("(?P<url>(?:https?://|www\.)[^\s]+)", res)
            if ree is None:
                yield ActionError("I couldn't find a URL for that website.")
            else:
                url = ree.group("url")
                webbrowser.open_new_tab(url)
                return True


class Open_Websites(BaseAction):
    def __init__(self, agent):
        super().__init__(agent, example='open google')
        self.desc_prefix = 'requires me to'
        self.desc = 'Open one or more arbitrary website(/s)'
        self.inputs.add('website_name/s')

    # re.search("(?P<url>https?://[^\s]+)", myString).group("url")
    def run_action(self):
        try:
            inp = self.inputs.get(0).value
            if '&&&' in inp:
                input_urls = inp.split('&&&')
            else:
                input_urls = [inp]

            success_websites = []
            failed_websites = []
            for input_url_or_name in input_urls:
                valid_url = helpers.is_url_valid(input_url_or_name)
                input_url = input_url_or_name
                if not valid_url:
                    res = llm.get_scalar(f"""
    Input website name: "{input_url_or_name}"
    Return the URL associated with this website as of your latest knowledge. Consider any phonetic mismatches in the transcription (eg. 'why combinator' = 'ycombinator').
    URL: """)
                    ree = re.search("(?P<url>(?:https?://|www\.)[^\s]+)", res)
                    if ree is None:
                        search = Search_Site(self.agent)
                        search.inputs.get('website_name/s').value = input_url_or_name
                        search.run_action()
                        failed_websites.append(input_url_or_name)
                        continue
                    input_url = ree.group("url")
                    # if not helpers.is_url_valid(input_url):
                    #     return_strings.append(f"[SAY]there was an error opening the website for :{input_url_or_name}.")
                    #     continue
                    # print(f'CONVERTED WEBSITE NAME {input_url_or_name}: {input_url}')

                webbrowser.open_new_tab(input_url)
                # current_url = agentpilot.toolkits.selenium_browser.get_current_url()
                # if current_url:
                #     if current_url.startswith(input_url):
                #         return_strings.append(f"[SAY]that '{self.inputs.get(0).value}' is already open.")
                #         continue
                # agentpilot.toolkits.selenium_browser.open_url(input_url)
                success_websites.append(self.inputs.get(0).value)

            if len(success_websites) > 0:
                resp = f"[SAY] Opened {', '.join(self.inputs.get(0).value.split('&&&'))}" + \
                       (f" and failed to open {','.join(failed_websites)}" if len(failed_websites) > 0 else '')
                yield ActionSuccess(resp)
            else:
                resp = f"[SAY] Failed to open {','.join(failed_websites)}"
                yield ActionError(resp)

        except Exception as e:
            yield ActionError("[SAY] There was an error opening the websites.")


class Read_Webpage_Text(BaseAction):
    def __init__(self, agent):
        super().__init__(agent, example='read the webpage text')
        self.desc_prefix = 'requires me to'
        self.desc = 'Read the text of the current webpage'

    def run_action(self):
        try:
            yield ActionError("[SAY] This action is not yet implemented.")
            # text = toolkits.browser.get_page_text()
            # if text is None: raise Exception()
            # s = 1
            # if not valid_url:
                # res = llm.get_scalar(f"""

        except Exception as e:
            yield ActionSuccess("[SAY]there was an error reading the page text.")
