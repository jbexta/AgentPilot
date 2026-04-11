"""Job Search and Submission API Adapters.

Provides a unified interface for searching jobs across multiple APIs
and submitting applications through ATS (Applicant Tracking System)
endpoints. Each adapter normalizes results into a common JobResult
dataclass.
"""

import asyncio
import base64
import json
import math
import re
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urlparse

import aiohttp


@dataclass
class JobResult:
    """Normalized job search result."""

    title: str = ''
    company: str = ''
    location: str = ''
    url: str = ''
    salary: str = ''
    description: str = ''
    source: str = ''
    ats_type: str = ''
    posted_date: str = ''
    remote: bool = False


class BaseJobAPI:
    """Base class for job search and submission adapters."""

    name = 'Base'

    async def search(self, query, location='', **kwargs):
        """Search for jobs. Returns list[JobResult]."""
        return []

    async def submit(self, job_url, resume_path, cover_letter,
                     applicant_info):
        """Submit an application. Returns dict with status/message."""
        return {'success': False, 'message': 'Submission not supported'}

    def can_submit(self, url):
        """Whether this adapter can submit to the given URL."""
        return False

    @staticmethod
    def _detect_ats_type(url):
        """Detect ATS type from a job URL."""
        if not url:
            return ''
        lower = url.lower()
        if 'greenhouse.io' in lower or 'boards.greenhouse' in lower:
            return 'Greenhouse'
        if 'smartrecruiters.com' in lower:
            return 'SmartRecruiters'
        if 'lever.co' in lower:
            return 'Lever'
        return ''


# ---------------------------------------------------------------------------
# Search-only adapters
# ---------------------------------------------------------------------------

class JSearchAPI(BaseJobAPI):
    """JSearch via RapidAPI - aggregates LinkedIn/Indeed/Glassdoor."""

    name = 'JSearch'

    async def search(self, query, location='', **kwargs):
        api_key = kwargs.get('api_key', '')
        if not api_key:
            return []

        max_results = kwargs.get('max_results', 50)
        params = {
            'query': f'{query} in {location}' if location else query,
            'page': '1',
            'num_pages': str(math.ceil(max_results / 10)),
        }
        work_type = kwargs.get('work_type', 'Any')
        if work_type == 'Remote':
            params['remote_jobs_only'] = 'true'

        job_type_map = {
            'Full-time': 'FULLTIME',
            'Part-time': 'PARTTIME',
            'Contract': 'CONTRACTOR',
            'Internship': 'INTERN',
        }
        job_type = kwargs.get('job_type', 'Any')
        if job_type in job_type_map:
            params['employment_types'] = job_type_map[job_type]

        headers = {
            'X-RapidAPI-Key': api_key,
            'X-RapidAPI-Host': 'jsearch.p.rapidapi.com',
        }
        results = []
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    'https://jsearch.p.rapidapi.com/search',
                    params=params, headers=headers, timeout=aiohttp.ClientTimeout(total=15),
                ) as resp:
                    if resp.status != 200:
                        return []
                    data = await resp.json()
            for job in data.get('data', []):
                results.append(JobResult(
                    title=job.get('job_title', ''),
                    company=job.get('employer_name', ''),
                    location=job.get('job_city', ''),
                    url=job.get('job_apply_link', '') or job.get('job_google_link', ''),
                    salary=self._format_salary(job),
                    description=job.get('job_description', ''),
                    source='JSearch',
                    ats_type=self._detect_ats_type(job.get('job_apply_link', '')),
                    posted_date=job.get('job_posted_at_datetime_utc', '')[:10],
                    remote=job.get('job_is_remote', False),
                ))
        except Exception:
            pass
        return results[:max_results]

    @staticmethod
    def _format_salary(job):
        lo = job.get('job_min_salary')
        hi = job.get('job_max_salary')
        if lo and hi:
            return f'${int(lo):,} - ${int(hi):,}'
        if lo:
            return f'${int(lo):,}+'
        return ''


