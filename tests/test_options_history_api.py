from uuid import UUID
from fastapi.testclient import TestClient
import pytest
from app.config import Settings
from app.main import create_app


class NoGateway:
    async def snapshot(self, *args):
        raise AssertionError('Historical import must not fetch streaming quotes')


@pytest.fixture
def workflow(tmp_path):
    app = create_app(Settings(api_key='', offline=True, db_path=tmp_path / 'history.sqlite3'), options_provider=NoGateway())
    return TestClient(app), app


def test_source_immutability_and_no_client_verified_override(workflow):
    c, _ = workflow
    data = c.get('/api/options/history/demo').json()
    demo = c.post('/api/options/history/demo').json()
    UUID(demo['analysis_id'])
    assert demo['source']['kind'] == 'demo' and not demo['source']['verified']
    assert c.get('/api/options/analyses/' + demo['analysis_id']).json() == demo
    imported = c.post('/api/options/history/import', json=data).json()
    assert imported['source']['kind'] == 'import' and not imported['source']['verified']
    data['source'] = {'kind':'ibkr_historical','verified':True}
    assert c.post('/api/options/history/import', json=data).status_code == 422


def test_period_rag_followups_export_and_no_streaming_refresh(workflow):
    c, _ = workflow
    report = c.post('/api/options/history/demo').json()
    first = c.post('/api/chat', json={'message':'解释这段历史，为什么看跌成交不能说明多数人看空？','analysis_id':report['analysis_id']}).json()
    assert first['mode'] == 'offline' and first['sources']
    ctx = first['analysis_context']
    assert ctx['analysis_kind'] == 'historical_options' and ctx['period'] == report['period']
    assert ctx['retrieval']['hits'] and ctx['realtime_guaranteed'] is False
    assert all(item['id'].startswith('expert.') for item in first['sources'])
    sid = first['session_id']
    second = c.post('/api/chat', json={'session_id':sid,'message':'为什么？'}).json()
    assert second['analysis_context']['analysis_id'] == report['analysis_id']
    export = c.get(f'/api/sessions/{sid}/export').json()
    assert len(export['messages']) == 4 and export['messages'][-1]['analysis_context'] == second['analysis_context']
    before = c.get(f'/api/sessions/{sid}').json()
    response = c.post(f'/api/sessions/{sid}/analysis/refresh', json={'analysis_id':report['analysis_id']})
    assert response.status_code == 422 and response.json()['detail']['code'] == 'historical_refresh_requires_new_dataset'
    assert c.get(f'/api/sessions/{sid}').json() == before


def test_general_question_does_not_inherit_historical_evidence(workflow):
    c, _ = workflow
    report = c.post('/api/options/history/demo').json()
    first = c.post('/api/chat', json={'message':'解释历史样本','analysis_id':report['analysis_id']}).json()
    response = c.post('/api/chat', json={'session_id':first['session_id'],'message':'解释一下光合作用。'}).json()
    assert not response.get('analysis_context')
    assert response['active_analysis']['analysis_id'] == report['analysis_id']


def test_credentials_not_stored_in_import_metadata(workflow):
    c, app = workflow
    data = c.get('/api/options/history/demo').json()
    data['source_label'] = 'sk-' + 'x' * 32
    response = c.post('/api/options/history/import', json=data)
    assert response.status_code == 422 and response.json()['detail']['code'] == 'sensitive_credential'
    with app.state.store.connect() as db:
        assert db.execute('SELECT count(*) FROM option_analyses').fetchone()[0] == 0


def test_expert_retrieval_is_public_read_only_and_bounded(workflow):
    c, _ = workflow
    hits = c.get('/api/experts/search', params={'q':'未平仓量不是资金流入','limit':3}).json()
    assert 1 <= len(hits) <= 3 and hits[0]['retrieval']['embedding'] is False
    assert c.get('/api/experts/search', params={'q':'OI','limit':100}).status_code == 422
    assert not c.get('/api/sessions').json()['sessions']


def test_archived_broker_history_preserves_partial_coverage_and_missing_oi(workflow):
    c, _ = workflow
    response = c.post('/api/options/history/sample')
    assert response.status_code == 200
    report = response.json()
    assert report['source']['kind'] == 'ibkr_historical'
    assert report['source']['verification_scope'] and report['source']['archive_sha256']
    assert report['bar_basis'] == 'derived_from_intraday_trades'
    assert report['period'] == {'start':'2026-11-06','end':'2026-11-10'}
    assert report['daily'][0]['volume_total'] == 7386
    assert report['daily'][-1]['volume_total'] == 12835
    assert all(day['oi_total'] is None for day in report['daily'])
    assert all(item['delta'] is None for item in report['changes'])
    assert report['historical_capture']['history_requests'] == 3
    assert len(report['underlying_history']) == 3


def test_production_history_fetch_has_separate_transport_and_no_model(tmp_path):
    import json
    from app.config import ROOT
    capture = json.loads((ROOT / 'reports/ibkr_history_probe_v13.json').read_text(encoding='utf-8'))
    class HistoricalProvider:
        calls = []
        async def fetch(self, *args):
            self.calls.append(args)
            return capture
    provider = HistoricalProvider()
    app = create_app(Settings(api_key='', offline=True, db_path=tmp_path/'fetch.sqlite3'), options_provider=NoGateway(), history_provider=provider)
    c = TestClient(app)
    response = c.post('/api/options/history/fetch', json={'symbol':'AAPL','expiry':'2026-11-13','strike':350,'days':5})
    assert response.status_code == 200
    report = response.json()
    assert provider.calls == [('AAPL','2026-11-13',350,5)]
    assert report['source']['kind'] == 'ibkr_historical' and report['source']['verified']
    assert not c.get('/api/sessions').json()['sessions']
    assert report['analysis_id']


def test_underlying_comparison_uses_exact_option_period_endpoints():
    import json
    from app.config import ROOT
    from app.main import analyze_history_capture
    capture = json.loads((ROOT/'reports/ibkr_history_probe_v13.json').read_text(encoding='utf-8'))
    capture['dataset']['rows'] = [row for row in capture['dataset']['rows'] if row['trading_date'] != '2026-11-06']
    result = analyze_history_capture(capture)
    item = next(item for item in result['evidence'] if item['id'] == 'h.underlying.trade_close')
    assert item['previous_trading_date'] == '2026-11-09' and item['before'] == 350.49
    stock = next(item for item in capture['instruments'] if item['role'] == 'stock')
    stock['derived_daily'] = [row for row in stock['derived_daily'] if row['trading_date'] != '2026-11-09']
    result = analyze_history_capture(capture)
    item = next(item for item in result['evidence'] if item['id'] == 'h.underlying.trade_close')
    assert item['status'] == 'incomparable' and item['delta'] is None
