(() => {
  'use strict';
  const $ = selector => document.querySelector(selector);
  const node = (tag, content, className) => { const item = document.createElement(tag); if (content !== undefined) item.textContent = content; if (className) item.className = className; return item; };
  const text = {
    skip:['跳到演示步骤','Skip to demo steps'], reduceMotion:['减少动态','Reduce motion'], workspace:['进入完整工作台 ↗','Open the full workspace ↗'],
    hero:['把历史数字，\n讲成有据可查的解释。','Historical numbers.\nExplanations you can check.'],
    description:['先看一份真实历史档案，再找到专家资料。最后，由你决定何时让 AI 解释这批数据。','Explore a real historical archive, find expert references, then decide when to ask AI to explain this data.'],
    principle1:['固定历史，不冒充实时','Fixed history, never presented as live'], principle2:['本地数字与专家依据分开','Local numbers and expert sources stay distinct'], principle3:['模型调用由你发起','You initiate model calls'],
    sessionNote:['本页只建立独立演示会话，不读取你已有的聊天。','This page creates its own demo conversation and does not read your existing chats.'], companion:['与你一起核查依据','Check the evidence together'],
    avatarIdle:['准备就绪','Ready'], avatarThinking:['正在处理当前步骤','Working on this step'], avatarError:['请查看操作提示','Check the status message'],
    avatarNote:['鲸鱼娘2D序列动画。动作表示操作状态，不代表判断置信度。','Whale-maid 2D sprite animation. Motion reflects activity, never confidence in a conclusion.'],
    characterLabel:['展示形象','Character'],whaleLabel:['鲸鱼娘 · 2D','Whale maid · 2D'],robotLabel:['原有机器人 · 2D/3D','Legacy robot · 2D/3D'],characterCredits:['角色来源与非商业许可 ↗','Character credits & noncommercial license ↗'],
    legacyAvatarNote:['原有 Three.js / SVG 机器人。动作只表示操作状态。','The legacy Three.js / SVG robot. Motion represents activity only.'],
    avatarFallback:['此设备的 3D 不可用，当前显示真实 2D 形象。','3D is unavailable on this device; the original 2D companion is shown.'],
    nav1:['一份历史档案','A historical archive'], nav1Hint:['先确定数据是什么','Establish what the data is'], nav2:['一组专家依据','Expert evidence'], nav2Hint:['查看检索的来路','Inspect how sources were found'], nav3:['可核查的 AI 解释','An explanation you can check'], nav3Hint:['每条回答都有范围','Each answer keeps its scope'],
    railNote:['这是学习与复盘流程，不是交易指令或涨跌预测。','A learning and review workflow, not trade instructions or a price forecast.'],
    archiveOverline:['从可追溯的历史开始','START WITH TRACEABLE HISTORY'], archiveTitle:['先看数据，再问结论。','The data comes before conclusions.'], localOnly:['本地档案回放','Local archive replay'],
    archiveDescription:['读取服务器已经保存的 IBKR 历史档案。这个按钮不会连接网关，也不会调用模型；合约到期后，档案仍可回看。','Read an IBKR historical archive already saved on this server. This button does not connect to the gateway or call a model; the archive remains available after contract expiration.'],
    load:['载入真实历史档案','Load the real historical archive'], reload:['重新载入这份档案','Reload this archive'], loadBoundary:['本次操作：0 次新行情采集 · 0 次模型调用','This action: 0 new market-data collections · 0 model calls'],
    archiveLoading:['正在读取已保存的历史档案…','Reading the saved historical archive…'], archiveReady:['历史档案已载入。没有重新连接网关或调用模型。','Historical archive loaded. No gateway reconnection or model call was made.'],
    expertsOverline:['把数字与专业原则放在一起','CONNECT NUMBERS WITH PROFESSIONAL PRINCIPLES'], expertsTitle:['找到解释背后的资料。','Find the references behind an explanation.'], retrievalOnly:['本地知识检索','Local knowledge retrieval'],
    expertsDescription:['提出一个关于这段历史的问题，查看实际检索的专家或官方片段。排名表示匹配程度，不是答案正确率，也不是向量模型的置信度。','Ask about this history and inspect the retrieved professional or official passages. Rankings indicate relevance, not answer accuracy or vector-model confidence.'],
    questionLabel:['你想弄清楚什么？','What would you like to understand?'], suggestActivity:['成交计数能说明情绪吗？','Do activity counts establish sentiment?'], suggestOI:['为什么缺少持仓不能补零？','Why can missing open interest not be zero?'], suggestPrice:['历史末值和当前报价有何不同？','How do historical end values differ from current quotes?'],
    search:['检索专家依据 ↗','Retrieve expert references ↗'], searching:['正在用词项与字符匹配检索本地资料…','Searching local references with term and character matching…'], searchReady:['候选资料已找到；本次检索未调用模型。','Candidate references found. This search made no model call.'],
    query:['本次候选检索问题','Candidate-search question'], reviewed:['资料审阅日期','Reference reviewed'], publisher:['资料发布方','Publisher'], openSource:['打开官方原文 ↗','Open the original reference ↗'],
    noHits:['没有找到与这个问题匹配的知识片段。可以改写问题；这不是“已找到充分依据”。','No matching passage was found. Rephrase the question; this does not establish sufficient evidence.'],
    candidatesNotice:['这里展示候选资料。生成时会根据实际提问再次检索；每条回答实际采用的来源在回答下方另列。','These are candidate references. Generation retrieves again for the actual question; each answer lists its own cited sources below.'],
    ranking:['查看双路检索与选择原因','Inspect retrieval routes and selection'], rankNotice:['BM25 词项与中文字符匹配各自排序，再由 RRF 合并。分数是相关性启发值，不是准确率，也没有使用 embedding 或向量数据库。','BM25 terms and Chinese character matches are ranked separately and fused with RRF. Scores are relevance heuristics, not accuracy. No embeddings or vector database are used.'],
    curated:['按问题或数据约束补充；不是自然检索排名。','Added for question or data constraints; this is not a natural retrieval rank.'], charRank:['字符排名','Character rank'], matched:['命中的主题或词项','Matched topics or terms'], notProvided:['未提供','Not provided'],
    selectedFacet:['为问题或数据约束选用；下列词法排名以实际返回值为准。','Selected for the question or data constraints; the lexical ranks below reflect the actual returned values.'], localExplanation:['本地说明','Local explanation'],
    aiOverline:['由你发起模型解释','YOU INITIATE THE MODEL EXPLANATION'], aiTitle:['让 AI 解释，也让依据可见。','Ask AI to explain. Keep the evidence visible.'], explicitModel:['明确点击才请求模型','Explicit click before a model call'],
    aiDescription:['模型读取这批已保存的历史摘要与检索资料。每条回答分别保留当时的数据依据和实际引用，新的问题不会改写旧回答。','The model receives this saved historical summary and retrieved references. Each answer keeps its evidence and citations; later questions do not rewrite earlier answers.'],
    modelLabel:['本次回答引擎','Answer engine'], checkingModels:['正在检查模型状态…','Checking model availability…'], modelReady:['所选引擎可用；你发送时才会请求。','Selected engine available; a request is made when you send.'], modelUnavailable:['当前没有可用引擎；仍可查看档案和检索资料。','No engine is available. You can still review the archive and retrieve references.'], modelUnknown:['未能确认模型状态，请稍后刷新页面重试。','Model availability could not be confirmed. Reload this page later.'],
    modelDisclosure:['点击下方按钮后，才会向所选模型发送这批历史摘要和问题；不会重新采集行情。','Only the button below sends this historical summary and question to the selected model; it does not collect new market data.'],
    chatLabel:['给模型的问题（可编辑）','Question for the model (editable)'], chatHint:['Enter 发送 · Shift + Enter 换行','Enter to send · Shift + Enter for a new line'], explain:['用 AI 解释这批数据','Ask AI to explain this data'], followup:['继续追问这段历史','Continue asking about this history'],
    thinking:['正在请求所选模型，核对回答依据…','Requesting the selected model and checking answer evidence…'], answerReady:['解释已返回；请一起阅读本地依据、来源和限制。','Explanation returned. Read its local evidence, references and limitations together.'],
    footer:['来源可追溯，不等于数据完整或判断必然正确。请结合历史区间、样本范围和每条依据阅读。','Traceable provenance does not establish completeness or correctness. Read the period, sample scope and evidence together.'],
    sourceReal:['真实 IBKR 历史档案 · 非当前行情','Real IBKR historical archive · not current quotes'], sourceDemo:['合成教学数据 · 非真实行情','Synthetic teaching data · not real market observations'], sourceImport:['导入资料 · 来源未经核验','Imported data · provenance unverified'],
    sourceScope:['来源可追溯仅表示由所配置网关返回；不代表独立交易所核验或完整时段覆盖。','Traceable provenance means the configured gateway returned the data; it does not establish exchange verification or complete-session coverage.'],
    historicalPeriod:['历史区间','Historical period'], expires:['合约到期日','Contract expiration'], fixedSample:['固定共同样本','Fixed common sample'], contracts:['份合约','contracts'], oiMissing:['未返回，保持缺失','Unavailable; kept missing'], oiRecorded:['有独立统计记录','Independent reports present'], coverage:['完整交易时段','Complete-session coverage'], coverageUnknown:['未核验','Unverified'], oiLabel:['未平仓量 / 独立统计日期','Open interest / reporting dates'],
    barNotice:['这些是所收盘中成交 bar 的末值和计数，不是官方收盘或结算价。覆盖未核验，不能把计数变化解释为全日活动变化。','These are end values and counts from received intraday trade bars, not official closing or settlement prices. Coverage is unverified, so count differences do not establish full-day activity changes.'],
    tradeNotice:['历史成交记录不是同步双边报价，也不代表现在可以按该价格交易。','Historical trade records are not synchronized bid/ask quotes or prices you can necessarily trade at now.'],
    call:['看涨 C','Call C'], put:['看跌 P','Put P'], strike:['行权价','Strike'], endValues:['同一合约所收 bar 末值','Received-bar end values for the same contract'], endpointNote:['左：首个历史日 · 右：末个历史日。值为每股报价，未乘合约乘数，不是整份合约总价；不同合约价格不混合。','Left: first historical date. Right: last historical date. Values are per-share quotes before the contract multiplier, not whole-contract cost. Prices of different contracts are not pooled.'],
    details:['核对所收 bar 数量与缺失','Check received bars and missing fields'], date:['历史日期','Historical date'], side:['合约类型','Side'], barCount:['所收 bar 数','Received bars'], firstBar:['首个 bar（UTC）','First bar (UTC)'], lastBar:['末个 bar（UTC）','Last bar (UTC)'], dailyValues:['查看本地按日数字','Inspect local daily values'], count:['所收样本计数','Received sample counts'], putShare:['样本看跌成交占比','Put share in the sample'], oi:['未平仓量','Open interest'], oiDate:['持仓统计日期','OI reporting date'],
    nextExperts:['接着查专家依据 ↗','Continue to expert references ↗'], nextAI:['接着编辑问题与模型解释 ↗','Continue to the model explanation ↗'], noContract:['档案没有返回可展示的逐合约末值。','No per-contract end values were returned for display.'],
    user:['你的问题','Your question'], assistant:['FinPilot 的解释','FinPilot explanation'], localEvidence:['本条回答的本地数据依据','Local data evidence for this answer'], dataRef:['数据依据','Data evidence'], expertRef:['专家来源','Expert source'], actualSources:['本条回答实际引用的资料','Sources actually cited in this answer'], replyRetrieval:['本条回答怎样检索知识','How references were retrieved for this answer'],
    first:['首个记录','First record'], last:['末个记录','Last record'], change:['变化量','Change'], incomparable:['不可直接比较','Not directly comparable'], percentagePoints:['个百分点','percentage points'], historyScope:['这条回答只针对所示历史区间，不代表当前行情。','This answer is limited to the shown historical period, not current market conditions.'],
    incomplete:['服务没有返回可核查的结果。','The service returned no result that could be checked.'], network:['无法连接本地服务，请检查服务后重试。','The local service could not be reached. Check it and retry.'], timeout:['请求超时，已保留本页的档案与输入，请稍后重试。','The request timed out. This page’s archive and input are retained; retry later.'], needQuestion:['请先写下具体问题。','Enter a specific question first.'],
    fallback:['本条回答有服务限制或采用了本地说明；请查看实际返回模式与引用。','A service limitation or locally generated explanation applies to this answer. Inspect the actual returned mode and citations.'],
    generalScope:['这条普通问答没有使用历史数据依据；已载入的历史档案仍保留在本页。','This general answer did not use historical data evidence. The loaded archive remains available on this page.'],
    grounding:['检查了哪些知识主题','Which knowledge topics were checked'], groundingNotice:['这是人工审阅主题的有限规则检查，不是逐句事实证明。未识别的说法不在这套规则保证内；数字仍以本地证据为准。','These are bounded rule checks against reviewed topics, not proof of every sentence. Unrecognized claims are outside this rule guarantee; numbers still come from local evidence.'],
    requiredTopics:['问题需要的主题','Topics required by the question'], coveredTopics:['实际覆盖的主题','Topics covered'], noTopics:['未返回覆盖明细；不能据此声称所有说法已被验证。','Coverage details were not returned. This does not establish that every claim was checked.'], supportingSources:['对应资料','Supporting references'], missingSource:['本条响应未提供该来源','This response did not return the source'], otherFacet:['其他返回主题（此页未收录名称）','Other returned topic (name not listed here)'],
    localName:['本地微调 · 实验版','Local fine-tuned · Experimental'], unavailable:['未就绪','Unavailable'], newArchive:['重新载入档案会开启新的独立演示上下文；不会改写已保存的旧会话。','Reloading the archive starts a new independent demo context; saved earlier conversations are not rewritten.'],
  };
  const questions = {
    activity:['这段期权历史中的成交计数和看跌占比，能否说明整体市场情绪？哪些地方不能比较？','Can activity counts and put share in this options history establish market-wide sentiment? What is not comparable?'],
    oi:['这段历史缺少未平仓量和独立统计日期，为什么不能补成零或推断资金流向？','Why can missing open interest and its reporting dates not be filled with zero or interpreted as fund flows?'],
    price:['这段历史里同一份看涨和看跌合约的所收 bar 末值，和官方收盘、结算价、当前报价有什么区别？','How do the received-bar end values for these call and put contracts differ from official closes, settlements and current quotes?'],
  };
  const facetNames = {
    bid_ask_execution:['双边报价、价差与成交','Bid/ask quotes, spreads and execution'], contract_comparability:['合约身份与可比范围','Contract identity and comparable scope'],
    expired_eod_limits:['到期期权与日终数据限制','Expired options and end-of-day limits'], historical_bar_semantics:['区间 bar 与同步报价','Interval bars and synchronized quotes'],
    historical_contract_iv_limits:['历史合约 IV 与希腊值限制','Historical contract IV and Greeks limits'], historical_oi_availability:['历史接口持仓字段边界','Historical API open-interest limits'],
    historical_permissions:['历史行情权限','Historical market-data permissions'], historical_time_basis:['历史日期与记录时间','Historical dates and recorded times'],
    historical_volume_filtering:['历史成交量筛选口径','Historical volume filtering'], iv_direction_limits:['波动幅度与涨跌方向','Volatility magnitude and price direction'],
    oi_reporting_cycle:['未平仓统计周期','Open-interest reporting cycle'], option_price_factors:['期权权利金影响因素','Factors affecting option premiums'],
    put_call_limits:['合约计数与人数','Contract counts and people'], volume_vs_oi:['成交量与未平仓量区别','Volume versus open interest'],
  };
  const state = { language:'zh', record:null, hits:[], searched:false, searchQuery:'', sessionId:null, messages:[], models:[], model:null, modelsChecked:false, modelError:false, busy:null, avatar:null, avatarCharacter:'whale', avatarMode:'2d', avatarState:'idle', reduced:matchMedia('(prefers-reduced-motion: reduce)').matches };
  const t = key => text[key]?.[state.language === 'en' ? 1 : 0] || key;
  const motion = () => state.reduced || matchMedia('(prefers-reduced-motion: reduce)').matches;
  const url = raw => { try { const parsed = new URL(raw); return ['https:','http:'].includes(parsed.protocol) ? parsed.href : null; } catch { return null; } };
  const number = (value, unit) => {
    if (typeof value !== 'number' || !Number.isFinite(value)) return t('notProvided');
    const amount = new Intl.NumberFormat(state.language === 'en' ? 'en-US' : 'zh-CN', { maximumFractionDigits:2 }).format(unit === 'fraction' ? value * 100 : value);
    if (unit === 'fraction' || unit === 'percent') return amount + '%';
    if (unit === 'contracts') return `${amount} ${t('contracts')}`;
    if (unit === 'percentage_points') return `${amount} ${t('percentagePoints')}`;
    return amount + (unit === 'USD' ? ' USD' : '');
  };
  function time(value) {
    const stamp = new Date(value || '');
    return Number.isNaN(stamp.getTime()) ? t('notProvided') : new Intl.DateTimeFormat(state.language === 'en' ? 'en-US' : 'zh-CN', { timeZone:'UTC', year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hourCycle:'h23' }).format(stamp);
  }
  async function api(path, { method='GET', body, timeout=20000 } = {}) {
    const controller = new AbortController(); const timer = setTimeout(() => controller.abort(), timeout);
    try {
      const response = await fetch(path, { method, signal:controller.signal, cache:'no-store', ...(body !== undefined ? { headers:{'Content-Type':'application/json'}, body:JSON.stringify(body) } : {}) });
      const data = await response.json().catch(() => null);
      if (!response.ok) { const detail = data?.detail; throw new Error(typeof detail === 'string' ? detail : detail?.message || `HTTP ${response.status}`); }
      return data;
    } catch (error) { if (error.name === 'AbortError') throw new Error(t('timeout')); if (error instanceof TypeError) throw new Error(t('network')); throw error; }
    finally { clearTimeout(timer); }
  }
  function error(stage, message) { const box = $(`#demo-${stage}-error`); box.textContent = message || ''; box.hidden = !message; }
  function status(stage, message) { const box = $(`#demo-${stage}-status`); box.textContent = message || ''; box.hidden = !message; }
  function avatarState(value) { state.avatarState = value; state.avatar?.setState(value); $('#demo-avatar-status').textContent = t(value === 'thinking' ? 'avatarThinking' : value === 'error' ? 'avatarError' : 'avatarIdle'); }
  function sync() {
    const busy = Boolean(state.busy), ready = state.models.some(model => model.id === state.model && model.available);
    $('#demo-load').disabled = busy;
    $('#demo-search-fields').disabled = busy || !state.record;
    $('#demo-chat-fields').disabled = busy || !state.record || !state.searched || !ready;
    $('#demo-model').disabled = busy || !state.modelsChecked || !state.models.some(model => model.available);
    $('#demo-language').disabled = busy;
    for (const [id, complete] of [['demo-archive',Boolean(state.record)],['demo-experts',state.searched],['demo-ai',state.messages.length > 0]]) {
      const section = $('#' + id); section.dataset.state = state.busy === id.slice(5) ? 'busy' : complete ? 'done' : id === 'demo-archive' || state.record ? 'ready' : 'locked';
      section.setAttribute('aria-busy', String(state.busy === id.slice(5)));
    }
    const step = !state.record ? 1 : !state.searched ? 2 : 3;
    document.querySelectorAll('[data-step-link]').forEach(link => { if (Number(link.dataset.stepLink) === step) link.setAttribute('aria-current','step'); else link.removeAttribute('aria-current'); });
    $('#demo-load [data-demo-text]').textContent = t(state.record ? 'reload' : 'load');
    $('#demo-explain').textContent = t(state.messages.length ? 'followup' : 'explain');
  }
  function setBusy(stage) { state.busy = stage; avatarState(stage ? 'thinking' : 'idle'); sync(); }
  function modelLabel(model) { return model.id === 'local' ? t('localName') : model.label || model.id; }
  function renderModels() {
    const select = $('#demo-model'); select.replaceChildren();
    for (const model of state.models) { const option = node('option', `${modelLabel(model)}${model.available ? '' : ' · ' + t('unavailable')}`); option.value = model.id; option.disabled = !model.available; select.append(option); }
    if (!state.models.length) { const option = node('option', t(state.modelsChecked ? 'modelUnavailable' : 'checkingModels')); select.append(option); }
    if (state.model) select.value = state.model;
    $('#demo-model-status').textContent = t(state.modelError ? 'modelUnknown' : state.models.some(model => model.id === state.model && model.available) ? 'modelReady' : state.modelsChecked ? 'modelUnavailable' : 'checkingModels');
    sync();
  }
  function table(headers, rows) {
    const scroll = node('div', undefined, 'table-scroll'); scroll.tabIndex = 0;
    const table = node('table'); const head = table.createTHead().insertRow();
    for (const label of headers) { const cell = node('th', label); cell.scope = 'col'; head.append(cell); }
    const body = table.createTBody(); for (const values of rows) { const row = body.insertRow(); for (const value of values) row.insertCell().textContent = value; }
    scroll.append(table); return scroll;
  }
  function details(label) { const item = node('details', undefined, 'quiet-details'); item.append(node('summary', label)); return item; }
  function archiveSource(record) { return record.source?.kind === 'demo' ? t('sourceDemo') : record.source?.kind === 'ibkr_historical' ? t('sourceReal') : t('sourceImport'); }
  function renderArchive() {
    const container = $('#demo-archive-result'); container.replaceChildren(); container.hidden = !state.record; if (!state.record) return;
    const record = state.record; container.className = 'archive-result'; container.dataset.analysisId = record.analysis_id;
    const badge = node('span', archiveSource(record), 'source-badge'); badge.dataset.demo = String(record.source?.kind === 'demo');
    container.append(badge, node('h3', record.label || record.symbol), node('p', `${record.symbol} · ${t('expires')} ${record.expiry} · ${t('historicalPeriod')} ${record.period?.start || '—'} → ${record.period?.end || '—'}`, 'archive-period'),
      node('p', record.bar_basis === 'derived_from_intraday_trades' ? t('barNotice') : t('tradeNotice'), 'archive-limit'), node('p', record.source?.kind === 'ibkr_historical' ? t('sourceScope') : archiveSource(record), 'archive-limit'));
    const facts = node('dl', undefined, 'archive-facts');
    const hasOI = record.daily.some(day => typeof day.oi_total === 'number' && Number.isFinite(day.oi_total));
    for (const [key,value] of [['fixedSample',number(record.quality?.common_contracts,'contracts')],['coverage',t('coverageUnknown')],['oiLabel',t(hasOI ? 'oiRecorded' : 'oiMissing')]]) { const fact = node('div', undefined, 'archive-fact'); fact.append(node('dt',t(key)),node('dd',value)); facts.append(fact); }
    container.append(facts);
    const cards = node('div', undefined, 'contract-cards');
    for (const contract of Array.isArray(record.contract_changes) ? record.contract_changes : []) {
      const card = node('article', undefined, 'contract-card'); card.dataset.contract = `${contract.strike}${contract.right}`;
      card.append(node('h4', `${t(contract.right === 'P' ? 'put' : 'call')} · ${t('strike')} ${number(contract.strike)}`));
      const pair = node('div', undefined, 'contract-price-pair'); pair.append(node('strong',number(contract.before,'USD')),node('span','→'),node('strong',number(contract.after,'USD')));
      card.append(pair,node('p',t('endValues')),node('p',t('endpointNote'))); cards.append(card);
    }
    if (!cards.childElementCount) cards.append(node('p', t('noContract'),'archive-limit'));
    container.append(cards);
    const provenance = record.historical_capture?.row_provenance;
    if (Array.isArray(provenance) && provenance.length) { const view = details(t('details')); view.append(table([t('date'),t('side'),t('barCount'),t('firstBar'),t('lastBar')],provenance.map(row => [row.trading_date || '—',row.right || '—',number(row.observed_hourly_bars),time(row.first_bar_at),time(row.last_bar_at)]))); container.append(view); }
    const daily = details(t('dailyValues')); daily.append(table([t('date'),t('count'),t('putShare'),t('oi'),t('oiDate')],record.daily.map(day => [day.date,number(day.volume_total,'contracts'),number(day.put_volume_share,'fraction'),number(day.oi_total,'contracts'),day.oi_asof_date || t('notProvided')]))); container.append(daily);
    const next = node('a', t('nextExperts'),'next-link'); next.href = '#demo-experts'; container.append(next,node('p',t('newArchive'),'small-note'));
  }
  function renderRanks(hit, parent) {
    const ranking = {...hit,...(hit.retrieval || {})};
    const box = details(t('ranking')); box.classList.add('retrieval-details');
    if (ranking.method === 'curated_support_facet') box.append(node('p', t('curated')));
    else {
      if (['required_facet','query_facet','context_facet'].includes(ranking.selection_reason)) box.append(node('p',t('selectedFacet')));
      const ranks = node('div',undefined,'retrieval-ranks'); ranks.append(node('span',`BM25: ${ranking.bm25_rank ?? '—'}`),node('span',`${t('charRank')}: ${ranking.char_rank ?? '—'}`),node('span',`RRF: ${typeof ranking.rrf_score === 'number' ? ranking.rrf_score.toFixed(5) : '—'}`)); box.append(ranks);
      box.append(node('p',t('rankNotice')));
    }
    const matched = [...(Array.isArray(ranking.matched_topics) ? ranking.matched_topics : []),...(Array.isArray(ranking.matched_terms) ? ranking.matched_terms : [])];
    if (matched.length) box.append(node('p',`${t('matched')} · ${[...new Set(matched)].slice(0,10).join(' / ')}`));
    parent.append(box);
  }
  function renderExperts() {
    const container = $('#demo-expert-results'); container.replaceChildren(); container.hidden = !state.searched; if (!state.searched) return;
    container.className = 'expert-results'; container.append(node('p',`${t('query')} · ${state.searchQuery}`,'expert-query'),node('p',t('candidatesNotice'),'archive-limit'));
    if (!state.hits.length) container.append(node('p',t('noHits'),'archive-limit'));
    state.hits.forEach((hit,index) => {
      const card = node('article',undefined,'expert-card'); card.dataset.sourceId = hit.id || '';
      card.append(node('h3',`${index + 1}. ${hit.title || hit.id}`));
      const meta = node('div',undefined,'expert-meta'); meta.append(node('span',`${t('publisher')} · ${hit.publisher || t('notProvided')}`),node('span',`${t('reviewed')} · ${hit.reviewed_at || t('notProvided')}`)); card.append(meta,node('p',state.language === 'en' ? hit.text_en || hit.text || '' : hit.text || hit.text_en || '','expert-excerpt'));
      const address = url(hit.url); if (address) { const link = node('a',t('openSource'),'expert-source-link'); link.href = address; link.target = '_blank'; link.rel = 'noopener noreferrer'; card.append(link); }
      renderRanks(hit,card); container.append(card);
    });
    const next = node('a',t('nextAI'),'next-link'); next.href = '#demo-ai'; container.append(next);
  }
  function renderEvidence(records) {
    const section = details(`${t('localEvidence')} (${records.length})`); section.classList.add('demo-local-evidence');
    const list = node('div',undefined,'demo-evidence-list'), references = new Map();
    for (const record of records) {
      if (!record || typeof record.id !== 'string') continue;
      const card = node('article',undefined,'demo-evidence-card'); card.tabIndex = -1; card.dataset.evidenceId = record.id;
      card.append(node('strong',record.label || record.id),node('p',number(record.value,record.unit)),node('code',record.id));
      if (record.description) card.append(node('p',record.description));
      if (record.trading_date || record.oi_asof_date) card.append(node('p',[record.trading_date,record.oi_asof_date ? `${t('oiDate')} ${record.oi_asof_date}` : ''].filter(Boolean).join(' · ')));
      if (Object.hasOwn(record,'before') || Object.hasOwn(record,'after')) {
        const values = node('dl',undefined,'evidence-pair');
        for (const [key,label] of [['before','first'],['after','last'],['delta','change']]) { const item = node('div'); let value = key === 'delta' && record.status !== 'comparable' ? t('incomparable') : number(record[key],key === 'delta' ? record.delta_unit : record.unit); if (key === 'delta' && record.status === 'comparable' && Number.isFinite(record.delta) && record.delta > 0) value = '+' + value; item.append(node('dt',t(label)),node('dd',value)); values.append(item); }
        card.append(values);
      }
      list.append(card); references.set(record.id,{card,section,number:references.size+1});
    }
    section.append(list); return {section,references};
  }
  function renderGrounding(grounding, sources) {
    const view = details(t('grounding')); view.classList.add('demo-grounding');
    view.append(node('p',t('groundingNotice')));
    const name = facet => facetNames[facet]?.[state.language === 'en' ? 1 : 0] || t('otherFacet');
    const required = Array.isArray(grounding.required_query_facets) ? grounding.required_query_facets : [];
    const covered = Array.isArray(grounding.covered_facets) ? grounding.covered_facets : [];
    if (required.length) view.append(node('p',`${t('requiredTopics')} · ${required.map(name).join(' / ')}`));
    if (covered.length) view.append(node('p',`${t('coveredTopics')} · ${covered.map(name).join(' / ')}`));
    const paragraphs = Array.isArray(grounding.paragraphs) ? grounding.paragraphs : [];
    let displayed = 0;
    for (const part of paragraphs) {
      for (const facet of Array.isArray(part.claim_facets) ? part.claim_facets : []) {
        const item = node('div',undefined,'grounding-topic'); item.dataset.facetId = facet;
        item.append(node('strong',name(facet)));
        const ids = Array.isArray(part.supporting_sources?.[facet]) ? part.supporting_sources[facet] : [];
        const row = node('p',`${t('supportingSources')} · `);
        if (!ids.length) row.append(document.createTextNode(t('missingSource')));
        for (const [index,id] of ids.entries()) {
          if (index) row.append(document.createTextNode(' / '));
          const source = sources.get(id), address = url(source?.url);
          if (!source) row.append(document.createTextNode(t('missingSource')));
          else { const link=node(address?'a':'span',source.title||t('expertRef')); link.dataset.sourceId=id; if(address){link.href=address;link.target='_blank';link.rel='noopener noreferrer';} row.append(link); }
        }
        item.append(row); view.append(item); displayed++;
      }
    }
    if (!displayed) view.append(node('p',t('noTopics')));
    return view;
  }
  function answerText(content, local, sources) {
    const container = node('div',undefined,'demo-answer-text');
    for (const paragraph of String(content || '').split(/\n\s*\n/)) {
      const p = node('p'); let offset = 0;
      for (const match of paragraph.matchAll(/\[([A-Za-z][A-Za-z0-9_.-]*)\]/g)) {
        p.append(document.createTextNode(paragraph.slice(offset,match.index)));
        const id = match[1];
        if (local.has(id)) {
          const reference = local.get(id), button = node('button',`${t('dataRef')} ${reference.number}`,'demo-inline-reference'); button.type = 'button'; button.dataset.evidenceId = id;
          button.addEventListener('click',() => { reference.section.open = true; reference.card.scrollIntoView({block:'center',behavior:motion()?'instant':'smooth'}); reference.card.focus({preventScroll:true}); }); p.append(button);
        } else if (sources.has(id) && url(sources.get(id).url)) {
          const source = sources.get(id), link = node('a',`${t('expertRef')} ${source.number}`,'demo-inline-reference demo-expert-reference'); link.href = url(source.url); link.target = '_blank'; link.rel = 'noopener noreferrer'; link.dataset.sourceId = id; link.title = source.title || id; p.append(link);
        } else p.append(document.createTextNode(match[0]));
        offset = match.index + match[0].length;
      }
      p.append(document.createTextNode(paragraph.slice(offset))); container.append(p);
    }
    return container;
  }
  function renderMessages() {
    const container = $('#demo-messages'); container.replaceChildren();
    for (const message of state.messages) {
      const item = node('article',undefined,`demo-message ${message.role}`);
      if (message.role === 'user') { item.textContent = message.content; container.append(item); continue; }
      const projectHelp=window.FinPilotMessages?.extractProjectHelp(message);
      if(projectHelp){const header=node('div',undefined,'demo-message-header');header.append(node('strong',t('assistant')),node('span',state.language==='en'?'Project guide · Local manual':'项目指南 · 本地手册','message-mode'));const text=node('div',message.content,'demo-answer-text project-help-canonical');text.hidden=true;item.append(header,text,window.FinPilotMessages.renderProjectHelp(projectHelp,{language:state.language}));container.append(item);continue;}
      const context = message.analysis_context || {}, records = Array.isArray(context.evidence) ? context.evidence : [];
      const evidence = renderEvidence(records), sources = new Map((message.sources || []).map((source,index) => [source.id,{...source,number:index+1}]));
      const mode = message.mode === 'deepseek' ? 'DeepSeek' : message.mode === 'local-lora' ? t('localName') : message.mode === 'offline' ? t('localExplanation') : message.mode || '—';
      const header = node('div',undefined,'demo-message-header'); header.append(node('strong',t('assistant')),node('span',mode,'message-mode'));
      item.append(header,answerText(message.content,evidence.references,sources));
      const period = context.period || {}; item.append(node('p',message.analysis_context ? `${t('historicalPeriod')} ${period.start || '—'} → ${period.end || '—'} · ${t('historyScope')} ${context.source_label || ''}` : t('generalScope'),'reply-scope'));
      if (message.warning) item.append(node('p',t('fallback'),'reply-warning'));
      if (records.length) item.append(evidence.section);
      if (sources.size) {
        const section = details(`${t('actualSources')} (${sources.size})`); section.open = true; section.classList.add('demo-actual-sources');
        const cards = node('div',undefined,'reply-sources');
        for (const source of sources.values()) { const card = node('div',undefined,'reply-source'); card.dataset.sourceId = source.id; const address = url(source.url), label = node(address ? 'a' : 'span',`${source.number}. ${source.title || t('expertRef')}`); if (address) { label.href=address;label.target='_blank';label.rel='noopener noreferrer'; } card.append(label,node('small',[source.publisher,source.reviewed_at ? `${t('reviewed')} ${source.reviewed_at}` : ''].filter(Boolean).join(' · '))); cards.append(card); }
        section.append(cards); item.append(section);
      }
      if (context.grounding && typeof context.grounding === 'object') item.append(renderGrounding(context.grounding,sources));
      if (Array.isArray(context.retrieval?.hits) && context.retrieval.hits.length) { const retrieval = details(t('replyRetrieval')); retrieval.append(node('p',t('candidatesNotice'))); for (const hit of context.retrieval.hits) { const row=node('div'); row.append(node('p',hit.title || sources.get(hit.id)?.title || hit.id)); renderRanks(hit,row); retrieval.append(row); } item.append(retrieval); }
      container.append(item);
    }
  }
  async function loadArchive() {
    if (state.busy) return; error('load',''); status('load',t('archiveLoading')); setBusy('archive');
    try {
      const record = await api(`/api/options/history/sample?language=${state.language}`,{method:'POST'});
      if (record?.analysis_kind !== 'historical_options' || typeof record.analysis_id !== 'string' || !Array.isArray(record.daily)) throw new Error(t('incomplete'));
      state.record=record;state.hits=[];state.searched=false;state.searchQuery='';state.sessionId=null;state.messages=[];
      renderArchive();renderExperts();renderMessages();$('#demo-chat-input').value=$('#demo-question').value; status('load',t('archiveReady'));status('search','');status('ai','');error('search','');error('ai','');
      $('#demo-archive-result').tabIndex=-1;$('#demo-archive-result').focus({preventScroll:true});
    } catch (failure) { error('load',failure.message); status('load',''); }
    finally { setBusy(null); if (!$('#demo-load-error').hidden) avatarState('error'); }
  }
  async function searchExperts(event) {
    event?.preventDefault(); if (state.busy || !state.record) return;
    const query = $('#demo-question').value.trim(); if (!query) { error('search',t('needQuestion')); $('#demo-question').focus(); return; }
    error('search','');status('search',t('searching'));setBusy('experts');
    try {
      const hits = await api(`/api/experts/search?q=${encodeURIComponent(query)}&limit=4`);
      if (!Array.isArray(hits)) throw new Error(t('incomplete'));
      state.hits=hits;state.searched=true;state.searchQuery=query;renderExperts();if(!state.messages.length||!$('#demo-chat-input').value.trim())$('#demo-chat-input').value=query;status('search',t('searchReady'));
      $('#demo-expert-results').tabIndex=-1;$('#demo-expert-results').focus({preventScroll:true});
    } catch (failure) { error('search',failure.message);status('search',''); }
    finally { setBusy(null); if (!$('#demo-search-error').hidden) avatarState('error'); }
  }
  async function askAI(event) {
    event?.preventDefault(); if (state.busy || !state.record || !state.searched || !state.models.some(model => model.id === state.model && model.available)) return;
    const input = $('#demo-chat-input'), message=input.value.trim(); if (!message) { error('ai',t('needQuestion'));input.focus();return; }
    const analysisId=state.record.analysis_id, engine=state.model, language=state.language;
    error('ai','');status('ai',t('thinking'));setBusy('ai');
    try {
      const reply=await api('/api/chat',{method:'POST',timeout:90000,body:{message,session_id:state.sessionId,analysis_id:analysisId,engine,language}});
      if (!reply?.session_id || typeof reply.answer !== 'string' || reply.analysis_context && reply.analysis_context.analysis_id !== analysisId) throw new Error(t('incomplete'));
      state.sessionId=reply.session_id;state.messages.push({role:'user',content:message},{role:'assistant',content:reply.answer,sources:Array.isArray(reply.sources)?reply.sources:[],mode:reply.mode,warning:reply.warning,analysis_context:reply.analysis_context,project_help:reply.project_help||null});
      input.value='';renderMessages();status('ai',t('answerReady'));$('#demo-messages').lastElementChild?.scrollIntoView({block:'start',behavior:motion()?'instant':'smooth'});
    } catch (failure) { error('ai',failure.message);status('ai',''); }
    finally { setBusy(null); if (!$('#demo-ai-error').hidden) avatarState('error'); }
  }
  function applyLanguage() {
    document.documentElement.lang=state.language==='en'?'en':'zh-CN'; document.title=state.language==='en'?'FinPilot · History, evidence & explanation':'FinPilot · 历史、依据与解释';
    document.querySelectorAll('[data-demo-text]').forEach(item=>{item.textContent=item.dataset.demoText==='usageGuide'?(state.language==='en'?'Usage guide ↗':'使用指南 ↗'):t(item.dataset.demoText);});
    $('#demo-title').style.whiteSpace='pre-line';$('#demo-language').textContent=state.language==='en'?'中文':'EN';$('#demo-language').setAttribute('aria-label',state.language==='en'?'切换为中文':'Switch to English');
    state.avatar?.setLanguage(state.language);renderModels();renderArchive();renderExperts();renderMessages();avatarState(state.avatarState);sync();
    if(!state.busy){if(state.record&&$('#demo-load-error').hidden)status('load',t('archiveReady'));if(state.searched&&$('#demo-search-error').hidden)status('search',t('searchReady'));if(state.messages.length&&$('#demo-ai-error').hidden)status('ai',t('answerReady'));}
  }
  function applyMotion() { document.documentElement.dataset.motion=motion()?'reduced':'full';$('#demo-motion').checked=motion();state.avatar?.setReducedMotion(motion()); }
  function mountAvatar() {
    const renderer=state.avatarCharacter==='whale'?window.FinPilotCompanion:window.FinPilotAvatar;
    if (state.avatar || !renderer) return;
    const stage=$('#demo-avatar-stage');
    state.avatar=renderer.mount(stage,{mode:state.avatarMode,language:state.language,reducedMotion:motion()});state.avatar.setReducedMotion(motion());state.avatar.setState(state.avatarState);
    window.finPilotDemoCompanion=state.avatar;
    renderAvatarStatus(state.avatar.getStatus());
  }
  function renderAvatarStatus(value) {
    $('#demo-avatar-renderer').textContent=state.avatarCharacter==='whale'?(value.renderer==='canvas2d'?'2D / SPRITE':value.renderer==='static-image'?'2D / STATIC':'2D / UNAVAILABLE'):value.renderer==='webgl2'?'3D / WEBGL':'2D / SVG';
    $('#demo-avatar-note').textContent=state.avatarCharacter==='whale'?t('avatarNote'):t(value.fallbackReason?'avatarFallback':'legacyAvatarNote');
  }
  for(const name of ['finpilot-avatar-status','finpilot-companion-status'])$('#demo-avatar-stage').addEventListener(name,event=>renderAvatarStatus(event.detail));
  $('#demo-avatar-character').addEventListener('change',event=>{state.avatar?.destroy();state.avatar=null;$('#demo-avatar-stage').replaceChildren();state.avatarCharacter=event.target.value;state.avatarMode=state.avatarCharacter==='whale'?'2d':'3d';$('#demo-legacy-modes').hidden=state.avatarCharacter==='whale';for(const mode of ['2d','3d'])$(`#demo-avatar-${mode}`).setAttribute('aria-pressed',String(mode===state.avatarMode));mountAvatar();});
  $('#demo-load').addEventListener('click',loadArchive);$('#demo-search-form').addEventListener('submit',searchExperts);$('#demo-chat-form').addEventListener('submit',askAI);
  $('#demo-chat-input').addEventListener('keydown',event=>{if(event.key==='Enter'&&!event.shiftKey&&!event.isComposing){event.preventDefault();askAI();}});
  $('#demo-language').addEventListener('click',()=>{if(state.busy)return;state.language=state.language==='zh'?'en':'zh';applyLanguage();});
  $('#demo-model').addEventListener('change',event=>{state.model=event.target.value;renderModels();});
  $('#demo-motion').addEventListener('change',event=>{state.reduced=event.target.checked;applyMotion();});matchMedia('(prefers-reduced-motion: reduce)').addEventListener('change',applyMotion);
  document.querySelectorAll('[data-question]').forEach(button=>button.addEventListener('click',()=>{const value=questions[button.dataset.question][state.language==='en'?1:0];$('#demo-question').value=value;$('#demo-question').focus();}));
  for (const mode of ['2d','3d']) $(`#demo-avatar-${mode}`).addEventListener('click',()=>{state.avatarMode=mode;state.avatar?.setMode?.(mode);for(const value of ['2d','3d'])$(`#demo-avatar-${value}`).setAttribute('aria-pressed',String(value===mode));});
  window.addEventListener('finpilot-avatar-ready',mountAvatar);window.addEventListener('finpilot-companion-ready',mountAvatar);window.addEventListener('pagehide',()=>state.avatar?.destroy(),{once:true});
  $('#demo-question').value=questions.activity[0];$('#demo-chat-input').value=questions.activity[0];
  applyLanguage();applyMotion();mountAvatar();
  api('/api/models').then(data=>{state.models=Array.isArray(data?.models)?data.models:[];state.modelsChecked=true;state.model=state.models.find(model=>model.id===data.default&&model.available)?.id||state.models.find(model=>model.available)?.id||null;renderModels();}).catch(()=>{state.modelsChecked=true;state.modelError=true;renderModels();});
})();