class AdzunaAPI(BaseJobAPI):
    """Adzuna - supports 12+ countries with salary data."""

    name = 'Adzuna'

    async def search(self, query, location='', **kwargs):
        app_id = kwargs.get('adzuna_app_id', '')
        app_key = kwargs.get('adzuna_app_key', '')
        if not app_id or not app_key:
            return []

        max_results = kwargs.get('max_results', 50)
        country = kwargs.get('adzuna_country', 'us')
        per_page = min(max_results, 50)
        params = {
            'app_id': app_id,
            'app_key': app_key,
            'results_per_page': per_page,
            'what': query,
        }
        if location:
            params['where'] = location

        job_type = kwargs.get('job_type', 'Any')
        if job_type == 'Full-time':
            params['full_time'] = 1
        elif job_type == 'Part-time':
            params['part_time'] = 1

        min_salary = kwargs.get('min_salary', 0)
        max_salary = kwargs.get('max_salary', 0)
        if min_salary:
            params['salary_min'] = min_salary
        if max_salary:
            params['salary_max'] = max_salary

        total_pages = math.ceil(max_results / per_page)
        results = []
        try:
            async with aiohttp.ClientSession() as session:
                for page in range(1, total_pages + 1):
                    url = (
                        f'https://api.adzuna.com/v1/api/jobs/'
                        f'{country}/search/{page}'
                    )
                    async with session.get(
                        url, params=params,
                        timeout=aiohttp.ClientTimeout(total=15),
                    ) as resp:
                        if resp.status != 200:
                            break
                        data = await resp.json()
                    jobs = data.get('results', [])
                    if not jobs:
                        break
                    for job in jobs:
                        sal_min = job.get('salary_min')
                        sal_max = job.get('salary_max')
                        salary = ''
                        if sal_min and sal_max:
                            salary = (
                                f'${int(sal_min):,} - '
                                f'${int(sal_max):,}'
                            )
                        elif sal_min:
                            salary = f'${int(sal_min):,}+'
                        loc = job.get('location', {})
                        loc_parts = (
                            loc.get('display_name', '')
                            if isinstance(loc, dict) else ''
                        )
                        results.append(JobResult(
                            title=job.get('title', ''),
                            company=job.get(
                                'company', {}).get(
                                'display_name', ''),
                            location=loc_parts,
                            url=job.get('redirect_url', ''),
                            salary=salary,
                            description=job.get(
                                'description', ''),
                            source='Adzuna',
                            ats_type=self._detect_ats_type(
                                job.get('redirect_url', '')),
                            posted_date=job.get(
                                'created', '')[:10],
                        ))
                    if len(results) >= max_results:
                        break
        except Exception:
            pass
        return results[:max_results]


class TheMuseAPI(BaseJobAPI):
    """The Muse - free API, 500 req/hr."""

    name = 'The Muse'

    async def search(self, query, location='', **kwargs):
        max_results = kwargs.get('max_results', 50)
        params = {'page': 0}
        if query:
            params['category'] = query
        if location:
            params['location'] = location

        total_pages = math.ceil(max_results / 20)
        results = []
        try:
            async with aiohttp.ClientSession() as session:
                for page in range(total_pages):
                    params['page'] = page
                    async with session.get(
                        'https://www.themuse.com/api/public/jobs',
                        params=params,
                        timeout=aiohttp.ClientTimeout(total=15),
                    ) as resp:
                        if resp.status != 200:
                            break
                        data = await resp.json()
                    jobs = data.get('results', [])
                    if not jobs:
                        break
                    for job in jobs:
                        locs = job.get('locations', [])
                        loc_str = (
                            ', '.join(
                                l.get('name', '') for l in locs)
                            if locs else ''
                        )
                        results.append(JobResult(
                            title=job.get('name', ''),
                            company=job.get(
                                'company', {}).get('name', ''),
                            location=loc_str,
                            url=job.get('refs', {}).get(
                                'landing_page', ''),
                            description=job.get('contents', ''),
                            source='The Muse',
                            ats_type=self._detect_ats_type(
                                job.get('refs', {}).get(
                                    'landing_page', '')),
                            posted_date=job.get(
                                'publication_date', '')[:10],
                        ))
                    if len(results) >= max_results:
                        break
        except Exception:
            pass
        return results[:max_results]


class JobicyAPI(BaseJobAPI):
    """Jobicy - remote jobs only, free API."""

    name = 'Jobicy'

    async def search(self, query, location='', **kwargs):
        max_results = kwargs.get('max_results', 50)
        params = {'count': min(max_results, 50)}
        if query:
            params['tag'] = query

        results = []
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    'https://jobicy.com/api/v2/remote-jobs',
                    params=params, timeout=aiohttp.ClientTimeout(total=15),
                ) as resp:
                    if resp.status != 200:
                        return []
                    data = await resp.json()
            for job in data.get('jobs', []):
                results.append(JobResult(
                    title=job.get('jobTitle', ''),
                    company=job.get('companyName', ''),
                    location=job.get('jobGeo', 'Remote'),
                    url=job.get('url', ''),
                    salary=job.get('annualSalaryMin', ''),
                    description=job.get('jobDescription', ''),
                    source='Jobicy',
                    ats_type=self._detect_ats_type(job.get('url', '')),
                    posted_date=job.get('pubDate', '')[:10],
                    remote=True,
                ))
        except Exception:
            pass
        return results


