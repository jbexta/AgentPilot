import ast
import json
import queue
import re
import sys
import threading
import time
import traceback

from jupyter_client import KernelManager

from plugins.openinterpreter.base_language import BaseLanguage

DEBUG_MODE = False

# When running from an executable, ipykernel calls itself infinitely
# This is a workaround to detect it and launch it manually
if "ipykernel_launcher" in sys.argv:
    if sys.path[0] == "":
        del sys.path[0]

    from ipykernel import kernelapp as app

    app.launch_new_instance()
    sys.exit(0)


class JupyterLanguage(BaseLanguage):
    file_extension = "py"
    name = "Python"
    aliases = ["py"]

    def __init__(self):
        self.km = KernelManager(kernel_name="python3")
        self.km.start_kernel()
        self.kc = self.km.client()
        self.kc.start_channels()
        while not self.kc.is_alive():
            time.sleep(0.1)
        time.sleep(0.5)

        self.listener_thread = None
        self.finish_flag = False

        # Use Inline, which bubbles everything up as an image
        code = """
%matplotlib inline
import matplotlib.pyplot as plt
""".strip()

        for _ in self.run(code):
            pass

    def terminate(self):
        self.kc.stop_channels()
        self.km.shutdown_kernel()

    def run(self, code):
        while not self.kc.is_alive():
            time.sleep(0.1)

        self.finish_flag = False
        try:
            try:
                preprocessed_code = self.preprocess_code(code)
            except:
                # Any errors produced here are our fault.
                # Also, for python, you don't need them! It's just for active_line and stuff. Just looks pretty.
                preprocessed_code = code
            message_queue = queue.Queue()
            self._execute_code(preprocessed_code, message_queue)
            yield from self._capture_output(message_queue)
        except GeneratorExit:
            raise  # gotta pass this up!
        except:
            content = traceback.format_exc()
            response_dict = {
                "status": "error",
                "result": content,
            }
            yield {"type": "console", "format": "output", "content": json.dumps(response_dict)}

    def _execute_code(self, code, message_queue):
        def iopub_message_listener():
            max_retries = 100
            while True:
                # If self.finish_flag = True, and we didn't set it (we do below), we need to stop. That's our "stop"
                if self.finish_flag == True:
                    if DEBUG_MODE:
                        print("interrupting kernel!!!!!")
                    self.km.interrupt_kernel()
                    return
                try:
                    msg = self.kc.iopub_channel.get_msg(timeout=0.05)
                except queue.Empty:
                    continue
                except Exception as e:
                    max_retries -= 1
                    if max_retries < 0:
                        raise
                    print("Jupyter error, retrying:", str(e))
                    continue

                if DEBUG_MODE:
                    print("-----------" * 10)
                    print("Message received:", msg["content"])
                    print("-----------" * 10)

                if (
                    msg["header"]["msg_type"] == "status"
                    and msg["content"]["execution_state"] == "idle"
                ):
                    # Set finish_flag and return when the kernel becomes idle
                    if DEBUG_MODE:
                        print("from thread: kernel is idle")
                    self.finish_flag = True
                    return

                content = msg["content"]

                if msg["msg_type"] == "stream":
                    line, active_line = self.detect_active_line(content["text"])
                    if active_line:
                        message_queue.put(
                            {
                                "type": "console",
                                "format": "active_line",
                                "content": active_line,
                            }
                        )
                    message_queue.put(
                        {"type": "console", "format": "output", "content": line}
                    )
                elif msg["msg_type"] == "error":
                    content = "\n".join(content["traceback"])
                    # Remove color codes
                    ansi_escape = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")
                    content = ansi_escape.sub("", content)
                    res_dict = {
                        "status": "error",
                        "result": content,
                    }
                    message_queue.put(
                        {
                            "type": "console",
                            "format": "output",
                            "content": json.dumps(res_dict),
                        }
                    )
                elif msg["msg_type"] in ["display_data", "execute_result"]:
                    data = content["data"]
                    if "image/png" in data:
                        message_queue.put(
                            {
                                "type": "image",
                                "format": "base64.png",
                                "content": data["image/png"],
                            }
                        )
                    elif "image/jpeg" in data:
                        message_queue.put(
                            {
                                "type": "image",
                                "format": "base64.jpeg",
                                "content": data["image/jpeg"],
                            }
                        )
                    elif "text/html" in data:
                        message_queue.put(
                            {
                                "type": "code",
                                "format": "html",
                                "content": data["text/html"],
                            }
                        )
                    elif "text/plain" in data:
                        message_queue.put(
                            {
                                "type": "console",
                                "format": "output",
                                "content": data["text/plain"],
                            }
                        )
                    elif "application/javascript" in data:
                        message_queue.put(
                            {
                                "type": "code",
                                "format": "javascript",
                                "content": data["application/javascript"],
                            }
                        )

        self.listener_thread = threading.Thread(target=iopub_message_listener)
        self.listener_thread.start()

        if DEBUG_MODE:
            print(
                "thread is on:", self.listener_thread.is_alive(), self.listener_thread
            )

        self.kc.execute(code)

    def detect_active_line(self, line):
        if "##active_line" in line:
            # Split the line by "##active_line" and grab the last element
            last_active_line = line.split("##active_line")[-1]
            # Split the last active line by "##" and grab the first element
            active_line = int(last_active_line.split("##")[0])
            # Remove all ##active_line{number}##\n
            line = re.sub(r"##active_line\d+##\n", "", line)
            return line, active_line
        return line, None

    def _capture_output(self, message_queue):
        while True:
            time.sleep(0.1)

            if self.listener_thread:
                try:
                    output = message_queue.get(timeout=0.1)
                    if DEBUG_MODE:
                        print(output)
                    yield output
                except queue.Empty:
                    if self.finish_flag:
                        time.sleep(0.1)

                        try:
                            output = message_queue.get(timeout=0.1)
                            if DEBUG_MODE:
                                print(output)
                            yield output
                        except queue.Empty:
                            if DEBUG_MODE:
                                print("we're done")
                            break

    def stop(self):
        self.finish_flag = True

    def preprocess_code(self, code):
        return preprocess_python(code)


