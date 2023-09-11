import time
import webbrowser
import selenium.webdriver
from selenium import webdriver
from selenium.webdriver import Keys, ActionChains, FirefoxProfile
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By

# def get_browser():
#     return selenium.webdriver.Firefox()
current_browser = None

current_windows = {}


def preferred_browser():
    try:
        preferred_browser = webbrowser.get().name
        return preferred_browser
    except webbrowser.Error:
        return None


def get_selenium_browser():
    global current_browser
    if current_browser: return current_browser

    pref_browser = preferred_browser()
    if pref_browser == 'firefox':
        profile = FirefoxProfile("/home/jb/.mozilla/firefox/8dy0clwi.myprof")
        # add argument to profile to open new links in tabs
        profile.set_preference("browser.link.open_newwindow", 3)
        options = webdriver.FirefoxOptions()
        options.set_preference('detach', True)
        current_browser = webdriver.Firefox(profile, options=options)

    elif pref_browser == 'chrome':
        options = webdriver.ChromeOptions()
        options.add_argument("user-data-dir=C:\\Path")  # Path to your chrome profile
        options.add_experimental_option('detach', True)
        current_browser = webdriver.Chrome(executable_path="C:\\Users\\chromedriver.exe", chrome_options=options)

    return current_browser


def open_url(url):
    global current_windows
    browser = get_selenium_browser()
    is_open_window = get_window_by_url(url)
    if is_open_window:
        browser.switch_to.window(is_open_window)
        return

    current_url = browser.current_url
    if current_url == 'about:blank':
        browser.get(url)
    else:
        browser.execute_script(f"window.open('{url}', '_blank');")
    # time.sleep(3)
    browser.implicitly_wait(6)
    win_handle = browser.window_handles[-1]
    current_windows[url] = win_handle


def send_keys(keys):
    browser = get_selenium_browser()
    browser.find_element(By.TAG_NAME, 'body').send_keys(keys)


def get_current_url():
    if current_browser is None: return None
    browser = get_selenium_browser()
    return browser.current_url


def get_window_by_url(url):
    global current_windows
    # browser = get_selenium_browser()
    for window_url, window_id in current_windows.items():
        if str(window_url).startswith(url):
            return window_id
    return None


def get_page_text():
    if current_browser is None: return None
    browser = get_selenium_browser()
    return browser.find_element(By.TAG_NAME, 'body').text


# def is_url_open_in_any_tab(url):
#     # browser = get_selenium_browser()
#     for window_id, window_url in current_windows.items():
#         if str(window_url).startswith(url):
#             return True


site_search_formats = {
    'google': 'https://www.google.com/search?q={}',
    'youtube': 'https://www.youtube.com/results?search_query={}',
}

def try_search_site():
    browser = get_selenium_browser()
    current_url = browser.current_url
    if current_url == 'about:blank':
        browser.get(url)
    else:
        browser.execute_script(f"window.open('{url}', '_blank');")


# def open_url_in_new_tab(url):
#     browser = get_selenium_browser()
#     browser.execute_script("window.open('" + url + "', '_blank');")

# def is_browser_open():
#     if
#     return webbrowser.get().name != None