class RemotiveAPI(BaseJobAPI):
    """Remotive - remote jobs only, free API."""

    name = 'Remotive'

    async def search(self, query, location='', **kwargs):
        max_results = kwargs.get('max_results', 50)
        params = {}
        if query:
            params['search'] = query

        results = []
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    'https://remotive.com/api/remote-jobs',
                    params=params, timeout=aiohttp.ClientTimeout(total=15),
                ) as resp:
                    if resp.status != 200:
                        return []
                    data = await resp.json()
            for job in data.get('jobs', [])[:max_results]:
                results.append(JobResult(
                    title=job.get('title', ''),
                    company=job.get('company_name', ''),
                    location=job.get('candidate_required_location', 'Remote'),
                    url=job.get('url', ''),
                    salary=job.get('salary', ''),
                    description=job.get('description', ''),
                    source='Remotive',
                    ats_type=self._detect_ats_type(job.get('url', '')),
                    posted_date=job.get('publication_date', '')[:10],
                    remote=True,
                ))
        except Exception:
            pass
        return results


class RemoteOKAPI(BaseJobAPI):
    """RemoteOK - remote jobs only, free API. Skip index 0 (metadata)."""

    name = 'RemoteOK'

    async def search(self, query, location='', **kwargs):
        max_results = kwargs.get('max_results', 50)
        headers = {'User-Agent': 'AgentPilot/1.0'}
        results = []
        try:
            url = 'https://remoteok.com/api'
            if query:
                url += f'?tags={query}'
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url, headers=headers, timeout=aiohttp.ClientTimeout(total=15),
                ) as resp:
                    if resp.status != 200:
                        return []
                    data = await resp.json(content_type=None)
            # Skip index 0 (legal/metadata)
            for job in data[1:max_results + 1]:
                tags = ', '.join(job.get('tags', []))
                results.append(JobResult(
                    title=job.get('position', ''),
                    company=job.get('company', ''),
                    location=job.get('location', 'Remote'),
                    url=job.get('url', ''),
                    salary=job.get('salary', ''),
                    description=job.get('description', ''),
                    source='RemoteOK',
                    ats_type=self._detect_ats_type(job.get('url', '')),
                    posted_date=job.get('date', '')[:10],
                    remote=True,
                ))
        except Exception:
            pass
        return results


class ReedAPI(BaseJobAPI):
    """Reed.co.uk - UK-focused, requires API key (basic auth)."""

    name = 'Reed'

    async def search(self, query, location='', **kwargs):
        api_key = kwargs.get('reed_api_key', '')
        if not api_key:
            return []

        max_results = kwargs.get('max_results', 50)
        per_page = min(max_results, 100)
        params = {'keywords': query, 'resultsToTake': per_page}
        if location:
            params['locationName'] = location

        min_salary = kwargs.get('min_salary', 0)
        max_salary = kwargs.get('max_salary', 0)
        if min_salary:
            params['minimumSalary'] = min_salary
        if max_salary:
            params['maximumSalary'] = max_salary

        auth = aiohttp.BasicAuth(api_key, '')
        results = []
        try:
            async with aiohttp.ClientSession(auth=auth) as session:
                skip = 0
                while len(results) < max_results:
                    params['resultsToSkip'] = skip
                    async with session.get(
                        'https://www.reed.co.uk/api/1.0/search',
                        params=params,
                        timeout=aiohttp.ClientTimeout(total=15),
                    ) as resp:
                        if resp.status != 200:
                            break
                        data = await resp.json()
                    jobs = data.get('results', [])
                    if not jobs:
                        break
                    for job in jobs:
                        sal_min = job.get('minimumSalary')
                        sal_max = job.get('maximumSalary')
                        salary = ''
                        if sal_min and sal_max:
                            salary = (
                                f'\u00a3{int(sal_min):,} - '
                                f'\u00a3{int(sal_max):,}'
                            )
                        elif sal_min:
                            salary = f'\u00a3{int(sal_min):,}+'
                        results.append(JobResult(
                            title=job.get('jobTitle', ''),
                            company=job.get('employerName', ''),
                            location=job.get(
                                'locationName', ''),
                            url=job.get('jobUrl', ''),
                            salary=salary,
                            description=job.get(
                                'jobDescription', ''),
                            source='Reed',
                            ats_type=self._detect_ats_type(
                                job.get('jobUrl', '')),
                            posted_date=job.get(
                                'date', '')[:10],
                        ))
                    skip += per_page
                    if len(jobs) < per_page:
                        break
        except Exception:
            pass
        return results[:max_results]


