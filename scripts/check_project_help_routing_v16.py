"""Local designed-case regression; no model, HTTP, user DB or broker.

This is not a blind benchmark or an answer-accuracy measurement. A parent route
expectation without a query accepts an explicit child query or guide anchor;
query-specific expectations remain exact. Public manual source links count as
offered guide navigation. Semantic fact checks still require human review.
"""
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import sys
from urllib.parse import urlsplit

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app.project_help import ProjectHelp


def compatible(actual,expected):
    a,e=urlsplit(actual),urlsplit(expected)
    if not actual.startswith('/') or actual.startswith('//') or a.scheme or a.netloc:
        return False
    return a.path==e.path and (not e.query or a.query==e.query) and (not e.fragment or a.fragment==e.fragment)


def main():
    h=ProjectHelp()
    path=ROOT/'evaluation/project_help_cases_v16.json'
    cases=json.loads(path.read_text(encoding='utf-8'))['cases']
    rows=[]
    for case in cases:
        found=h.resolve(case['message'],language=case.get('language','zh'))
        routing=bool(found)==case['expected_project_help']
        if found and case.get('expected_any_topic_ids'):
            routing=routing and bool(set(case['expected_any_topic_ids'])&set(found['topic_ids']))
        routes=[x['url'] for x in found['links']+found['sources']] if found else []
        navigation=not case.get('expected_any_routes') or bool(found) and any(compatible(actual,expected) for actual in routes for expected in case['expected_any_routes'])
        rows.append({'id':case['id'],'passed':bool(routing and navigation),'routing_and_topic_passed':bool(routing),'navigation_passed':bool(navigation),'actual_topics':found['topic_ids'] if found else []})
    now=datetime.now(UTC)
    report={'checked_at':now.isoformat(),'status':'passed' if all(x['passed'] for x in rows) else 'failed',
        'scope':__doc__,'total':len(rows),'passed':sum(x['passed'] for x in rows),'cases':rows,
        'source_sha256':{name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in ('app/project_help.py','data/project_help.json','evaluation/project_help_cases_v16.json')},
        'external_model_calls':0,'broker_calls':0,'user_database_reads':0,
        'prior_strict_route_rule':'Initial audit compared only direct links by exact URL and overlooked valid parent query routes/manual source anchors. That failed report is retained; the actual three missed usage phrasings were fixed and included in pytest.'}
    target=ROOT/'reports/project_help_routing_v16.json'
    if target.exists():target=target.with_stem(target.stem+'-'+now.strftime('%Y%m%dT%H%M%S%fZ'))
    target.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'status':report['status'],'passed':report['passed'],'total':len(rows),'report':str(target)},ensure_ascii=False))
    return 0 if report['status']=='passed' else 1


if __name__=='__main__':
    raise SystemExit(main())
