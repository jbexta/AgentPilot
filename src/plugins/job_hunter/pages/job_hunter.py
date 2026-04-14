import asyncio
import json
import webbrowser
from dataclasses import asdict

import qasync

from PySide6.QtWidgets import QPushButton, QCheckBox, QLabel
from PySide6.QtGui import Qt

from gui.widgets.config_tabs import ConfigTabs
from gui.widgets.config_joined import ConfigJoined
from gui.widgets.config_fields import ConfigFields
from gui.widgets.config_table import ConfigTable
from gui.widgets.config_db_tree import ConfigDBTree
from gui.util import CHBoxLayout
from utils import sql
from utils.helpers import (
    display_message, set_module_type, compute_workflow_async,
)

from plugins.job_hunter.controllers.job_apis import (
    JobSearchAggregator, JobResult,
)

sql.define_table('job_applications')


def _get_settings():
    """Load the persisted job_hunter_config from the settings table."""
    raw = sql.get_scalar(
        "SELECT value FROM settings WHERE field = 'job_hunter_config'")
    if raw:
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            pass
    return {}


def _ensure_settings_row():
    """Ensure a settings row exists for job_hunter_config."""
    exists = sql.get_scalar(
        "SELECT id FROM settings WHERE field = 'job_hunter_config'")
    if not exists:
        sql.execute(
            "INSERT INTO settings (field, value) VALUES (?, ?)",
            ('job_hunter_config', '{}'))


_ensure_settings_row()

_aggregator = JobSearchAggregator()