class USAJobsAPI(BaseJobAPI):
    """USAJobs - US government jobs, requires API key + email headers."""

    name = 'USAJobs'

    async def search(self, query, location='', **kwargs):
        api_key = kwargs.get('usajobs_api_key', '')
        email = kwargs.get('usajobs_email', '')
        if not api_key or not email:
            return []

        max_results = kwargs.get('max_results', 50)
        params = {
            'Keyword': query,
            'ResultsPerPage': min(max_results, 500),
        }
        if location:
            params['LocationName'] = location

        min_salary = kwargs.get('min_salary', 0)
        max_salary = kwargs.get('max_salary', 0)
        if min_salary:
            params['RemunerationMinimumAmount'] = min_salary
        if max_salary:
            params['RemunerationMaximumAmount'] = max_salary

        headers = {
            'Authorization-Key': api_key,
            'User-Agent': email,
            'Host': 'data.usajobs.gov',
        }
        results = []
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    'https://data.usajobs.gov/api/Search',
                    params=params, headers=headers,
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as resp:
                    if resp.status != 200:
                        return []
                    data = await resp.json()
            items = data.get('SearchResult', {}).get('SearchResultItems', [])
            for item in items:
                job = item.get('MatchedObjectDescriptor', {})
                pos_loc = job.get('PositionLocation', [])
                loc_str = pos_loc[0].get('LocationName', '') if pos_loc else ''
                sal = job.get('PositionRemuneration', [])
                salary = ''
                if sal:
                    lo = sal[0].get('MinimumRange', '')
                    hi = sal[0].get('MaximumRange', '')
                    if lo and hi:
                        salary = f'${int(float(lo)):,} - ${int(float(hi)):,}'
                results.append(JobResult(
                    title=job.get('PositionTitle', ''),
                    company=job.get('OrganizationName', ''),
                    location=loc_str,
                    url=job.get('PositionURI', ''),
                    salary=salary,
                    description=job.get('UserArea', {}).get('Details', {}).get('MajorDuties', [''])[0] if job.get('UserArea') else '',
                    source='USAJobs',
                    posted_date=job.get('PublicationStartDate', '')[:10],
                ))
        except Exception:
            pass
        return results


class CareerJetAPI(BaseJobAPI):
    """CareerJet - global aggregator via careerjet_api Python lib."""

    name = 'CareerJet'

    async def search(self, query, location='', **kwargs):
        affid = kwargs.get('careerjet_affid', '')
        if not affid:
            return []

        max_results = kwargs.get('max_results', 50)
        results = []
        try:
            from careerjet_api import CareerjetAPIClient
            cj = CareerjetAPIClient('en_US')
            resp = cj.search({
                'keywords': query,
                'location': location or '',
                'affid': affid,
                'pagesize': min(max_results, 99),
                'user_ip': '127.0.0.1',
                'user_agent': 'AgentPilot/1.0',
                'url': 'https://localhost',
            })
            for job in resp.get('jobs', []):
                results.append(JobResult(
                    title=job.get('title', ''),
                    company=job.get('company', ''),
                    location=job.get('locations', ''),
                    url=job.get('url', ''),
                    salary=job.get('salary', ''),
                    description=job.get('description', ''),
                    source='CareerJet',
                    ats_type=self._detect_ats_type(job.get('url', '')),
                    posted_date=job.get('date', ''),
                ))
        except ImportError:
            pass
        except Exception:
            pass
        return results


# ---------------------------------------------------------------------------
# ATS submission adapters
# ---------------------------------------------------------------------------

