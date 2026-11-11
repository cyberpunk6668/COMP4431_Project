"""The original options chat uses reviewed experts without replacing local data."""
import json
import pytest

from test_options_chat import answer, reply, report, service, Provider
from app.expert_knowledge import ExpertKnowledge
from app.expert_grounding import retrieve_expert_context


def test_snapshot_explanation_has_separate_expert_and_numeric_provenance():
    output = reply("看跌成交不能直接解释成看空人数，交易也可能用于对冲或组合策略。", ["expert.put_call"])
    chat, cloud = service(output)
    result = answer(chat, "为什么看跌成交更多不能说明多数人看空？")
    assert result['mode'] == 'deepseek' and not result.get('warning')
    assert result['sources'][0]['id'] == 'expert.put_call'
    assert result['analysis_context']['evidence'] == []
    assert result['analysis_context']['expert_source_ids'] == ['expert.put_call']
    trace = result['analysis_context']['retrieval']
    assert trace['knowledge_version'] == chat.knowledge.version
    assert trace['corpus_sha256'] == chat.knowledge.corpus_sha256
    assert result['analysis_context']['grounding']['paragraphs'][0]['supporting_sources']['put_call_limits'] == ['expert.put_call']
    sent = json.loads(cloud.calls[0]['messages'][-1]['content'])
    assert 'expert.put_call' in {doc['id'] for doc in sent['expert_sources']}


def test_wrong_but_known_source_cannot_silently_support_a_different_claim():
    output = reply("看跌成交不是看空人数。", ['expert.history_limits'])
    chat, cloud = service(output)
    result = answer(chat, '已到期期权历史限制能解释为什么看跌成交不是看空人数吗？')
    assert result['mode'] == 'offline' and result['warning'] == 'options_answer_validation_failed'
    assert len(cloud.calls) == 2


def test_citation_repair_can_use_original_prompt_source_but_cannot_add_data():
    class Sequence(Provider):
        async def complete(self, messages, **kwargs):
            self.calls.append({'messages':messages,'kwargs':kwargs})
            return (reply('看跌成交不是看空人数。', ['expert.history_limits']) if len(self.calls)==1
                    else reply('看跌成交不是看空人数。', ['expert.put_call']))
    from app.options_chat import OptionsChat
    from app.config import Settings
    cloud=Sequence()
    chat=OptionsChat(Settings(api_key='test-only'),cloud)
    result=answer(chat,'为什么看跌成交不能说明多数人看空？')
    assert result['mode']=='deepseek' and result['schema_repair_attempts']==1
    assert result['sources'][0]['id']=='expert.put_call'
    payload=json.loads(cloud.calls[1]['messages'][-1]['content'])
    allowed=payload['schema_repair']['allowed_evidence_ids']
    assert 'expert.put_call' in allowed and not any(key.startswith('g0.') for key in allowed)
    plan=payload['schema_repair']['citation_repairs'][0]
    assert plan['paragraph']==1 and plan['missing_facets']==['put_call_limits']
    assert plan['candidates_by_facet']['put_call_limits']==['expert.put_call']
    assert 'text' not in plan


def test_knowledge_fingerprint_changes_when_the_reviewed_corpus_changes(tmp_path):
    from app.expert_knowledge import DEFAULT_PATH
    raw=json.loads(DEFAULT_PATH.read_text(encoding='utf-8'))
    first=ExpertKnowledge()
    raw['documents'][0]['text'] += ' 测试审阅修订。'
    path=tmp_path/'revision.json'
    path.write_text(json.dumps(raw),encoding='utf-8')
    revised=ExpertKnowledge(path)
    assert first.corpus_sha256 != revised.corpus_sha256
    assert revised.search('成交量')[0]['retrieval']['corpus_sha256']==revised.corpus_sha256


@pytest.mark.parametrize('text', [
    '这些数据不能预测未来，但成交量增加。',
    'I cannot predict the future, but volume increased.',
    '成交量没有增加。',
])
def test_unrelated_disclaimer_cannot_unlock_incomparable_snapshot_direction(text):
    from app.options_chat import _validate_changes
    evidence={'change.s0.volume_total':{'status':'incomparable','delta':None}}
    with pytest.raises(ValueError,match='Incomparable'):
        _validate_changes([{'kind':'observation','text':text,'evidence_ids':list(evidence)}],evidence)


def test_mixed_comparison_paragraph_requests_explicit_attribution():
    from app.options_chat import _validate_changes
    evidence = {
        'change.s0.volume_total': {'status':'comparable','delta':0},
        'change.s0.oi_total': {'status':'incomparable','delta':None},
    }
    with pytest.raises(ValueError, match='split each comparison metric'):
        _validate_changes([{'kind':'observation','text':'成交总数未变，未平仓数无法比较。','evidence_ids':list(evidence)}],evidence)


@pytest.mark.parametrize('question',[
    '为什么看跌成交不能说明多数人看空？',
    '为什么看跌成交不能说明多数人看空？不要更新行情。',
    "Why are put counts not bearish headcount? Do not refresh quotes.",
])
def test_unrequested_comparison_is_not_sent_or_allowed_but_remains_in_saved_context(monkeypatch,question):
    from test_options_chat import refreshed
    _, current = refreshed(monkeypatch)
    chat, cloud = service(reply('看跌成交不是看空人数。',['expert.put_call']))
    result = answer(chat,question,current)
    payload = json.loads(cloud.calls[0]['messages'][-1]['content'])
    assert result['mode']=='deepseek'
    assert result['analysis_context']['refresh_comparison']==current['refresh_comparison']
    assert 'refresh_comparison' not in payload['saved_snapshot']
    assert all(not row['id'].startswith('change.') for row in payload['evidence'])

    chat, _ = service(reply('成交量增加。',['change.s0.volume_total'],'observation'))
    rejected = answer(chat,'解释报价覆盖的局限。',current)
    assert rejected['mode']=='offline' and rejected['warning']=='options_answer_validation_failed'
