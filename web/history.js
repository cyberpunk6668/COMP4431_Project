(() => {
  'use strict';
  const panel = document.getElementById('history-panel');
  if (!panel) return;
  const form = document.getElementById('history-form');
  const fields = document.getElementById('history-fields');
  const fileInput = document.getElementById('history-file');
  const fileStatus = document.getElementById('history-file-status');
  const preview = document.getElementById('history-preview');
  const status = document.getElementById('history-status');
  const error = document.getElementById('history-error');
  const result = document.getElementById('history-result');
  const submit = document.getElementById('history-submit');
  const demo = document.getElementById('history-demo');
  const sample = document.getElementById('history-sample');
  const MAX_ROWS = 300, MAX_BYTES = 32000;
  const rowKeys = ['trading_date','strike','right','open','high','low','close','volume','open_interest','oi_asof_date'];
  const numericKeys = new Set(['strike','open','high','low','close','volume','open_interest']);
  const copy = {
    title:['历史复盘与专家依据','Historical review & expert evidence'], mode:['日线复盘 · 不是即时行情','Daily review · not live quotes'],
    intro:['导入几天的期权日线资料，先核对来源与共同合约，再看成交和持仓变化。收盘价是历史记录，不是当前买卖报价。','Import a few days of option records. Check provenance and common contracts before reviewing activity and positioning. Historical close prices are not current bid/ask quotes.'],
    step1:['历史样本','Historical sample'], step1Hint:['核对来源与范围','Check provenance and scope'], step2:['本地计算','Local calculations'], step2Hint:['固定规则与可比性检查','Fixed rules and comparability checks'], step3:['专家依据与解释','Expert evidence & explanation'], step3Hint:['聊天发送后再检索与回答','Retrieve and answer after chat Send'],
    demo:['加载教学样例','Load teaching example'], csvTemplate:['下载 CSV 模板','Download CSV template'], jsonTemplate:['下载 JSON 模板','Download JSON template'],
    sample:['回放真实 IBKR 历史样本','Replay a saved IBKR history sample'], sampleHint:['真实样本来自服务器保存的只读网关历史档案；点击只回放，不重新访问网关。教学样例是独立的合成数据。','The real sample replays a saved read-only gateway archive on this server. This button makes no new gateway request. The teaching example is separate synthetic data.'],
    templateHint:['模板只有字段与空清单，不含行情。教学样例会始终标为合成数据。','Templates contain headers or an empty list, with no market observations. Teaching examples always remain labelled synthetic.'],
    file:['选择 CSV / JSON 文件','Choose a CSV / JSON file'], fileHelp:['最多 300 行、32 KB。CSV 必须有 trading_date、strike、right；C 为看涨，P 为看跌，空值不会填成零。','Up to 300 rows and 32 KB. CSV requires trading_date, strike and right; use C for call and P for put. Missing values are not filled with zero.'],
    label:['给这段复盘起个名字','Name this review'], symbol:['公司或基金代码','Company or fund symbol'], expiry:['这批合约的到期日','Expiration of these contracts'],
    provenance:['补充来源说明（可选）','Add provenance notes (optional)'], sourceLabel:['原始资料的来源说明','Original data source description'],
    exportedAt:['原文件导出时间（含时区，可留空）','Original export time (with timezone, optional)'],
    submit:['生成本地历史复盘','Build local historical review'], localOnly:['此步骤只在本地分析，不调用云端模型。追问时需另行点击发送。','This step runs locally and makes no cloud model call. Follow-up questions require a separate Send.'],
    labelPlaceholder:['例如：AAPL 最近几天','For example: AAPL over a few days'], sourcePlaceholder:['例如：券商导出的日线记录','For example: broker-exported daily records'],
    fileReady:['已读取 {count} 行。请核对代码、到期日与预览，再生成复盘。','Read {count} rows. Check the symbol, expiration and preview before building the review.'],
    reading:['正在本地读取文件…','Reading the file locally…'], processing:['正在核对历史样本并计算共同合约的变化…','Checking historical samples and calculating changes for common contracts…'],
    complete:['本地历史复盘已生成；尚未向模型发送数据。','Local historical review ready. No data has been sent to a model.'],
    invalidFile:['请上传 UTF-8 CSV 或 JSON 文件。','Upload a UTF-8 CSV or JSON file.'], tooLarge:['文件或转换后的请求超过 32 KB，请缩小数据范围。','The file or converted request exceeds 32 KB. Reduce the data range.'],
    invalidRows:['请提供 2 至 300 行历史合约记录。','Provide between 2 and 300 historical contract records.'],
    unsupportedUnits:['目前只接受 USD、标准乘数 100 的期权资料；不会把其他币种或合约乘数改写为该单位。','Only USD options with the standard multiplier of 100 are supported. Other currencies or multipliers will not be relabelled.'],
    unsupportedBasis:['bar_basis 仅支持 trade_ohlc 或 derived_from_intraday_trades，请核对文件的价格口径。','bar_basis must be trade_ohlc or derived_from_intraday_trades. Check how the file’s prices were defined.'],
    badCsv:['CSV 格式有误。请使用模板字段，确认引号完整且每行列数一致。','CSV format is invalid. Use the template headers and check balanced quotes and consistent columns.'],
    badRow:['第 {row} 行：请核对日期、正数行权价、C/P 类型，以及非负数值；空白字段可留空。','Row {row}: check the date, positive strike, C/P side and non-negative numbers. Optional missing fields may stay blank.'],
    noFile:['先选择并读取一个有效文件。','Choose and read a valid file first.'], noRows:['暂无可显示的记录。','No records to display.'],
    invalidResponse:['本地服务没有返回可读的历史复盘。','The local service returned no readable historical review.'],
    network:['无法连接本地服务，请检查后重试。','The local service could not be reached. Check it and retry.'], timeout:['请求超时，原复盘仍保留。请稍后重试。','The request timed out. The previous review is retained; retry later.'],
    previous:['下方保留此前的复盘，本次失败没有替换它。','The previous review is retained below; this failed request did not replace it.'],
    unverified:['本地文件导入 · 来源未独立核验','Local file import · provenance unverified'], teaching:['教学合成数据 · 不是真实行情','Synthetic teaching data · not real market observations'],
    brokerHistory:['历史数据源读取 · 非即时行情','Historical source read · not live quotes'], source:['资料来源','Data provenance'], period:['历史区间','Historical period'],
    derivedBoundary:['这批数据由所收到的盘中成交 bar 汇总；不保证覆盖完整交易时段。成交计数不是已核验的全日成交量，bar 末值不是官方收盘或结算价。','These values are aggregated from received intraday trade bars; complete session coverage is not guaranteed. Counts are not verified full-day volume, and a received-bar end value is not an official close or settlement.'],
    derivedActivity:['仅保留所收到的 bar 计数。完整时段覆盖未核验，不能据此判断全日成交量增加或减少。','Only received-bar counts are retained. Full-session coverage is unverified, so they do not establish an increase or decrease in full-day volume.'],
    derivedTrend:['所收样本记录，逐日对照','Compare the received samples over time'], derivedVolume:['所收 bar 成交计数','Received-bar volume counts'],
    derivedPrices:['逐合约所收 bar 末值变化（非官方收盘）','Received-bar end-value changes by contract (not official closes)'],
    derivedBefore:['首日所收 bar 末值','First-date received-bar end'], derivedAfter:['末日所收 bar 末值','Last-date received-bar end'],
    boundary:['这是指定合约的历史记录，不是即时市场，也不是完整期权链。不同合约的价格不会混合成一个“市场价格”。','These are historical records for selected contracts, not the live market or a complete chain. Different contract prices are not pooled into one “market price”.'],
    question1:['这段资料覆盖什么？','What does this dataset cover?'], question2:['成交活动如何变化？','How did reported activity change?'],
    question3:['持仓提供什么线索？','What does open interest tell us?'], question4:['哪些仍不能确定？','What remains uncertain?'],
    noActivity:['成交记录或共同样本不足，暂不能作首尾比较。','Activity records or common samples are insufficient for an endpoint comparison.'],
    activity:['相同合约范围内，首日成交总数 {before}，末日为 {after}。这只是样本成交计数，不是多空人数。','Within the same contract sample, reported volume was {before} on the first date and {after} on the last. Counts do not represent bullish or bearish people.'],
    interest:['相同合约范围内，未平仓量由 {before} 变为 {after}。持仓有独立统计日期，不能直接解释为资金流入或新开仓方向。','Within the same sample, open interest changed from {before} to {after}. It has separate reporting dates and does not directly measure money flows or new-position direction.'],
    noInterest:['未平仓量或独立统计日期不足，保留原始记录，但不生成持仓变化判断。','Open interest or its independent reporting dates are insufficient. Original records are retained without a positioning-change conclusion.'],
    uncertainty:['这些历史线索不能单独证明市场整体情绪或预测涨跌；还需要核查样本范围、数据缺失与专业依据。','These historical clues alone cannot establish market-wide sentiment or predict prices. Check sample scope, missing data and the supporting professional sources.'],
    trend:['同一批合约，逐日对照','Compare the same contracts over time'], volume_total:['样本成交总数','Sample volume'], put_volume_share:['看跌成交占比','Put volume share'],
    oi_total:['样本未平仓量','Sample open interest'], put_oi_share:['看跌持仓占比','Put open-interest share'],
    chartHint:['每一点是一个已提供数据的交易日；缺失处断开，零值保留。只比较全期共同合约。','Each point is a supplied trading date. Missing observations break the line; zero values are kept. Only contracts common to the entire period are compared.'],
    noChart:['这一指标缺少可绘制数据，不能用零代替。','This indicator has no plottable observations; missing data cannot be replaced with zero.'],
    daily:['查看按日数字与统计日期','Review daily values and reporting dates'], changes:['首日与末日的可比变化','Comparable first-to-last changes'],
    before:['首日','First'], after:['末日','Last'], delta:['变化量','Change'], missing:['未提供','Not provided'], incomparable:['暂不能比较','Not comparable'],
    contracts:['份合约','contracts'], points:['个百分点','percentage points'],
    reasonOI:['未平仓量或独立统计日期未满足比较条件。','Open interest or its independent reporting dates do not meet comparison conditions.'],
    reasonCoverage:['完整交易时段覆盖未核验，不能据此前后计数判断全日成交活动增减。','Full-session coverage is unverified; these counts cannot establish a change in full-day trading activity.'],
    reasonOIDate:['未平仓统计日期未推进，重复的统计记录不能当作新增持仓变化。','The open-interest reporting date did not advance; repeated reports do not establish a new positioning change.'],
    reasonSample:['缺失记录、日期数或共同配对样本不足，不能直接比较。','Missing records, too few dates or insufficient common pairs prevent direct comparison.'],
    prices:['逐合约收盘变化（不混合价格）','Closing changes by contract (prices are not pooled)'],
    strike:['行权价','Strike'], side:['类型','Side'], call:['看涨','Call'], put:['看跌','Put'], closeBefore:['首日收盘','First close'], closeAfter:['末日收盘','Last close'], priceChange:['价格变化','Price change'],
    date:['交易日期','Trading date'], received:['提供合约数','Contracts supplied'], common:['共同合约数','Common contracts'], oiDate:['持仓统计日期','OI reporting date'],
    preview:['文件前几行预览','Preview of the first file rows'], evidence:['本地计算依据','Locally computed evidence'],
    evidenceNote:['这里是数据与本地计算依据；专家或官方资料在聊天回答的来源中另列，二者不能混为一谈。','These are data and locally computed evidence. Professional or official references appear separately in chat sources; they are distinct kinds of support.'],
    limitations:['读这份复盘前要知道','Before interpreting this review'], followup:['带着这段历史追问','Ask about this historical period'],
    followupHint:['只关联这段已保存的历史并预填问题。你点击聊天发送后，模型才会结合数据与可检索资料解释。','This attaches the saved historical review and prefills a question. Only your chat Send asks the model to explain it with the data and retrievable references.'],
    followupPrompt:['请用非专业人士能懂的话复盘这段历史期权数据：哪些成交和持仓变化有依据，哪些不能比较？请区分本地数据证据与专家或官方资料，并说明为什么不能据此预测涨跌。','Review this historical options data in plain language. Which activity and positioning changes are supported, and which are not comparable? Separate local data evidence from professional or official references, and explain why this is not a price forecast.'],
    attachFailed:['暂未能关联历史复盘；没有发送给模型，请稍后重试。','The historical review could not be attached. Nothing was sent to the model; retry later.'],
  };
  const language = () => document.documentElement.lang.startsWith('en') ? 1 : 0;
  const t = key => copy[key]?.[language()] || key;
  const el = (tag, text, className) => { const item = document.createElement(tag); if (text !== undefined) item.textContent = text; if (className) item.className = className; return item; };
  let rows = [], metadata = {}, currentRecord, controller, busy = false, fileSequence = 0, selectedMetric = 'volume_total';
  const isDemo = record => record?.source?.kind === 'demo';
  const isDerived = record => record?.bar_basis === 'derived_from_intraday_trades';
  const format = (value, unit) => {
    if (value === null || value === undefined || typeof value !== 'number' || !Number.isFinite(value)) return t('missing');
    const number = new Intl.NumberFormat(language() ? 'en-US' : 'zh-CN', { maximumFractionDigits:2 }).format(unit === 'fraction' ? value * 100 : value);
    return unit === 'fraction' || unit === 'percent' ? number + '%' : unit === 'contracts' ? `${number} ${t('contracts')}` : unit === 'percentage_points' ? `${number} ${t('points')}` : number;
  };
  function showError(message) { error.textContent = message || ''; error.hidden = !message; }
  function setBusy(value) {
    busy = value; fields.disabled = value; demo.disabled = value; sample.disabled = value;
    submit.disabled = value || !rows.length; form.setAttribute('aria-busy', String(value));
    const followup = result.querySelector('.history-followup button'); if (followup) followup.disabled = value;
    status.hidden = !value; status.textContent = value ? t('processing') : '';
  }
  function validDate(value) {
    if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
    const [year, month, day] = value.split('-').map(Number);
    const stamp = new Date(Date.UTC(year, month - 1, day));
    return stamp.getUTCFullYear() === year && stamp.getUTCMonth() === month - 1 && stamp.getUTCDate() === day;
  }
  function normalizeRows(input) {
    if (!Array.isArray(input) || input.length < 2 || input.length > MAX_ROWS) throw new Error(t('invalidRows'));
    return input.map((source, index) => {
      if (!source || typeof source !== 'object' || Array.isArray(source)) throw new Error(t('badRow').replace('{row}', index + 1));
      const row = {};
      for (const key of rowKeys) {
        const value = source[key];
        if (value === null || value === undefined || value === '') continue;
        if (typeof value === 'string' && !value.trim()) continue;
        if (numericKeys.has(key)) {
          if (typeof value !== 'number' && typeof value !== 'string') throw new Error(t('badRow').replace('{row}', index + 1));
          const numeric = typeof value === 'number' ? value : Number(value.trim());
          if (!Number.isFinite(numeric) || numeric < 0 || key === 'strike' && numeric <= 0) throw new Error(t('badRow').replace('{row}', index + 1));
          row[key] = numeric;
        } else row[key] = String(value).trim();
      }
      row.right = row.right?.toUpperCase();
      if (!validDate(row.trading_date) || !Number.isFinite(row.strike) || !['C','P'].includes(row.right) || row.oi_asof_date !== undefined && !validDate(row.oi_asof_date)) throw new Error(t('badRow').replace('{row}', index + 1));
      return row;
    });
  }
  function parseCsv(text) {
    const grid = []; let row = [], field = '', quoted = false, afterQuote = false;
    const pushField = () => { row.push(field.trim()); field = ''; afterQuote = false; };
    const pushRow = () => { pushField(); if (row.some(value => value !== '')) grid.push(row); row = []; };
    const value = text.replace(/^\uFEFF/, '');
    for (let index = 0; index < value.length; index++) {
      const char = value[index];
      if (quoted) {
        if (char === '"' && value[index + 1] === '"') { field += '"'; index++; }
        else if (char === '"') { quoted = false; afterQuote = true; }
        else field += char;
      } else if (char === '"') {
        if (field.trim() || afterQuote) throw new Error(t('badCsv'));
        field = ''; quoted = true;
      } else if (char === ',') pushField();
      else if (char === '\n' || char === '\r') { if (char === '\r' && value[index + 1] === '\n') index++; pushRow(); }
      else if (afterQuote && char.trim()) throw new Error(t('badCsv'));
      else if (!afterQuote) field += char;
    }
    if (quoted) throw new Error(t('badCsv'));
    if (field || row.length || afterQuote) pushRow();
    if (!grid.length) throw new Error(t('badCsv'));
    const headers = grid.shift().map(value => value.trim().toLowerCase());
    if (new Set(headers).size !== headers.length || !['trading_date','strike','right'].every(key => headers.includes(key))) throw new Error(t('badCsv'));
    return normalizeRows(grid.map(values => {
      if (values.length !== headers.length) throw new Error(t('badCsv'));
      return Object.fromEntries(headers.map((key, index) => [key, values[index]]));
    }));
  }
  function table(headers, data) {
    const scroll = el('div', undefined, 'history-table-scroll'); scroll.tabIndex = 0;
    const body = el('table', undefined, 'history-table');
    const head = body.createTHead().insertRow();
    for (const label of headers) { const cell = el('th', label); cell.scope = 'col'; head.append(cell); }
    const tbody = body.createTBody();
    for (const values of data) { const row = tbody.insertRow(); for (const value of values) row.insertCell().textContent = value; }
    scroll.append(body); return scroll;
  }
  function renderPreview() {
    preview.replaceChildren(); preview.hidden = !rows.length;
    if (!rows.length) return;
    preview.append(el('p', t('preview')), table([t('date'),t('strike'),t('side'),'close','volume','open_interest',t('oiDate')], rows.slice(0, 6).map(row => [row.trading_date,format(row.strike),row.right,format(row.close),format(row.volume),format(row.open_interest),row.oi_asof_date || t('missing')])));
  }
  async function readFile() {
    const sequence = ++fileSequence;
    const file = fileInput.files?.[0]; rows = []; metadata = {}; submit.disabled = true; renderPreview(); showError('');
    document.getElementById('history-source-label').value = ''; document.getElementById('history-exported-at').value = '';
    if (!file) { fileStatus.textContent = ''; return; }
    fileStatus.textContent = t('reading');
    try {
      if (file.size > MAX_BYTES) throw new Error(t('tooLarge'));
      if (!/\.(csv|json)$/i.test(file.name)) throw new Error(t('invalidFile'));
      const text = await file.text();
      if (sequence !== fileSequence) return;
      if (/\.csv$/i.test(file.name)) rows = parseCsv(text);
      else {
        const parsed = JSON.parse(text.replace(/^\uFEFF/, ''));
        if (!parsed || typeof parsed !== 'object') throw new Error(t('invalidFile'));
        if (!Array.isArray(parsed) && (parsed.currency !== undefined && parsed.currency !== 'USD' || parsed.multiplier !== undefined && parsed.multiplier !== 100)) throw new Error(t('unsupportedUnits'));
        if (!Array.isArray(parsed) && parsed.bar_basis !== undefined && !['trade_ohlc','derived_from_intraday_trades'].includes(parsed.bar_basis)) throw new Error(t('unsupportedBasis'));
        rows = normalizeRows(Array.isArray(parsed) ? parsed : parsed.rows);
        if (!Array.isArray(parsed)) for (const key of ['label','symbol','expiry','source_label','exported_at','bar_basis']) if (typeof parsed[key] === 'string') metadata[key] = parsed[key];
        for (const key of ['label','symbol','expiry','source_label','exported_at']) if (metadata[key] !== undefined) document.getElementById(`history-${key.replaceAll('_','-')}`).value = metadata[key];
      }
      fileStatus.textContent = `${file.name} · ${t('fileReady').replace('{count}', rows.length)}`;
      submit.disabled = false; renderPreview();
    } catch (failure) {
      rows = []; fileStatus.textContent = ''; renderPreview();
      showError(failure instanceof SyntaxError ? t('invalidFile') : failure.message);
    }
  }
  async function request(path, body) {
    if (busy) return;
    const current = new AbortController(); controller = current;
    const timeout = setTimeout(() => current.abort('timeout'), 20000);
    let completed = false;
    showError(''); setBusy(true);
    try {
      const response = await fetch(`${path}?language=${language() ? 'en' : 'zh'}`, { method:'POST', signal:current.signal, cache:'no-store', ...(body ? { headers:{'Content-Type':'application/json'}, body:JSON.stringify(body) } : {}) });
      const record = await response.json().catch(() => null);
      if (!response.ok) {
        const detail = record?.detail;
        const message = typeof detail === 'string' ? detail : Array.isArray(detail) ? detail.map(item => `${(item.loc || []).join('.')} · ${item.msg || ''}`).join(' / ') : detail?.message || `HTTP ${response.status}`;
        throw new Error(message);
      }
      if (record?.analysis_kind !== 'historical_options' || !Array.isArray(record.daily) || typeof record.analysis_id !== 'string') throw new Error(t('invalidResponse'));
      if (current.signal.aborted || controller !== current) return;
      currentRecord = record; selectedMetric = 'volume_total'; renderRecord(record);
      completed = true;
      result.scrollIntoView({ block:'start', behavior:document.documentElement.dataset.motion === 'reduced' ? 'instant' : 'smooth' });
    } catch (failure) {
      if (current.signal.aborted && current.signal.reason !== 'timeout') return;
      const message = current.signal.aborted ? t('timeout') : failure instanceof TypeError ? t('network') : failure.message;
      showError(message + (currentRecord ? ` ${t('previous')}` : ''));
    } finally {
      clearTimeout(timeout); if (controller === current) { controller = null; setBusy(false); if (completed) { status.textContent = t('complete'); status.hidden = false; } }
    }
  }
  function sourceLabel(record) { return isDemo(record) ? t('teaching') : record.source?.kind === 'ibkr_historical' ? t('brokerHistory') : t('unverified'); }
  function changeReason(change) {
    if (change?.reason === 'historical_bar_coverage_unverified') return t('reasonCoverage');
    if (change?.reason === 'oi_asof_not_advanced') return t('reasonOIDate');
    const interestMetric = /\.(?:oi_total|put_oi_share)$/.test(change?.id || '');
    return interestMetric && /oi|asof/.test(change?.reason || '') ? t('reasonOI') : t('reasonSample');
  }
  function renderChange(change) {
    const card = el('article', undefined, 'history-change'); card.dataset.changeId = change.id || '';
    card.append(el('strong', change.label || t('changes')));
    const list = el('dl', undefined, 'history-change-values');
    for (const [key, label] of [['before','before'],['after','after'],['delta','delta']]) {
      const item = el('div');
      const comparable = change.status === 'comparable';
      let value = key === 'delta' && !comparable ? t('incomparable') : format(change[key], key === 'delta' ? change.delta_unit : change.unit);
      if (key === 'delta' && comparable && Number.isFinite(change.delta) && change.delta > 0) value = '+' + value;
      item.append(el('dt', t(label)), el('dd', value)); list.append(item);
    }
    card.append(list);
    if (change.status !== 'comparable') card.append(el('p', changeReason(change)));
    return card;
  }
  function renderChart(record) {
    const figure = el('figure', undefined, 'history-chart'); figure.append(el('h4', t(isDerived(record) ? 'derivedTrend' : 'trend')));
    const controls = el('div', undefined, 'history-chart-controls'); controls.setAttribute('role', 'group'); controls.setAttribute('aria-label', t('trend'));
    const keys = ['volume_total','put_volume_share','oi_total','put_oi_share'];
    for (const key of keys) {
      const button = el('button', t(key === 'volume_total' && isDerived(record) ? 'derivedVolume' : key)); button.type = 'button'; button.dataset.metric = key;
      button.setAttribute('aria-pressed', String(key === selectedMetric));
      button.addEventListener('click', () => { selectedMetric = key; figure.replaceWith(renderChart(record)); }); controls.append(button);
    }
    figure.append(controls);
    const data = record.daily.slice().sort((a,b) => String(a.date).localeCompare(String(b.date)));
    const numbers = data.map(item => item[selectedMetric]).filter(value => typeof value === 'number' && Number.isFinite(value));
    const unit = selectedMetric.includes('share') ? 'fraction' : 'contracts';
    if (!numbers.length) figure.append(el('p', t('noChart')));
    else {
      const ns = 'http://www.w3.org/2000/svg';
      const width = Math.max(280, Math.min(640, result.clientWidth - 40 || 640));
      const svg = document.createElementNS(ns, 'svg'); svg.setAttribute('viewBox', `0 0 ${width} 250`); svg.setAttribute('role', 'img'); svg.setAttribute('aria-label', `${sourceLabel(record)} · ${t(selectedMetric)} · ${record.period?.start || ''} — ${record.period?.end || ''}`);
      const make = (tag, attributes, text) => { const item = document.createElementNS(ns, tag); for (const [key,value] of Object.entries(attributes)) item.setAttribute(key, String(value)); if (text !== undefined) item.textContent = text; svg.append(item); return item; };
      const max = Math.max(...numbers, 1), left = 52, top = 15, plotWidth = width - 67, plotHeight = 185;
      for (const proportion of [0,.5,1]) {
        const y = top + plotHeight * (1 - proportion);
        make('line', { x1:left, x2:left + plotWidth, y1:y, y2:y, class:'history-chart-grid' });
        make('text', { x:left - 8, y:y + 4, 'text-anchor':'end' }, format(max * proportion, unit === 'fraction' ? 'fraction' : undefined));
      }
      let segment = [];
      const flush = () => { if (segment.length > 1 && !isDerived(record)) make('polyline', { points:segment.join(' '), class:'history-chart-line' }); segment = []; };
      data.forEach((day, index) => {
        const x = data.length === 1 ? left + plotWidth / 2 : left + index / (data.length - 1) * plotWidth;
        const value = day[selectedMetric];
        if (typeof value === 'number' && Number.isFinite(value)) {
          const y = top + plotHeight * (1 - value / max); segment.push(`${x},${y}`);
          const point = make('circle', { cx:x, cy:y, r:4, class:'history-chart-dot', 'data-date':day.date, 'data-value':value });
          const title = document.createElementNS(ns, 'title'); title.textContent = `${day.date} · ${format(value, unit)}`; point.append(title);
        } else flush();
        if (index === 0 || index === data.length - 1 || data.length > 4 && index === Math.floor(data.length / 2)) make('text', { x, y:227, 'text-anchor':index === 0 ? 'start' : index === data.length - 1 ? 'end' : 'middle' }, String(day.date));
      });
      flush(); figure.append(svg);
    }
    figure.append(el('figcaption', `${sourceLabel(record)} · ${t('chartHint')}${isDerived(record) ? ' ' + t('derivedActivity') : ''}`)); return figure;
  }
  function renderRecord(record) {
    result.replaceChildren(); result.hidden = false; result.dataset.analysisId = record.analysis_id; result.dataset.sourceKind = record.source?.kind || 'import';
    const badge = el('span', sourceLabel(record), 'history-source-badge'); badge.dataset.demo = String(isDemo(record));
    result.append(badge, el('h3', record.label || `${record.symbol} · ${record.expiry}`),
      el('p', `${record.symbol || ''} · ${record.expiry || ''} · ${t('period')} ${record.period?.start || '—'} — ${record.period?.end || '—'}`, 'history-period'),
      el('p', `${t('source')} · ${record.source?.label || t('unverified')}`, 'history-source'), el('p', t('boundary'), 'history-boundary'));
    if (record.source?.exported_at) result.append(el('p', `${t('exportedAt')} · ${record.source.exported_at}`, 'history-source'));
    if (isDerived(record)) result.append(el('p', t('derivedBoundary'), 'history-boundary history-derived-boundary'));
    const changes = Array.isArray(record.changes) ? record.changes : [];
    const volume = changes.find(item => item.id?.endsWith('volume_total'));
    const interest = changes.find(item => item.id?.endsWith('oi_total'));
    const brief = Array.isArray(record.brief) ? record.brief.filter(value => typeof value === 'string') : [];
    const cards = el('div', undefined, 'history-questions');
    const answers = [brief.slice(0, 2).join(' ') || `${record.period?.start || ''} — ${record.period?.end || ''}`,
      isDerived(record) ? t('derivedActivity') : volume?.status === 'comparable' ? t('activity').replace('{before}', format(volume.before, 'contracts')).replace('{after}', format(volume.after, 'contracts')) : t('noActivity'),
      interest?.status === 'comparable' ? t('interest').replace('{before}', format(interest.before, 'contracts')).replace('{after}', format(interest.after, 'contracts')) : t('noInterest'), t('uncertainty')];
    for (let index = 0; index < 4; index++) { const card = el('article', undefined, 'history-question-card'); card.append(el('h4', t(`question${index + 1}`)), el('p', answers[index])); cards.append(card); }
    result.append(cards, renderChart(record));
    const daily = el('details', undefined, 'history-details'); daily.append(el('summary', t('daily')),
      table([t('date'),t('received'),t('common'),t('volume_total'),t('put_volume_share'),t('oi_total'),t('put_oi_share'),t('oiDate')], record.daily.map(day => [day.date,format(day.received_contracts),format(day.common_contracts),format(day.volume_total,'contracts'),format(day.put_volume_share,'fraction'),format(day.oi_total,'contracts'),format(day.put_oi_share,'fraction'),day.oi_asof_date || t('missing')]))); result.append(daily);
    const changeCards = el('section', undefined, 'history-changes'); changeCards.setAttribute('aria-label', t('changes'));
    for (const change of changes) changeCards.append(renderChange(change)); result.append(changeCards);
    if (Array.isArray(record.contract_changes) && record.contract_changes.length) {
      const prices = el('details', undefined, 'history-details'); prices.append(el('summary', t(isDerived(record) ? 'derivedPrices' : 'prices')),
        table([t('strike'),t('side'),t(isDerived(record) ? 'derivedBefore' : 'closeBefore'),t(isDerived(record) ? 'derivedAfter' : 'closeAfter'),t('priceChange')], record.contract_changes.map(item => [format(item.strike),t(item.right === 'P' ? 'put' : 'call'),format(item.before),format(item.after),item.status === 'comparable' ? format(item.change_pct,'percent') : t('incomparable')]))); result.append(prices);
    }
    if (Array.isArray(record.evidence) && record.evidence.length) {
      const evidence = el('details', undefined, 'history-details'); evidence.append(el('summary', t('evidence')), el('p', t('evidenceNote'), 'history-boundary'));
      for (const item of record.evidence) { const card = el('article', undefined, 'history-evidence'); card.append(el('strong', `${item.label || item.id} · ${format(item.value, item.unit)}`),el('code', item.id || ''),el('p', item.description || '')); evidence.append(card); }
      result.append(evidence);
    }
    if (Array.isArray(record.limitations) && record.limitations.length) {
      const limits = el('details', undefined, 'history-details'); limits.append(el('summary', t('limitations')));
      const list = el('ul', undefined, 'history-limitations'); for (const line of record.limitations) list.append(el('li', String(line))); limits.append(list); result.append(limits);
    }
    const followup = el('section', undefined, 'history-followup');
    const button = el('button', t('followup'), 'primary-button'); button.type = 'button'; button.disabled = busy;
    const note = el('p', t('followupHint'));
    button.addEventListener('click', async () => {
      if (busy || window.FinPilotAnalysis?.isBusy()) return;
      button.disabled = true;
      try { const attached = await window.FinPilotAnalysis?.attach(record, t('followupPrompt')); if (!attached) note.textContent = t('attachFailed'); }
      catch { note.textContent = t('attachFailed'); }
      finally { button.disabled = false; }
    });
    followup.append(button,note); result.append(followup);
  }
  function download(kind) {
    const dataset = { label:'', symbol:'', expiry:'YYYY-MM-DD', currency:'USD', multiplier:100, source_label:'', rows:[] };
    const text = kind === 'csv' ? rowKeys.join(',') + '\r\n' : JSON.stringify(dataset, null, 2) + '\n';
    const url = URL.createObjectURL(new Blob([text], { type:kind === 'csv' ? 'text/csv;charset=utf-8' : 'application/json;charset=utf-8' }));
    const link = el('a'); link.href = url; link.download = `finpilot_options_history_template.${kind}`; document.body.append(link); link.click(); link.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  function applyCopy() {
    panel.querySelectorAll('[data-history-text]').forEach(item => { item.textContent = t(item.dataset.historyText); });
    document.getElementById('history-label').placeholder = t('labelPlaceholder'); document.getElementById('history-source-label').placeholder = t('sourcePlaceholder');
    if (rows.length) fileStatus.textContent = t('fileReady').replace('{count}', rows.length);
    if (busy) status.textContent = t('processing'); renderPreview(); if (currentRecord) renderRecord(currentRecord);
  }
  fileInput.addEventListener('change', readFile);
  demo.addEventListener('click', () => request('/api/options/history/demo'));
  sample.addEventListener('click', () => request('/api/options/history/sample'));
  document.getElementById('history-template-csv').addEventListener('click', () => download('csv'));
  document.getElementById('history-template-json').addEventListener('click', () => download('json'));
  form.addEventListener('submit', event => {
    event.preventDefault(); if (busy) return; if (!rows.length) { showError(t('noFile')); return; }
    const data = new FormData(form);
    const payload = { label:String(data.get('label') || '').trim(), symbol:String(data.get('symbol') || '').trim().toUpperCase(), expiry:String(data.get('expiry') || '').trim(), currency:'USD', multiplier:100, rows };
    if (data.get('source_label')) payload.source_label = String(data.get('source_label')).trim();
    if (data.get('exported_at')) payload.exported_at = String(data.get('exported_at')).trim();
    if (metadata.bar_basis === 'derived_from_intraday_trades') payload.bar_basis = metadata.bar_basis;
    if (new TextEncoder().encode(JSON.stringify(payload)).length > MAX_BYTES) { showError(t('tooLarge')); return; }
    request('/api/options/history/import', payload);
  });
  document.getElementById('options-dialog').addEventListener('close', () => { if (controller) controller.abort('closed'); });
  new MutationObserver(applyCopy).observe(document.documentElement, { attributes:true, attributeFilter:['lang'] });
  window.FinPilotHistory = { showSavedReport(record) {
    if (record?.analysis_kind !== 'historical_options' || !Array.isArray(record.daily)) return;
    currentRecord = record; panel.open = true; closeSidebar(); openToolDialog(document.getElementById('options-dialog')); showError(''); renderRecord(record); result.scrollIntoView({ block:'start', behavior:'instant' });
  } };
  applyCopy();
})();
