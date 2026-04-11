import os
import inspect
from gui.main import launch

os.environ['LITELLM_LOG'] = 'ERROR'

SHOW_TRACE = False # True #   
APP_DIR = os.path.dirname(__file__)
exclude_classes = []  # ['DraggableMember', 'CustomGraphicsView']
n = 0

def trace_calls(frame, event, arg):
    if event == "call" and SHOW_TRACE:
        filepath = frame.f_code.co_filename
        is_my_code = filepath.startswith(APP_DIR)
        if not is_my_code:
            return trace_calls
        filename = os.path.basename(filepath)
        func_name = frame.f_code.co_name
        
        lineno = frame.f_lineno

        # Try to detect class name
        class_name = None
        if "self" in frame.f_locals:
            class_name = frame.f_locals["self"].__class__.__name__
        elif "cls" in frame.f_locals and inspect.isclass(frame.f_locals["cls"]):
            class_name = frame.f_locals["cls"].__name__

        if class_name in exclude_classes:
            return trace_calls

        global n
        n += 1
        if class_name:
            print(f"{n}`{filename} -> {class_name}.{func_name}() : {lineno}`")
        else:
            print(f"{n}`{filename} -> {func_name}() : {lineno}`")
    return trace_calls

if SHOW_TRACE:
    import sys
    sys.settrace(trace_calls)


if __name__ == '__main__':
    launch()
    