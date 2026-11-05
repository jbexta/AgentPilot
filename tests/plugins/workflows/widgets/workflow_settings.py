import json

from PySide6.QtCore import QPoint, QRectF, Qt
from PySide6.QtWidgets import QMessageBox, QWidget

from gui import system


def test_WorkflowSettings(self, main, ui):
    from gui.gui_utils.tree_dialog import TreeDialog
    on_main = ui.run_on_main

    # Check header_widget and workflow_buttons exist as QWidgets and verify the header is visible.
    assert isinstance(self.header_widget, QWidget), "WorkflowSettings.header_widget is missing or not a QWidget"
    assert isinstance(self.workflow_buttons, QWidget), "WorkflowSettings.workflow_buttons is missing or not a QWidget"
    assert on_main(self.header_widget.isVisible), "WorkflowSettings.header_widget should be visible when the widget is mounted in a visible page"

    # An empty workflow (e.g. a fresh embedded chat) is valid.
    members = on_main(lambda: dict(self.members_in_view))

    # Walk every member and verify it carries a member_config and is typed.
    for member_id, member in members.items():
        assert getattr(member, 'member_config', None), f"Member {member_id!r} has no member_config"
        assert '_TYPE' in member.member_config or getattr(member, 'member_type', None), f"Member {member_id!r} has neither member_config['_TYPE'] nor a member_type attribute"

    # Serialize via get_config() and verify the required keys, type, and member count.
    config = on_main(self.get_config)
    for key in ('_TYPE', 'name', 'members', 'options'):  # 'inputs',
        assert key in config, f"WorkflowSettings.get_config() missing key {key!r}"
    assert config['_TYPE'] == 'workflow', f"WorkflowSettings.get_config()['_TYPE'] == {config['_TYPE']!r}, expected 'workflow'"
    assert len(config['members']) == len(members), f"get_config()['members'] has {len(config['members'])} entries but members_in_view has {len(members)}"

    # Reach into workflow_buttons and verify the inner toolbar exposes the expected toggle buttons.
    inner = getattr(self.workflow_buttons, 'inner_widget', None)
    assert inner is not None, "WorkflowSettings.workflow_buttons has no inner_widget toolbar"
    for btn_attr in ('btn_workflow_params', 'btn_description', 'btn_workflow_options'):
        assert hasattr(inner, btn_attr), f"WorkflowSettings.workflow_buttons.inner_widget is missing {btn_attr!r}"

    # Toggle workflow_params on then off and verify the panel follows.
    params_btn = inner.btn_workflow_params
    started = on_main(self.workflow_params.isVisible)
    ui.click_widget(params_btn)
    ui.wait_until(lambda: self.workflow_params.isVisible() != started,
                  message="Toggling btn_workflow_params did not change workflow_params visibility")
    ui.click_widget(params_btn)
    ui.wait_until(lambda: self.workflow_params.isVisible() == started,
                  message="Second toggle of btn_workflow_params did not restore workflow_params visibility")

    # For the agent member, add → edit → delete via real OS
    # input events. Driving the UI through pyautogui keeps every QObject
    # mutation on the GUI thread (Qt processes the synthesized events in
    # its event loop), so DraggableMember construction is thread-safe.
    toolbar = self.workflow_buttons.inner_widget
    btn_add = toolbar.btn_add
    btn_delete = toolbar.btn_delete
    member_ids = lambda: set(self.members_in_view.keys())

    member_modules = system.manager.modules.get_modules_in_folder(
        module_type='Members',
        fetch_keys=('name', 'kind_folder', 'class',),
    )
    # Delete is only offered with more than one other member, so the
    # add -> delete cycle needs one already there.
    if on_main(self.count_other_members) < 1:
        return
    for module_name, kind_folder, module_class in member_modules:
        if module_name != 'agent':
            continue
        insert_mode = getattr(module_class, 'workflow_insert_mode', None)
        if not insert_mode:
            continue

        start_ids = on_main(member_ids)

        # Add: open the workflow_buttons "Add" popup menu and click the
        # action for this member type.
        ui.click_widget(btn_add)
        ui.choose_menu_action(module_name.replace('_', ' ').title())

        # 'list' members open an entity picker first. Its blank row (e.g.
        # "Empty agent") carries a config of this member type; saved
        # entities are whole workflows. Double-clicking the blank row
        # closes the picker and starts the ghost.
        if insert_mode == 'list':
            picker = ui.wait_for_modal(TreeDialog)

            def blank_row():
                for item in picker.tree_widget.findItems('', Qt.MatchContains | Qt.MatchRecursive):
                    data = item.data(0, Qt.UserRole)
                    if isinstance(data, dict) and json.loads(data.get('config') or '{}').get('_TYPE') == module_name:
                        return item.text(0)
                return None
            entity = ui.run_on_main(blank_row)
            assert entity is not None, f"Entity picker for {module_name!r} has no blank {module_name!r} row"
            ui.click_tree_item_cell(picker.tree_widget, entity, 0, double=True)
            ui.wait_until(lambda: not picker.isVisible(),
                          message=f"Entity picker for {module_name!r} stayed open after choosing a row")

        # Commit the ghost (centred on the cursor) at the free spot closest
        # to the middle, so it can't land under an existing member.
        def free_spot(half=35, step=10):
            viewport = self.view.viewport()
            center = viewport.rect().center()
            taken = [m.member_ellipse.sceneBoundingRect() for m in self.members_in_view.values()]
            offsets = sorted(
                ((dx, dy) for dx in range(-center.x(), center.x(), step)
                 for dy in range(-center.y(), center.y(), step)),
                key=lambda o: o[0] ** 2 + o[1] ** 2,
            )
            for dx, dy in offsets:
                pt = center + QPoint(dx, dy)
                scene_pt = self.view.mapToScene(pt)
                area = QRectF(scene_pt.x() - half, scene_pt.y() - half, 2 * half, 2 * half)
                if not any(area.intersects(r) for r in taken):
                    global_pt = viewport.mapToGlobal(pt)
                    return global_pt.x(), global_pt.y()
            return None
        spot = ui.run_on_main(free_spot)
        assert spot is not None, "No free spot in the workflow view for a new member"
        ui.click_coords(*spot)
        new_ids = ui.wait_until(
            lambda: member_ids() - start_ids,
            message=f"Adding {module_name!r} produced no new member",
        )
        assert len(new_ids) == 1, f"Adding {module_name!r} produced {len(new_ids)} new members, expected 1"
        new_id = next(iter(new_ids))
        new_member = on_main(lambda: self.members_in_view[new_id])
        assert new_member.member_config.get('_TYPE') == module_name, f"New {module_name!r} member has _TYPE={new_member.member_config.get('_TYPE')!r}"

        # Edit: mutate the member_config dict and trigger update_config
        # via a synthesized click on the member (selection re-runs the
        # config flow on the GUI thread). Verify the edit lands in
        # get_config()['members'].
        edited_name = f"Edited_{module_name}"
        new_member.member_config['name'] = edited_name
        ui.click_widget(new_member.member_ellipse)
        ui.wait_until(new_member.isSelected,
                      message=f"Clicking the new {module_name!r} member did not select it")

        def serialized():
            return next((m for m in self.get_config()['members'] if m['id'] == new_id), None)
        ui.wait_until(serialized, message=f"Edited {module_name!r} member missing from get_config()['members']")
        saved_name = on_main(serialized)['config'].get('name')
        assert saved_name == edited_name, f"Edited {module_name!r} member name={saved_name!r}, expected {edited_name!r}"

        # Delete: the delete button shows an Ok/Cancel confirmation.
        ui.wait_until(lambda: btn_delete.isVisible() and btn_delete.isEnabled(),
                      message=f"Delete button not shown for the selected {module_name!r} member")
        ui.click_widget(btn_delete)
        ui.confirm(QMessageBox.Ok)
        ui.wait_until(lambda: new_id not in self.members_in_view,
                      message=f"Deleting {module_name!r} member {new_id!r} left it in members_in_view")
