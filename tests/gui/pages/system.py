def test_Page_System_Settings(self, main, ui):
    """Toggle fields that drive other widgets and restore them."""
    import time
    from gui.demo import _run_on_main as run_on_main

    fields = self.widgets[0]

    def config_value(key):
        return run_on_main(lambda: fields.get_config().get(key))

    # Auto title shows/hides its dependent model + prompt fields
    ui.testing('auto title toggle')
    orig_auto_title = run_on_main(fields.auto_title_wgt.isChecked)
    for _ in range(2):
        ui.click_widget(fields.auto_title_wgt)
        time.sleep(0.3)
        checked = run_on_main(fields.auto_title_wgt.isChecked)
        for dep in ('auto_title_model_wgt', 'auto_title_prompt_wgt'):
            hidden = run_on_main(getattr(fields, dep).isHidden)
            assert hidden != checked, (
                f"{dep} visibility doesn't follow auto_title={checked}"
            )
        assert config_value('system.auto_title') == checked, (
            "auto_title checkbox didn't propagate to config"
        )
    assert run_on_main(fields.auto_title_wgt.isChecked) == orig_auto_title

    # has_toggle fields drop their key from config when unchecked
    for key in ('auto_run_tools', 'auto_run_code'):
        ui.testing(f'{key} toggle')
        toggle = getattr(fields, f'{key}_tgl')
        widget = getattr(fields, f'{key}_wgt')
        orig_checked = run_on_main(toggle.isChecked)
        for _ in range(2):
            ui.click_widget(toggle)
            time.sleep(0.3)
            checked = run_on_main(toggle.isChecked)
            assert run_on_main(widget.isHidden) != checked, (
                f"{key} field visibility doesn't follow its toggle"
            )
            has_key = config_value(f'system.{key}') is not None
            assert has_key == checked, (
                f"{key} config presence doesn't follow its toggle"
            )
        assert run_on_main(toggle.isChecked) == orig_checked
