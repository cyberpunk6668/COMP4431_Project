"""Opt-in, two-turn real DeepSeek acceptance over a private application DB.

No normal server, user chat, native window or broker is used. --live permits
at most four provider requests (one generation plus one schema repair per
turn). No script retries. Default only prints this policy.
"""
from datetime import UTC, datetime
import argparse
import hashlib
import json
import os
import re
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
QUESTIONS = (
    "请用白话解释这份合成教学试算的成本、到期盈亏平衡和最大损失。保留教学日期、数据依据和适用边界。",
    "为什么这份试算中标的到期上涨仍可能亏损？请解释权利金的作用，并说明为什么不能用它预测当前市场。",
)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live',action='store_true')
    parser.add_argument('--diagnostic-one-turn',action='store_true',help='One bounded turn; retain synthetic-only raw generation and validation errors')
    args=parser.parse_args()
    if not args.live:
        print(json.dumps({'live':False,'turns':2,'maximum_provider_requests':4,
                          'script_retries':0,'broker_requests':0,'user_database':False},ensure_ascii=False))
        return 0
    stamp=datetime.now(UTC).strftime('%Y%m%dT%H%M%S%fZ')
    scratch=ROOT/'tmp/options-lab-live-v17'/stamp
    scratch.mkdir(parents=True,exist_ok=False)
    os.environ['FINPILOT_DB']=str(scratch/'owned.sqlite3')
    os.environ['IBKR_ENABLED']='false'
    os.environ['FINPILOT_OPTIONS_MODEL_DIAGNOSTICS']='0'
    os.environ['FINPILOT_OFFLINE']='false'
    sys.path.insert(0,str(ROOT))
    from app.config import Settings
    from app.main import create_app
    from fastapi.testclient import TestClient

    class NoBroker:
        async def snapshot(self,*args,**kwargs):
            raise AssertionError('Broker prohibited in synthetic learning acceptance')
        async def fetch(self,*args,**kwargs):
            raise AssertionError('History broker prohibited in learning acceptance')

    settings=Settings(db_path=scratch/'owned.sqlite3',offline=False)
    if not settings.online:
        print(json.dumps({'status':'not_run','reason':'cloud_unconfigured'}))
        return 2
    app=create_app(settings,options_provider=NoBroker(),history_provider=NoBroker())
    complete=app.state.history_chat.cloud.complete
    calls=[]
    questions=QUESTIONS[:1] if args.diagnostic_one_turn else QUESTIONS
    limit=len(questions)*2
    import app.history_chat as history_module
    validate=history_module._validate
    def traced_validate(*values,**kwargs):
        try:return validate(*values,**kwargs)
        except (ValueError,TypeError) as error:
            if calls:calls[-1]['validation_error']=str(error)[:1400]
            raise
    history_module._validate=traced_validate
    async def bounded(messages,**kwargs):
        if len(calls)>=limit:raise AssertionError('Live request ceiling reached')
        entry={'number':len(calls)+1,'json_output':kwargs.get('json_output',False)}
        calls.append(entry)
        start=time.perf_counter()
        try:
            value=await complete(messages,**kwargs)
            entry['returned']=True
            entry['synthetic_only_raw_response']=re.sub(r'\bsk-[A-Za-z0-9_-]{6,}', '[credential-redacted]',value[:18000])
            return value
        except Exception as error:
            entry['error_code']=getattr(error,'code',type(error).__name__)
            raise
        finally:entry['elapsed_seconds']=round(time.perf_counter()-start,3)
    app.state.history_chat.cloud.complete=bounded
    report={'checked_at':datetime.now(UTC).isoformat(),'status':'failed',
            'scope':'Real DeepSeek through application HTTP routes (ASGI TestClient), private DB, synthetic teaching report; not current market, broker or native UI acceptance.',
            'questions':list(questions),'calls':calls,'turns':[],'model':settings.model,
            'broker_requests':0,'script_retries':0,'maximum_provider_requests':limit,
            'normal_server_accessed':False,'user_chat_database_read':False,
            'database':str((scratch/'owned.sqlite3').relative_to(ROOT)),
            'manual_semantic_review':'pending',
            'limits':['Finite schema, citation, numeric-card and selected-claim checks are not a universal financial correctness guarantee.','Scenario quotes, IV and dates are authored assumptions; no real investment performance is measured.']}
    try:
        with TestClient(app) as client:
            saved=client.post('/api/options-lab/save',json={'expiry_price':102}).json()
            aid=saved['analysis_id']
            report['analysis_id']=aid
            report['trial']=saved['lab_context']['trial']
            session=client.post('/api/sessions',json={'title':'Owned v17 real model acceptance'}).json()['id']
            assert client.put(f'/api/sessions/{session}/analysis',json={'analysis_id':aid}).status_code==200
            assert not calls, 'Startup/save/bind generated unexpectedly'
            for question in questions:
                tick=time.perf_counter()
                response=client.post('/api/chat',json={'session_id':session,'message':question,'engine':'deepseek','language':'zh'})
                response.raise_for_status()
                result=response.json()
                ctx=result.get('analysis_context',{})
                trial=ctx.get('lab_context',{}).get('trial',{})
                evidence_ids=ctx.get('evidence_ids',[])
                checks={
                    'actual_cloud_mode':result.get('mode')=='deepseek' and not result.get('warning'),
                    'same_bound_report':ctx.get('analysis_id')==aid,
                    'saved_inputs':trial.get('expiry_price')==102 and trial.get('cost')==360 and trial.get('pnl')==-160,
                    'synthetic_provenance':ctx.get('lab_context',{}).get('synthetic') is True and ctx.get('source_verified') is False,
                    'local_trial_references':any(str(x).startswith('h.lab.trial.') for x in evidence_ids),
                    'bounded_generations':result.get('generation_attempts',0) in (1,2) and result.get('schema_repair_attempts',0)<=1,
                    'dated_notice':'2026-11-11' in result.get('answer','') and '合成' in result.get('answer',''),
                }
                report['turns'].append({'question':question,'checks':checks,'passed':all(checks.values()),
                                        'elapsed_seconds':round(time.perf_counter()-tick,3),'result':result})
            messages=client.get(f'/api/sessions/{session}').json()['messages']
            report['persisted_turns']=len(messages)//2
            report['immutable_saved_context']=all(messages[i*2+1]['analysis_context']==item['result']['analysis_context'] for i,item in enumerate(report['turns']))
            report['status']='passed' if all(x['passed'] for x in report['turns']) and len(messages)==len(questions)*2 and report['immutable_saved_context'] else 'failed'
    except Exception as error:
        report['error_type']=type(error).__name__
        report['error_code']=getattr(error,'code',None)
    finally:
        history_module._validate=validate
        report['source_sha256']={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in
            ('app/options_lab.py','app/history_chat.py','app/main.py','app/expert_grounding.py','data/options_lab_knowledge.json')}
        target=ROOT/'reports'/('options_lab_live_v17-'+stamp+'.json')
        target.write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
        print(json.dumps({'status':report['status'],'turns':len(report['turns']),'provider_requests':len(calls),'report':target.relative_to(ROOT).as_posix()}))
    return 0 if report['status']=='passed' else 1


if __name__=='__main__':raise SystemExit(main())
