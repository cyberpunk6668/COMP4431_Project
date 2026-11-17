(() => {
  'use strict';
  const $ = selector => document.querySelector(selector);
  const state = { scenario: null, record: null, busy: false, messages: [], request: 0, controller: null, engine: 'local', configLoaded: false };
  const frameLabel = frame => frame === 1 ? '更新批次' : '起始批次';
  const modeLabel = mode => ({ local: '本地规则说明', deepseek: 'DeepSeek 实际生成', local_fallback: '本地回退说明' }[mode] || '模式未确认');
  const node = (tag, value, className) => {
    const element = document.createElement(tag);
    if (value !== undefined && value !== null) element.textContent = String(value);
    if (className) element.className = className;
    return element;
  };
  const finite = value => typeof value === 'number' && Number.isFinite(value);
  const numeric = (value, digits = 2) => finite(value) ? new Intl.NumberFormat('zh-CN', { maximumFractionDigits: digits }).format(value) : '缺失';
  function formatted(value, unit = '') {
    if (value === null || value === undefined) return '缺失';
    if (typeof value === 'string') return value;
    if (!finite(value)) return '缺失';
    if (unit === 'fraction') return `${numeric(value * 100)}%`;
    if (['percent', 'percentage', '%', 'percent_of_spot'].includes(unit)) return `${numeric(value)}%`;
    if (['percentage_points', 'pp', '百分点', '波动率百分点'].includes(unit)) return `${numeric(value)} 个百分点`;
    if (['contracts', '份', '份合约'].includes(unit)) return `${numeric(value, 0)} 份`;
    if (unit === 'USD') return `${numeric(value)} USD`;
    if (['ratio', '倍'].includes(unit)) return `${numeric(value)} 倍`;
    return numeric(value);
  }
  function stamp(value, zone) {
    const date = new Date(value || '');
    if (Number.isNaN(date.getTime())) return '未提供';
    return new Intl.DateTimeFormat('zh-CN', { timeZone: zone, year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23' }).format(date);
  }
  function status(message) { $('#demo-status').textContent = message; }
  function error(message) { $('#demo-error').textContent = message || ''; $('#demo-error').hidden = !message; }
  function sync() {
    const loaded = !!state.record;
    $('#demo-start').disabled = state.busy || !state.configLoaded;
    $('#demo-next').disabled = state.busy || !loaded || state.record.frame === 1;
    $('#demo-reset').disabled = state.busy || !loaded;
    $('#demo-chat-fields').disabled = state.busy || !loaded;
    $('#demo-engine').disabled = state.busy || !state.configLoaded;
    $('#demo-engine').value = state.engine;
    $('#demo-status').dataset.busy = String(state.busy);
    $('#demo-controls').setAttribute('aria-busy', String(state.busy));
    $('.chat-panel').setAttribute('aria-busy', String(state.busy));
    $('#demo-empty').hidden = loaded;
    $('#demo-result').hidden = !loaded;
    document.body.classList.toggle('demo-active', loaded);
    $('#demo-start').replaceChildren(document.createTextNode((loaded ? '重新分析' : '一键分析') + (state.engine === 'deepseek' ? ' · DeepSeek ' : ' ')), node('span', '↗'));
    $('#demo-start span').setAttribute('aria-hidden', 'true');
    $('.control-copy strong').textContent = !loaded ? '读取数据，理解波动。' : '波动与风险解读已完成。';
    $('#demo-control-hint').textContent = !loaded ? (state.engine === 'deepseek' ? '一次读取样本，由 DeepSeek 解释风险定价与适用范围。' : '一次读取样本，提供风险定价与适用范围的本地解读。') : '查看本次解释，按需展开汇总依据核对。';
    $('#demo-engine-notice').textContent = state.engine === 'deepseek' ? `${state.scenario?.configured_model || 'DeepSeek'} · 每次分析或发送会请求真实模型，可能产生 API 费用。` : '分析和提问均在本地处理；本地规则说明不是模型生成。';
    $('#demo-engine-summary').textContent = state.engine === 'deepseek' ? 'DeepSeek' : '本地规则';
    $('#demo-ask-local').textContent = state.engine === 'deepseek' ? '发送给 DeepSeek' : '本地解释这个问题';
    $('#demo-submit-note').textContent = state.engine === 'deepseek' ? 'DeepSeek · 当前批次' : '不会请求模型';
    ['data', 'analysis', 'chat'].forEach(part => { $('#demo-stage-' + part).dataset.complete = String(loaded); });
  }
  async function request(path, body, timeout = 65000) {
    const controller = new AbortController();
    state.controller = controller;
    const timer = setTimeout(() => controller.abort(), timeout);
    try {
      const response = await fetch(path, { cache: 'no-store', signal: controller.signal, ...(body === undefined ? {} : { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }) });
      const data = await response.json().catch(() => null);
      if (!response.ok) {
        const detail = data?.detail;
        throw new Error(typeof detail === 'string' ? detail : `本地服务返回 HTTP ${response.status}，请稍后重试。`);
      }
      if (!data || typeof data !== 'object') throw new Error('服务未返回可读取的结果，请重试。');
      return data;
    } catch (err) {
      if (err.name === 'AbortError') throw new Error('请求已超时。保留当前样本与问答，请重试。');
      if (err instanceof TypeError) throw new Error('无法连接本地服务，请确认启动脚本正在运行。');
      throw err;
    } finally {
      clearTimeout(timer);
      if (state.controller === controller) state.controller = null;
    }
  }
  function metricParts(item) {
    const display = formatted(item.value, item.unit);
    if (!finite(item.value)) return [display, ''];
    if (['percentage_points', 'pp', '百分点', '波动率百分点'].includes(item.unit)) return [numeric(item.value), '个百分点'];
    if (item.unit === 'fraction') return [numeric(item.value * 100), '%'];
    if (['percent', 'percentage', '%', 'percent_of_spot'].includes(item.unit)) return [numeric(item.value), '%'];
    if (['ratio', '倍'].includes(item.unit)) return [numeric(item.value), '比值'];
    return [display, ''];
  }
  function renderMetrics(record) {
    const parent = $('#demo-metrics'); parent.replaceChildren();
    record.metrics.forEach(item => {
      const card = node('article', null, 'metric-card'); card.dataset.metric = item.id;
      card.append(node('h3', item.label));
      const value = node('div', null, 'metric-value');
      const [amount, unit] = metricParts(item); value.append(node('span', amount)); if (unit) value.append(node('small', unit));
      card.append(value, node('p', item.detail || '仅覆盖当前所示样本。')); parent.append(card);
    });
  }
  function renderOverview(record) {
    const snapshot = record.snapshot;
    $('#demo-expiry').textContent = `到期日 ${record.scenario.expiry || snapshot.expiration || '未提供'} · 所选合约样本`;
    $('#demo-overview-description').textContent = '同一到期日的部分期权定价输入；仅描述所选范围，不代表整个市场。';
    const values = new Map(record.evidence.map(item => [item.id, item.value]));
    const hasIv = snapshot.quotes.some(quote => finite(quote.implied_volatility) && quote.implied_volatility > 0);
    const ivMeaning = hasIv
      ? ['隐含波动率如何理解？', '隐含波动率是期权价格中的波动定价尺度，既受预期影响，也受风险补偿和供需影响；它不是已实现波动率，也不直接给出方向。样本使用给定的合成 IV。']
      : ['隐含波动率输入暂不可用', '隐含波动率通常由期权价格和定价模型反推；当前样本缺少有效输入，暂不判断其波动定价。'];
    const skew = values.get('iv_skew_25_delta');
    let pricing = ['两翼相对定价线索暂不完整', '当前缺少可比的两翼隐含波动率，暂不判断不同方向的相对波动定价。'];
    if (finite(skew)) {
      pricing = skew > 1e-9 ? ['下行侧隐含波动率相对较高', '所选可比两翼中，看跌隐含波动率更高，显示相对波动定价差异；不能单凭它确认恐慌、对冲需求或具体事件。']
        : skew < -1e-9 ? ['上行侧隐含波动率相对较高', '所选可比两翼中，看涨隐含波动率更高，显示相对波动定价差异；不能单凭它确认乐观情绪、需求或具体事件。']
          : ['所选两翼隐含波动率相同', '当前指标未显示两翼隐含波动率差异；这仍不能确定未来涨跌或宏观背景。'];
    }
    const atm = values.get('atm_straddle');
    const straddle = finite(atm) && atm > 0
      ? ['跨式定价提供成本线索', '平值看涨与看跌的合计中价描述双向波动的期权定价成本，不是保证成交价、发生概率或价格必达的区间。']
      : ['跨式成本线索暂不可用', '当前缺少可用的平值跨式中价输入；不会用缺失报价估造成本、波动区间或发生概率。'];
    const parent = $('#demo-phenomena'); parent.replaceChildren();
    [['iv_meaning', ivMeaning], ['risk_pricing', pricing], ['straddle', straddle]].forEach(([key, [title, description]]) => {
      const card = node('article', null, 'phenomenon-card'); card.dataset.phenomenon = key;
      card.append(node('h3', title), node('p', description)); parent.append(card);
    });
    const quality = record.quality || {};
    const valid = quality.valid_quote_contracts, requested = quality.requested_contracts;
    let qualityText = '报价完整性尚未确认，不能将缺失值视为零。';
    if (finite(valid) && finite(requested) && requested > 0 && valid >= 0 && valid <= requested) {
      qualityText = valid === requested ? '所选样本的双边报价完整；没有历史基准，不能判断当前波动率是否异常偏高。' : '部分双边报价缺失；仅解释仍有依据的定价信息，不补造缺失值。';
    }
    $('#demo-quality-note').textContent = qualityText;
    $('#demo-quality-note').dataset.complete = String(valid === requested && requested > 0);
  }
  function appendSourceLinks(card, item) {
    const candidates = [item.source_url, ...(Array.isArray(item.source_urls) ? item.source_urls : [])];
    const urls = [...new Set(candidates.filter(value => typeof value === 'string'))].flatMap(value => {
      try { const url = new URL(value); return url.protocol === 'https:' ? [url] : []; } catch { return []; }
    });
    if (!urls.length) return;
    const explanation = node('p', `概念解释依据${item.publisher ? ` · ${item.publisher}` : ''}，不验证当前样本的行情。`, 'evidence-source');
    const links = node('div', null, 'evidence-links');
    urls.forEach(url => {
      const link = node('a', `${url.hostname.replace(/^www\./, '')} ↗`);
      link.href = url.href; link.target = '_blank'; link.rel = 'noopener noreferrer'; links.append(link);
    });
    card.append(explanation, links);
  }
  function renderEvidence(record) {
    const parent = $('#demo-evidence'); parent.replaceChildren();
    $('#demo-evidence-count').textContent = `${record.evidence.length} 条`;
    record.evidence.forEach((item, index) => {
      const card = node('article', null, 'evidence-item'); card.id = 'demo-current-evidence-' + index; card.dataset.evidence = item.id; card.tabIndex = -1;
      if (item.id.startsWith('knowledge.')) card.classList.add('knowledge-evidence');
      const header = node('div', null, 'evidence-item-header'); header.append(node('strong', item.label), node('span', formatted(item.value, item.unit)));
      card.append(header, node('p', item.detail || '当前批次的本地数据依据。'), node('code', item.id)); appendSourceLinks(card, item); parent.append(card);
    });
    const limits = $('#demo-limitations'); limits.replaceChildren();
    (record.limitations || []).forEach(line => limits.append(node('li', line)));
  }
  function renderChanges(record) {
    const changes = record.changes || [];
    $('#demo-changes-section').hidden = record.frame !== 1 || changes.length === 0;
    const parent = $('#demo-changes'); parent.replaceChildren();
    changes.forEach(item => {
      const card = node('article', null, 'change-card'); card.dataset.change = item.id || '';
      const values = node('div', null, 'change-values'); values.append(node('span', formatted(item.before, item.unit)), node('span', '→'), node('strong', formatted(item.after, item.unit)));
      card.append(node('h3', item.label), values, node('p', item.detail || '相同合约范围内的批次变化。')); parent.append(card);
    });
  }
  function showEvidence(entry, id, button) {
    // Each answer keeps a copied evidence record; old answers never point at a new frame.
    const container = button.closest('.message-pair').querySelector('.answer-details');
    let details = container.querySelector('.saved-answer-evidence');
    if (!details) {
      details = node('div', null, 'saved-answer-evidence evidence-list');
      container.append(details);
    }
    const item = entry.evidence.find(candidate => candidate.id === id);
    if (!item) return;
    details.replaceChildren();
    const card = node('article', null, 'evidence-item'); card.tabIndex = -1;
    if (item.id.startsWith('knowledge.')) card.classList.add('knowledge-evidence');
    const header = node('div', null, 'evidence-item-header'); header.append(node('strong', item.label), node('span', formatted(item.value, item.unit)));
    card.append(header, node('p', item.detail || ''), node('p', `${frameLabel(entry.frame)} · 样本时点 ${stamp(entry.recorded_at, 'UTC')} UTC`), node('code', item.id)); appendSourceLinks(card, item);
    details.append(card); card.focus({ preventScroll: true });
  }
  function renderMessages() {
    const parent = $('#demo-messages'); parent.replaceChildren();
    state.messages.forEach(entry => {
      const pair = node('article', null, 'message-pair'); pair.dataset.frame = String(entry.frame);
      pair.append(node('div', entry.question, 'user-message'));
      const meta = node('div', null, 'message-meta'); meta.append(node('strong', 'FinPilot'), node('span', `${frameLabel(entry.frame)} · ${stamp(entry.recorded_at, 'UTC')} UTC`), node('span', modeLabel(entry.answer.mode), 'message-mode'));
      pair.append(meta, node('div', entry.answer.text, 'answer-text'));
      const fallbackReason = { cloud_unconfigured: '原因：模型未配置或当前离线。', model_validation_failed: '原因：模型输出未通过格式或引用检查。', provider_unavailable: '原因：模型服务暂不可用或请求超时。' }[entry.answer.fallback_reason];
      const notice = [entry.answer.notice, fallbackReason, `数据来源：合成样本；未连接 IBKR。${entry.model_called ? '本次已发起模型请求。' : '本次未发起模型请求。'}`].filter(Boolean).join(' ');
      pair.append(node('p', fallbackReason || (entry.model_called ? '依据当前合成样本生成；可展开核对本条依据。' : '本地规则解读，未请求语言模型。'), 'answer-notice'));
      const proof = node('details', null, 'answer-details'); proof.append(node('summary', '查看这条回答的依据'), node('p', notice, 'answer-source-note'));
      const references = node('div', null, 'answer-evidence'); references.append(node('span', '本条依据'));
      (entry.answer.evidence_ids || []).forEach(id => {
        const item = entry.evidence.find(candidate => candidate.id === id);
        const button = node('button', item?.label || id); button.type = 'button'; button.title = `查看${frameLabel(entry.frame)}的依据：${item?.label || id}`;
        button.addEventListener('click', () => showEvidence(entry, id, button)); references.append(button);
      });
      if ((entry.answer.evidence_ids || []).length) proof.append(references);
      pair.append(proof);
      parent.append(pair);
    });
    parent.scrollTop = parent.scrollHeight;
  }
  function renderRecord(record) {
    $('#demo-frame-label').textContent = frameLabel(record.frame);
    $('#demo-scope').textContent = `${record.scenario.symbol || 'AAPL'} · 风险定价样本`;
    $('#demo-recorded-at').textContent = stamp(record.provenance.recorded_at, 'UTC');
    $('#demo-processed-at').textContent = stamp(record.provenance.processed_at, 'Asia/Shanghai');
    $('#demo-answer-mode').textContent = modeLabel(record.answer.mode);
    renderOverview(record); renderMetrics(record); renderEvidence(record); renderChanges(record); renderMessages();
  }
  function validRecord(data) {
    return data && [0, 1].includes(data.frame) && data.scenario && data.snapshot && Array.isArray(data.snapshot.quotes) && Array.isArray(data.metrics) && Array.isArray(data.evidence) && data.provenance?.source_kind === 'synthetic_replay' && data.provenance.gateway_connected === false && typeof data.answer?.text === 'string';
  }
  async function run(frame, engine, question, { restart = false } = {}) {
    if (state.busy) return;
    const sequence = ++state.request;
    state.busy = true; error(''); sync();
    status(engine === 'deepseek' ? '正在把当前合成样本摘要发送给 DeepSeek，并检查回答中的依据引用…' : '正在读取固定合成样本、计算指标，并生成本地规则说明…');
    try {
      const data = await request('/api/options-demo/run', { frame, engine, ...(question ? { question } : {}) });
      if (sequence !== state.request) return;
      if (!validRecord(data)) throw new Error('服务返回的分析数据不完整，已保留之前的结果。');
      if (restart) { state.messages = []; $('#demo-followup').open = false; }
      state.record = data;
      state.messages.push({ frame: data.frame, question: data.question || question || '请解释当前期权样本。', recorded_at: data.provenance.recorded_at, model_called: data.provenance.model_called === true, answer: structuredClone(data.answer), evidence: structuredClone(data.evidence) });
      renderRecord(data);
      status(`${frameLabel(data.frame)}解读完成 · ${modeLabel(data.answer.mode)} · ${data.provenance.model_called ? '已请求模型' : '未请求模型'} · 未连接 IBKR。已说明风险定价含义与数据边界。`);
    } catch (err) {
      if (sequence === state.request) { error(err.message || '请求失败，请重试。'); status('本次请求未完成。当前已展示的样本与问答保持原样。'); }
    } finally {
      if (sequence === state.request) { state.busy = false; sync(); }
    }
  }
  function question() {
    const text = $('#demo-question').value.trim();
    if (!text) { error('请先填写问题，或选择一个建议问题。'); $('#demo-question').focus(); return null; }
    return text;
  }
  function renderScenario(data) {
    state.scenario = data;
    state.configLoaded = true;
    state.engine = data.cloud_configured === true ? 'deepseek' : 'local';
    $('#demo-engine option[value=deepseek]').disabled = data.cloud_configured !== true;
    const presets = $('#demo-presets'); presets.replaceChildren();
    (data.questions || []).filter((_, index) => index === 1 || index === 3).forEach(text => {
      const button = node('button', text); button.type = 'button';
      button.addEventListener('click', () => { $('#demo-question').value = text; $('#demo-question').focus(); }); presets.append(button);
    });
    if (data.cloud_configured === false) {
      $('#demo-cloud-notice').textContent = '当前 DeepSeek 未配置或处于离线模式，可使用本地规则分析。配置有效 API 并重启服务后，可选择 DeepSeek 解读。';
      $('#demo-cloud-notice').dataset.unavailable = 'true';
    }
    status(data.cloud_configured === true ? 'DeepSeek 已配置。点击「一键分析 · DeepSeek」开始分析；也可切换本地规则模式。' : '本地规则分析已就绪，点击「一键分析」开始。');
    sync();
  }
  $('#demo-start').addEventListener('click', () => run(0, state.engine, undefined, { restart: true }));
  $('#demo-next').addEventListener('click', () => run(1, state.engine, '与起始批次相比，这批期权样本有哪些变化？哪些结论不能推出？'));
  $('#demo-engine').addEventListener('change', () => { state.engine = $('#demo-engine').value === 'deepseek' ? 'deepseek' : 'local'; sync(); status(state.engine === 'deepseek' ? '已选择 DeepSeek；下次分析或发送时请求模型。' : '已选择本地规则；下次分析或发送不请求模型。'); });
  $('#demo-reset').addEventListener('click', () => {
    if (state.busy) return;
    state.request += 1; state.record = null; state.messages = [];
    $('#demo-question').value = ''; $('#demo-messages').replaceChildren(); $('#demo-evidence-details').open = false; $('#demo-analysis-details').open = false; $('#demo-followup').open = false;
    error(''); status('本页分析记录已清空。点击「一键分析」开始新的分析。'); sync(); $('#demo-start').focus();
  });
  $('#demo-chat-form').addEventListener('submit', event => { event.preventDefault(); const text = question(); if (text && state.record) run(state.record.frame, state.engine, text); });
  // A textarea keeps its ordinary Enter behavior, including CJK IME composition.
  sync();
  request('/api/options-demo/scenario', undefined, 12000).then(renderScenario).catch(err => { error(err.message); state.configLoaded = true; state.scenario = { cloud_configured: false }; state.engine = 'local'; sync(); status('样本配置暂未加载。可以点击「一键分析」重试读取固定样本；目前仅启用本地规则模式。'); });
})();