class GreenhouseAPI(BaseJobAPI):
    """Greenhouse ATS - public application submission endpoint."""

    name = 'Greenhouse'

    def can_submit(self, url):
        return 'greenhouse.io' in url.lower()

    def _parse_greenhouse_url(self, url):
        """Extract board token and job ID from a Greenhouse URL.

        Handles patterns like:
          boards.greenhouse.io/company/jobs/12345
        """
        m = re.search(
            r'boards\.greenhouse\.io/([^/]+)/jobs/(\d+)', url)
        if m:
            return m.group(1), m.group(2)
        return None, None

    async def submit(self, job_url, resume_path, cover_letter,
                     applicant_info):
        board, job_id = self._parse_greenhouse_url(job_url)
        if not board or not job_id:
            return {'success': False, 'message': 'Could not parse Greenhouse URL'}

        endpoint = (
            f'https://boards-api.greenhouse.io/v1/boards/'
            f'{board}/jobs/{job_id}/applications'
        )
        data = aiohttp.FormData()
        data.add_field('first_name', applicant_info.get('first_name', ''))
        data.add_field('last_name', applicant_info.get('last_name', ''))
        data.add_field('email', applicant_info.get('email', ''))
        if applicant_info.get('phone'):
            data.add_field('phone', applicant_info['phone'])
        if cover_letter:
            data.add_field('cover_letter', cover_letter)

        if resume_path:
            import os
            fname = os.path.basename(resume_path)
            with open(resume_path, 'rb') as f:
                data.add_field(
                    'resume', f.read(),
                    filename=fname,
                    content_type='application/pdf',
                )

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    endpoint, data=data,
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as resp:
                    body = await resp.text()
                    if resp.status in (200, 201):
                        return {'success': True, 'message': 'Application submitted via Greenhouse'}
                    return {'success': False, 'message': f'Greenhouse {resp.status}: {body[:200]}'}
        except Exception as e:
            return {'success': False, 'message': str(e)}


class SmartRecruitersAPI(BaseJobAPI):
    """SmartRecruiters ATS - JSON-based candidate submission."""

    name = 'SmartRecruiters'

    def can_submit(self, url):
        return 'smartrecruiters.com' in url.lower()

    def _parse_sr_url(self, url):
        """Extract company and posting UUID from a SmartRecruiters URL.

        Handles patterns like:
          jobs.smartrecruiters.com/Company/12345-posting-slug
        """
        m = re.search(
            r'smartrecruiters\.com/([^/]+)/([a-f0-9-]+)', url, re.I)
        if m:
            return m.group(1), m.group(2).split('-')[0]
        return None, None

    async def submit(self, job_url, resume_path, cover_letter,
                     applicant_info):
        company, posting_uuid = self._parse_sr_url(job_url)
        if not company or not posting_uuid:
            return {'success': False, 'message': 'Could not parse SmartRecruiters URL'}

        endpoint = (
            f'https://api.smartrecruiters.com/v1/companies/'
            f'{company}/postings/{posting_uuid}/candidates'
        )
        payload = {
            'firstName': applicant_info.get('first_name', ''),
            'lastName': applicant_info.get('last_name', ''),
            'email': applicant_info.get('email', ''),
        }
        if applicant_info.get('phone'):
            payload['phoneNumber'] = applicant_info['phone']
        if cover_letter:
            payload['messageToHiringManager'] = cover_letter

        if resume_path:
            import os
            with open(resume_path, 'rb') as f:
                resume_b64 = base64.b64encode(f.read()).decode()
            payload['resume'] = {
                'fileName': os.path.basename(resume_path),
                'data': resume_b64,
            }

        headers = {'Content-Type': 'application/json'}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    endpoint, json=payload, headers=headers,
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as resp:
                    body = await resp.text()
                    if resp.status in (200, 201):
                        return {'success': True, 'message': 'Application submitted via SmartRecruiters'}
                    return {'success': False, 'message': f'SmartRecruiters {resp.status}: {body[:200]}'}
        except Exception as e:
            return {'success': False, 'message': str(e)}


class LeverAPI(BaseJobAPI):
    """Lever ATS - multipart form submission."""

    name = 'Lever'

    def can_submit(self, url):
        return 'lever.co' in url.lower()

    def _parse_lever_url(self, url):
        """Extract company and posting ID from a Lever URL.

        Handles patterns like:
          jobs.lever.co/company/uuid
        """
        m = re.search(
            r'lever\.co/([^/]+)/([a-f0-9-]+)', url, re.I)
        if m:
            return m.group(1), m.group(2)
        return None, None

    async def submit(self, job_url, resume_path, cover_letter,
                     applicant_info):
        company, posting_id = self._parse_lever_url(job_url)
        if not company or not posting_id:
            return {'success': False, 'message': 'Could not parse Lever URL'}

        endpoint = (
            f'https://api.lever.co/v0/postings/'
            f'{company}/{posting_id}'
        )
        data = aiohttp.FormData()
        data.add_field('name',
                       f"{applicant_info.get('first_name', '')} "
                       f"{applicant_info.get('last_name', '')}".strip())
        data.add_field('email', applicant_info.get('email', ''))
        if applicant_info.get('phone'):
            data.add_field('phone', applicant_info['phone'])
        if cover_letter:
            data.add_field('comments', cover_letter)

        if resume_path:
            import os
            fname = os.path.basename(resume_path)
            with open(resume_path, 'rb') as f:
                data.add_field(
                    'resume', f.read(),
                    filename=fname,
                    content_type='application/pdf',
                )

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    endpoint, data=data,
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as resp:
                    body = await resp.text()
                    if resp.status in (200, 201):
                        return {'success': True, 'message': 'Application submitted via Lever'}
                    return {'success': False, 'message': f'Lever {resp.status}: {body[:200]}'}
        except Exception as e:
            return {'success': False, 'message': str(e)}


