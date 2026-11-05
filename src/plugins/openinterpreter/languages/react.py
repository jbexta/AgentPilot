import re

from plugins.openinterpreter.base_language import BaseLanguage

template = """<!DOCTYPE html>
<html>
<head>
    <title>React App</title>
</head>
<body>
    <div id="root"></div>

    <!-- React and ReactDOM from CDN -->
    <script crossorigin src="https://unpkg.com/react@17/umd/react.development.js"></script>
    <script crossorigin src="https://unpkg.com/react-dom@17/umd/react-dom.development.js"></script>

    <!-- Babel for JSX parsing -->
    <script crossorigin src="https://unpkg.com/@babel/standalone@7.12.1/babel.min.js"></script>

    <!-- React code here -->
    <script type="text/babel">
        {insert_react_code}
    </script>
</body>
</html>"""


def is_incompatible(code):
    lines = code.split("\n")

    # Check for require statements at the start of any of the first few lines
    # Check for ES6 import/export statements
    for line in lines[:5]:
        if re.match(r"\s*require\(", line):
            return True
        if re.match(r"\s*import\s", line) or re.match(r"\s*export\s", line):
            return True

    return False


class React(BaseLanguage):
    name = "React"
    file_extension = "html"

    def run(self, code):
        if is_incompatible(code):
            yield {
                "type": "console",
                "format": "output",
                "content": "Error: React format not supported. `require` and `import` aren't supported.",
                "recipient": "assistant",
            }
            return

        code = template.replace("{insert_react_code}", code)

        yield {
            "type": "console",
            "format": "output",
            "content": "React is being displayed on the user's machine...",
            "recipient": "assistant",
        }

        # User sees interactive HTML
        yield {"type": "code", "format": "html", "content": code, "recipient": "user"}
