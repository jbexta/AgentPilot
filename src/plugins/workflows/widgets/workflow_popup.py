import asyncio
import os

from PIL import Image
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog

from gui.gui_utils.helpers import find_main
from gui.gui_utils.layouts import CVBoxLayout
from plugins.workflows.widgets.multi_preview import MultiPreview
from utils import sql
from utils.helpers import display_message, try_parse_json


def run_entity_workflow_on_file(parent, entity_uuid, filepath, on_result, entity_table='entities'):
    """Run an entity's workflow on *filepath*, delivering a result image path to *on_result*.

    If the run produces a single ready image, *on_result* is called directly.
    Multiple or still-generating results open a RunWorkflowPopup to pick from.
    """
    asyncio.ensure_future(_run(parent, entity_uuid, entity_table, filepath, on_result))


async def _run(parent, entity_uuid, entity_table, filepath, on_result):
    from plugins.workflows.members.workflow import Workflow
    from plugins.workflows.utils.workflows import get_entity_workflow_config

    entity_name = sql.get_scalar(
        f"SELECT name FROM `{entity_table}` WHERE uuid = ?", (entity_uuid,)
    ) or 'Workflow'
    wf_config = get_entity_workflow_config(f'{entity_name}:{entity_table}:{entity_uuid}')
    if not wf_config:
        display_message(f"Couldn't load workflow for '{entity_name}'", "Run Workflow")
        return

    workflow = Workflow(
        main=find_main(),
        config=wf_config,
        kind='STUDIO',
        params={'filepath': filepath},
        chat_title=f'{entity_name}: {os.path.basename(filepath)}',
    )
    try:
        from plugins.workflows.utils.runs import get_run_manager
        await get_run_manager().start(workflow, notify=False)
    except Exception as e:
        display_message(f"Workflow error: {e}", "Run Workflow")
        return

    results = _collect_image_results(workflow, skip_paths={filepath})
    if not results:
        display_message(
            f"'{entity_name}' finished without producing an image", "Run Workflow"
        )
        return

    if len(results) == 1 and 'filepath' in results[0]:
        on_result(results[0]['filepath'])
        return

    popup = RunWorkflowPopup(parent, results, on_result)
    popup.show()


def _collect_image_results(workflow, skip_paths=None):
    """Gather image results from a workflow run's messages.

    Image results take the shapes MediaMember produces: an immediate
    {'filepath'} or an async {'request_id', 'model_name', 'provider'}.
    """
    skip_paths = skip_paths or set()
    results = []
    for msg in workflow.message_history.messages:
        _, parsed = try_parse_json(msg.content)
        if not isinstance(parsed, dict):
            continue
        result_path = parsed.get('filepath')
        if result_path:
            if result_path in skip_paths or not os.path.exists(result_path):
                continue
            try:
                with Image.open(result_path):
                    pass
            except Exception:
                continue  # not an image (eg. an audio/video result)
            results.append({'filepath': result_path})
        elif 'request_id' in parsed and 'model_name' in parsed:
            results.append({
                'request_id': parsed['request_id'],
                'model_name': parsed['model_name'],
                'provider': parsed.get('provider'),
            })
    return results


class RunWorkflowPopup(QDialog):
    """Modeless popup showing workflow results to pick from with a Use button."""

    def __init__(self, parent, results, on_result):
        super().__init__(parent)
        self.setWindowTitle("Workflow Results")
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.on_result = on_result

        self.layout = CVBoxLayout(self)
        self.multi_preview = MultiPreview(parent=self, on_use=self._use)
        self.layout.addWidget(self.multi_preview)
        self.resize(420, 260)

        self.multi_preview.set_results(results, _save=False)

    def _use(self, filepath):
        self.on_result(filepath)
        self.close()