# ---------------------------------------------------------------------------
# Aggregator
# ---------------------------------------------------------------------------

class JobSearchAggregator:
    """Orchestrates searches across multiple APIs and routes submissions."""

    def __init__(self):
        self.search_adapters = {
            'JSearch': JSearchAPI(),
            'Adzuna': AdzunaAPI(),
            'The Muse': TheMuseAPI(),
            'Jobicy': JobicyAPI(),
            'Remotive': RemotiveAPI(),
            'RemoteOK': RemoteOKAPI(),
            'Reed': ReedAPI(),
            'USAJobs': USAJobsAPI(),
            'CareerJet': CareerJetAPI(),
        }
        self.submit_adapters = [
            GreenhouseAPI(),
            SmartRecruitersAPI(),
            LeverAPI(),
        ]

    async def search(self, query, location='', enabled_apis=None,
                     **kwargs):
        """Run search across enabled APIs, deduplicate by URL.

        Parameters
        ----------
        query : str
            Search keywords.
        location : str
            Location filter.
        enabled_apis : list[str] or None
            API names to query. None means all.
        **kwargs
            API keys and other adapter-specific options.
        """
        if enabled_apis is None:
            enabled_apis = list(self.search_adapters.keys())

        tasks = []
        for name in enabled_apis:
            adapter = self.search_adapters.get(name)
            if adapter:
                tasks.append(adapter.search(query, location, **kwargs))

        if not tasks:
            return []

        results_lists = await asyncio.gather(*tasks, return_exceptions=True)

        seen_urls = set()
        combined = []
        for result_list in results_lists:
            if isinstance(result_list, Exception):
                continue
            for job in result_list:
                if job.url and job.url not in seen_urls:
                    seen_urls.add(job.url)
                    if not job.ats_type:
                        job.ats_type = BaseJobAPI._detect_ats_type(job.url)
                    combined.append(job)

        # Client-side post-filtering
        work_type = kwargs.get('work_type', 'Any')
        min_salary = kwargs.get('min_salary', 0)
        max_salary = kwargs.get('max_salary', 0)

        if work_type == 'Remote':
            combined = [
                j for j in combined
                if j.remote
                or 'remote' in (j.location or '').lower()
            ]
        elif work_type == 'On-site':
            combined = [
                j for j in combined
                if not j.remote
                and 'remote' not in (j.location or '').lower()
            ]

        if min_salary or max_salary:
            combined = [
                j for j in combined
                if self._salary_in_range(
                    j.salary, min_salary, max_salary)
            ]

        return combined

    @staticmethod
    def _parse_salary_number(salary_str):
        """Extract the first numeric salary value from a string.

        Returns
        -------
        int or None
            The parsed salary, or None if unparseable.
        """
        if not salary_str:
            return None
        nums = re.findall(r'[\d,]+', salary_str)
        if not nums:
            return None
        try:
            return int(nums[0].replace(',', ''))
        except (ValueError, IndexError):
            return None

    @classmethod
    def _salary_in_range(cls, salary_str, min_sal, max_sal):
        """Check if a salary string falls within the given range.

        Jobs with unparseable or empty salary are kept (not excluded).
        """
        val = cls._parse_salary_number(salary_str)
        if val is None:
            return True
        if min_sal and val < min_sal:
            return False
        if max_sal and val > max_sal:
            return False
        return True

    async def submit(self, job_url, resume_path, cover_letter,
                     applicant_info):
        """Find the right ATS adapter and submit."""
        for adapter in self.submit_adapters:
            if adapter.can_submit(job_url):
                return await adapter.submit(
                    job_url, resume_path, cover_letter, applicant_info)
        return {'success': False, 'message': 'No ATS adapter found for this URL'}