@set_module_type('Pages')
class Page_Job_Hunter(ConfigTabs):
    """Main job hunter page with Search, Applications, and Settings tabs."""

    display_name = 'Job Hunter'
    icon_path = ':/resources/icon-tasks.png'
    page_type = 'main'

    def __init__(self, parent):
        super().__init__(parent=parent)
        self.pages = {
            'Search': self.Search_Tab(parent=self),
            'Applications': self.Applications_Tab(parent=self),
            'Settings': self.Settings_Tab(parent=self),
        }

    # ------------------------------------------------------------------
    # Search Tab
    # ------------------------------------------------------------------
    class Search_Tab(ConfigJoined):
        """Keyword search form + results table."""

        def __init__(self, parent):
            super().__init__(
                parent=parent,
                layout_type='vertical',
                resizable=True,
            )
            self.widgets = [
                self.Search_Form(parent=self),
                self.Search_Results(parent=self),
            ]

        class Search_Form(ConfigFields):
            """Search parameters form."""

            def __init__(self, parent):
                super().__init__(
                    parent=parent,
                    propagate_config=False,
                    label_width=90,
                    schema=[
                        {
                            'text': 'Keywords',
                            'key': 'keywords',
                            'type': str,
                            'default': '',
                            'width': 250,
                            'row_key': 'row1',
                        },
                        {
                            'text': 'Location',
                            'key': 'location',
                            'type': str,
                            'default': '',
                            'width': 200,
                            'row_key': 'row1',
                        },
                        {
                            'text': 'Work Type',
                            'key': 'work_type',
                            'type': ('Any', 'Remote', 'Hybrid', 'On-site'),
                            'default': 'Any',
                            'row_key': 'row2',
                        },
                        {
                            'text': 'Job Type',
                            'key': 'job_type',
                            'type': (
                                'Any', 'Full-time', 'Part-time',
                                'Contract', 'Internship',
                            ),
                            'default': 'Any',
                            'row_key': 'row2',
                        },
                        {
                            'text': 'Min Salary',
                            'key': 'min_salary',
                            'type': int,
                            'default': 0,
                            'width': 100,
                            'row_key': 'row3',
                        },
                        {
                            'text': 'Max Salary',
                            'key': 'max_salary',
                            'type': int,
                            'default': 0,
                            'width': 100,
                            'row_key': 'row3',
                        },
                        {
                            'text': 'Max Results',
                            'key': 'max_results',
                            'type': int,
                            'default': 50,
                            'minimum': 10,
                            'maximum': 500,
                            'step': 10,
                            'width': 100,
                            'row_key': 'row3',
                        },
                    ],
                )

            def after_init(self):
                # API toggle checkboxes
                self.api_checkboxes = {}
                api_row = CHBoxLayout()
                api_label = QLabel('APIs:')
                api_label.setFixedWidth(90)
                api_row.addWidget(api_label)
                for api_name in _aggregator.search_adapters:
                    cb = QCheckBox(api_name)
                    cb.setChecked(True)
                    self.api_checkboxes[api_name] = cb
                    api_row.addWidget(cb)
                api_row.addStretch(1)
                self.layout.addLayout(api_row)

                # Search button
                btn_row = CHBoxLayout()
                self.btn_search = QPushButton('Search')
                self.btn_search.setFixedWidth(120)
                self.btn_search.clicked.connect(self.run_search)
                btn_row.addWidget(self.btn_search)
                self.search_status = QLabel('')
                btn_row.addWidget(self.search_status)
                btn_row.addStretch(1)
                self.layout.addLayout(btn_row)

                # Load defaults from settings
                settings = _get_settings()
                if settings.get('default_keywords'):
                    self.keywords_wgt.set_value(
                        settings['default_keywords'])
                if settings.get('default_location'):
                    self.location_wgt.set_value(
                        settings['default_location'])

            @qasync.asyncSlot()
            async def run_search(self):
                """Execute search across enabled APIs."""
                self.btn_search.setEnabled(False)
                self.search_status.setText('Searching...')

                keywords = self.keywords_wgt.get_value()
                location = self.location_wgt.get_value()
                work_type = self.work_type_wgt.get_value()
                job_type = self.job_type_wgt.get_value()
                min_salary = self.min_salary_wgt.get_value()
                max_salary = self.max_salary_wgt.get_value()
                max_results = self.max_results_wgt.get_value()

                enabled = [
                    name for name, cb in self.api_checkboxes.items()
                    if cb.isChecked()
                ]

                settings = _get_settings()
                kwargs = {
                    'api_key': settings.get('jsearch_api_key', ''),
                    'adzuna_app_id': settings.get('adzuna_app_id', ''),
                    'adzuna_app_key': settings.get('adzuna_app_key', ''),
                    'adzuna_country': settings.get(
                        'adzuna_country', 'us'),
                    'reed_api_key': settings.get('reed_api_key', ''),
                    'usajobs_api_key': settings.get(
                        'usajobs_api_key', ''),
                    'usajobs_email': settings.get(
                        'usajobs_email', ''),
                    'careerjet_affid': settings.get(
                        'careerjet_affid', ''),
                    'work_type': work_type,
                    'job_type': job_type,
                    'min_salary': min_salary,
                    'max_salary': max_salary,
                    'max_results': max_results,
                }

                try:
                    results = await _aggregator.search(
                        keywords, location, enabled, **kwargs)
                    results_widget = self.parent.widgets[1]
                    results_widget.populate(results)
                    self.search_status.setText(
                        f'Found {len(results)} jobs')
                except Exception as e:
                    self.search_status.setText(f'Error: {e}')
                finally:
                    self.btn_search.setEnabled(True)

        class Search_Results(ConfigTable):
            """Table displaying search results."""

            def __init__(self, parent):
                super().__init__(
                    parent=parent,
                    show_table_buttons=False,
                    full_row_select=True,
                    schema=[
                        {
                            'text': 'Title',
                            'key': 'title',
                            'width': 250,
                            'stretch': True,
                        },
                        {
                            'text': 'Company',
                            'key': 'company',
                            'width': 150,
                        },
                        {
                            'text': 'Location',
                            'key': 'location',
                            'width': 120,
                        },
                        {
                            'text': 'Salary',
                            'key': 'salary',
                            'width': 120,
                        },
                        {
                            'text': 'Source',
                            'key': 'source',
                            'width': 80,
                        },
                        {
                            'text': 'ATS',
                            'key': 'ats_type',
                            'width': 100,
                        },
                        {
                            'text': 'Posted',
                            'key': 'posted_date',
                            'width': 90,
                        },
                    ],
                )
                self._results = []

            def after_init(self):
                btn_row = CHBoxLayout()
                self.btn_save = QPushButton('Save')
                self.btn_save.setFixedWidth(80)
                self.btn_save.clicked.connect(self.save_selected)

                self.btn_apply = QPushButton('Quick Apply')
                self.btn_apply.setFixedWidth(100)
                self.btn_apply.clicked.connect(self.quick_apply)

                self.btn_open = QPushButton('Open in Browser')
                self.btn_open.setFixedWidth(120)
                self.btn_open.clicked.connect(self.open_in_browser)

                btn_row.addWidget(self.btn_save)
                btn_row.addWidget(self.btn_apply)
                btn_row.addWidget(self.btn_open)
                btn_row.addStretch(1)
                self.layout.addLayout(btn_row)

            def populate(self, results):
                """Load a list of JobResult into the table."""
                self._results = results
                rows = []
                for r in results:
                    rows.append([
                        r.title, r.company, r.location,
                        r.salary, r.source, r.ats_type,
                        r.posted_date,
                    ])
                self.table.load(rows, schema=self.schema)

            def _get_selected_job(self):
                """Return the JobResult for the selected row."""
                sel = self.table.selectionModel().currentIndex()
                if not sel.isValid():
                    return None
                source_idx = self.table.proxy_model.mapToSource(sel)
                row = source_idx.row()
                if 0 <= row < len(self._results):
                    return self._results[row]
                return None

            def save_selected(self):
                """Save selected job to the applications DB."""
                job = self._get_selected_job()
                if not job:
                    display_message('No job selected')
                    return
                config = json.dumps({
                    'url': job.url,
                    'salary': job.salary,
                    'description': job.description,
                    'ats_type': job.ats_type,
                    'source': job.source,
                    'location': job.location,
                    'company': job.company,
                    'status': 'saved',
                    'cover_letter': '',
                    'notes': '',
                    'posted_date': job.posted_date,
                    'remote': job.remote,
                })
                sql.execute(
                    "INSERT INTO job_applications (name, kind, config)"
                    " VALUES (?, 'JOB', ?)",
                    (job.title, config))
                display_message(f'Saved: {job.title}')

            def open_in_browser(self):
                """Open the selected job URL in the default browser."""
                job = self._get_selected_job()
                if not job or not job.url:
                    display_message('No job URL available')
                    return
                webbrowser.open(job.url)

            @qasync.asyncSlot()
            async def quick_apply(self):
                """Generate cover letter via LLM and submit through ATS."""
                job = self._get_selected_job()
                if not job:
                    display_message('No job selected')
                    return

                if not job.ats_type:
                    display_message(
                        'No ATS detected for this job. '
                        'Open in browser to apply manually.')
                    return

                settings = _get_settings()
                resume_path = settings.get('resume_path', '')
                applicant_info = {
                    'first_name': settings.get('first_name', ''),
                    'last_name': settings.get('last_name', ''),
                    'email': settings.get('email', ''),
                    'phone': settings.get('phone', ''),
                }

                # Check ATS auto-apply is enabled
                ats_key = f'enable_{job.ats_type.lower()}'
                if not settings.get(ats_key, False):
                    display_message(
                        f'{job.ats_type} auto-apply is disabled. '
                        f'Enable it in Settings.')
                    return

                # Generate cover letter via LLM
                cover_letter = ''
                template = settings.get('cover_letter_template', '')
                try:
                    prompt = (
                        f'Write a concise, professional cover letter '
                        f'for the following job:\n\n'
                        f'Title: {job.title}\n'
                        f'Company: {job.company}\n'
                        f'Description: {job.description[:1000]}\n\n'
                        f'Applicant: {applicant_info["first_name"]} '
                        f'{applicant_info["last_name"]}\n'
                    )
                    if template:
                        prompt += f'\nUse this template as a guide:\n{template}\n'
                    prompt += (
                        '\nReturn ONLY the cover letter text, '
                        'no extra commentary.'
                    )
                    from gui import system
                    cover_letter = await system.manager.blocks.compute_block_async(
                        'chat', {'user_msg': prompt})
                except Exception:
                    pass

                # Submit
                try:
                    result = await _aggregator.submit(
                        job.url, resume_path, cover_letter,
                        applicant_info)
                    status = 'applied' if result.get('success') else 'failed'
                    display_message(result.get('message', status))
                except Exception as e:
                    status = 'failed'
                    display_message(f'Submission error: {e}')

                # Save to applications DB
                config = json.dumps({
                    'url': job.url,
                    'salary': job.salary,
                    'description': job.description,
                    'ats_type': job.ats_type,
                    'source': job.source,
                    'location': job.location,
                    'company': job.company,
                    'status': status,
                    'cover_letter': cover_letter,
                    'notes': '',
                    'posted_date': job.posted_date,
                    'remote': job.remote,
                })
                sql.execute(
                    "INSERT INTO job_applications (name, kind, config)"
                    " VALUES (?, 'JOB', ?)",
                    (job.title, config))

    # ------------------------------------------------------------------
    # Applications Tab
    # ------------------------------------------------------------------
    class Applications_Tab(ConfigDBTree):
        """Track saved and applied jobs."""

        def __init__(self, parent):
            super().__init__(
                parent=parent,
                table_name='job_applications',
                kind='JOB',
                query="""
                    SELECT
                        name,
                        id,
                        COALESCE(json_extract(config, '$.company'), ''),
                        COALESCE(json_extract(config, '$.status'), 'saved'),
                        COALESCE(json_extract(config, '$.source'), ''),
                        COALESCE(json_extract(config, '$.location'), ''),
                        folder_id
                    FROM job_applications
                    WHERE kind = 'JOB'
                    ORDER BY id DESC""",
                schema=[
                    {
                        'text': 'Job Title',
                        'key': 'name',
                        'type': str,
                        'stretch': True,
                    },
                    {
                        'text': 'id',
                        'key': 'id',
                        'type': int,
                        'visible': False,
                    },
                    {
                        'text': 'Company',
                        'key': 'company',
                        'type': str,
                        'is_config_field': True,
                        'width': 150,
                    },
                    {
                        'text': 'Status',
                        'key': 'status',
                        'type': (
                            'saved', 'applied', 'interview',
                            'rejected', 'offer', 'failed',
                        ),
                        'is_config_field': True,
                        'width': 100,
                    },
                    {
                        'text': 'Source',
                        'key': 'source',
                        'type': str,
                        'is_config_field': True,
                        'width': 80,
                    },
                    {
                        'text': 'Location',
                        'key': 'location',
                        'type': str,
                        'is_config_field': True,
                        'width': 120,
                    },
                ],
                folder_key='job_applications',
                readonly=False,
                layout_type='vertical',
                config_widget=self.Application_Config(parent=self),
                add_item_options={
                    'title': 'Add Application',
                    'prompt': 'Enter a job title:',
                },
                del_item_options={
                    'title': 'Delete Application',
                    'prompt': 'Are you sure you want to delete this application?',
                },
            )

        class Application_Config(ConfigFields):
            """Detail view for a selected application."""

            def __init__(self, parent):
                super().__init__(
                    parent=parent,
                    label_width=100,
                    schema=[
                        {
                            'text': 'URL',
                            'key': 'url',
                            'type': str,
                            'default': '',
                            'width': 350,
                        },
                        {
                            'text': 'Salary',
                            'key': 'salary',
                            'type': str,
                            'default': '',
                            'width': 200,
                        },
                        {
                            'text': 'ATS Type',
                            'key': 'ats_type',
                            'type': str,
                            'default': '',
                            'width': 150,
                        },
                        {
                            'text': 'Description',
                            'key': 'description',
                            'type': str,
                            'default': '',
                            'num_lines': 6,
                            'stretch_y': True,
                        },
                        {
                            'text': 'Cover Letter',
                            'key': 'cover_letter',
                            'type': str,
                            'default': '',
                            'num_lines': 6,
                            'stretch_y': True,
                        },
                        {
                            'text': 'Notes',
                            'key': 'notes',
                            'type': str,
                            'default': '',
                            'num_lines': 4,
                            'stretch_y': True,
                        },
                    ],
                )

    # ------------------------------------------------------------------
    # Settings Tab
    # ------------------------------------------------------------------
    class Settings_Tab(ConfigFields):
        """API keys, applicant info, and default search preferences."""

        def __init__(self, parent):
            super().__init__(
                parent=parent,
                propagate_config=False,
                label_width=150,
                schema=[
                    # Applicant info
                    {
                        'text': 'First Name',
                        'key': 'first_name',
                        'type': str,
                        'default': '',
                        'width': 200,
                        'row_key': 'applicant',
                    },
                    {
                        'text': 'Last Name',
                        'key': 'last_name',
                        'type': str,
                        'default': '',
                        'width': 200,
                        'row_key': 'applicant',
                    },
                    {
                        'text': 'Email',
                        'key': 'email',
                        'type': str,
                        'default': '',
                        'width': 250,
                        'row_key': 'contact',
                    },
                    {
                        'text': 'Phone',
                        'key': 'phone',
                        'type': str,
                        'default': '',
                        'width': 200,
                        'row_key': 'contact',
                    },
                    {
                        'text': 'Resume',
                        'key': 'resume_path',
                        'type': 'file_picker',
                        'mode': 'directory',
                        'default': '',
                    },
                    # API Keys
                    {
                        'text': 'JSearch API Key',
                        'key': 'jsearch_api_key',
                        'type': str,
                        'default': '',
                        'width': 300,
                    },
                    {
                        'text': 'Adzuna App ID',
                        'key': 'adzuna_app_id',
                        'type': str,
                        'default': '',
                        'width': 200,
                        'row_key': 'adzuna',
                    },
                    {
                        'text': 'Adzuna App Key',
                        'key': 'adzuna_app_key',
                        'type': str,
                        'default': '',
                        'width': 200,
                        'row_key': 'adzuna',
                    },
                    {
                        'text': 'Reed API Key',
                        'key': 'reed_api_key',
                        'type': str,
                        'default': '',
                        'width': 300,
                    },
                    {
                        'text': 'USAJobs API Key',
                        'key': 'usajobs_api_key',
                        'type': str,
                        'default': '',
                        'width': 300,
                        'row_key': 'usajobs',
                    },
                    {
                        'text': 'USAJobs Email',
                        'key': 'usajobs_email',
                        'type': str,
                        'default': '',
                        'width': 250,
                        'row_key': 'usajobs',
                    },
                    {
                        'text': 'CareerJet Affid',
                        'key': 'careerjet_affid',
                        'type': str,
                        'default': '',
                        'width': 200,
                    },
                    # Auto-apply toggles
                    {
                        'text': 'Greenhouse',
                        'key': 'enable_greenhouse',
                        'type': bool,
                        'default': False,
                        'row_key': 'ats_toggles',
                    },
                    {
                        'text': 'SmartRecruiters',
                        'key': 'enable_smartrecruiters',
                        'type': bool,
                        'default': False,
                        'row_key': 'ats_toggles',
                    },
                    {
                        'text': 'Lever',
                        'key': 'enable_lever',
                        'type': bool,
                        'default': False,
                        'row_key': 'ats_toggles',
                    },
                    # Cover letter template
                    {
                        'text': 'Cover Letter Template',
                        'key': 'cover_letter_template',
                        'type': str,
                        'default': '',
                        'num_lines': 6,
                    },
                    # Default search prefs
                    {
                        'text': 'Default Keywords',
                        'key': 'default_keywords',
                        'type': str,
                        'default': '',
                        'width': 250,
                        'row_key': 'defaults',
                    },
                    {
                        'text': 'Default Location',
                        'key': 'default_location',
                        'type': str,
                        'default': '',
                        'width': 200,
                        'row_key': 'defaults',
                    },
                    {
                        'text': 'Adzuna Country',
                        'key': 'adzuna_country',
                        'type': (
                            'us', 'gb', 'au', 'ca', 'de', 'fr',
                            'in', 'nl', 'nz', 'pl', 'sg', 'za',
                        ),
                        'default': 'us',
                    },
                ],
            )
            self.data_source = {
                'table_name': 'settings',
                'data_column': 'value',
                'lookup_column': 'field',
                'lookup_value': 'job_hunter_config',
            }