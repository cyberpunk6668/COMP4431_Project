"""Opt-in actual model check over an existing immutable IBKR snapshot.

No --live: no HTTP, broker or model requests. --live: one loopback GET of an
existing v12 snapshot, then one real OptionsChat turn (at most one repair).
It never collects quotes or changes sessions, account state or the saved report.
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
QUESTION = "复盘这批保存的期权样本：请结合报价覆盖解释它的局限，为什么不能据此判断现在市场看空？再用专家依据解释合约计数不是人数。不要更新行情。"


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False).encode()).hexdigest()


async def run(args):
    import httpx
    from app.config import Settings
    from app.expert_knowledge import ExpertKnowledge
    from app.llm import DeepSeek
    from app.options_chat import OptionsChat, _evidence, describe_analysis
    from scripts.check_options_chat_live_v10 import safe_text

    settings = Settings()
    if not settings.online:
        raise RuntimeError("Configured cloud model is required for --live")
    previous = json.loads((ROOT / 'reports/ibkr_browser_live_v12.json').read_text(encoding='utf-8'))
    identifier = previous['new_analysis_id']
    async with httpx.AsyncClient(base_url=args.base, timeout=15, follow_redirects=False) as client:
        response = await client.get('/api/options/analyses/' + identifier)
        response.raise_for_status()
        record = response.json()
    assert record['analysis_id'] == identifier and record['snapshot']['source'] == 'ibkr'
    original_hash = digest(record)
    if args.diagnostics:
        os.environ['FINPILOT_OPTIONS_MODEL_DIAGNOSTICS'] = '1'
    answer = await OptionsChat(settings, DeepSeek(settings)).answer(QUESTION, [], 'zh', 'deepseek', record)
    report = {'checked_at': datetime.now(UTC).isoformat(), 'status': 'failed',
              'scope': 'Existing actual IBKR snapshot, one real model question; zero new market-data requests and zero session mutations.',
              'snapshot_source_report': 'reports/ibkr_browser_live_v12.json', 'analysis_id': identifier,
              'snapshot_fingerprint': original_hash, 'broker_requests': 0, 'session_mutations': 0,
              'mode': answer.get('mode'), 'warning': answer.get('warning'),
              'generation_attempts': answer.get('generation_attempts'), 'schema_repair_attempts': answer.get('schema_repair_attempts'),
              'answer_excerpt': safe_text(answer.get('answer', ''))[:6500],
              'grounding': answer.get('analysis_context', {}).get('grounding'),
              'sources': answer.get('sources', []), 'analysis_context': answer.get('analysis_context')}
    assert digest(record) == original_hash
    if answer.get('mode') == 'deepseek' and not answer.get('warning'):
        context = answer['analysis_context']
        assert context['analysis_id'] == identifier and context['realtime_guaranteed'] is False
        assert context['evidence'] and context['expert_source_ids']
        assert context['retrieval']['corpus_sha256'] == ExpertKnowledge().corpus_sha256
        assert 'put_call_limits' in context['grounding']['covered_facets']
        original = _evidence(record, describe_analysis(record), 'zh')
        for item in context['evidence']:
            assert item == original[item['id']]
        report['status'] = 'passed_limited'
    target = ROOT / 'reports/snapshot_expert_cloud_v14.json'
    if target.exists():
        target = target.with_stem(target.stem + '-' + datetime.now(UTC).strftime('%Y%m%dT%H%M%S%fZ'))
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    print(json.dumps({key: report[key] for key in ('status', 'mode', 'warning', 'generation_attempts', 'schema_repair_attempts', 'broker_requests')}, ensure_ascii=False))
    print(target.relative_to(ROOT).as_posix())
    return 0 if report['status'] == 'passed_limited' else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live', action='store_true')
    parser.add_argument('--diagnostics', action='store_true', help='Opt-in redacted failed-output diagnostics in this process only')
    parser.add_argument('--base', default='http://127.0.0.1:8000', choices=['http://127.0.0.1:8000'])
    args = parser.parse_args()
    if not args.live:
        parser.print_help()
        print('No --live: zero external calls, no state changes.')
        return 0
    return asyncio.run(run(args))


if __name__ == '__main__':
    raise SystemExit(main())
