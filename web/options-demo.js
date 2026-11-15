(() => {
  'use strict';
  const $ = selector => document.querySelector(selector);
  const state = { scenario: null, record: null, busy: false, messages: [], request: 0, controller: null, engine: 'local', configLoaded: false };
  const frameLabel = frame => frame === 1 ? '第二帧' : '第一帧';
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
    $('#demo-start').replaceChildren(document.createTextNode((loaded ? '重新播放第一帧' : '一键演示') + (state.engine === 'deepseek' ? ' · DeepSeek ' : ' ')), node('span', '↗'));
    $('#demo-start span').setAttribute('aria-hidden', 'true');
    $('.control-copy strong').textContent = !loaded ? '准备好，从第一帧开始。' : state.record.frame === 0 ? '第一帧已就绪，继续看变化。' : '第二帧已就绪，可以继续追问。';
    $('#demo-control-hint').textContent = !loaded ? (state.engine === 'deepseek' ? '一次点击，读取样本、计算指标，并真实请求 DeepSeek 解释。' : '一次点击，完成样本读取、指标计算与本地说明。') : state.record.frame === 0 ? '下一帧沿用同一合约范围，并展示一处双边报价缺失。' : '重新播放可回到第一帧；「重新开始」清空本页演示记录。';
    $('#demo-engine-notice').textContent = state.engine === 'deepseek' ? `${state.scenario?.configured_model || 'DeepSeek'} · 每次播放或发送会请求真实模型，可能产生 API 费用。` : '播放和发送都在本地运行；本地规则说明不是模型生成。';
    $('#demo-ask-local').textContent = state.engine === 'deepseek' ? '发送给 DeepSeek' : '本地解释这个问题';
    $('#demo-submit-note').textContent = state.engine === 'deepseek' ? '真实模型 · 当前帧' : '不会请求模型';
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
  function renderQuotes(record) {
    const snapshot = record.snapshot;
    $('#demo-underlying').textContent = numeric(snapshot.underlying?.price);
    $('#demo-expiry').textContent = `教学到期日 ${record.scenario.expiry || snapshot.expiration || '未提供'} · ${snapshot.quotes.length} 个合约`;
    const body = $('#demo-quotes tbody'); body.replaceChildren();
    snapshot.quotes.forEach(quote => {
      const row = document.createElement('tr'); row.dataset.contract = `${quote.right}${quote.strike}`;
      [numeric(quote.strike), quote.right === 'C' ? '看涨 C' : '看跌 P', numeric(quote.bid), numeric(quote.ask), numeric(quote.volume, 0), numeric(quote.open_interest, 0), finite(quote.implied_volatility) ? `${numeric(quote.implied_volatility * 100)}%` : '缺失'].forEach((value, index) => {
        const cell = node('td', value);
        if (index === 1 && quote.right === 'P') cell.classList.add('put-cell');
        if (value === '缺失') cell.classList.add('missing-cell');
        row.append(cell);
      });
      body.append(row);
    });
  }
  function renderEvidence(record) {
    const parent = $('#demo-evidence'); parent.replaceChildren();
    $('#demo-evidence-count').textContent = `${record.evidence.length} 条`;
    record.evidence.forEach((item, index) => {
      const card = node('article', null, 'evidence-item'); card.id = 'demo-current-evidence-' + index; card.dataset.evidence = item.id; card.tabIndex = -1;
      const header = node('div', null, 'evidence-item-header'); header.append(node('strong', item.label), node('span', formatted(item.value, item.unit)));
      card.append(header, node('p', item.detail || '当前帧的本地数据依据。'), node('code', item.id)); parent.append(card);
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
      card.append(node('h3', item.label), values, node('p', item.detail || '固定共同样本的教学变化。')); parent.append(card);
    });
  }
  function showEvidence(entry, id, button) {
    // Each answer keeps a copied evidence record; old answers never point at a new frame.
    let details = button.closest('.message-pair').querySelector('.saved-answer-evidence');
    if (!details) {
      details = node('div', null, 'saved-answer-evidence evidence-list');
      button.closest('.message-pair').append(details);
    }
    const item = entry.evidence.find(candidate => candidate.id === id);
    if (!item) return;
    details.replaceChildren();
    const card = node('article', null, 'evidence-item'); card.tabIndex = -1;
    const header = node('div', null, 'evidence-item-header'); header.append(node('strong', item.label), node('span', formatted(item.value, item.unit)));
    card.append(header, node('p', item.detail || ''), node('p', `${frameLabel(entry.frame)} · 教学时点 ${stamp(entry.recorded_at, 'UTC')} UTC`), node('code', item.id));
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
      const notice = [entry.answer.notice, fallbackReason, `数据来源：合成教学回放；实际 IBKR 请求：无。${entry.model_called ? '本次已发起模型请求。' : '本次未发起模型请求。'}`].filter(Boolean).join(' ');
      pair.append(node('p', notice, 'answer-notice'));
      const references = node('div', null, 'answer-evidence'); references.append(node('span', '本条依据'));
      (entry.answer.evidence_ids || []).forEach(id => {
        const item = entry.evidence.find(candidate => candidate.id === id);
        const button = node('button', item?.label || id); button.type = 'button'; button.title = `查看${frameLabel(entry.frame)}的依据：${item?.label || id}`;
        button.addEventListener('click', () => showEvidence(entry, id, button)); references.append(button);
      });
      if ((entry.answer.evidence_ids || []).length) pair.append(references);
      parent.append(pair);
    });
    parent.scrollTop = parent.scrollHeight;
  }
  function renderRecord(record) {
    $('#demo-frame-label').textContent = frameLabel(record.frame);
    $('#demo-scope').textContent = `${record.scenario.symbol || 'AAPL'} · 合成教学样本`;
    $('#demo-recorded-at').textContent = stamp(record.provenance.recorded_at, 'UTC');
    $('#demo-processed-at').textContent = stamp(record.provenance.processed_at, 'Asia/Shanghai');
    $('#demo-answer-mode').textContent = modeLabel(record.answer.mode);
    renderMetrics(record); renderQuotes(record); renderEvidence(record); renderChanges(record); renderMessages();
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
      if (!validRecord(data)) throw new Error('服务返回的演示数据不完整，已保留之前的结果。');
      if (restart) state.messages = [];
      state.record = data;
      state.messages.push({ frame: data.frame, question: data.question || question || '请解释当前期权样本。', recorded_at: data.provenance.recorded_at, model_called: data.provenance.model_called === true, answer: structuredClone(data.answer), evidence: structuredClone(data.evidence) });
      renderRecord(data);
      status(`${frameLabel(data.frame)}已读取 · ${modeLabel(data.answer.mode)} · ${data.provenance.model_called ? '已请求模型' : '未请求模型'} · 未连接 IBKR。${data.frame === 0 ? '可播放下一帧查看变化。' : '报价缺失已保留，可继续追问。'}`);
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
    (data.questions || []).slice(0, 4).forEach(text => {
      const button = node('button', text); button.type = 'button';
      button.addEventListener('click', () => { $('#demo-question').value = text; $('#demo-question').focus(); }); presets.append(button);
    });
    if (data.cloud_configured === false) {
      $('#demo-cloud-notice').textContent = '当前 DeepSeek 未配置或处于离线模式。可完整演示本地数据与规则说明；配置有效 API 后重新打开本页即可请求模型。';
      $('#demo-cloud-notice').dataset.unavailable = 'true';
    }
    status(data.cloud_configured === true ? 'DeepSeek 已配置。点击「一键演示 · DeepSeek」会发起一次真实模型请求；也可切换本地规则模式。' : '本地规则模式已就绪，无需密钥或行情权限；当前不请求模型。');
    sync();
  }
  $('#demo-start').addEventListener('click', () => run(0, state.engine, undefined, { restart: true }));
  $('#demo-next').addEventListener('click', () => run(1, state.engine, '与上一帧相比，这批期权样本有哪些变化？哪些结论不能推出？'));
  $('#demo-engine').addEventListener('change', () => { state.engine = $('#demo-engine').value === 'deepseek' ? 'deepseek' : 'local'; sync(); status(state.engine === 'deepseek' ? '已选择 DeepSeek；下次播放或发送时才会请求真实模型。' : '已选择本地规则；下次播放或发送不请求模型。'); });
  $('#demo-reset').addEventListener('click', () => {
    if (state.busy) return;
    state.request += 1; state.record = null; state.messages = [];
    $('#demo-question').value = ''; $('#demo-messages').replaceChildren(); $('#demo-evidence-details').open = false;
    error(''); status('演示记录已清空。点击「一键演示」重新开始；未请求模型或网关。'); sync(); $('#demo-start').focus();
  });
  $('#demo-chat-form').addEventListener('submit', event => { event.preventDefault(); const text = question(); if (text && state.record) run(state.record.frame, state.engine, text); });
  // A textarea keeps its ordinary Enter behavior, including CJK IME composition.
  sync();
  request('/api/options-demo/scenario', undefined, 12000).then(renderScenario).catch(err => { error(err.message); state.configLoaded = true; state.scenario = { cloud_configured: false }; state.engine = 'local'; sync(); status('场景说明暂未加载。可以点击「一键演示」重试读取固定样本；目前仅启用本地规则模式。'); });
})();
