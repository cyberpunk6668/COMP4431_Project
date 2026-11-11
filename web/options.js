(() => {
  'use strict';

  const dialog = document.getElementById('options-dialog');
  const form = document.getElementById('options-form');
  const fields = document.getElementById('options-fields');
  const symbolInput = document.getElementById('options-symbol');
  const analysisMode = document.getElementById('options-analysis-mode');
  const batchInput = document.getElementById('options-batch-items');
  const gateway = document.getElementById('options-gateway');
  const progress = document.getElementById('options-request-status');
  const errorBox = document.getElementById('options-error');
  const results = document.getElementById('options-results');
  const errorActions = document.getElementById('options-error-actions');
  const expirySelect = document.getElementById('options-expiry');
  const expiryStatus = document.getElementById('options-expiry-status');
  const expiryRefresh = document.getElementById('options-refresh-expirations');

  const copy = {
    nav: ['期权分析', 'Options analysis'],
    easyView: ['易懂解读', 'Easy reading'],
    professionalView: ['专业详情', 'Technical details'],
    symbolHint: ['例如 AAPL（苹果）或 SPY（标普 500 ETF）。', 'For example AAPL (Apple) or SPY (an S&P 500 ETF).'],
    advancedSettings: ['调整日期、范围与报价时间', 'Adjust dates, sample range and quote timing'],
    whatThisMeans: ['这对理解数据意味着什么', 'How to read this'],
    checkEvidence: ['查看依据', 'Check the evidence'],
    whyAndEvidence: ['展开解释与依据', 'Explanation and evidence'],
    nextSteps: ['接下来可以看什么', 'What to look at next'],
    glossary: ['这些词是什么意思？', 'What do these words mean?'],
    batchReading: ['逐个项目看', 'Read each item'],
    selectedScope: ['本次查看范围', 'Scope of this report'],
    missingBrief: ['这份响应还没有易懂解读，可以切换到专业详情核查数据。', 'This response has no plain-language brief yet. You can review its technical details.'],
    aiMore: ['AI 的补充解释', 'Additional AI explanation'],
    dataTime: ['先看数据时间', 'Start with the data timing'],
    retryDelayed: ['改用延迟数据重试', 'Retry with delayed data'],
    openDataSettings: ['查看数据设置', 'Open data settings'],
    failedPlain: ['这些项目暂时没有读到数据', 'Data was unavailable for these items'],
    title: ['看懂期权里的市场线索', 'Understand the options picture'],
    description: ['先看这批数据有多新、交易分布怎样，再了解它能说明什么。', 'Start with how current the data is and where activity sits, then see what it can tell you.'],
    analysisMode: ['你想了解什么', 'What would you like to explore?'],
    singleMode: ['了解一个公司或基金', 'Explore one company or fund'],
    batchMode: ['把几个标的或日期放在一起比较', 'Compare companies, funds or dates'],
    batchItems: ['对比清单', 'Comparison list'],
    batchHint: ['每行一个代码，后面可填写实际到期日（YYYY-MM-DD）；最多 4 行，提交前会核验日期。', 'One symbol per line, optionally followed by an actual expiration (YYYY-MM-DD). Up to four lines; dates are verified before collection.'],
    invalidBatch: ['请填写 1 至 4 行有效代码，日期格式为 YYYY-MM-DD，并删除重复项目。', 'Enter one to four valid symbols with optional YYYY-MM-DD dates and remove duplicate entries.'],
    symbol: ['公司或基金代码', 'Company or fund symbol'],
    expiry: ['合约到期日', 'Option expiration'],
    expiryHint: ['日期来自所选标的的实际期权链。留空使用最近可用到期日。', 'Dates come from the selected symbol’s actual option chain. Leave blank for the nearest available expiration.'],
    expiryNearest: ['最近可用到期日（自动选择）', 'Nearest available expiration (automatic)'],
    expiryRefresh: ['读取可选到期日', 'Load available expirations'],
    expiryLoading: ['正在从 IBKR 读取可用到期日…', 'Reading available expirations from IBKR…'],
    expiryChooseSymbol: ['先填写公司或基金代码，再读取可选到期日。', 'Enter a company or fund symbol, then load its available expirations.'],
    expiryAvailable: ['以下只列出期权链返回的可用到期日。', 'Only available expirations returned by the option chain are listed.'],
    expiryUnavailable: ['未能读取日期列表。仍可留空，让服务选择最近可用到期日。', 'The date list could not be loaded. Leave it blank to let the service choose the nearest available expiration.'],
    expiryEmpty: ['该标的暂未返回可用到期日。', 'No available expiration was returned for this symbol.'],
    expiryDates: ['可用到期日', 'Available expirations'],
    expiryChecking: ['正在核对所选日期是否属于该标的的实际到期日…', 'Checking the selected dates against the symbols’ actual expirations…'],
    followupTitle: ['接着，把这批数据问清楚', 'Keep exploring this data'],
    followupAction: ['针对这批数据追问', 'Ask about this data'],
    followupHint: ['为这批数据开启专属追问会话，只预填问题。点击发送后，才会把这批摘要交给当前选择的模型。', 'Open a dedicated conversation for this snapshot and prefill a question. Only Send gives its summary to your selected model.'],
    followupMeaning: ['这些数据说明什么？', 'What does this data tell us?'],
    followupEvidence: ['哪项依据最重要？', 'Which evidence matters most?'],
    followupUnknown: ['有哪些不能确定的？', 'What remains uncertain?'],
    followupPrediction: ['为何不是涨跌预测？', 'Why is this not a price forecast?'],
    followupPrompt: ['请用非专业人士能懂的话解释这批期权数据：主要说明什么，依据是什么，又有哪些不能确定？', 'Explain this options snapshot in plain language: what does it suggest, what evidence supports that, and what remains uncertain?'],
    savedReport: ['正在查看已保存的固定快照；此操作不会重新采集行情。', 'Viewing a saved, fixed snapshot. Opening it does not collect new market data.'],
    followupFailed: ['未能关联这批分析。尚未发送给模型，请稍后重试。', 'The analysis could not be linked. Nothing was sent to the model; try again.'],
    savedFreshness: ['已保存的行情快照', 'Saved market-data snapshot'],
    savedFreshnessMeaning: ['本次未重新读取行情。行情类型、质量与报告结论对应采集时记录，不代表当前市场。', 'No new market data was read. Feed types, quality and conclusions describe the captured sample, not the current market.'],
    savedQuality: ['以下为采集时的质量记录；“采集距报告完成”是原报告生成时的间隔，不是这份快照当前的年龄。', 'Quality below describes collection time. “Capture age at report completion” is the original report interval, not the snapshot’s current age.'],
    radius: ['查看的约定价格范围', 'Which contract prices should be sampled?'],
    radiusHint: ['围绕最接近股票或基金现价的约定价格取样。', 'Sample contract prices around the current stock or fund reference price.'],
    requestedMode: ['希望获取哪一类报价', 'Which kind of quotes should be requested?'],
    serverMode: ['采用本机设置', 'Use this computer’s setting'],
    requestLive: ['实时数据', 'Live data'],
    requestFrozen: ['冻结报价（保留的旧数据）', 'Frozen quotes (retained older data)'],
    requestDelayed: ['接受延迟数据', 'Accept delayed data'],
    requestDelayedFrozen: ['延迟且冻结的数据', 'Delayed and frozen data'],
    feedHint: ['报告会明确显示实际收到的数据时间类型。', 'The report shows which kind of data actually arrived.'],
    interpret: ['让 AI 补充解释', 'Ask AI for an additional explanation'],
    interpretHint: ['会把汇总指标发给模型服务。请在你的行情许可允许时勾选。', 'This sends aggregate indicators to the model provider. Enable it when your market data license permits.'],
    submit: ['帮我读懂这批期权', 'Help me understand these options'],
    loading: ['正在读取数据，核对时间与覆盖范围，并整理解释…', 'Reading the data, checking its time and coverage, and preparing the explanation…'],
    complete: ['期权分析已完成。', 'Options analysis completed.'],
    timeout: ['请求超时，请检查 IB Gateway 后重试。', 'The request timed out. Check IB Gateway and try again.'],
    disconnected: ['无法连接本地服务，请检查服务后重试。', 'The local service could not be reached. Check the service and try again.'],
    invalidResponse: ['服务没有返回可显示的期权分析。', 'The service returned no readable options analysis.'],
    invalidSymbol: ['请输入美股或 ETF 的标的代码。', 'Enter a US stock or ETF symbol.'],
    gateway: ['数据连接', 'Data connection'],
    gatewayChecking: ['正在检查网关端口…', 'Checking the gateway port…'],
    gatewayUnknown: ['无法确认网关端口状态。', 'The gateway port status is unknown.'],
    disabled: ['本地期权行情功能尚未启用。', 'The local options provider is disabled.'],
    dependency_missing: ['本地服务缺少 IBKR 行情依赖。', 'The local service is missing the IBKR market data dependency.'],
    gateway_unreachable: ['网关端口不可访问。请检查本机 IB Gateway。', 'The gateway port is unreachable. Check IB Gateway on this computer.'],
    tcp_ready: ['已找到本机数据网关。读取后检查数据是否可用。', 'The local data gateway was found. Collect data to check its availability.'],
    source: ['行情来源', 'Data source'],
    snapshotId: ['快照编号', 'Snapshot ID'],
    modelEvidence: ['模型选中的指标', 'Indicators selected by the model'],
    fixture: ['测试样本', 'Test fixture'],
    underlying: ['标的参考价', 'Underlying reference'],
    referenceClose: ['标的价格来自收盘参考', 'Underlying price uses a closing reference'],
    referenceCloseMeaning: ['仅收到收盘参考价，用于选择合约范围；不是当前可成交报价。', 'Only a closing reference was received and used to choose the contract range. This is not a currently executable quote.'],
    referenceCloseDate: ['收盘价所属日期：接口未提供，不能由本地接收时间推断。', 'Closing-price date: not provided by the interface. It cannot be inferred from local receipt time.'],
    referenceLast: ['标的价格来自最近成交参考', 'Underlying price uses a last-trade reference'],
    referenceLastMeaning: ['这是已发生交易的价格参考，不代表现在能以此价格买入或卖出，也不是双边报价。', 'This references an earlier trade. It is not a two-sided quote or a guarantee that you can trade at that price now.'],
    referenceTradeTime: ['最近成交时间（UTC）', 'Last trade time (UTC)'],
    referenceTradeUnknown: ['交易时间未知；接口未提供可核验的交易时刻。', 'Trade time is unknown; the interface provided no verifiable trade timestamp.'],
    closeReference: ['收盘参考价', 'Closing reference'],
    retainedReport: ['本次没有生成新的分析。下方保留上一次成功的固定快照，不能当作本次行情。', 'No new analysis was produced. The previous successful fixed snapshot is retained below; it is not data from this request.'],
    coverage: ['有效报价覆盖', 'Valid quote coverage'],
    freshCoverage: ['新鲜实时有效报价', 'Fresh live valid quotes'],
    received: ['本地接收时间', 'Local receipt time'],
    window: ['采集窗口（UTC）', 'Collection window (UTC)'],
    underlyingTime: ['标的参考数据接收（UTC）', 'Underlying reference receipt (UTC)'],
    receivedCount: ['有数据合约', 'Contracts with data'],
    freshPairs: ['新鲜实时成对行权价覆盖', 'Fresh live paired-strike coverage'],
    freshnessCutoff: ['本地接收新鲜度阈值', 'Local receipt freshness cutoff'],
    seconds: ['秒', 's'],
    timestampNote: ['时间为本地采集服务的接收时间。', 'Timestamps record receipt by the local data service.'],
    metricHeading: ['抽样指标', 'Sample indicators'],
    put_call_volume: ['看跌 / 看涨成交量', 'Put/call volume'],
    put_call_open_interest: ['看跌 / 看涨未平仓量', 'Put/call open interest'],
    iv_skew_25_delta: ['约 25Δ 隐含波动率差', 'Approx. 25Δ IV skew'],
    atm_straddle: ['平值跨式权利金 / 标的价', 'ATM straddle premium / spot'],
    volPoints: ['波动率点', 'vol. pts'],
    paired: ['成对行权价', 'Paired strikes'],
    put: ['看跌', 'Put'],
    call: ['看涨', 'Call'],
    premium: ['合计权利金', 'Total premium'],
    chain: ['合约明细', 'Contract details'],
    side: ['合约类型', 'Option type'],
    all: ['全部', 'All'],
    strike: ['行权价', 'Strike'],
    bid: ['买价', 'Bid'],
    ask: ['卖价', 'Ask'],
    last: ['成交价', 'Last'],
    volume: ['成交量', 'Volume'],
    interest: ['未平仓量', 'Open interest'],
    mode: ['行情类型', 'Feed type'],
    emptyRows: ['当前没有可显示的合约。', 'No contracts to display.'],
    scrollTable: ['可横向滚动查看完整报价和希腊字母。', 'Scroll horizontally to see all quotes and Greeks.'],
    signals: ['期权情绪线索', 'Options sentiment clues'],
    noSignals: ['本次样本没有满足计算条件的相对信号。', 'No relative signals met the calculation requirements in this sample.'],
    caveats: ['数据质量与解读范围', 'Data quality and interpretation scope'],
    modelHeading: ['API 模型解读', 'API model interpretation'],
    modelSkipped: ['本次未发送指标给模型服务。', 'No indicators were sent to the model provider for this request.'],
    modelUnavailable: ['本次无法提供模型解读。抽样指标与行情质量仍可查看。', 'Model interpretation is unavailable for this request. The indicators and data quality remain available.'],
    metricUnavailable: ['当前样本不足以计算。', 'The current sample is insufficient.'],
    collectiveHeading: ['整批期权综合分析', 'Cohort synthesis'],
    descriptive: ['样本结构分析', 'Descriptive sample analysis'],
    insufficient: ['部分证据不足', 'Limited evidence'],
    supporting: ['主要发现', 'Findings'],
    conflicts: ['信号冲突与替代解释', 'Conflicts and alternatives'],
    limitations: ['分析局限', 'Limitations'],
    evidence: ['分析依据', 'Evidence'],
    evidenceValue: ['数值', 'Value'],
    evidenceScope: ['覆盖范围', 'Scope'],
    liquidity: ['流动性与可分析程度', 'Liquidity and usable coverage'],
    medianSpread: ['相对买卖价差中位数', 'Median relative bid/ask spread'],
    wideSpreads: ['宽价差合约', 'Wide-spread contracts'],
    distribution: ['成交与持仓在行权价上的分布', 'Activity and positioning across strikes'],
    total: ['合计', 'Total'],
    share: ['样本占比', 'Sample share'],
    topConcentration: ['最高两档集中度', 'Top-two strike concentration'],
    peakStrikes: ['最高集中行权价', 'Peak activity strikes'],
    noDistribution: ['当前样本缺少可配对的分布数据。', 'The sample has no comparable distribution data.'],
    positioning: ['成交与持仓是否一致', 'Activity versus positioning'],
    putVolumeShare: ['看跌成交量占比', 'Put volume share'],
    putInterestShare: ['看跌未平仓量占比', 'Put open interest share'],
    putShareGap: ['两者占比差', 'Difference in shares'],
    commonStrikes: ['共同覆盖行权价', 'Common strikes'],
    volatility: ['波动率结构', 'Volatility structure'],
    atmIV: ['平值参考 IV', 'ATM reference IV'],
    relativeIV: ['相对平值 IV 差', 'IV difference from ATM'],
    moneyness: ['行权价相对标的', 'Strike relative to spot'],
    modelSynthesis: ['API 模型综合报告', 'API model synthesis'],
    observations: ['综合解读', 'Interpretation'],
    scenarios: ['条件情景', 'Conditional scenarios'],
    scenarioIf: ['如果', 'If'],
    scenarioThen: ['含义', 'Implication'],
    comparison: ['跨期权链联合分析', 'Cross-chain comparison'],
    chainReports: ['各期权链的完整分析', 'Individual chain reports'],
    failedItems: ['未完成的采集项目', 'Items not collected'],
    noReports: ['本批次未获得足以展示的期权链。', 'No option chain was available to display in this batch.'],
    completedAt: ['批次完成时间（UTC）', 'Batch completion (UTC)'],
    generatedAt: ['模型报告生成时间（UTC）', 'Model report generated (UTC)'],
    captureAge: ['采集距报告完成', 'Capture age at report completion'],
    notComparable: ['当前样本缺少可比较的条件。', 'The samples do not meet comparison requirements.'],
    chainComparison: ['各组证据对照', 'Evidence by chain'],
    termStructure: ['同标的到期结构', 'Same-underlying term structure'],
    ivTermGap: ['远期减近期 IV', 'Far minus near IV'],
    sampledStrikes: ['档行权价', 'sampled strikes'],
    termNotComparable: ['IV 口径、行情模式、平值程度或接收时间未满足可比要求。', 'IV basis, feed type, moneyness or receipt time do not meet comparison requirements.'],
  };

  const modes = {
    live: ['实时类型', 'Live feed type'],
    delayed: ['延迟行情', 'Delayed feed'],
    frozen: ['冻结行情', 'Frozen feed'],
    delayed_frozen: ['延迟冻结行情', 'Delayed-frozen feed'],
    mixed: ['行情类型混合', 'Mixed feed types'],
    unavailable: ['行情不可用', 'Quotes unavailable'],
    unknown: ['行情类型未知', 'Feed type unknown'],
  };

  const signalCopy = {
    more_put_volume: ['本次成对样本的看跌成交量较高。', 'Put volume is higher in the paired sample.'],
    more_call_volume: ['本次成对样本的看涨成交量较高。', 'Call volume is higher in the paired sample.'],
    equal_put_call_volume: ['本次成对样本的看跌与看涨成交量相等。', 'Put and call volume are equal in the paired sample.'],
    more_put_open_interest: ['本次成对样本的看跌未平仓量较高。', 'Put open interest is higher in the paired sample.'],
    more_call_open_interest: ['本次成对样本的看涨未平仓量较高。', 'Call open interest is higher in the paired sample.'],
    equal_put_call_open_interest: ['本次成对样本的看跌与看涨未平仓量相等。', 'Put and call open interest are equal in the paired sample.'],
    higher_put_iv: ['接近 25Δ 的样本中，看跌隐含波动率较高。', 'Put implied volatility is higher in the near-25Δ sample.'],
    higher_call_iv: ['接近 25Δ 的样本中，看涨隐含波动率较高。', 'Call implied volatility is higher in the near-25Δ sample.'],
    equal_put_call_iv: ['接近 25Δ 的样本中，看跌与看涨隐含波动率相等。', 'Put and call implied volatility are equal in the near-25Δ sample.'],
  };

  const reasons = {
    market_data_not_consistently_live: ['样本未达到一致实时行情类型要求。', 'The sample does not meet the consistent live-feed requirement.'],
    underlying_live_midpoint_unavailable: ['缺少新鲜的实时报价中间价。', 'A fresh live underlying midpoint is unavailable.'],
    insufficient_fresh_live_pairs: ['满足新鲜实时条件的看涨、看跌合约配对不足。', 'Too few call and put pairs meet the live freshness requirement.'],
    insufficient_recent_metric_evidence: ['符合新鲜度与覆盖要求的指标不足。', 'Too few indicators meet freshness and coverage requirements.'],
    ambiguous_contracts_excluded: ['歧义合约已从计算中排除。', 'Ambiguous contracts were excluded from the calculations.'],
    market_data_type_unconfirmed: ['行情类型未经一致确认。', 'The feed type is unconfirmed or inconsistent.'],
    insufficient_paired_strikes: ['可用的成对行权价不足。', 'Too few matched strikes are available.'],
    zero_call_total: ['看涨合计为零，比率无法计算。', 'The call total is zero, so the ratio is undefined.'],
    underlying_unavailable: ['缺少标的参考价。', 'The underlying reference price is unavailable.'],
    underlying_price_stale: ['标的参考价已超过新鲜度阈值。', 'The underlying reference exceeds the freshness cutoff.'],
    atm_strike_too_far: ['最近行权价与标的价相距较远。', 'The nearest strike is too far from the underlying price.'],
    atm_quote_unavailable: ['平值看涨或看跌报价缺失。', 'An ATM call or put quote is missing.'],
    atm_quote_stale: ['平值报价已超过新鲜度阈值。', 'ATM quotes exceed the freshness cutoff.'],
    unsynchronized_receipts: ['相关报价接收时间相隔较远。', 'The corresponding quote receipt times are too far apart.'],
    wide_bid_ask_spread: ['买卖价差超过本指标允许的范围。', 'Bid/ask spreads exceed the indicator limit.'],
    invalid_numeric_range: ['数值超出本指标支持的范围。', 'Values fall outside the indicator range.'],
    insufficient_comparable_greeks: ['缺少可比较且接近 25Δ 的看涨、看跌合约。', 'Comparable call and put contracts near 25Δ are unavailable.'],
  };

  const ibkrErrors = {
    duplicate_resolved_contract_scope: ['此项目解析到同一到期日和合约范围，已略去重复样本。', 'This item resolved to a previously collected contract scope and was omitted.'],
    ibkr_disabled: ['请在后端配置中启用 IBKR 期权行情。', 'Enable IBKR options in the backend configuration.'],
    ibkr_dependency_missing: ['请在后端环境安装 requirements-options.txt 中的依赖。', 'Install requirements-options.txt in the backend environment.'],
    ibkr_busy: ['正在采集另一批期权数据。请稍后重试。', 'Another option snapshot is running. Try again shortly.'],
    ibkr_timeout: ['IB Gateway 行情请求超时。请检查网关和行情权限。', 'The IB Gateway request timed out. Check the gateway and data permissions.'],
    ibkr_connection_failed: ['无法建立或保持 IB Gateway API 连接。请检查登录和 API 端口。', 'The IB Gateway API connection failed. Check login and the API port.'],
    ibkr_client_id_conflict: ['当前 IBKR API 客户端编号已被使用。', 'The configured IBKR API client ID is in use.'],
    ibkr_contract_not_found: ['无法识别该美股或 ETF 标的。', 'The US stock or ETF could not be identified.'],
    ibkr_chain_unavailable: ['网关没有返回该标的的标准 SMART 期权链。', 'The gateway returned no standard SMART option chain.'],
    ibkr_expiration_unavailable: ['此到期日不在可用期权链中。', 'This expiration is unavailable in the option chain.'],
    ibkr_competing_session: ['IBKR 报告另一个会话正在占用该账户的行情。', 'IBKR reports that another session is using market data for this account.'],
    ibkr_line_limit: ['IBKR 行情订阅行数已用完。可缩小本次行权价范围后重试。', 'IBKR market data lines are exhausted. Try again with a smaller strike range.'],
    ibkr_entitlement_missing: ['未获得请求的行情。请核对行情权限，或选择允许延迟后重试。', 'The requested data is unavailable under the current entitlement. Check data permissions or select Allow delayed and retry.'],
    ibkr_underlying_unavailable: ['没有收到可用标的价格。请检查行情类型与权限。', 'No usable underlying price was received. Check feed type and permissions.'],
    ibkr_option_data_unavailable: ['未收到本次请求的期权报价或指标。', 'No requested option quotes or metrics were received.'],
  };

  const priceBasis = {
    mid: ['买卖中间价', 'Bid/ask midpoint'],
    midpoint: ['买卖中间价', 'Bid/ask midpoint'],
    last: ['最近成交价', 'Last trade'],
    close: ['收盘参考价', 'Closing reference'],
  };

  const codes = { 1: 'live', 2: 'frozen', 3: 'delayed', 4: 'delayed_frozen' };
  const language = () => document.documentElement.lang.startsWith('en') ? 'en' : 'zh';
  const locale = () => language() === 'en' ? 'en-US' : 'zh-CN';
  const translate = pair => pair[language() === 'en' ? 1 : 0];
  const t = key => translate(copy[key]);
  const modeLabel = key => translate(modes[key] || modes.unknown);

  let gatewayStatus;
  let gatewayRequest;
  let currentRequest;
  let currentResult;
  let viewingSavedReport = false;
  let retainingPreviousResult = false;
  let filter = 'all';
  let chainSerial = 0;
  let readingMode = localStorage.getItem('finpilot-options-reading') === 'professional' ? 'professional' : 'simple';
  const expirationCache = new Map();
  const expirationControllers = new Set();
  let expirationQueue = Promise.resolve();
  let expirationSequence = 0;
  let expirationLoad;
  let expirationState = 'empty';
  let expirationData;
  let expirationError = '';
  let expirationSelection = '';

  function normalizedSymbol() { return symbolInput.value.trim().toUpperCase(); }

  function validSymbol(symbol) {
    return symbol.length <= 12 && /^[A-Z][A-Z0-9]*(?:[ .-][A-Z0-9]+)?$/.test(symbol);
  }

  function availableDates(value) {
    return Array.isArray(value) ? [...new Set(value.filter(date => typeof date === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(date)))].sort() : [];
  }

  function renderExpirations() {
    const selected = expirationSelection;
    const nearest = node('option', t('expiryNearest'));
    nearest.value = '';
    expirySelect.replaceChildren(nearest);
    const matches = expirationData?.symbol === normalizedSymbol();
    if (matches && expirationState === 'ready') {
      for (const date of expirationData.expirations) {
        const option = node('option', date);
        option.value = date;
        expirySelect.append(option);
      }
      if (expirationData.expirations.includes(selected)) expirySelect.value = selected;
      else expirationSelection = '';
    }
    expirySelect.disabled = analysisMode.value === 'batch' || expirationState !== 'ready' || !matches;
    expiryRefresh.disabled = expirationState === 'loading';
    expirySelect.setAttribute('aria-busy', String(expirationState === 'loading'));
    const key = { empty: 'expiryChooseSymbol', loading: 'expiryLoading', ready: 'expiryAvailable', failed: 'expiryUnavailable', unavailable: 'expiryEmpty' }[expirationState];
    expiryStatus.textContent = t(key || 'expiryChooseSymbol') + (expirationState === 'failed' && expirationError ? ` ${expirationError}` : '');
    expiryStatus.dataset.state = expirationState;
  }

  function resetExpirations() {
    expirationSequence += 1;
    expirationData = undefined;
    expirationLoad = undefined;
    expirationState = 'empty';
    expirationError = '';
    expirationSelection = '';
    expirySelect.value = '';
    renderExpirations();
  }

  async function requestExpirations(symbol, signal, force = false) {
    const cached = expirationCache.get(symbol);
    if (!force && cached && Date.now() - cached.fetchedAt < 60000) return cached.data;
    const operation = expirationQueue.catch(() => {}).then(async () => {
      if (signal?.aborted) throw new DOMException('Aborted', 'AbortError');
      const fresh = expirationCache.get(symbol);
      if (!force && fresh && Date.now() - fresh.fetchedAt < 60000) return fresh.data;
      const response = await fetch(`/api/options/expirations?symbol=${encodeURIComponent(symbol)}`, { signal, cache: 'no-store' });
      const data = await response.json().catch(() => null);
      if (!response.ok) {
        const error = new Error(providerError(data?.detail, response.status));
        error.providerCode = data?.detail?.code;
        throw error;
      }
      if (data?.source !== 'ibkr' || data.symbol !== symbol || !Array.isArray(data.expirations)) throw new Error(t('invalidResponse'));
      const metadata = { ...data, symbol, expirations: availableDates(data.expirations) };
      expirationCache.set(symbol, { data: metadata, fetchedAt: Date.now() });
      return metadata;
    });
    expirationQueue = operation.catch(() => {});
    return operation;
  }

  async function loadExpirations(force = false) {
    if (analysisMode.value === 'batch') return;
    const symbol = normalizedSymbol();
    if (!validSymbol(symbol)) { resetExpirations(); return; }
    if (expirationState === 'loading' && expirationLoad) return expirationLoad;
    const sequence = ++expirationSequence;
    const controller = new AbortController();
    expirationControllers.add(controller);
    const timer = setTimeout(() => controller.abort(), 20000);
    expirationState = 'loading'; expirationError = '';
    renderExpirations();
    const operation = (async () => {
      try {
        const data = await requestExpirations(symbol, controller.signal, force);
        if (sequence !== expirationSequence || normalizedSymbol() !== symbol) return;
        expirationData = data;
        expirationState = data.expirations.length ? 'ready' : 'unavailable';
      } catch (error) {
        if (sequence !== expirationSequence || normalizedSymbol() !== symbol) return;
        expirationState = 'failed';
        expirationError = error.name === 'AbortError' ? t('timeout') : error.message;
      } finally {
        clearTimeout(timer);
        expirationControllers.delete(controller);
        if (sequence === expirationSequence) {
          expirationLoad = undefined;
          renderExpirations();
        }
      }
    })();
    expirationLoad = operation;
    return operation;
  }

  async function validateBatchDates(items, signal) {
    const requested = new Map();
    for (const item of items) {
      if (!item.expiry) continue;
      if (!requested.has(item.symbol)) requested.set(item.symbol, await requestExpirations(item.symbol, signal));
      const dates = requested.get(item.symbol).expirations;
      if (!dates.includes(item.expiry)) {
        const error = new Error(`${item.symbol} · ${item.expiry} — ${translate(ibkrErrors.ibkr_expiration_unavailable)} ${t('expiryDates')} · ${dates.slice(0, 8).join(' / ') || '—'}`);
        error.providerCode = 'ibkr_expiration_unavailable';
        throw error;
      }
    }
  }

  function node(tag, content, className) {
    const element = document.createElement(tag);
    if (content !== undefined) element.textContent = content;
    if (className) element.className = className;
    return element;
  }

  function number(value, digits = 2) {
    return Number.isFinite(value) ? new Intl.NumberFormat(locale(), { maximumFractionDigits: digits }).format(value) : '—';
  }

  function percent(value) {
    return Number.isFinite(value) ? new Intl.NumberFormat(locale(), { style: 'percent', maximumFractionDigits: 1 }).format(value) : '—';
  }

  function time(value) {
    const timestamp = typeof value === 'string' ? new Date(value) : new Date(NaN);
    if (Number.isNaN(timestamp.getTime())) return '—';
    return new Intl.DateTimeFormat(locale(), {
      timeZone: 'UTC', year: 'numeric', month: '2-digit', day: '2-digit',
      hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23',
    }).format(timestamp);
  }

  function showGateway() {
    if (viewingSavedReport) { gateway.textContent = t('savedReport'); gateway.hidden = false; return; }
    const endpoint = gatewayStatus?.endpoint;
    const message = gatewayStatus ? t(copy[gatewayStatus.status] ? gatewayStatus.status : 'gatewayUnknown') : t('gatewayChecking');
    gateway.textContent = `${t('gateway')} · ${message}${endpoint && readingMode === 'professional' ? ` (${endpoint})` : ''}`;
    gateway.hidden = false;
  }

  async function refreshGateway() {
    gatewayRequest?.abort();
    const controller = new AbortController();
    gatewayRequest = controller;
    const timer = setTimeout(() => controller.abort(), 5000);
    gatewayStatus = null;
    showGateway();
    try {
      const response = await fetch('/api/options/status', { signal: controller.signal, cache: 'no-store' });
      if (!response.ok) throw new Error('gateway status unavailable');
      const data = await response.json();
      if (gatewayRequest === controller) gatewayStatus = data;
    } catch {
      if (gatewayRequest === controller) gatewayStatus = { status: 'gatewayUnknown' };
    } finally {
      clearTimeout(timer);
      if (gatewayRequest === controller) showGateway();
    }
  }

  function addSummaryField(list, label, value) {
    const field = node('div');
    field.append(node('dt', label), node('dd', value));
    list.append(field);
  }

  function renderSummary(snapshot, quality, snapshotId) {
    const summary = node('section');
    const head = node('div', undefined, 'options-summary-head');
    const badge = node('span', modeLabel(quality.market_data_status), 'options-feed-pill');
    badge.dataset.mode = snapshot.source === 'ibkr' ? quality.market_data_status : 'unknown';
    head.append(node('h3', `${snapshot.symbol} · ${snapshot.expiration}`), badge);

    const list = node('dl', undefined, 'options-summary-grid');
    const source = snapshot.source === 'ibkr' ? 'IBKR / IB Gateway' : snapshot.source === 'fixture' ? t('fixture') : '—';
    const spot = number(snapshot.underlying?.price);
    addSummaryField(list, t('source'), source);
    addSummaryField(list, t('underlying'), spot === '—' ? spot : `${spot} ${snapshot.currency || ''}`.trim());
    addSummaryField(list, t('coverage'), `${number(quality.valid_quote_contracts, 0)} / ${number(quality.requested_contracts, 0)} · ${percent(quality.quote_coverage)}`);
    addSummaryField(list, t('freshCoverage'), `${number(quality.fresh_live_quote_contracts, 0)} / ${number(quality.requested_contracts, 0)}`);

    const basis = priceBasis[snapshot.underlying?.price_basis];
    const context = [
      `${t('window')} ${time(snapshot.started_at)} → ${time(snapshot.received_at)}`,
      `${t('receivedCount')} ${number(quality.received_contracts, 0)} / ${number(quality.requested_contracts, 0)}`,
      `${t('underlyingTime')} ${time(snapshot.underlying?.received_at)} · ${modeLabel(codes[snapshot.underlying?.market_data_type])}${basis ? ` · ${translate(basis)}` : ''}`,
      `${t('freshPairs')} ${percent(quality.fresh_live_pair_coverage)} · ${t('freshnessCutoff')} ${number(quality.freshness_seconds, 1)} ${t('seconds')}`,
      t('timestampNote'),
    ];
    if (typeof snapshotId === 'string') context.push(`${t('snapshotId')} ${snapshotId.slice(0, 12)}`);
    summary.append(head, list, ...context.map(value => node('p', value, 'options-meta')));
    return summary;
  }

  function renderReferenceNotice(snapshot) {
    const underlying = snapshot?.underlying || {};
    if (!['close', 'last'].includes(underlying.price_basis)) return null;
    const closing = underlying.price_basis === 'close';
    const section = node('aside', undefined, 'options-reference-notice');
    section.dataset.priceBasis = underlying.price_basis;
    const value = number(underlying.price);
    section.append(node('h4', `${snapshot.symbol || ''} · ${t(closing ? 'referenceClose' : 'referenceLast')}`),
      node('strong', `${value} ${snapshot.currency || ''}`.trim()), node('p', t(closing ? 'referenceCloseMeaning' : 'referenceLastMeaning')));
    if (closing) section.append(node('p', t('referenceCloseDate')));
    const tradeTime = time(underlying.last_trade_at);
    section.append(node('small', tradeTime === '—' ? t('referenceTradeUnknown') : `${t('referenceTradeTime')} · ${tradeTime}`),
      node('small', `${t('received')}（UTC） · ${time(closing ? underlying.close_received_at || underlying.received_at : underlying.received_at)}`));
    return section;
  }

  function renderDiagnostics(data, error = false) { return window.FinPilotDiagnostics?.render(data, { error }) || null; }

  function appendFailureDiagnostics(target, failures) {
    for (const item of failures || []) {
      const diagnostic = renderDiagnostics(item.diagnostics, true);
      if (!diagnostic) continue;
      diagnostic.prepend(node('h4', [item.symbol, item.expiry].filter(Boolean).join(' · ')));
      target.append(diagnostic);
    }
  }

  function renderMetrics(metrics) {
    const section = node('section');
    const list = node('div', undefined, 'options-metrics');
    for (const key of ['put_call_volume', 'put_call_open_interest', 'iv_skew_25_delta', 'atm_straddle']) {
      const metric = metrics[key] || {};
      const card = node('article', undefined, 'options-metric');
      const available = Number.isFinite(metric.value);
      card.dataset.unavailable = String(!available);
      const suffix = key === 'atm_straddle' ? '%' : key === 'iv_skew_25_delta' ? ` ${t('volPoints')}` : '';
      card.append(node('h4', t(key)), node('strong', available ? `${number(metric.value)}${suffix}` : '—', 'options-metric-value'));
      if (metric.market_data_status) card.append(node('p', modeLabel(metric.market_data_status), 'options-metric-note'));
      if (!available) {
        const reason = reasons[metric.reason];
        card.append(node('p', reason ? translate(reason) : t('metricUnavailable'), 'options-metric-note'));
      } else if (key.startsWith('put_call')) {
        card.append(node('p', `${t('paired')} ${number(metric.paired_strikes, 0)} · ${percent(metric.pair_coverage)}`, 'options-metric-note'));
        card.append(node('p', `${t('put')} ${number(metric.put_total, 0)} · ${t('call')} ${number(metric.call_total, 0)}`, 'options-metric-note'));
      } else if (key === 'iv_skew_25_delta') {
        card.append(node('p', `${t('put')} ${percent(metric.put_iv)} · ${t('call')} ${percent(metric.call_iv)}`, 'options-metric-note'));
      } else {
        card.append(node('p', `${t('strike')} ${number(metric.strike)} · ${t('premium')} ${number(metric.premium)}`, 'options-metric-note'));
      }
      list.append(card);
    }
    section.append(node('h3', t('metricHeading')), list);
    return section;
  }

  function textPanel(title, lines) {
    const section = node('section', undefined, 'options-panel');
    section.append(node('h3', title));
    const list = node('ul');
    for (const line of lines) list.append(node('li', line));
    section.append(list);
    return section;
  }

  function evidenceContext(collective = {}, extraRecords = [], aliases = []) {
    const records = [...(Array.isArray(collective.evidence) ? collective.evidence : []), ...extraRecords];
    const context = { records: new Map(records.filter(record => typeof record.id === 'string').map(record => [record.id, record])), targets: new Map() };
    const details = node('details', undefined, 'options-evidence-catalogue');
    context.details = details;
    details.append(node('summary', t('evidence')));
    const table = node('table', undefined, 'options-evidence-table');
    const row = table.createTHead().insertRow();
    for (const label of [t('evidence'), t('evidenceValue'), t('evidenceScope')]) {
      const cell = node('th', label); cell.scope = 'col'; row.append(cell);
    }
    const body = table.createTBody();
    for (const record of context.records.values()) {
      const entry = body.insertRow(); entry.tabIndex = -1;
      const label = entry.insertCell();
      const labelKey = { quote_coverage: 'coverage', median_relative_spread_pct: 'medianSpread', put_volume_share: 'putVolumeShare', atm_iv: 'atmIV' }[record.label];
      label.append(node('strong', labelKey ? t(labelKey) : record.label || record.id), node('small', record.description || record.id));
      entry.insertCell().textContent = Number.isFinite(record.value)
        ? record.unit === 'fraction' ? percent(record.value) : `${number(record.value, 4)}${record.unit ? ` ${record.unit}` : ''}`
        : record.value == null ? '—' : String(record.value);
      const scope = record.scope;
      entry.insertCell().textContent = typeof scope === 'string' ? scope : scope
        ? [scope.symbol, scope.expiration, scope.market_data_status ? modeLabel(scope.market_data_status) : '', Number.isFinite(scope.requested_strikes) ? `${scope.requested_strikes} ${t('sampledStrikes')}` : ''].filter(Boolean).join(' · ')
        : '—';
      context.targets.set(record.id, entry);
    }
    for (const [alias, target] of aliases) {
      if (!context.records.has(target)) continue;
      context.records.set(alias, context.records.get(target));
      context.targets.set(alias, context.targets.get(target));
    }
    const scroll = node('div', undefined, 'options-evidence-scroll');
    scroll.append(table); details.append(scroll);
    return context;
  }

  function citations(ids, context) {
    const group = node('div', undefined, 'options-evidence-links');
    if (!Array.isArray(ids) || !context) return group;
    const resolved = [...new Set(ids)].filter(id => context.records.has(id));
    if (readingMode === 'simple' && resolved.length) {
      const disclosure = node('details', undefined, 'options-citation-group');
      disclosure.append(node('summary', `${t('checkEvidence')}（${resolved.length}）`));
      const choices = node('div', undefined, 'options-citation-choices');
      for (const id of resolved) {
        const record = context.records.get(id);
        const button = node('button', record.label || t('checkEvidence'));
        button.type = 'button';
        button.dataset.evidenceId = id;
        const provenance = typeof record.scope === 'object' && record.scope
          ? [record.scope.symbol, record.scope.expiration].filter(Boolean).join(' · ') : '';
        button.title = [record.label || id, provenance].filter(Boolean).join(' · ');
        button.setAttribute('aria-label', `${t('checkEvidence')} · ${button.title}`);
        button.addEventListener('click', () => {
          context.details.open = true;
          const selected = context.targets.get(id);
          for (const target of new Set(context.targets.values())) {
            target.dataset.selected = String(target === selected);
          }
          selected?.focus({ preventScroll: false });
        });
        choices.append(button);
      }
      disclosure.append(choices);
      group.append(disclosure);
      return group;
    }
    for (const id of ids) {
      const record = context.records.get(id);
      if (!record) continue;
      const button = node('button', readingMode === 'professional' ? `[${id}]` : t('checkEvidence'));
      button.dataset.evidenceId = id;
      button.type = 'button';
      const provenance = typeof record.scope === 'object' && record.scope
        ? [record.scope.symbol, record.scope.expiration].filter(Boolean).join(' · ') : '';
      button.title = [record.label || id, provenance].filter(Boolean).join(' · ');
      button.setAttribute('aria-label', `${t('evidence')} ${button.title}`);
      button.addEventListener('click', () => {
        context.details.open = true;
        context.targets.get(id)?.focus({ preventScroll: false });
      });
      group.append(button);
    }
    return group;
  }

  function findingList(title, findings, context) {
    const section = node('section', undefined, 'options-findings');
    section.append(node('h4', title));
    const list = node('ul');
    for (const finding of findings) {
      const item = node('li');
      if (finding.title) item.append(node('strong', finding.title));
      item.append(node('p', finding.text || ''), citations(finding.evidence_ids, context));
      list.append(item);
    }
    section.append(list);
    return section;
  }

  function renderAssessment(assessment, context, title) {
    const section = node('section', undefined, 'options-assessment');
    const head = node('div', undefined, 'options-summary-head');
    head.append(node('h3', title), node('span', t(assessment.status === 'descriptive' ? 'descriptive' : 'insufficient'), 'options-feed-pill'));
    section.append(head, node('p', assessment.headline || t('notComparable'), 'options-assessment-headline'));
    if (assessment.findings?.length) section.append(findingList(t('supporting'), assessment.findings, context));
    if (assessment.conflicts?.length) section.append(findingList(t('conflicts'), assessment.conflicts, context));
    if (assessment.limitations?.length) section.append(textPanel(t('limitations'), assessment.limitations));
    return section;
  }

  function renderLiquidity(liquidity = {}) {
    const section = node('section', undefined, 'options-panel');
    section.append(node('h3', t('liquidity')));
    const values = node('dl', undefined, 'options-summary-grid');
    addSummaryField(values, t('coverage'), `${number(liquidity.valid_contracts, 0)} / ${number(liquidity.requested_contracts, 0)} · ${percent(liquidity.coverage)}`);
    addSummaryField(values, t('medianSpread'), Number.isFinite(liquidity.median_relative_spread_pct) ? `${number(liquidity.median_relative_spread_pct)}%` : '—');
    addSummaryField(values, t('wideSpreads'), `${number(liquidity.wide_spread_contracts, 0)} · > ${number(liquidity.wide_spread_threshold_pct)}%`);
    addSummaryField(values, t('mode'), modeLabel(liquidity.market_data_status));
    section.append(values);
    return section;
  }

  function renderDistribution(name, distribution = {}) {
    const section = node('section', undefined, 'options-distribution');
    section.append(node('h4', t(name)));
    const rows = Array.isArray(distribution.rows) ? distribution.rows : [];
    if (!rows.length) {
      section.append(node('p', t('noDistribution'), 'options-meta'));
      return section;
    }
    section.append(node('p', `${t('coverage')} ${percent(distribution.coverage)} · ${t('topConcentration')} ${percent(distribution.top_two_strike_share)}`, 'options-meta'));
    if (distribution.peak_strikes?.length) section.append(node('p', `${t('peakStrikes')} ${distribution.peak_strikes.map(value => number(value)).join(' / ')}`, 'options-meta'));
    const table = node('table', undefined, 'options-distribution-table');
    const heading = table.createTHead().insertRow();
    for (const label of [t('strike'), t('call'), t('put'), t('share')]) {
      const cell = node('th', label); cell.scope = 'col'; heading.append(cell);
    }
    const body = table.createTBody();
    for (const item of rows) {
      const row = body.insertRow();
      for (const value of [item.strike, item.call, item.put]) row.insertCell().textContent = number(value);
      const share = row.insertCell();
      share.append(node('span', percent(item.share)));
      if (Number.isFinite(item.share)) {
        const meter = node('meter');
        meter.min = 0; meter.max = 1; meter.value = Math.max(0, Math.min(1, item.share));
        meter.setAttribute('aria-label', `${t('strike')} ${number(item.strike)} ${t('share')}`);
        share.append(meter);
      }
    }
    section.append(table);
    return section;
  }

  function renderVolatility(volatility = {}) {
    const section = node('section', undefined, 'options-panel');
    section.append(node('h3', t('volatility')), node('p', `${t('atmIV')} ${percent(volatility.atm_iv)}`));
    if (!Array.isArray(volatility.points) || !volatility.points.length) {
      section.append(node('p', t('notComparable')));
      return section;
    }
    const table = node('table', undefined, 'options-distribution-table');
    const heading = table.createTHead().insertRow();
    for (const label of [t('strike'), t('side'), 'IV', t('relativeIV')]) {
      const cell = node('th', label); cell.scope = 'col'; heading.append(cell);
    }
    const body = table.createTBody();
    for (const point of volatility.points) {
      const row = body.insertRow();
      const values = [number(point.strike), point.right === 'C' ? t('call') : t('put'), percent(point.iv), `${number(point.iv_minus_atm_pp)} ${t('volPoints')}`];
      for (const value of values) row.insertCell().textContent = value;
    }
    section.append(table);
    return section;
  }

  function renderCollective(collective, context) {
    const wrapper = node('section', undefined, 'options-collective');
    wrapper.append(renderAssessment(collective.assessment || {}, context, t('collectiveHeading')));
    if (collective.liquidity) wrapper.append(renderLiquidity(collective.liquidity));
    if (collective.distributions) {
      const distribution = node('section');
      distribution.append(node('h3', t('distribution')));
      const grid = node('div', undefined, 'options-distribution-grid');
      grid.append(renderDistribution('volume', collective.distributions.volume), renderDistribution('interest', collective.distributions.open_interest));
      distribution.append(grid); wrapper.append(distribution);
    }
    if (collective.positioning) {
      const panel = node('section', undefined, 'options-panel');
      panel.append(node('h3', t('positioning')));
      const values = node('dl', undefined, 'options-summary-grid');
      addSummaryField(values, t('putVolumeShare'), percent(collective.positioning.put_volume_share));
      addSummaryField(values, t('putInterestShare'), percent(collective.positioning.put_open_interest_share));
      addSummaryField(values, t('putShareGap'), Number.isFinite(collective.positioning.put_share_gap_pp) ? `${number(collective.positioning.put_share_gap_pp)} pp` : '—');
      addSummaryField(values, t('commonStrikes'), Array.isArray(collective.positioning.common_strikes) ? collective.positioning.common_strikes.map(value => number(value)).join(' / ') : number(collective.positioning.common_strikes, 0));
      panel.append(values); wrapper.append(panel);
    }
    if (collective.volatility) wrapper.append(renderVolatility(collective.volatility));
    if (context.records.size) wrapper.append(context.details);
    return wrapper;
  }

  function renderComparison(comparison) {
    const wrapper = node('section', undefined, 'options-comparison');
    const rows = Array.isArray(comparison.rows) ? comparison.rows : [];
    if (rows.length) {
      wrapper.append(node('h3', t('chainComparison')));
      const table = node('table', undefined, 'options-distribution-table');
      const heading = table.createTHead().insertRow();
      for (const label of [t('symbol'), t('expiry'), t('mode'), t('coverage'), t('medianSpread'), t('putVolumeShare'), t('atmIV'), t('received')]) {
        const cell = node('th', label); cell.scope = 'col'; heading.append(cell);
      }
      const body = table.createTBody();
      for (const entry of rows) {
        const row = body.insertRow();
        const values = [entry.symbol, entry.expiration, modeLabel(entry.market_data_status), percent(entry.quote_coverage),
          Number.isFinite(entry.median_relative_spread_pct) ? `${number(entry.median_relative_spread_pct)}%` : '—',
          percent(entry.put_volume_share), percent(entry.atm_iv), time(entry.received_at)];
        for (const value of values) row.insertCell().textContent = value || '—';
      }
      const scroll = node('div', undefined, 'options-table-scroll options-comparison-scroll');
      scroll.tabIndex = 0;
      scroll.setAttribute('role', 'region'); scroll.setAttribute('aria-label', t('chainComparison'));
      scroll.append(table); wrapper.append(scroll);
    }
    if (Array.isArray(comparison.term_structure) && comparison.term_structure.length) {
      const panel = node('section', undefined, 'options-panel');
      panel.append(node('h3', t('termStructure')));
      const list = node('ul');
      for (const term of comparison.term_structure) {
        const near = rows.find(row => row.report_index === term.near_report_index);
        const far = rows.find(row => row.report_index === term.far_report_index);
        const labels = `${near?.symbol || ''} ${near?.expiration || '—'} → ${far?.expiration || '—'}`;
        list.append(node('li', `${labels} · ${Number.isFinite(term.far_minus_near_iv_pp) ? `${t('ivTermGap')} ${number(term.far_minus_near_iv_pp)} ${t('volPoints')}` : t('termNotComparable')}`));
      }
      panel.append(list); wrapper.append(panel);
    }
    return wrapper;
  }

  function renderInterpretation(interpretation = {}, context) {
    const section = node('section', undefined, 'options-panel');
    section.classList.add('options-model-report');
    section.append(node('h3', t(interpretation.report ? 'modelSynthesis' : 'modelHeading')));
    if (interpretation.status === 'ok' && interpretation.report) {
      if (interpretation.model) section.append(node('p', interpretation.model, 'options-meta'));
      const report = interpretation.report;
      if (report.summary?.text) section.append(node('p', report.summary.text, 'options-model-summary'), citations(report.summary.evidence_ids, context));
      if (report.observations?.length) section.append(findingList(t('observations'), report.observations, context));
      if (report.conflicts?.length) section.append(findingList(t('conflicts'), report.conflicts, context));
      if (report.scenarios?.length) {
        const scenarios = node('section', undefined, 'options-scenarios');
        scenarios.append(node('h4', t('scenarios')));
        for (const scenario of report.scenarios) {
          const item = node('div', undefined, 'options-scenario');
          item.append(node('strong', `${t('scenarioIf')} · ${scenario.condition || ''}`), node('p', `${t('scenarioThen')} · ${scenario.implication || ''}`), citations(scenario.evidence_ids, context));
          scenarios.append(item);
        }
        section.append(scenarios);
      }
      if (report.limitations?.length) section.append(textPanel(t('limitations'), report.limitations));
      if (interpretation.generated_at) section.append(node('p', `${t('generatedAt')} ${time(interpretation.generated_at)}`, 'options-meta'));
    } else if (interpretation.status === 'ok' && typeof interpretation.text === 'string') {
      if (interpretation.model) section.append(node('p', interpretation.model));
      const evidence = Array.isArray(interpretation.evidence) ? interpretation.evidence.filter(id => copy[id]).map(id => t(id)) : [];
      if (evidence.length) section.append(node('p', `${t('modelEvidence')} · ${evidence.join(' / ')}`, 'options-meta'));
      section.append(node('p', interpretation.text, 'options-llm-text'));
    } else {
      const skipped = interpretation.status === 'skipped' || !interpretation.status;
      section.append(node('p', t(skipped ? 'modelSkipped' : 'modelUnavailable')));
    }
    return section;
  }

  function renderChain(snapshot) {
    const section = node('section');
    const title = node('h3', t('chain'));
    title.id = `options-chain-title-${++chainSerial}`;
    const rows = snapshot.quotes.slice().sort((a, b) => a.strike - b.strike || String(a.right).localeCompare(String(b.right)));
    const selector = node('select');
    for (const [value, key] of [['all', 'all'], ['C', 'call'], ['P', 'put']]) {
      const option = node('option', t(key));
      option.value = value;
      selector.append(option);
    }
    selector.value = filter;
    const control = node('label', undefined, 'options-chain-filter');
    control.append(node('span', t('side')), selector);
    const head = node('div', undefined, 'options-chain-head');
    head.append(title, control);

    const table = node('table', undefined, 'options-chain-table');
    const header = table.createTHead().insertRow();
    const hasClose = rows.some(quote => Number.isFinite(quote.close));
    const labels = [t('strike'), t('side'), t('bid'), t('ask'), t('last'), ...(hasClose ? [t('closeReference')] : []), t('volume'), t('interest'), 'IV', 'Δ', 'Γ', 'Vega', 'Θ', t('mode'), `${t('received')} (UTC)`];
    for (const label of labels) {
      const cell = node('th', label);
      cell.scope = 'col';
      header.append(cell);
    }
    const body = table.createTBody();
    function populate() {
      body.replaceChildren();
      const selected = rows.filter(row => filter === 'all' || filter === row.right);
      if (!selected.length) {
        const cell = body.insertRow().insertCell();
        cell.colSpan = labels.length;
        cell.textContent = t('emptyRows');
        return;
      }
      for (const quote of selected) {
        const row = body.insertRow();
        const side = quote.right === 'C' ? t('call') : quote.right === 'P' ? t('put') : '—';
        const cells = [number(quote.strike), side, number(quote.bid), number(quote.ask), number(quote.last), ...(hasClose ? [number(quote.close)] : []),
          number(quote.volume, 0), number(quote.open_interest, 0), percent(quote.implied_volatility),
          number(quote.delta, 3), number(quote.gamma, 4), number(quote.vega, 4), number(quote.theta, 4),
          modeLabel(codes[quote.market_data_type]), time(quote.quote_received_at || quote.received_at)];
        for (const value of cells) row.insertCell().textContent = value;
      }
    }
    selector.addEventListener('change', () => { filter = selector.value; populate(); });
    populate();

    const scroll = node('div', undefined, 'options-table-scroll');
    scroll.tabIndex = 0;
    scroll.setAttribute('role', 'region');
    scroll.setAttribute('aria-labelledby', title.id);
    scroll.append(table);
    section.append(head, scroll, node('p', t('scrollTable'), 'options-meta'));
    return section;
  }

  function renderSingle(data) {
    const { snapshot, quality, metrics, signals = [], caveats = [], interpretation } = data;
    const clues = signals.filter(signal => signalCopy[signal.code]).map(signal => translate(signalCopy[signal.code]));
    const limits = (quality.reason_codes || []).filter(code => reasons[code]).map(code => translate(reasons[code]));
    const wrapper = node('div', undefined, 'options-single-report');
    const localEvidence = Array.isArray(data.collective?.evidence) ? data.collective.evidence : [];
    const context = evidenceContext(data.collective, [], localEvidence.map(record => [`g0.${record.id}`, record.id]));
    wrapper.append(renderSummary(snapshot, quality, data.snapshot_id));
    const reference = renderReferenceNotice(snapshot);
    if (reference) wrapper.append(reference);
    const diagnostic = renderDiagnostics(snapshot.diagnostics);
    if (diagnostic) wrapper.append(diagnostic);
    if (Number.isFinite(data.capture_age_seconds)) wrapper.append(node('p', `${t('captureAge')} ${number(data.capture_age_seconds, 1)} ${t('seconds')}`, 'options-meta'));
    if (data.collective) {
      if (interpretation?.status === 'ok' && interpretation.report) wrapper.append(renderInterpretation(interpretation, context));
      wrapper.append(renderCollective(data.collective, context));
    }
    const details = node('details', undefined, 'options-raw-details');
    details.append(node('summary', t('metricHeading')),
      renderMetrics(metrics), textPanel(t('signals'), clues.length ? clues : [t('noSignals')]));
    if (limits.length || caveats.length) details.append(textPanel(t('caveats'), [...limits, ...caveats]));
    details.append(renderChain(snapshot));
    wrapper.append(details);
    if (!interpretation?.report) wrapper.append(renderInterpretation(interpretation, context));
    return wrapper;
  }

  function evidenceForResult(data) {
    if (!Array.isArray(data.reports)) {
      const records = Array.isArray(data.collective?.evidence) ? data.collective.evidence : [];
      return evidenceContext(data.collective, [], records.map(record => [`g0.${record.id}`, record.id]));
    }
    const comparison = data.comparison || {};
    const records = data.reports.flatMap((report, index) => {
      const snapshot = report.snapshot || {};
      return (Array.isArray(report.collective?.evidence) ? report.collective.evidence : []).map(record => ({
        ...record, id: `g${index}.${record.id}`,
        scope: { ...(typeof record.scope === 'object' && record.scope ? record.scope : {}), symbol: snapshot.symbol, expiration: snapshot.expiration },
      }));
    });
    const comparisonEvidence = Array.isArray(comparison.evidence) ? comparison.evidence : [];
    return evidenceContext(comparison, records, comparisonEvidence.map(record => [`comparison.${record.id}`, record.id]));
  }

  function partVisual(visual) {
    if (visual?.type !== 'parts' || !Number.isFinite(visual.first_value) || !Number.isFinite(visual.second_value)) return null;
    if (visual.first_value < 0 || visual.second_value < 0 || Math.abs(visual.first_value + visual.second_value - 100) > .1) return null;
    const figure = node('figure', undefined, 'options-parts');
    const track = node('div', undefined, 'options-parts-track');
    track.setAttribute('aria-hidden', 'true');
    const first = node('span', undefined, 'options-parts-first');
    const second = node('span', undefined, 'options-parts-second');
    first.style.flexGrow = String(visual.first_value);
    second.style.flexGrow = String(visual.second_value);
    track.append(first, second);
    const legend = node('div', undefined, 'options-parts-legend');
    legend.append(node('span', `${visual.first_label} · ${number(visual.first_value, 1)}`),
      node('span', `${visual.second_label} · ${number(visual.second_value, 1)}`));
    figure.append(track, legend, node('figcaption', visual.unit || ''));
    return figure;
  }

  function renderGlossary(glossary) {
    const details = node('details', undefined, 'options-glossary');
    details.append(node('summary', t('glossary')));
    const list = node('dl');
    for (const item of glossary || []) {
      if (!item || typeof item.term !== 'string' || typeof item.meaning !== 'string') continue;
      const entry = node('div');
      entry.append(node('dt', item.term), node('dd', item.meaning));
      list.append(entry);
    }
    details.append(list);
    return details;
  }

  function renderPlainBrief(data) {
    const brief = data.plain_brief;
    const wrapper = node('section', undefined, 'options-plain-report');
    wrapper.setAttribute('aria-label', t('easyView'));
    if (!brief || typeof brief.headline !== 'string') {
      wrapper.append(node('p', t('missingBrief')));
      return wrapper;
    }
    const context = evidenceForResult(data);
    const freshness = node('aside', undefined, 'options-freshness');
    freshness.dataset.tone = viewingSavedReport ? 'attention' : brief.freshness?.tone || 'neutral';
    if (viewingSavedReport) {
      freshness.append(node('strong', t('savedFreshness')), node('p', t('savedFreshnessMeaning')));
      const reports = Array.isArray(data.reports) ? data.reports : [data];
      for (const report of reports) {
        const snapshot = report.snapshot || {};
        freshness.append(node('small', `${snapshot.symbol || ''} · ${t('received')}（UTC） · ${time(snapshot.received_at)}`));
      }
    } else freshness.append(node('strong', brief.freshness?.label || t('dataTime')), node('p', brief.freshness?.meaning || ''));
    wrapper.append(freshness);
    const reportsForReference = Array.isArray(data.reports) ? data.reports : [data];
    for (const report of reportsForReference) {
      const reference = renderReferenceNotice(report.snapshot);
      if (reference) wrapper.append(reference);
      const diagnostic = renderDiagnostics(report.snapshot?.diagnostics);
      if (diagnostic) {
        if (reportsForReference.length > 1) diagnostic.prepend(node('h4', report.snapshot?.symbol || ''));
        wrapper.append(diagnostic);
      }
    }
    const scope = [brief.scope?.symbol, brief.scope?.expiration].filter(Boolean).join(' · ');
    const heading = node('header', undefined, 'options-plain-heading');
    if (scope) heading.append(node('p', `${t('selectedScope')} · ${scope}`, 'options-meta'));
    heading.append(node('h3', brief.title || t('easyView')), node('p', brief.headline, 'options-plain-takeaway'));
    wrapper.append(heading);

    const cards = node('div', undefined, 'options-plain-cards');
    for (const card of brief.cards || []) {
      const article = node('article', undefined, 'options-plain-card');
      article.dataset.cardId = card.id || '';
      article.dataset.tone = card.tone || 'neutral';
      article.append(node('h4', card.question || ''), node('p', card.answer || '', 'options-plain-answer'),
        node('p', card.meaning || '', 'options-plain-meaning'));
      const visual = partVisual(card.visual);
      if (visual) article.append(visual);
      if (card.details) {
        const details = node('details', undefined, 'options-plain-explanation');
        details.append(node('summary', t('whyAndEvidence')));
        const lines = Array.isArray(card.details) ? card.details : [card.details];
        for (const line of lines) details.append(node('p', line));
        article.append(details);
      }
      if (card.evidence_ids?.length) article.append(citations(card.evidence_ids, context));
      cards.append(article);
    }
    wrapper.append(cards);

    if (Array.isArray(brief.items) && brief.items.length) {
      const items = node('section', undefined, 'options-plain-items');
      items.append(node('h4', t('batchReading')));
      for (const item of brief.items) {
        const entry = node('article');
        entry.append(node('h5', [item.symbol, item.expiration].filter(Boolean).join(' · ')),
          node('p', item.headline || ''));
        if (item.activity) entry.append(node('p', item.activity));
        if (item.pricing) entry.append(node('p', item.pricing));
        if (item.freshness) entry.append(node('small', typeof item.freshness === 'string' ? item.freshness : item.freshness.label || ''));
        entry.append(citations(item.evidence_ids, context));
        items.append(entry);
      }
      wrapper.append(items);
    }
    if (Array.isArray(data.failures) && data.failures.length) {
      wrapper.append(textPanel(t('failedPlain'), data.failures.map(batchFailureText)));
      appendFailureDiagnostics(wrapper, data.failures);
    }
    if (brief.next_steps?.length) wrapper.append(textPanel(t('nextSteps'), brief.next_steps));
    if (Array.isArray(brief.glossary) && brief.glossary.length) wrapper.append(renderGlossary(brief.glossary));
    if (data.interpretation?.status === 'ok' && data.interpretation.report) {
      const ai = node('details', undefined, 'options-ai-more');
      ai.append(node('summary', t('aiMore')), renderInterpretation(data.interpretation, context));
      wrapper.append(ai);
    }
    if (context.records.size) wrapper.append(context.details);
    const advanced = node('button', t('professionalView'), 'options-open-professional');
    advanced.type = 'button';
    advanced.addEventListener('click', () => setReadingMode('professional'));
    wrapper.append(advanced);
    return wrapper;
  }

  function renderProfessionalResult(data, target) {
    if (Array.isArray(data.reports)) {
      const comparison = data.comparison || {};
      const context = evidenceForResult(data);
      target.replaceChildren(renderAssessment(comparison.assessment || {}, context, t('comparison')));
      if (data.interpretation) target.append(renderInterpretation(data.interpretation, context));
      target.append(renderComparison(comparison));
      if (context.records.size) target.append(context.details);
      if (data.completed_at) target.append(node('p', `${t('completedAt')} ${time(data.completed_at)}`, 'options-meta'));
      if (Array.isArray(data.failures) && data.failures.length) {
        target.append(textPanel(t('failedItems'), data.failures.map(batchFailureText)));
        appendFailureDiagnostics(target, data.failures);
      }
      if (!data.reports.length) target.append(node('p', t('noReports')));
      const chains = node('section', undefined, 'options-batch-chains');
      chains.append(node('h3', t('chainReports')));
      for (const report of data.reports) {
        const details = node('details', undefined, 'options-chain-report');
        const snapshot = report.snapshot || {};
        details.append(node('summary', `${snapshot.symbol || '—'} · ${snapshot.expiration || '—'} · ${modeLabel(report.quality?.market_data_status)}`));
        details.append(renderSingle(report));
        chains.append(details);
      }
      target.append(chains);
    } else {
      target.replaceChildren(renderSingle(data));
    }
    if (viewingSavedReport) target.prepend(node('p', t('savedQuality'), 'options-saved-quality'));
    target.hidden = false;
  }

  function renderResult(data) {
    const plain = renderPlainBrief(data);
    const professional = node('section', undefined, 'options-professional-report');
    renderProfessionalResult(data, professional);
    plain.hidden = readingMode !== 'simple';
    professional.hidden = readingMode !== 'professional';
    results.replaceChildren(plain, professional);
    if (typeof data.analysis_id === 'string' && data.analysis_id) {
      const followup = node('section', undefined, 'options-followup');
      followup.append(node('h3', t('followupTitle')));
      const followupStatus = node('p', undefined, 'options-followup-status'); followupStatus.setAttribute('role', 'status');
      const attach = async prompt => {
        followupStatus.textContent = '';
        const attached = await window.FinPilotAnalysis?.attach(data, prompt);
        if (attached === false) followupStatus.textContent = t('followupFailed');
      };
      const main = node('button', t('followupAction') + ' ↗', 'primary-button options-followup-main'); main.type = 'button';
      main.disabled = window.FinPilotAnalysis?.isBusy() || false;
      main.addEventListener('click', () => attach(t('followupPrompt')));
      followup.append(main, node('p', t('followupHint')));
      const suggestions = node('div', undefined, 'options-followup-suggestions');
      for (const key of ['followupMeaning', 'followupEvidence', 'followupUnknown', 'followupPrediction']) {
        const button = node('button', t(key)); button.type = 'button';
        button.disabled = window.FinPilotAnalysis?.isBusy() || false;
        button.addEventListener('click', () => attach(t(key)));
        suggestions.append(button);
      }
      followup.append(suggestions, followupStatus); results.prepend(followup);
    }
    if (data.refresh_comparison && window.FinPilotAnalysis?.renderComparison) {
      results.insertBefore(window.FinPilotAnalysis.renderComparison(data.refresh_comparison), plain);
    }
    if (retainingPreviousResult) results.prepend(node('p', t('retainedReport'), 'options-retained-notice'));
    results.hidden = false;
  }

  function setReadingMode(mode) {
    readingMode = mode;
    localStorage.setItem('finpilot-options-reading', mode);
    document.getElementById('options-view-simple').setAttribute('aria-pressed', String(mode === 'simple'));
    document.getElementById('options-view-professional').setAttribute('aria-pressed', String(mode === 'professional'));
    dialog.dataset.reading = mode;
    if (currentResult) renderResult(currentResult);
    if (gatewayStatus) showGateway();
  }

  function syncAnalysisMode() {
    const batch = analysisMode.value === 'batch';
    document.querySelectorAll('[data-options-single]').forEach(label => { label.hidden = batch; });
    document.querySelectorAll('[data-options-batch]').forEach(label => { label.hidden = !batch; });
    symbolInput.required = !batch;
    symbolInput.disabled = batch;
    renderExpirations();
    batchInput.required = batch;
    batchInput.disabled = !batch;
  }

  function parseBatch(value) {
    const lines = value.split(/\r?\n/).map(line => line.trim()).filter(Boolean);
    if (!lines.length || lines.length > 4) return null;
    const items = [];
    const keys = new Set();
    for (const line of lines) {
      const match = line.match(/^(.*?)(?:\s+(\d{4}-\d{2}-\d{2}))?$/);
      const symbol = match?.[1].trim().toUpperCase();
      const expiry = match?.[2] || null;
      if (!symbol || symbol.length > 12 || !/^[A-Z][A-Z0-9]*(?:[ .-][A-Z0-9]+)?$/.test(symbol)) return null;
      const key = `${symbol}|${expiry || ''}`;
      if (keys.has(key)) return null;
      keys.add(key); items.push({ symbol, expiry });
    }
    return items;
  }

  function applyCopy() {
    document.querySelectorAll('[data-options-text]').forEach(element => { element.textContent = t(element.dataset.optionsText); });
    for (const option of document.getElementById('options-radius').options) {
      const count = Number(option.value) * 2 + 1;
      option.textContent = language() === 'zh' ? `${count} 档约定价格` : `${count} contract prices`;
    }
    renderExpirations();
    if (currentRequest) progress.textContent = t('loading');
    else if (currentResult) progress.textContent = t('complete');
    if (dialog.open) {
      showGateway();
      if (currentResult) renderResult(currentResult);
    }
  }

  function providerError(detail, status) {
    if (typeof detail === 'string') return detail;
    if (Array.isArray(detail)) return detail.map(issue => issue.msg).filter(Boolean).join(' · ');
    if (ibkrErrors[detail?.code]) {
      const dates = availableDates(detail.available_expirations);
      return translate(ibkrErrors[detail.code]) + (dates.length ? ` ${t('expiryDates')} · ${dates.slice(0, 8).join(' / ')}` : '');
    }
    if (typeof detail?.message === 'string') return detail.message;
    return `HTTP ${status}`;
  }

  function batchFailureText(item) {
    const dates = availableDates(item.available_expirations);
    return `${item.symbol || ''} ${item.expiry || ''} · ${providerError(item, 424)}`
      + (dates.length && !ibkrErrors[item.code] ? ` ${t('expiryDates')} · ${dates.slice(0, 8).join(' / ')}` : '');
  }

  function showErrorActions(code) {
    errorActions.replaceChildren();
    errorActions.hidden = true;
    const select = document.getElementById('options-feed-mode');
    if (code !== 'ibkr_entitlement_missing' || ['3', '4'].includes(select.value)) return;
    const retry = node('button', t('retryDelayed'), 'options-retry-delayed');
    retry.type = 'button';
    retry.addEventListener('click', () => {
      if (currentRequest) return;
      select.value = '3';
      document.getElementById('options-advanced').open = true;
      form.requestSubmit();
    });
    errorActions.append(retry);
    errorActions.hidden = false;
  }

  async function analyze(event) {
    event.preventDefault();
    if (currentRequest) return;
    if (expirationLoad) {
      await expirationLoad;
      if (currentRequest || !dialog.open) return;
    }
    const previousResult = currentResult;
    showErrorActions();
    const values = new FormData(form);
    const batch = values.get('analysis_mode') === 'batch';
    const symbol = String(values.get('symbol') || '').trim().toUpperCase();
    const items = batch ? parseBatch(String(values.get('batch_items') || '')) : null;
    if ((batch && !items) || (!batch && !symbol)) {
      errorBox.textContent = t(batch ? 'invalidBatch' : 'invalidSymbol');
      errorBox.hidden = false;
      (batch ? batchInput : symbolInput).focus();
      return;
    }
    if (!batch) symbolInput.value = symbol;
    viewingSavedReport = false; retainingPreviousResult = false;
    const controller = new AbortController();
    currentRequest = controller;
    const timer = setTimeout(() => controller.abort('timeout'), batch ? 240000 : 120000);
    fields.disabled = true;
    form.setAttribute('aria-busy', 'true');
    progress.textContent = t('loading');
    progress.hidden = false;
    errorBox.hidden = true;
    results.hidden = true;
    currentResult = null;
    filter = 'all';

    let failure;
    let failureCode;
    let failureDiagnostics;
    try {
      await expirationQueue;
      if (controller.signal.aborted) return;
      if (batch && items.some(item => item.expiry)) {
        progress.textContent = t('expiryChecking');
        await validateBatchDates(items, controller.signal);
        progress.textContent = t('loading');
      }
      const payload = {
        ...(batch ? { items } : { symbol, expiry: values.get('expiry') || null }), radius: Number(values.get('radius')),
        interpret_with_llm: values.has('interpret'), language: language(),
      };
      if (values.get('market_data_type')) payload.market_data_type = Number(values.get('market_data_type'));
      const response = await fetch(batch ? '/api/options/batch' : '/api/options/analyze', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        signal: controller.signal,
        body: JSON.stringify(payload),
      });
      const data = await response.json().catch(() => null);
      if (!response.ok) {
        const error = new Error(providerError(data?.detail, response.status));
        error.providerCode = data?.detail?.code;
        error.detail = data?.detail;
        throw error;
      }
      const valid = batch ? Array.isArray(data?.reports) && data.comparison
        : Array.isArray(data?.snapshot?.quotes) && data.quality && data.metrics;
      if (!valid) throw new Error(t('invalidResponse'));
      if (controller.signal.aborted || !dialog.open) return;
      renderResult(data);
      currentResult = data;
      if (Array.isArray(data.failures) && data.failures.some(item => item.code === 'ibkr_entitlement_missing')) {
        showErrorActions('ibkr_entitlement_missing');
      }
      progress.textContent = t('complete');
      results.scrollIntoView({ block: 'start', behavior: document.documentElement.dataset.motion === 'reduced' ? 'instant' : 'smooth' });
    } catch (error) {
      if (controller.signal.aborted) {
        if (controller.signal.reason === 'timeout') failure = t('timeout');
      } else {
        failureCode = error.providerCode;
        failureDiagnostics = error.detail?.diagnostics;
        failure = error instanceof TypeError ? t('disconnected') : error.message;
      }
      if (failure && dialog.open) {
        errorBox.textContent = failure;
        const diagnostic = renderDiagnostics(failureDiagnostics, true);
        if (diagnostic) errorBox.append(diagnostic);
        errorBox.hidden = false;
        showErrorActions(failureCode);
        if (previousResult) {
          currentResult = previousResult; viewingSavedReport = true; retainingPreviousResult = true;
          renderResult(previousResult); showGateway();
        }
        progress.hidden = true;
        errorBox.scrollIntoView({ block: 'nearest', behavior: document.documentElement.dataset.motion === 'reduced' ? 'instant' : 'smooth' });
      }
    } finally {
      clearTimeout(timer);
      if (currentRequest === controller) {
        currentRequest = null;
        fields.disabled = false;
        form.setAttribute('aria-busy', 'false');
        progress.hidden = Boolean(failure) || !currentResult;
      }
    }
  }

  function open() {
    closeSidebar();
    openToolDialog(dialog);
    if (currentResult) renderResult(currentResult);
    refreshGateway();
    if (document.getElementById('options-advanced').open && validSymbol(normalizedSymbol())) loadExpirations();
  }

  window.FinPilotOptions = { showSavedReport(data) {
    if (!data?.analysis_id) return;
    closeSidebar(); openToolDialog(dialog);
    currentResult = data; viewingSavedReport = true; retainingPreviousResult = false; showGateway(); renderResult(data);
    errorBox.hidden = true; errorActions.hidden = true; progress.hidden = true;
    results.scrollIntoView({ block:'start', behavior:'instant' });
  } };

  document.getElementById('nav-options').addEventListener('click', open);
  dialog.addEventListener('close', () => {
    gatewayRequest?.abort();
    gatewayRequest = null;
    currentRequest?.abort();
    for (const controller of expirationControllers) controller.abort();
  });
  document.getElementById('options-view-simple').addEventListener('click', () => setReadingMode('simple'));
  document.getElementById('options-view-professional').addEventListener('click', () => setReadingMode('professional'));
  form.addEventListener('submit', analyze);
  analysisMode.addEventListener('change', syncAnalysisMode);
  symbolInput.addEventListener('input', resetExpirations);
  symbolInput.addEventListener('change', () => {
    if (document.getElementById('options-advanced').open) loadExpirations();
  });
  expiryRefresh.addEventListener('click', () => loadExpirations(true));
  expirySelect.addEventListener('change', () => { expirationSelection = expirySelect.value; });
  document.getElementById('options-advanced').addEventListener('toggle', event => {
    if (event.target.open) loadExpirations();
  });
  new MutationObserver(applyCopy).observe(document.documentElement, { attributes: true, attributeFilter: ['lang'] });
  applyCopy();
  syncAnalysisMode();
  setReadingMode(readingMode);

  const query = new URLSearchParams(location.search);
  if (query.get('view') === 'options' && !['compound', 'loan', 'budget'].includes(query.get('tool'))) open();
})();