def preprocess_python(code):
    """
    Add active line markers
    Wrap in a try except
    """

    code = code.strip()

    # Add print commands that tell us what the active line is
    # but don't do this if any line starts with ! or %
    if not any(line.strip().startswith(("!", "%")) for line in code.split("\n")):
        code = add_active_line_prints(code)

    # Remove any whitespace lines, as this will break indented blocks
    # (are we sure about this? test this)
    code_lines = code.split("\n")
    code_lines = [c for c in code_lines if c.strip() != ""]
    code = "\n".join(code_lines)

    return code


def add_active_line_prints(code):
    """
    Add print statements indicating line numbers to a python string.
    """
    # Replace newlines and comments with pass statements, so the line numbers are accurate (ast will remove them otherwise)
    code_lines = code.split("\n")
    in_multiline_string = False
    for i in range(len(code_lines)):
        line = code_lines[i]
        if '"""' in line or "'''" in line:
            in_multiline_string = not in_multiline_string
        if not in_multiline_string and (line.strip().startswith("#") or line == ""):
            whitespace = len(line) - len(line.lstrip(" "))
            code_lines[i] = " " * whitespace + "pass"
    processed_code = "\n".join(code_lines)
    try:
        tree = ast.parse(processed_code)
    except:
        # If you can't parse the processed version, try the unprocessed version before giving up
        tree = ast.parse(code)
    transformer = AddLinePrints()
    new_tree = transformer.visit(tree)
    return ast.unparse(new_tree)


class AddLinePrints(ast.NodeTransformer):
    """
    Transformer to insert print statements indicating the line number
    before every executable line in the AST.
    """

    def insert_print_statement(self, line_number):
        """Inserts a print statement for a given line number."""
        return ast.Expr(
            value=ast.Call(
                func=ast.Name(id="print", ctx=ast.Load()),
                args=[ast.Constant(value=f"##active_line{line_number}##")],
                keywords=[],
            )
        )

    def process_body(self, body):
        """Processes a block of statements, adding print calls."""
        new_body = []

        # In case it's not iterable:
        if not isinstance(body, list):
            body = [body]

        for sub_node in body:
            if hasattr(sub_node, "lineno"):
                new_body.append(self.insert_print_statement(sub_node.lineno))
            new_body.append(sub_node)

        return new_body

    def visit(self, node):
        """Overridden visit to transform nodes."""
        new_node = super().visit(node)

        # If node has a body, process it
        if hasattr(new_node, "body"):
            new_node.body = self.process_body(new_node.body)

        # If node has an orelse block (like in for, while, if), process it
        if hasattr(new_node, "orelse") and new_node.orelse:
            new_node.orelse = self.process_body(new_node.orelse)

        # Special case for Try nodes as they have multiple blocks
        if isinstance(new_node, ast.Try):
            for handler in new_node.handlers:
                handler.body = self.process_body(handler.body)
            if new_node.finalbody:
                new_node.finalbody = self.process_body(new_node.finalbody)

        return new_node
