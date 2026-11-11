'use strict';

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
// Apply the light redesign once and retain theme choices made after migration.
if (localStorage.getItem('finpilot-workspace-skin') !== 'coinwise-v5') {
  localStorage.setItem('finpilot-theme', 'light');
  localStorage.setItem('finpilot-workspace-skin', 'coinwise-v5');
}
const motionMedia = matchMedia('(prefers-reduced-motion: reduce)');
const activeAnimations = new Set();
const state = { language: localStorage.getItem('finpilot-language') === 'en' ? 'en' : 'zh', sessionId: null, messages: [], sessions: [], busy: false, health: null, calculatorKind: 'compound', recognition: null, recording: false, toastTimer: null, lastAnswer: null };
Object.assign(state, {
  theme: localStorage.getItem('finpilot-theme') === 'dark' ? 'dark' : 'light',
  engine: localStorage.getItem('finpilot-engine') || 'deepseek', models: [],
  avatarCharacter: localStorage.getItem('finpilot-avatar-character') === 'robot' ? 'robot' : 'whale',
  avatarMode: localStorage.getItem('finpilot-avatar-character') === 'robot' && localStorage.getItem('finpilot-avatar-mode') !== '2d' ? '3d' : '2d',
  avatarState: 'idle', avatar: null, speech: null, speechStarted: false, avatarRenderStatus: null,
  reducedMotion: localStorage.getItem('finpilot-reduced-motion') === 'true',
  panelExpanded: innerWidth > 1180, smallLayout: innerWidth <= 1180,
  osReducedMotion: motionMedia.matches, calculationSequence: 0, menuOpen: false,
  analysisContext: null, analysisHistory: [], contextBusy: false, refreshing: false, sessionSequence: 0, drafts: new Map(),
  remoteBusy:false, companionClient:null, companionConnection:null, companionActivities:[], pendingSharedSession:null,
});
const companionLocalActivities = new Map();
const companionMessageHighWater = new Map();
let companionActivityErrorTimer = null;

const translations = {
  zh: {
    brandSub:'金融知识 · 理性决策', workspace:'个人学习工作台', navChat:'知识助手', navCalculator:'财务计算器', navKnowledge:'知识来源', recentSessions:'最近会话', noSessions:'从一个问题开始你的探索。', sidebarNote:'让数据解释假设，\n让来源支持判断。', projectSub:'金融领域 AI 项目', research:'研究与规划', workbench:'金融知识工作台', newSession:'新建会话', heroTitle:'让每个财务问题，\n都有据可循。', heroDescription:'从理解一个概念，到计算一份计划。\n和你的 AI 金融知识助手，一起把复杂问题想清楚。', tagSource:'来源可追溯', tagMath:'确定性计算', tagLanguage:'中英双语', artText:'理解，是长期的资产', artCaption:'示意图 · 非市场数据', startHere:'从这里开始', startHint:'选一个问题，开启探索', prompt1Category:'投资入门', prompt1:'分散投资，真的能降低风险吗？', prompt1Hint:'理解风险与收益的关系', prompt2Category:'长期规划', prompt2:'每月存一笔钱，10 年后会怎样？', prompt2Hint:'用复利计算看见假设的影响', prompt3Category:'日常财务', prompt3:'应急储备金，需要准备多少？', prompt3Hint:'建立一份有缓冲的财务计划', thinking:'正在检索知识并整理回答…', inputLabel:'你的金融问题', inputPlaceholder:'问一个金融问题，或描述你的财务计算需求…', voiceInput:'语音输入', voiceUnavailable:'语音不可用', calculate:'计算', enterHint:'Enter 发送 · Shift + Enter 换行', disclaimer:'聊天仅供金融知识学习。期权行情请打开「期权分析」。', export:'导出会话 ↗', footer:'基于知识检索与 DeepSeek 构建', calculatorTitle:'把计划，算清楚。', calculatorDescription:'结果由固定公式计算；改变假设，比较不同计划。', compoundTab:'复利储蓄', loanTab:'贷款月供', budgetTab:'收支预算', runCalculation:'计算结果 ↗', knowledgeTitle:'每个判断，都有来处。', knowledgeDescription:'本地精选知识库支持回答检索。来源链接可供进一步查阅；知识库不代表实时行情或完整的监管建议。', connecting:'连接中', offline:'离线知识模式', online:'DeepSeek 已配置', connectionError:'服务未连接', user:'你', assistant:'FinPilot', modeOffline:'离线检索', modeDeepseek:'DeepSeek + 检索', modeCalculator:'公式计算', sources:'参考来源 · 点击查看原文', readAloud:'朗读回答', copy:'复制回答', copied:'已复制到剪贴板', copyFailed:'复制失败，请手动选择文本。', unsupportedVoice:'此浏览器不支持语音识别，请使用 Chrome / Edge 或键盘输入。', unsupportedSpeech:'此浏览器不支持语音朗读。', voiceError:'语音识别未完成，请检查麦克风权限或使用键盘输入。', listening:'正在聆听…', deleteSession:'删除会话', deleteConfirm:'确定删除此会话？删除后无法恢复。', unnamedSession:'新会话', sessionRemoved:'会话已删除', noKnowledge:'暂无可用知识来源。', loading:'正在加载…', errorPrefix:'操作未完成：', disconnected:'无法连接服务，请确认本地服务已启动后重试。', timeout:'请求超时，请稍后重试。输入内容已保留。', principal:'初始金额', loanPrincipal:'贷款本金', annualRate:'名义年利率', years:'期限', monthlyContribution:'每月追加', income:'月收入', expenses:'月支出', currency:'元', yearUnit:'年', rateHint:'输入百分数，例如 5 表示 5%', contributionHint:'假设每月月末追加', loanHint:'等额本息，不含费用', incomeHint:'使用每月税后收入', expensesHint:'包含固定与可变支出', assumptions:'计算假设', formula:'计算公式', chartStart:'起点', chartEnd:'期末', changedLanguage:'界面语言已切换；已有回答保持原语言。', send:'发送', openNavigation:'打开导航', close:'关闭', updateDate:'知识核验日期：', financialNotice:'计算结果为假设情景，不代表实际收益或银行报价。', noCalculation:'没有返回可显示的计算结果。', sessionBusy:'当前回答完成后可切换会话。', stoppedSpeech:'已停止朗读', stopSpeech:'停止朗读', budgetHint:'仅做收支估算；不构成个人财务建议。', offlineWarning:'当前未配置或无法连接模型，将使用本地知识检索回答。', positive:'盈余', negative:'缺口' 
  },
  en: {
    brandSub:'FINANCE · CLEAR THINKING', workspace:'Personal learning workspace', navChat:'Knowledge assistant', navCalculator:'Financial calculators', navKnowledge:'Knowledge sources', recentSessions:'RECENT CONVERSATIONS', noSessions:'Every insight starts with a question.', sidebarNote:'Let numbers explain assumptions.\nLet sources support decisions.', projectSub:'Finance AI project', research:'Research & planning', workbench:'Financial knowledge workspace', newSession:'New conversation', heroTitle:'Financial questions.\nGrounded answers.', heroDescription:'From understanding a concept to calculating a plan.\nMake complex questions clearer with your AI finance assistant.', tagSource:'Traceable sources', tagMath:'Verified formulas', tagLanguage:'Chinese & English', artText:'Understanding is a lasting asset', artCaption:'ILLUSTRATION · NOT MARKET DATA', startHere:'A good place to start', startHint:'Choose a question to explore', prompt1Category:'INVESTING BASICS', prompt1:'Can diversification really reduce risk?', prompt1Hint:'Understand risk and return', prompt2Category:'LONG-TERM PLANNING', prompt2:'What could monthly saving look like in 10 years?', prompt2Hint:'Explore the effects of compounding', prompt3Category:'EVERYDAY FINANCE', prompt3:'How much should an emergency fund hold?', prompt3Hint:'Build a plan with a financial buffer', thinking:'Searching knowledge and preparing an answer…', inputLabel:'Your financial question', inputPlaceholder:'Ask a financial question or describe a calculation…', voiceInput:'Voice input', voiceUnavailable:'Voice unavailable', calculate:'Calculate', enterHint:'Enter to send · Shift + Enter for a new line', disclaimer:'Chat is for financial education. Use Options Analysis for options market data.', export:'Export chat ↗', footer:'Built with knowledge retrieval & DeepSeek', calculatorTitle:'Give your plans some numbers.', calculatorDescription:'Results use fixed formulas. Change the assumptions and compare your plans.', compoundTab:'Compound savings', loanTab:'Loan payment', budgetTab:'Monthly budget', runCalculation:'Calculate ↗', knowledgeTitle:'Answers with a place to start.', knowledgeDescription:'A curated local knowledge base supports retrieval. Follow source links to learn more. These materials are not live market data or complete regulatory guidance.', connecting:'Connecting', offline:'Offline knowledge', online:'DeepSeek configured', connectionError:'Service unavailable', user:'You', assistant:'FinPilot', modeOffline:'Offline retrieval', modeDeepseek:'DeepSeek + retrieval', modeCalculator:'Formula calculation', sources:'REFERENCES · OPEN ORIGINAL SOURCE', readAloud:'Read aloud', copy:'Copy answer', copied:'Copied to clipboard', copyFailed:'Copy failed. Please select and copy the text manually.', unsupportedVoice:'Speech recognition is unavailable in this browser. Try Chrome / Edge or type your question.', unsupportedSpeech:'Speech synthesis is unavailable in this browser.', voiceError:'Speech recognition could not finish. Check microphone permission or type your question.', listening:'Listening…', deleteSession:'Delete conversation', deleteConfirm:'Delete this conversation? This cannot be undone.', unnamedSession:'New conversation', sessionRemoved:'Conversation deleted', noKnowledge:'No knowledge sources are available.', loading:'Loading…', errorPrefix:'Could not complete: ', disconnected:'Cannot reach the service. Check that the local server is running and try again.', timeout:'The request timed out. Your input has been preserved; please retry.', principal:'Initial amount', loanPrincipal:'Loan principal', annualRate:'Nominal annual interest', years:'Term', monthlyContribution:'Monthly contribution', income:'Monthly income', expenses:'Monthly expenses', currency:'amount', yearUnit:'years', rateHint:'Use a percentage: 5 means 5%', contributionHint:'Contributed at the end of each month', loanHint:'Equal monthly payments; fees excluded', incomeHint:'Use monthly take-home income', expensesHint:'Include fixed and variable costs', assumptions:'Assumptions', formula:'Formula', chartStart:'Start', chartEnd:'End of term', changedLanguage:'Interface language changed. Existing answers keep their original language.', send:'Send', openNavigation:'Open navigation', close:'Close', updateDate:'Knowledge reviewed: ', financialNotice:'Hypothetical results are not actual returns or a bank quotation.', noCalculation:'No calculation results were returned.', sessionBusy:'Wait for the current answer before changing conversations.', stoppedSpeech:'Reading stopped', stopSpeech:'Stop reading', budgetHint:'A simple cash-flow estimate, not personal financial advice.', offlineWarning:'The model is not configured or could not be reached. Local knowledge retrieval is available.', positive:'Surplus', negative:'Shortfall'
  }
};

Object.assign(translations.zh, {
  companion:'交互助手', companionIntro:'一起理解概念、核查来源，\n把每一步计划想清楚。', spatialMode:'立体', simpleMode:'简约',
  readLatest:'朗读最新回答', reduceMotion:'减少动态效果', avatarExplanation:'动作随对话与语音状态变化；说话动作为近似演绎。',
  sessionFocus:'今日的学习原则', focusAdvice:'先问依据，再看数字。', modelLabel:'回答引擎', modelDefaultDescription:'结合本地知识来源，整理金融教育回答。',
  groundedContext:'知识驱动 · 来源可查', lightTheme:'切换浅色主题', darkTheme:'切换深色主题', previewSource:'查看知识摘录',
  avatarIdle:'准备就绪', avatarListening:'正在聆听', avatarThinking:'正在整理回答', avatarSpeaking:'正在朗读', avatarError:'请检查提示后重试',
  expandAssistant:'展开交互助手', collapseAssistant:'折叠交互助手', modelUnavailable:'该引擎当前不可用', modeLocal:'本地 LoRA + 检索',
  localConfigured:'本地 LoRA 可用', sourceCitation:'查看来源：', speechError:'语音朗读未能完成，请检查设备声音或可用语音。',
  avatarFallback:'当前设备的 3D 渲染不可用，已显示 2D 形象。文字与语音操作保持可用。',
  localModelLabel:'本地微调 · 实验版', localNotReady:'本地微调 · 未就绪', cloudNotReady:'DeepSeek · 暂不可用',
  deepseekDescription:'适合日常金融概念学习与来源核查。重要结论请打开原文确认。',
  localDescription:'在本机运行的金融学习实验模型，回答质量仍有限。请结合来源核查。',
  localUnavailableDescription:'本地实验模型尚未就绪。可继续使用 DeepSeek，或查看离线资料。',
  cloudUnavailableDescription:'云端模型暂不可用，仍可查看本地知识资料。',
});
Object.assign(translations.en, {
  companion:'COMPANION', companionIntro:'Understand concepts. Check the evidence.\nThink through your next step.', spatialMode:'Spatial', simpleMode:'Simple',
  readLatest:'Read latest answer', reduceMotion:'Reduce motion', avatarExplanation:'Actions reflect chat and speech states. Speaking animation is approximate.',
  sessionFocus:'A PRINCIPLE FOR TODAY', focusAdvice:'Evidence first. Numbers second.', modelLabel:'ANSWER ENGINE', modelDefaultDescription:'Financial education responses grounded in local references.',
  groundedContext:'GROUNDED IN REFERENCES', lightTheme:'Switch to light theme', darkTheme:'Switch to dark theme', previewSource:'Preview reference extract',
  avatarIdle:'Ready when you are', avatarListening:'Listening', avatarThinking:'Preparing your answer', avatarSpeaking:'Reading aloud', avatarError:'Check the message and retry',
  expandAssistant:'Expand interactive companion', collapseAssistant:'Collapse interactive companion', modelUnavailable:'This engine is unavailable', modeLocal:'Local LoRA + retrieval',
  localConfigured:'Local LoRA available', sourceCitation:'Open source: ', speechError:'Read-aloud could not finish. Check device audio and the available voices.',
  avatarFallback:'3D rendering is unavailable on this device. A 2D companion is shown; text and speech controls remain available.',
  localModelLabel:'Local fine-tuned · Experimental', localNotReady:'Local fine-tuned · Not ready', cloudNotReady:'DeepSeek · Unavailable',
  deepseekDescription:'For everyday financial learning and checking sources. Open the original reference to verify important claims.',
  localDescription:'A financial learning experiment running on this computer. Answer quality is limited; verify claims against the sources.',
  localUnavailableDescription:'The local experimental model is not ready. You can use DeepSeek or read the offline references.',
  cloudUnavailableDescription:'The cloud model is unavailable. Local knowledge references remain accessible.',
});

Object.assign(translations.zh, {
  motionToggle:'暂停动效', motionResume:'开启动效', motionSystem:'系统已减少动效',
  modelSwitched:'已切换为 {model}，下一条问题将使用此引擎。',
  thinkingCloud:'DeepSeek 正在整理回答…', thinkingLocal:'本地微调模型正在整理回答…',
  inputLabel:'你的问题', inputPlaceholder:'问一个金融或一般问题，也可以描述计算需求…',
  disclaimer:'支持金融学习与一般问答。期权行情请打开「期权分析」。',
});
Object.assign(translations.en, {
  motionToggle:'Pause motion', motionResume:'Enable motion', motionSystem:'System motion reduced',
  modelSwitched:'Switched to {model}. Your next question will use this engine.',
  thinkingCloud:'DeepSeek is preparing an answer…', thinkingLocal:'The local fine-tuned model is preparing an answer…',
  inputLabel:'Your question', inputPlaceholder:'Ask a finance or everyday question, or describe a calculation…',
  disclaimer:'Financial learning and everyday questions. Use Options Analysis for options market data.',
});

Object.assign(translations.zh, {
  analysisAttached:'已附上这批期权摘要', analysisForNext:'从输入框发送问题时，将把这批摘要交给 {model} 解释；仅修改草稿不会调用模型。',
  analysisSnapshot:'固定快照，不会自动刷新行情。', analysisStale:'快照已超过 30 秒，请勿当作当前行情。',
  analysisTimingUnknown:'本地接收时间无法确认。', analysisCaptured:'本地接收时间（UTC）', analysisScope:'分析范围',
  analysisRemove:'移除这批数据', analysisView:'回看原分析', analysisWorking:'正在关联分析会话…',
  analysisReply:'本条回答依据的期权快照', analysisEvidence:'本地计算依据', analysisValue:'数值',
  analysisSource:'数据来源', analysisPartial:'部分项目未取得数据，当前结论仅覆盖成功项目。',
  analysisMissing:'原分析无法读取，请稍后重试；当前摘要不会被刷新。', analysisSession:'期权追问',
  analysisUpdating:'正在保存会话的数据范围…', analysisUnknown:'未确认', analysisFeedLive:'实时类型',
  analysisFeedDelayed:'延迟行情', analysisFeedFrozen:'冻结报价', analysisFeedMixed:'混合行情类型',
  analysisFeedDelayedFrozen:'延迟且冻结', analysisFeedUnavailable:'行情不可用', analysisNoGuarantee:'时间记录本地接收，不保证交易所延迟；行情类型不保证每项报价仍然新鲜。',
  analysisScopeComparison:'跨项目比较', analysisAttachFailed:'未能关联这批分析，尚未发送给模型。',
  analysisFreshnessUnknown:'无法确认这份快照的新鲜度，请勿当作当前行情。', analysisEvidenceShort:'依据',
  analysisNotProvided:'未提供', analysisPoints:'百分点', analysisContracts:'份合约',
});
Object.assign(translations.en, {
  analysisAttached:'Options summary attached', analysisForNext:'Sending a question from the input will give this summary to {model}. Editing the draft does not call the model.',
  analysisSnapshot:'Fixed snapshot. Market data does not refresh automatically.', analysisStale:'Snapshot is over 30 seconds old; do not treat it as current quotes.',
  analysisTimingUnknown:'Local receipt time could not be confirmed.', analysisCaptured:'Local receipt (UTC)', analysisScope:'Scope',
  analysisRemove:'Remove this data', analysisView:'Review original analysis', analysisWorking:'Linking an analysis conversation…',
  analysisReply:'Options snapshot used for this answer', analysisEvidence:'Locally computed evidence', analysisValue:'Value',
  analysisSource:'Data source', analysisPartial:'Some items were unavailable. Conclusions cover the successful items only.',
  analysisMissing:'The saved analysis could not be read. Try again; the attached snapshot has not been refreshed.', analysisSession:'Options follow-up',
  analysisUpdating:'Saving the data scope for this conversation…', analysisUnknown:'Unconfirmed', analysisFeedLive:'Live feed type',
  analysisFeedDelayed:'Delayed quotes', analysisFeedFrozen:'Frozen quotes', analysisFeedMixed:'Mixed feed types',
  analysisFeedDelayedFrozen:'Delayed-frozen quotes', analysisFeedUnavailable:'Quotes unavailable', analysisNoGuarantee:'Times record local receipt, not guaranteed exchange latency. Feed type does not guarantee every quote is still fresh.',
  analysisScopeComparison:'Cross-item comparison', analysisAttachFailed:'The analysis could not be linked. Nothing has been sent to the model.',
  analysisFreshnessUnknown:'Snapshot freshness could not be confirmed. Do not treat it as current quotes.', analysisEvidenceShort:'Evidence',
  analysisNotProvided:'Not provided', analysisPoints:'percentage points', analysisContracts:'contracts',
});
Object.assign(translations.zh, {
  analysisRefresh:'刷新并解释变化', analysisRefreshDisclosure:'重新采集相同的标的、到期日与范围，并将摘要和前后变化发送给 {model}。点击即开始本次采集与模型解释；输入框里的草稿不会发送。',
  analysisRefreshing:'正在重新采集并解释变化…', analysisRefreshIntent:'请刷新这批期权数据，并用易懂的话解释与上一次相比发生了什么变化。',
  analysisRefreshFailed:'刷新未完成。当前显示的快照与草稿已保留。', analysisRefreshIncomplete:'刷新返回的数据不完整，请重新打开当前会话核对已保存的结果。',
  analysisHistory:'分析记录', analysisHistoryCurrent:'当前使用', analysisHistoryPast:'较早快照', analysisHistoryHint:'回看只打开已保存的报告，不切换当前数据，也不重新采集行情。',
  analysisChanges:'这次与上次有什么变化', analysisBefore:'上一次', analysisAfter:'本次', analysisChange:'变化量', analysisNoComparison:'暂不能直接比较',
  analysisComparable:'可在所示范围内比较', analysisPartialComparison:'部分项目可以比较', analysisIncomparable:'缺少直接比较的条件',
  analysisChangeScopeAdded:'本次新增的范围，没有前值可比较。', analysisChangeScopeMissing:'本次未取得这一范围，不能比较。',
  analysisChangeNoMetrics:'没有满足直接比较条件的指标。', analysisVolatilityPoints:'个波动率点',
  analysisRefreshNotice:'变化由本地计算。成交与持仓有不同统计周期；前后差值不等于新增交易，也不能预测涨跌。',
  analysisReasonFeed:'前后行情类型不一致。', analysisReasonMissing:'前后有数据未取得。', analysisReasonScope:'采样范围或配对条件不同。',
  analysisReasonTime:'接收时间无法确认或比较间隔不符合要求。', analysisReasonQuality:'报价覆盖或质量不足。', analysisReasonOther:'比较条件未满足；请结合采集范围、时间与质量阅读。',
});
Object.assign(translations.en, {
  analysisRefresh:'Refresh and explain changes', analysisRefreshDisclosure:'Collect the same symbols, expirations and sample range again, then send the summaries and changes to {model}. Clicking starts this collection and model explanation; your input draft is not sent.',
  analysisRefreshing:'Collecting new data and explaining changes…', analysisRefreshIntent:'Refresh this options snapshot and explain in plain language what has changed since the previous collection.',
  analysisRefreshFailed:'Refresh did not complete. The displayed snapshot and your draft have been retained.', analysisRefreshIncomplete:'The refresh response was incomplete. Reopen this conversation to check the saved result.',
  analysisHistory:'Analysis history', analysisHistoryCurrent:'Currently used', analysisHistoryPast:'Earlier snapshot', analysisHistoryHint:'Review opens a saved report. It does not switch the active data or collect quotes again.',
  analysisChanges:'What changed since the previous snapshot', analysisBefore:'Previous', analysisAfter:'Current', analysisChange:'Change', analysisNoComparison:'Not directly comparable',
  analysisComparable:'Comparable within the shown scope', analysisPartialComparison:'Some items can be compared', analysisIncomparable:'Direct comparison conditions are not met',
  analysisChangeScopeAdded:'New scope in this collection; there is no previous value.', analysisChangeScopeMissing:'This scope was unavailable in the new collection and cannot be compared.',
  analysisChangeNoMetrics:'No indicators met direct comparison conditions.', analysisVolatilityPoints:'volatility points',
  analysisRefreshNotice:'Changes are calculated locally. Volume and open interest use different reporting periods; a difference is not newly executed trades or a price forecast.',
  analysisReasonFeed:'Feed types differ between the two collections.', analysisReasonMissing:'Data is missing from one or both collections.', analysisReasonScope:'Sampling or paired-contract conditions differ.',
  analysisReasonTime:'Receipt time is uncertain or the comparison interval does not meet requirements.', analysisReasonQuality:'Quote coverage or quality is insufficient.', analysisReasonOther:'Comparison conditions are not met. Read the scope, timing and data quality together.',
});

const valueLabels = {
  future_value:['期末总额','Future value'], total_contributions:['累计投入','Total contributions'], total_invested:['累计投入','Total invested'], total_interest:['累计利息','Total interest'], interest_earned:['预计利息','Interest earned'], monthly_payment:['每月还款','Monthly payment'], total_payment:['还款总额','Total payment'], total_payments:['还款总额','Total payments'], remaining_balance:['剩余本金','Remaining balance'], monthly_surplus:['月度结余','Monthly surplus'], surplus:['月度结余','Monthly surplus'], savings_rate:['储蓄率','Savings rate'], annual_surplus:['年度结余','Annual surplus'], emergency_fund_3_months:['3 个月应急储备','3-month emergency fund'], emergency_fund_6_months:['6 个月应急储备','6-month emergency fund'], principal:['本金','Principal'], income:['月收入','Monthly income'], expenses:['月支出','Monthly expenses'], monthly_income:['月收入','Monthly income'], monthly_expenses:['月支出','Monthly expenses'], months:['总期数（月）','Term (months)'], total_months:['总期数（月）','Term (months)'], balance:['余额','Balance'], total_deposits:['累计投入','Total deposits'], interest:['利息','Interest'], savings_rate_percent:['储蓄率','Savings rate']
};

const warningLabels = {
  offline_requested:['当前使用离线知识库，回答为资料摘录。','Offline knowledge mode is enabled; this answer contains reference extracts.'],
  api_key_missing:['尚未配置模型服务，当前展示本地知识摘录。','The model service is not configured. Showing local reference extracts.'],
  authentication_failed:['模型服务认证失败，已切换为本地知识摘录。请检查服务端密钥配置。','Model authentication failed. Showing local extracts; check the server credential configuration.'],
  insufficient_balance:['模型服务账户余额不足，已切换为本地知识摘录。','The model account has insufficient balance. Showing local reference extracts.'],
  rate_limited:['模型服务请求繁忙，当前展示本地知识摘录。可稍后重试。','The model service is rate limited. Showing local extracts; try again later.'],
  network_or_timeout:['模型服务连接超时或网络不可用，已切换为本地知识摘录。','The model service could not be reached or timed out. Showing local reference extracts.'],
  provider_unavailable:['模型服务暂不可用，已切换为本地知识摘录。','The model service is temporarily unavailable. Showing local reference extracts.'],
  incomplete_response:['模型回答未完整生成，当前展示本地知识摘录。','The model answer was incomplete. Showing local reference extracts.'],
  empty_response:['模型未返回有效回答，当前展示本地知识摘录。','The model returned no answer. Showing local reference extracts.'],
  invalid_response:['模型响应无法使用，当前展示本地知识摘录。','The model response could not be used. Showing local reference extracts.'],
  no_live_data:['数据范围提示：本项目未接入实时市场数据。','Data coverage: this project has no live market feed.'],
  education_boundary:['服务范围提示：仅提供金融教育，不执行交易或提供个别买卖指令。','Scope: financial education only; no trades or personal buy/sell instructions.'],
  insufficient_evidence:['当前知识库依据不足，请补充或调整问题。','The available references are insufficient. Please clarify or rephrase your question.'],
  invalid_calculation:['请在计算器中输入完整且有效的参数。','Enter complete, valid parameters in the calculator.'],
  sensitive_input:['请删除密钥、密码等敏感信息后重试。','Remove credentials or other sensitive information and try again.']
};
warningLabels.local_model_unavailable = ['本地微调模型尚未就绪，当前展示本地知识摘录。可切换 DeepSeek。','The local fine-tuned model is unavailable. Showing reference extracts; you can switch to DeepSeek.'];
warningLabels.cloud_unconfigured = ['云端模型未配置，当前显示本地生成的数据说明。','The cloud model is not configured. Showing a locally generated data explanation.'];
warningLabels.options_answer_validation_failed = ['模型回答未通过证据核验，当前显示本地生成的数据说明。','The model answer did not pass evidence validation. Showing a locally generated data explanation.'];
warningLabels.options_answer_unavailable = ['模型解释暂不可用，新采集的快照已保留。当前显示本地生成的数据说明。','The model explanation is unavailable. The newly collected snapshot has been retained; showing a locally generated data explanation.'];

function warningText(code, analysisContext = false) {
  if (analysisContext && ['offline_requested','api_key_missing','authentication_failed','insufficient_balance','rate_limited','network_or_timeout','provider_unavailable','incomplete_response','empty_response','invalid_response','local_model_unavailable'].includes(code)) {
    return state.language === 'zh' ? '本次模型解释受限，当前显示本地生成的数据说明。快照与计算依据仍可查看。' : 'The model explanation was limited. Showing a locally generated data explanation; the snapshot and computed evidence remain available.';
  }
  return warningLabels[code]?.[state.language === 'zh' ? 0 : 1] || (state.language === 'zh' ? '当前回答存在服务限制，请核实信息来源。' : 'A service limitation applies. Please verify the cited sources.');
}

Object.assign(translations.zh,{navHelp:'使用指南',helpPromptLabel:'不熟悉操作？',helpHistory:'怎么做历史复盘？',helpPet:'怎么连接桌宠？',helpModels:'怎么切换回答模型？',helpManual:'查看手册 ↗'});
Object.assign(translations.en,{navHelp:'Usage guide',helpPromptLabel:'Need a hand?',helpHistory:'How do I review history?',helpPet:'How do I connect the pet?',helpModels:'How do I switch models?',helpManual:'Read the guide ↗'});
function t(key) { return translations[state.language][key] || key; }
function element(tag, className, content) { const el = document.createElement(tag); if (className) el.className = className; if (content !== undefined) el.textContent = content; return el; }
function safeURL(url) { try { const parsed = new URL(url); return ['https:', 'http:'].includes(parsed.protocol) ? parsed.href : null; } catch { return null; } }
function showError(message) { $('#error-banner').textContent = message; $('#error-banner').hidden = !message; }
function toast(message) { clearTimeout(state.toastTimer); $('#toast').textContent = message; $('#toast').hidden = false; state.toastTimer = setTimeout(() => { $('#toast').hidden = true; }, 4200); }

async function api(path, options = {}) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), options.timeout || 70000);
  const finishActivity = path === '/api/calculate' && options.method === 'POST' ? beginCompanionActivity('calculate') : null;
  let activityStatus = 'failed';
  try {
    const response = await fetch(path, { ...options, headers: { 'Content-Type': 'application/json', ...options.headers }, signal: controller.signal });
    let data;
    try { data = await response.json(); } catch { throw new Error(response.ok ? t('noCalculation') : `HTTP ${response.status}`); }
    if (!response.ok) {
      const detail = data.detail || data.error || `HTTP ${response.status}`;
      const message = Array.isArray(detail) ? detail.map(item => `${(item.loc || []).slice(1).join('.')}: ${item.msg}`).join('; ') : typeof detail === 'string' ? detail : detail.message || JSON.stringify(detail);
      const error = new Error(message); error.detail = detail; error.status = response.status; throw error;
    }
    activityStatus = 'completed'; return data;
  } catch (error) {
    if (error.name === 'AbortError') { activityStatus = 'cancelled'; throw new Error(t('timeout')); }
    if (error instanceof TypeError) throw new Error(t('disconnected'));
    throw error;
  } finally { clearTimeout(timer); finishActivity?.(activityStatus); }
}

function isCurrentSharedSession() {
  return Boolean(state.sessionId && state.companionConnection?.session_id === state.sessionId);
}
function companionText(zh,en) { return state.language === 'zh' ? zh : en; }
function renderCompanionConnection() {
  const copy={character:['展示形象','Character'],whale:['鲸鱼娘 · 2D','Whale maid · 2D'],robot:['原有机器人 · 2D/3D','Legacy robot · 2D/3D'],shareTitle:['让桌宠接着聊','Continue with the desktop pet'],connect:['连接当前会话','Connect this conversation'],disconnect:['断开','Disconnect'],preview:['打开桌宠网页预览 ↗','Open pet browser preview ↗'],credits:['角色来源与非商业许可 ↗','Character credits & noncommercial license ↗']};
  document.querySelectorAll('[data-companion-copy]').forEach(node=>{const pair=copy[node.dataset.companionCopy];if(pair)node.textContent=pair[state.language==='zh'?0:1];});
  const current=state.companionConnection,status=$('#companion-connection-status');
  if (!status) return;
  if(!current)status.textContent=companionText('桌宠同步尚未连接；聊天和计算仍可使用。','Pet sync is not connected; chat and calculations remain available.');
  else if(!current.session_id)status.textContent=companionText('只同步你明确连接的会话。连接和动作不会调用模型。','Only an explicitly connected conversation is shared. Connecting and gestures make no model calls.');
  else if(isCurrentSharedSession())status.textContent=current.desktop_connected?companionText('Windows桌宠正在共享当前会话及报告。','The Windows pet shares this conversation and report.'):companionText('当前会话已连接；Windows桌宠未在线，可先启动桌宠。','This conversation is connected; start the Windows pet to continue there.');
  else status.textContent=companionText('桌宠仍连接另一会话；当前页面不会自动切换。','The pet remains linked to another conversation; this page will not switch automatically.');
  status.dataset.shared=String(isCurrentSharedSession());status.dataset.desktopConnected=String(Boolean(current?.desktop_connected));
  $('#companion-connect').disabled=conversationLocked()||!state.companionClient;
  $('#companion-disconnect').disabled=!current?.session_id;
}
function refreshCompanionActivity() {
  const activities=isCurrentSharedSession()?state.companionActivities:[];
  state.remoteBusy=activities.some(item=>['chat','refresh'].includes(item.kind));
  setBusy(state.busy);if(state.avatarState!=='error')settleAvatar();renderCompanionConnection();
}
function beginCompanionActivity(kind,phase) {
  const id=crypto.randomUUID(),sid=state.sessionId;
  const item={operation_id:id,kind,phase,status:'started'};companionLocalActivities.set(id,item);
  const publish=status=>state.companionClient?.publishActivity({operationId:id,kind,status,sessionId:sid,phase});
  publish('started');const heartbeat=setInterval(()=>publish('started'),25000);
  settleAvatar();let ended=false;
  const finish=(status='completed')=>{
    if(ended)return;ended=true;clearInterval(heartbeat);companionLocalActivities.delete(id);publish(status);
    if(status==='failed'&&!state.busy&&!state.remoteBusy&&!companionLocalActivities.size){setAvatarState('error');clearTimeout(companionActivityErrorTimer);companionActivityErrorTimer=setTimeout(settleAvatar,4000);}
    else settleAvatar();
  };
  item.finish=finish;return finish;
}
window.FinPilotActivities=Object.freeze({begin:beginCompanionActivity});
function applySharedSession(session) {
  if(!session||session.id!==state.sessionId)return;
  const highWater=Math.max(0,...(session.messages||[]).map(message=>Number.isInteger(message.id)?message.id:0));
  if(highWater<(companionMessageHighWater.get(session.id)||0))return;
  companionMessageHighWater.set(session.id,highWater);
  state.messages=Array.isArray(session.messages)?session.messages:[];
  state.analysisContext=session.active_analysis||null;state.analysisHistory=[];syncAnalysisHistory(session.analysis_history);
  renderMessages();renderAnalysisContext();renderSessions();
}
function shareCompanionPreferences() {
  if(isCurrentSharedSession())state.companionClient?.setPreferences({language:state.language,engine:state.engine}).catch(error=>showError(error.message));
}
function initializeCompanionConnection() {
  if(state.companionClient||!window.FinPilotCompanionClient)return;
  state.companionClient=window.FinPilotCompanionClient.create({surface:'workspace',shouldSync:sid=>sid===state.sessionId,
    onConnection:connection=>{
      state.companionConnection=connection;
      if(isCurrentSharedSession()) {
        const changed=state.language!==connection.language;
        state.language=connection.language;state.engine=connection.engine;
        localStorage.setItem('finpilot-language',state.language);localStorage.setItem('finpilot-engine',state.engine);
        if(changed)applyLanguage();else{renderModelOptions();setHealthBadge();renderModelSwitchStatus();}
      }
      state.companionActivities=connection.activities||[];refreshCompanionActivity();
    },
    onSession:session=>{if(state.busy){state.pendingSharedSession=session;state.analysisContext=session.active_analysis||null;syncAnalysisHistory(session.analysis_history);renderAnalysisContext();}else applySharedSession(session);},
    onActivity:(activities,event)=>{
      state.companionActivities=activities;refreshCompanionActivity();
      if(isCurrentSharedSession()&&event?.payload?.status==='failed'&&!state.busy&&!activities.length){setAvatarState('error');clearTimeout(companionActivityErrorTimer);companionActivityErrorTimer=setTimeout(settleAvatar,4000);}
    },
    onStatus:value=>{if(!value.connected&&value.error)$('#companion-connection-status').textContent=companionText('桌宠同步暂时断开；将自动重连，不会自动重新提问。','Pet sync disconnected; reconnecting without resending questions.');},
  });
  window.finPilotCompanionClient=state.companionClient;renderCompanionConnection();
}
async function connectCurrentCompanion() {
  if(conversationLocked()||!state.companionClient)return;
  try {
    if(!state.sessionId){const session=await api('/api/sessions',{method:'POST',body:JSON.stringify({title:companionText('桌宠对话','Companion conversation')})});state.sessionId=session.id;localStorage.setItem('finpilot-session',session.id);await loadSessions();}
    await state.companionClient.connect(state.sessionId,{language:state.language,engine:state.engine});renderCompanionConnection();
  }catch(error){showError(error.message);}
}

const diagnosticCopy = {
  title:['本次采集诊断','Collection diagnostics'], details:['查看接口记录','View interface records'],
  two_sided_quotes:['接口收到了买价与卖价字段；请结合报价覆盖和时间判断可用性。','Bid and ask fields were received. Check coverage and timing to judge usability.'],
  last_reference:['取得了最近成交参考，不能把它当作当前双边报价。','A last-trade reference was received. It is not a current two-sided quote.'],
  close_reference:['取得了收盘参考，不能把它当作当前双边报价。','A closing reference was received. It is not a current two-sided quote.'],
  no_reference:['尚未取得可用价格参考。','No usable price reference was received.'],
  limited_option_fields:['期权字段不完整，请核对实际收到的数量。','Options fields are incomplete. Check the actual received counts.'],
  realtime_unsubscribed_delayed_available:['网关明确提示实时订阅受限、可用延迟行情；这不代表已收到延迟报价。','The gateway explicitly reported a limited real-time entitlement with delayed data available. This does not mean delayed quotes arrived.'],
  explicit_denial:['本次出现明确的订阅拒绝提示；这不等于所有行情都被拒绝。','An explicit subscription-denial message was observed. This does not establish that all data was denied.'],
  partialSubscription:['部分请求字段存在订阅限制；已收到字段仍可读取，不能据此声称全部数据被拒绝。','Some requested fields have subscription restrictions. Received fields remain readable; this does not establish that all data was denied.'],
  no_denial_observed:['未观察到明确权限拒绝；仍不能据此确认完整行情授权。','No explicit entitlement denial was observed. This does not confirm full market-data access.'],
  unconfirmed:['行情权限尚未确认。','Market-data entitlement is unconfirmed.'],
  delayedNoQuote:['已收到延迟类型回调，但没有收到双边或最近成交报价。','Delayed-type callbacks arrived, but no two-sided or last-trade quotes were received.'],
  requested:['本次请求类型','Requested feed'], received:['接口返回类型','Received feed types'],
  unknown:['未确认','Unconfirmed'], default:['采用本机设置','Use this computer’s setting'],
  contracts:['请求期权合约','Option contracts requested'], bidAsk:['收到买价和卖价','With bid and ask'], last:['收到最近成交价','With last price'],
  close:['收到收盘参考价','With closing reference'], interest:['收到未平仓量','With open interest'],
  fields:['标的已接收字段','Underlying fields received'], ticks:['观察到的字段类型编号','Observed tick-type IDs'], codes:['网关错误或提示编号','Broker message codes'],
  wait:['本次等待时间（秒）','Collection wait (seconds)'], timeBasis:['时间记录方式','Timestamp basis'], localCallback:['本地字段回调到达时间，不是交易所成交时间。','Local field-callback arrival, not exchange trade time.'],
  interface:['接口回调情况','Interface callbacks'], market_callbacks_received:['已观察到行情字段回调。','Market-field callbacks were observed.'],
  no_market_callbacks:['未观察到行情字段回调；仅凭这一点无法断言权限或接口故障。','No market-field callbacks were observed. This alone does not establish an entitlement or interface fault.'],
};
function diagnosticText(key) { return diagnosticCopy[key]?.[state.language === 'zh' ? 0 : 1] || diagnosticCopy.unknown[state.language === 'zh' ? 0 : 1]; }
function diagnosticFeed(value) { return ({ 1:'live', 2:'frozen', 3:'delayed', 4:'delayed_frozen' })[value] ? `${analysisFeed(({ 1:'live', 2:'frozen', 3:'delayed', 4:'delayed_frozen' })[value])} (${value})` : diagnosticText(value === null || value === undefined ? 'default' : 'unknown'); }
function renderMarketDiagnostics(data, { error = false } = {}) {
  if (!data || typeof data !== 'object' || Array.isArray(data)) return null;
  const section = element('section', 'market-diagnostics'); section.dataset.stage = typeof data.stage === 'string' ? data.stage : '';
  const headline = diagnosticCopy[data.data_status] ? diagnosticText(data.data_status) : diagnosticText('title');
  section.append(element('strong', 'market-diagnostics-heading', headline));
  if (Array.isArray(data.broker_codes) && data.broker_codes.includes(10090)) section.append(element('p', 'market-diagnostics-partial-subscription', diagnosticText('partialSubscription')));
  const entitlement = diagnosticText(diagnosticCopy[data.entitlement_status] ? data.entitlement_status : 'unconfirmed');
  const received = Array.isArray(data.received_market_data_types) ? [...new Set(data.received_market_data_types.filter(value => [1,2,3,4].includes(value)))] : [];
  if (error) section.append(element('p', 'market-diagnostics-entitlement', entitlement));
  if (error && received.some(value => value === 3 || value === 4) && data.option_contracts_requested > 0 && data.option_contracts_with_bid_ask === 0 && data.option_contracts_with_last === 0) section.append(element('p', 'market-diagnostics-delayed', diagnosticText('delayedNoQuote')));
  const details = element('details', 'market-diagnostics-records'); details.append(element('summary', '', diagnosticText('details')));
  if (!error) details.append(element('p', 'market-diagnostics-entitlement', entitlement));
  const list = element('dl', 'market-diagnostics-facts');
  const add = (label, value) => { const entry = element('div'); entry.append(element('dt', '', diagnosticText(label)), element('dd', '', value)); list.append(entry); };
  add('requested', diagnosticFeed(data.requested_market_data_type));
  add('received', received.length ? received.map(diagnosticFeed).join(' / ') : diagnosticText('unknown'));
  for (const [key, label] of [['option_contracts_requested','contracts'], ['option_contracts_with_bid_ask','bidAsk'], ['option_contracts_with_last','last'], ['option_contracts_with_close','close'], ['option_contracts_with_open_interest','interest']]) {
    if (Number.isFinite(data[key]) && data[key] >= 0) add(label, new Intl.NumberFormat(state.language === 'zh' ? 'zh-CN' : 'en-US').format(data[key]));
  }
  for (const [key, label] of [['underlying_fields','fields'], ['observed_tick_types','ticks'], ['broker_codes','codes']]) {
    if (Array.isArray(data[key])) add(label, data[key].filter(value => typeof value === 'string' || Number.isFinite(value)).map(String).join(' / ') || diagnosticText('unknown'));
  }
  if (Number.isFinite(data.wait_seconds)) add('wait', String(Math.round(data.wait_seconds * 10) / 10));
  if (data.timestamp_basis === 'local_callback_arrival') add('timeBasis', diagnosticText('localCallback'));
  if (['market_callbacks_received','no_market_callbacks'].includes(data.interface_status)) add('interface', diagnosticText(data.interface_status));
  details.append(list); section.append(details); return section;
}
window.FinPilotDiagnostics = { render:renderMarketDiagnostics };
function showDiagnosticError(message, diagnostics) {
  showError(message);
  const rendered = renderMarketDiagnostics(diagnostics, { error:true });
  if (rendered) $('#error-banner').append(rendered);
}

function conversationLocked() { return state.busy || state.contextBusy || state.remoteBusy; }
function analysisModelName() { return state.models.find(model => model.id === state.engine)?.label || (state.engine === 'local' ? t('localModelLabel') : 'DeepSeek'); }
function analysisTime(value) {
  const stamp = new Date(value || '');
  return Number.isNaN(stamp.getTime()) ? t('analysisTimingUnknown') : new Intl.DateTimeFormat(state.language === 'zh' ? 'zh-CN' : 'en-US', {
    timeZone:'UTC', year:'numeric', month:'2-digit', day:'2-digit', hour:'2-digit', minute:'2-digit', second:'2-digit', hourCycle:'h23',
  }).format(stamp);
}
function analysisFeed(value) {
  if (value === 'historical') return state.language === 'zh' ? '历史数据复盘' : 'Historical review';
  return t(({ live:'analysisFeedLive', delayed:'analysisFeedDelayed', frozen:'analysisFeedFrozen', delayed_frozen:'analysisFeedDelayedFrozen', mixed:'analysisFeedMixed', unavailable:'analysisFeedUnavailable' })[value] || 'analysisUnknown');
}
function analysisScopes(context) { return Array.isArray(context?.scopes) ? context.scopes : []; }
function analysisIsStale(context) {
  if (context?.analysis_kind === 'historical_options') return false;
  const stamp = Date.parse(context?.captured_at || '');
  return Number.isFinite(stamp) && stamp <= Date.now() && Date.now() - stamp > 30000;
}
function analysisFreshnessUnconfirmed(context) {
  if (context?.analysis_kind === 'historical_options') return false;
  const captured = Date.parse(context.captured_at || '');
  return !Number.isFinite(captured) || captured > Date.now() || (context.stale && !analysisIsStale(context))
    || analysisScopes(context).some(scope => {
      const stamp = Date.parse(scope.received_at || '');
      return (scope.time_status && scope.time_status !== 'known') || !Number.isFinite(stamp) || stamp > Date.now();
    });
}
function addAnalysisMetadata(target, context) {
  if (context.analysis_kind === 'historical_options') {
    const zh = state.language === 'zh';
    const period = context.period || {};
    target.append(element('strong', 'analysis-history-period', `${zh ? '历史复盘区间' : 'Historical period'} · ${period.start || '—'} → ${period.end || '—'}`),
      element('p', 'analysis-source', `${zh ? '数据来源' : 'Data source'} · ${context.source_label || context.source || '—'}`),
      element('p', 'analysis-time', `${zh ? '本地保存时间（UTC）' : 'Locally saved at (UTC)'} · ${analysisTime(context.captured_at)}`),
      element('p', 'analysis-snapshot-note', context.notice || (zh ? '固定历史样本，不代表当前行情。' : 'A fixed historical sample, not current market data.')));
    const labels = analysisScopes(context).map(scope => [scope.symbol, scope.expiry].filter(Boolean).join(' · '));
    target.append(element('small', 'analysis-quality-note', labels.join(' / ')));
    return;
  }
  const scopes = element('ul', 'analysis-scope-list');
  for (const scope of analysisScopes(context)) {
    const item = element('li');
    item.append(element('strong', '', [scope.symbol, scope.expiry].filter(Boolean).join(' · ') || t('analysisScope')),
      element('span', 'analysis-feed', analysisFeed(scope.market_data_status)));
    if (analysisScopes(context).length > 1 || !context.captured_at) item.append(element('small', 'analysis-scope-time', `${t('analysisCaptured')} · ${analysisTime(scope.received_at)}`));
    scopes.append(item);
  }
  target.append(scopes, element('p', 'analysis-time', `${t('analysisCaptured')} · ${analysisTime(context.captured_at)}`),
    element('p', 'analysis-source', `${t('analysisSource')} · ${context.source === 'ibkr' ? 'IBKR' : context.source || t('analysisUnknown')}`));
  const notice = element('p', 'analysis-snapshot-note', t('analysisSnapshot'));
  if (context.captured_at) notice.dataset.capturedAt = context.captured_at;
  if (analysisIsStale(context)) { notice.append(document.createTextNode(' ' + t('analysisStale'))); notice.dataset.stale = 'true'; }
  if (analysisFreshnessUnconfirmed(context)) notice.append(document.createTextNode(' ' + t('analysisFreshnessUnknown')));
  target.append(notice, element('small', 'analysis-quality-note', t('analysisNoGuarantee')));
  if (context.partial_failures?.length) target.append(element('p', 'analysis-partial', t('analysisPartial')));
}
async function viewSavedAnalysis(id) {
  if (!id || conversationLocked()) return;
  const sessionSequence = state.sessionSequence;
  setContextBusy(true);
  try {
    const report = await api(`/api/options/analyses/${encodeURIComponent(id)}`, { timeout:15000 });
    if (sessionSequence === state.sessionSequence && report.analysis_id === id) {
      if (report.analysis_kind === 'historical_options') window.FinPilotHistory?.showSavedReport(report);
      else window.FinPilotOptions?.showSavedReport(report);
    }
  } catch { showError(t('analysisMissing')); }
  finally { setContextBusy(false); }
}
function analysisViewButton(id) {
  const view = element('button', 'analysis-text-button', t('analysisView')); view.type = 'button';
  view.addEventListener('click', () => viewSavedAnalysis(id));
  view.disabled = conversationLocked();
  return view;
}
function syncAnalysisHistory(history, current = state.analysisContext) {
  if (Array.isArray(history)) {
    const seen = new Set();
    state.analysisHistory = history.filter(item => item && typeof item.analysis_id === 'string' && !seen.has(item.analysis_id) && seen.add(item.analysis_id));
  }
  if (!current?.analysis_id) return;
  const index = state.analysisHistory.findIndex(item => item.analysis_id === current.analysis_id);
  if (index < 0) state.analysisHistory.unshift({ ...current });
  else state.analysisHistory[index] = { ...state.analysisHistory[index], ...current };
}
function renderAnalysisHistory() {
  const history = element('details', 'analysis-history');
  history.append(element('summary', '', `${t('analysisHistory')} (${state.analysisHistory.length})`),
    element('p', 'analysis-history-hint', t('analysisHistoryHint')));
  const entries = element('ol', 'analysis-history-list');
  for (const item of state.analysisHistory) {
    const entry = element('li', 'analysis-history-entry'); entry.dataset.analysisId = item.analysis_id;
    const current = state.analysisContext?.analysis_id === item.analysis_id;
    const heading = element('div', 'analysis-history-heading');
    heading.append(element('strong', '', analysisScopes(item).map(scope => [scope.symbol, scope.expiry].filter(Boolean).join(' · ')).join(' / ') || t('analysisScope')),
      element('span', 'analysis-history-tag', t(current ? 'analysisHistoryCurrent' : 'analysisHistoryPast')));
    entry.dataset.current = String(current);
    const historyTimeLabel = item.analysis_kind === 'historical_options' ? (state.language === 'zh' ? '本地保存时间（UTC）' : 'Locally saved at (UTC)') : t('analysisCaptured');
    if (item.analysis_kind === 'historical_options' && item.period) entry.append(element('p', 'analysis-history-period', `${item.period.start || '—'} → ${item.period.end || '—'}`));
    entry.append(heading, element('p', 'analysis-time', `${historyTimeLabel} · ${analysisTime(item.captured_at)}`),
      element('small', 'analysis-history-feed', `${item.source === 'ibkr' ? 'IBKR' : item.source || t('analysisUnknown')} · ${[...new Set(analysisScopes(item).map(scope => analysisFeed(scope.market_data_status)))].join(' / ')}`));
    const view = analysisViewButton(item.analysis_id); view.classList.add('analysis-history-view'); entry.append(view);
    entries.append(entry);
  }
  history.append(entries); return history;
}
function renderAnalysisContext() {
  const card = $('#analysis-context-card');
  const historyOpen = $('.analysis-history', card)?.open || false;
  card.replaceChildren(); card.hidden = !state.analysisContext;
  const status = $('#analysis-context-status');
  status.textContent = state.refreshing ? t('analysisRefreshing') : state.contextBusy ? t('analysisUpdating') : '';
  if (!state.analysisContext) return;
  const context = state.analysisContext;
  card.dataset.analysisId = context.analysis_id || '';
  card.append(element('strong', 'analysis-context-title', t('analysisAttached')));
  addAnalysisMetadata(card, context);
  card.append(element('p', 'analysis-next-send', t('analysisForNext').replace('{model}', analysisModelName())));
  const refresh = element('div', 'analysis-refresh-section');
  const refreshButton = element('button', 'primary-button analysis-refresh-button', t('analysisRefresh')); refreshButton.type = 'button';
  refreshButton.disabled = conversationLocked() || !state.sessionId;
  refreshButton.addEventListener('click', refreshAnalysis);
  refresh.append(refreshButton, element('p', 'analysis-refresh-disclosure', t('analysisRefreshDisclosure').replace('{model}', analysisModelName())));
  if (context.analysis_kind !== 'historical_options') card.append(refresh);
  else card.append(element('p', 'analysis-refresh-disclosure', state.language === 'zh' ? '历史复盘保持固定；导入另一批历史记录可建立新版本。这里不会请求实时报价。' : 'This historical review stays fixed. Import another dataset to create a new version; no live quote request is made here.'));
  const actions = element('div', 'analysis-context-actions');
  const remove = element('button', 'analysis-text-button analysis-remove', t('analysisRemove')); remove.type = 'button';
  remove.disabled = conversationLocked(); remove.addEventListener('click', detachAnalysis);
  actions.append(analysisViewButton(context.analysis_id), remove); card.append(actions);
  if (state.analysisHistory.length) {
    const history = renderAnalysisHistory(); history.open = historyOpen; card.append(history);
  }
}
function setContextBusy(busy) {
  state.contextBusy = busy; setBusy(state.busy); renderAnalysisContext();
}
function saveDraft() { state.drafts.set(state.sessionId || '__new__', $('#message-input').value); }
function restoreDraft() {
  const input = $('#message-input'); input.value = state.drafts.get(state.sessionId || '__new__') || '';
  input.dispatchEvent(new Event('input'));
}
async function detachAnalysis() {
  if (conversationLocked()) return;
  const id = state.sessionId;
  setContextBusy(true); showError('');
  try {
    if (id) await api(`/api/sessions/${encodeURIComponent(id)}/analysis`, { method:'PUT', body:JSON.stringify({ analysis_id:null }) });
    if (state.sessionId === id) state.analysisContext = null;
  } catch (error) { showError(t('errorPrefix') + error.message); }
  finally { setContextBusy(false); }
}
async function refreshAnalysis() {
  if (conversationLocked() || !state.sessionId || !state.analysisContext?.analysis_id) return;
  const sessionId = state.sessionId;
  const expectedId = state.analysisContext.analysis_id;
  const engine = state.engine;
  const language = state.language;
  cancelSpeech();
  if (state.recording) state.recognition?.stop();
  state.refreshing = true; showError(''); setBusy(true); renderAnalysisContext();
  $('#analysis-context-status').scrollIntoView({ block:'nearest', behavior:scrollBehavior() });
  try {
    const result = await api(`/api/sessions/${encodeURIComponent(sessionId)}/analysis/refresh`, {
      method:'POST', body:JSON.stringify({ analysis_id:expectedId, language, engine }), timeout:300000,
    });
    if (result.session_id !== sessionId || !result.active_analysis?.analysis_id || result.active_analysis.analysis_id === expectedId
      || result.analysis_context?.analysis_id !== result.active_analysis.analysis_id || typeof result.answer !== 'string' || typeof result.user_message !== 'string') throw new Error(t('analysisRefreshIncomplete'));
    state.analysisContext = result.active_analysis;
    syncAnalysisHistory(result.analysis_history);
    state.messages.push({ role:'user', content:result.user_message }, { role:'assistant', content:result.answer,
      sources:result.sources || [], mode:result.mode, warning:result.warning, analysis_context:result.analysis_context || null });
    renderMessages({ animateLast:true }); renderAnalysisContext();
    loadSessions().catch(() => {});
    $('#chat-messages').lastElementChild?.scrollIntoView({ block:'start', behavior:scrollBehavior() });
  } catch (error) {
    showDiagnosticError(`${t('analysisRefreshFailed')} ${error.message}`, error.detail?.diagnostics); setAvatarState('error');
    $('#error-banner').scrollIntoView({ block:'nearest', behavior:scrollBehavior() });
  } finally {
    state.refreshing = false; setBusy(false); renderAnalysisContext();
  }
}
async function attachOptionAnalysisReport(report, prompt) {
  if (conversationLocked() || !report?.analysis_id) return false;
  setContextBusy(true); showError('');
  try {
    if (state.analysisContext?.analysis_id !== report.analysis_id || !state.sessionId) {
      const reports = Array.isArray(report.reports) ? report.reports : [report];
      const symbols = [...new Set(reports.map(item => item.snapshot?.symbol || item.symbol).filter(Boolean))].join(' / ');
      const session = await api('/api/sessions', { method:'POST', body:JSON.stringify({ title:`${t('analysisSession')} · ${symbols}` }) });
      const linked = await api(`/api/sessions/${encodeURIComponent(session.id)}/analysis`, { method:'PUT', body:JSON.stringify({ analysis_id:report.analysis_id }) });
      if (!linked.active_analysis || linked.active_analysis_id !== report.analysis_id) throw new Error(t('analysisAttachFailed'));
      saveDraft(); state.sessionSequence += 1;
      state.sessionId = session.id; state.messages = []; state.lastAnswer = null;
      state.analysisContext = linked.active_analysis;
      state.analysisHistory = []; syncAnalysisHistory(undefined, linked.active_analysis);
      localStorage.setItem('finpilot-session', session.id);
      cancelSpeech(); settleAvatar(); renderMessages();
      await loadSessions().catch(() => {});
    }
    $('#options-dialog').close(); closeSidebar();
    const input = $('#message-input'); input.value = prompt || ''; input.dispatchEvent(new Event('input'));
    renderAnalysisContext(); input.scrollIntoView({ block:'center', behavior:scrollBehavior() }); input.focus({ preventScroll:true });
    animateElement($('#analysis-context-card'), [{ opacity:0, transform:'translateY(8px)' }, { opacity:1, transform:'translateY(0)' }]);
    return true;
  } catch (error) { showError(t('errorPrefix') + error.message); toast(t('analysisAttachFailed')); return false; }
  finally { setContextBusy(false); }
}
window.FinPilotAnalysis = { attach:attachOptionAnalysisReport, isBusy:conversationLocked, renderComparison:renderRefreshComparison };

function renderAnalysisReply(context) {
  if (window.FinPilotMessages) return window.FinPilotMessages.renderAnalysisParts(context, {language:state.language,onOpenAnalysis:viewSavedAnalysis,renderMetadata:addAnalysisMetadata});
  const wrapper = element('section', 'message-analysis-context'); wrapper.dataset.analysisId = context.analysis_id || '';
  wrapper.append(element('h3', '', context.analysis_kind === 'historical_options' ? (state.language === 'zh' ? '本条回答依据的历史复盘' : 'Historical review used for this answer') : t('analysisReply'))); addAnalysisMetadata(wrapper, context);
  if (context.retrieval?.hits?.length) {
    const zh = state.language === 'zh';
    const retrieval = element('details', 'message-analysis-evidence expert-retrieval');
    retrieval.append(element('summary', '', zh ? '专家知识是怎样找到的' : 'How expert knowledge was retrieved'),
      element('p', '', zh ? '词项 BM25 与中文字符匹配分别排序，再用 RRF 合并。必要概念可按问题和数据约束补充；补充项没有伪造的检索排名。排名表示相关性，不是结论正确率。' : 'BM25 term and Chinese character rankings are fused with RRF. Required concepts can be added from reviewed support facets without invented ranks. Ranks indicate relevance, not answer accuracy.'));
    const hits = element('ol', 'expert-retrieval-hits');
    for (const hit of context.retrieval.hits.slice(0, 6)) {
      const ranking = hit.retrieval || hit;
      const row = element('li');
      row.append(element('strong', '', hit.title || hit.id),
        element('p', '', `BM25: ${ranking.bm25_rank ?? '—'} · ${zh ? '字符排名' : 'Character rank'}: ${ranking.char_rank ?? '—'}`));
      if (['required_facet', 'query_facet', 'context_facet'].includes(ranking.selection_reason) || ranking.method === 'curated_support_facet') row.append(element('small', '', zh ? '为问题或数据约束选用的专业依据' : 'Reviewed support selected for question or data constraints'));
      hits.append(row);
    }
    retrieval.append(hits); wrapper.append(retrieval);
  }
  if (context.refresh_comparison) wrapper.append(renderRefreshComparison(context.refresh_comparison));
  const catalogue = element('details', 'message-analysis-evidence');
  const records = Array.isArray(context.evidence) ? context.evidence : [];
  catalogue.append(element('summary', '', `${t('analysisEvidence')} (${records.length})`));
  const list = element('div', 'analysis-evidence-list');
  const references = new Map();
  for (const record of records) {
    if (!record || typeof record.id !== 'string') continue;
    const item = element('article', 'analysis-evidence-card'); item.tabIndex = -1; item.dataset.evidenceId = record.id;
    const value = formatAnalysisEvidence(record);
    item.append(element('strong', '', record.label || record.id), element('span', 'analysis-evidence-id', record.id),
      element('p', 'analysis-evidence-value', `${t('analysisValue')} · ${value}`),
      element('small', '', [record.symbol, record.expiry, record.scope === 'comparison' ? t('analysisScopeComparison') : null].filter(Boolean).join(' · ')));
    if (record.description) item.append(element('p', '', record.description));
    if (Object.hasOwn(record, 'before') || Object.hasOwn(record, 'after')) {
      item.append(changeValues(record), element('p', 'analysis-change-reason', record.status === 'comparable' ? t('analysisComparable') : `${t('analysisNoComparison')} · ${comparisonReason(record.reason, record.reason_text)}`));
    }
    if (record.received_at) item.append(element('small', 'analysis-evidence-time', `${t('analysisCaptured')} · ${analysisTime(record.received_at)} · ${analysisFeed(record.market_data_status)}`));
    list.append(item); references.set(record.id, { analysisTarget:item, catalogue, title:record.label || record.id, number:references.size + 1 });
  }
  catalogue.append(list); wrapper.append(catalogue);
  wrapper.append(analysisViewButton(context.analysis_id));
  return { wrapper, references };
}
function comparisonReason(code, explanation) {
  if (typeof explanation === 'string' && explanation.trim()) return explanation;
  if (code === 'historical_bar_coverage_unverified') return state.language === 'zh' ? '完整交易时段覆盖未核验' : 'Complete trading-session coverage is unverified';
  if (code === 'oi_asof_not_advanced') return state.language === 'zh' ? '未平仓量统计日期没有推进' : 'The open-interest as-of date did not advance';
  if (code === 'missing_value_or_oi_asof') return state.language === 'zh' ? '数值或未平仓统计日期缺失' : 'A value or open-interest as-of date is missing';
  if (code === 'insufficient_days_or_common_sample') return state.language === 'zh' ? '历史日期或固定共同样本不足' : 'Insufficient historical dates or fixed common contracts';
  if (typeof code !== 'string' || !code) return t('analysisReasonOther');
  if (/feed|market_data|mode/.test(code)) return t('analysisReasonFeed');
  if (/missing|unavailable|absent|failed|zero_denominator/.test(code)) return t('analysisReasonMissing');
  if (/scope|strike|pair|mismatch|basis|different/.test(code)) return t('analysisReasonScope');
  if (/time|age|stale|receipt|window|future/.test(code)) return t('analysisReasonTime');
  if (/quality|spread|coverage|insufficient/.test(code)) return t('analysisReasonQuality');
  return t('analysisReasonOther');
}
function changeValues(metric) {
  const values = element('dl', 'analysis-change-values');
  for (const [key, label] of [['before','analysisBefore'], ['after','analysisAfter'], ['delta','analysisChange']]) {
    const field = element('div');
    const comparable = metric.status === 'comparable';
    const value = key === 'delta' && !comparable ? t('analysisNoComparison')
      : formatAnalysisEvidence({ value:metric[key], unit:key === 'delta' ? metric.delta_unit : metric.unit });
    field.append(element('dt', '', t(label)), element('dd', '', key === 'delta' && comparable && Number.isFinite(metric.delta) && metric.delta > 0 ? '+' + value : value)); values.append(field);
  }
  return values;
}
function renderRefreshComparison(comparison) {
  const section = element('section', 'analysis-refresh-comparison');
  section.dataset.status = comparison.status || 'incomparable';
  section.append(element('h4', '', t('analysisChanges')),
    element('p', 'analysis-comparison-status', t(comparison.status === 'comparable' ? 'analysisComparable' : comparison.status === 'partial' ? 'analysisPartialComparison' : 'analysisIncomparable')));
  const times = element('dl', 'analysis-comparison-times');
  for (const [label, value] of [['analysisBefore', comparison.previous_captured_at], ['analysisAfter', comparison.current_captured_at]]) {
    const item = element('div'); item.append(element('dt', '', `${t(label)} · ${t('analysisCaptured')}`), element('dd', '', analysisTime(value))); times.append(item);
  }
  section.append(times);
  if (comparison.summary) section.append(element('p', 'analysis-comparison-summary', comparison.summary));
  const scopes = Array.isArray(comparison.scopes) ? comparison.scopes : [];
  for (const scope of scopes) {
    const group = element('section', 'analysis-change-scope'); group.dataset.scopeId = scope.id || '';
    group.append(element('h5', '', [scope.symbol, scope.expiry].filter(Boolean).join(' · ') || t('analysisScope')),
      element('p', 'analysis-change-feeds', `${t('analysisBefore')} · ${analysisFeed(scope.before_feed)} → ${t('analysisAfter')} · ${analysisFeed(scope.after_feed)}`));
    if (scopes.length > 1) group.append(element('small', 'analysis-change-scope-times', `${t('analysisBefore')} · ${analysisTime(scope.previous_received_at)} / ${t('analysisAfter')} · ${analysisTime(scope.received_at)} (UTC)`));
    if (scope.status === 'added') group.append(element('p', 'analysis-change-reason', t('analysisChangeScopeAdded')));
    else if (['missing','failed'].includes(scope.status)) group.append(element('p', 'analysis-change-reason', t('analysisChangeScopeMissing')));
    const metrics = element('div', 'analysis-change-metrics');
    for (const metric of Array.isArray(scope.metrics) ? scope.metrics : []) {
      const card = element('article', 'analysis-change-metric'); card.dataset.changeId = `${scope.id || ''}.${metric.id || ''}`;
      card.dataset.status = metric.status || 'incomparable';
      card.append(element('strong', '', metric.label || t('analysisValue')), changeValues(metric));
      if (metric.status !== 'comparable') card.append(element('p', 'analysis-change-reason', `${t('analysisNoComparison')} · ${comparisonReason(metric.reason, metric.reason_text)}`));
      metrics.append(card);
    }
    if (metrics.childElementCount) group.append(metrics);
    else group.append(element('p', 'analysis-change-reason', t('analysisChangeNoMetrics')));
    if (Array.isArray(scope.reason_messages) && scope.reason_messages.length) group.append(element('p', 'analysis-change-reason', scope.reason_messages.filter(value => typeof value === 'string').join(' ')));
    else if (Array.isArray(scope.reasons) && scope.reasons.length) group.append(element('p', 'analysis-change-reason', [...new Set(scope.reasons.map(code => comparisonReason(code)))].join(' ')));
    section.append(group);
  }
  if (Array.isArray(comparison.failures) && comparison.failures.length) section.append(element('p', 'analysis-partial', t('analysisPartial')));
  section.append(element('p', 'analysis-comparison-notice', t('analysisRefreshNotice')));
  return section;
}
function formatAnalysisEvidence(record) {
  if (record.value === null || record.value === undefined) return t('analysisNotProvided');
  if (typeof record.value !== 'number' || !Number.isFinite(record.value)) return typeof record.value === 'object' ? JSON.stringify(record.value) : String(record.value);
  const unit = record.unit;
  const value = new Intl.NumberFormat(state.language === 'zh' ? 'zh-CN' : 'en-US', { maximumFractionDigits:2 }).format(unit === 'fraction' ? record.value * 100 : record.value);
  if (unit === 'fraction' || unit === 'percent') return value + '%';
  if (unit === 'percentage_points') return `${value} ${t('analysisPoints')}`;
  if (unit === 'volatility_points') return `${value} ${t('analysisVolatilityPoints')}`;
  if (unit === 'contracts') return `${value} ${t('analysisContracts')}`;
  return value + (unit && !['ratio','number','count'].includes(unit) ? ' ' + unit : '');
}

function applyTheme() {
  document.documentElement.dataset.theme = state.theme;
  const button = $('#theme-toggle');
  button.textContent = state.theme === 'dark' ? '☀' : '☾';
  button.title = t(state.theme === 'dark' ? 'lightTheme' : 'darkTheme');
  button.setAttribute('aria-label', button.title);
  button.setAttribute('aria-pressed', String(state.theme === 'dark'));
  document.querySelector('meta[name="theme-color"]').content = state.theme === 'dark' ? '#111319' : '#FAFAFA';
}

function setAvatarState(next) {
  state.avatarState = next;
  document.body.dataset.assistantState = next;
  $('#copilot-panel').dataset.avatarState = next;
  const key = `avatar${next.charAt(0).toUpperCase()}${next.slice(1)}`;
  $('#avatar-status').textContent = t(key);
  $('.avatar-status-pill').dataset.state = next;
  state.avatar?.setState(next);
  document.dispatchEvent(new CustomEvent('finpilot-assistant-state', { detail: { state: next } }));
}

function settleAvatar() {
  const operations = [...companionLocalActivities.values(), ...(isCurrentSharedSession() ? state.companionActivities : [])];
  const voice = operations.find(item=>item.kind==='speech' && item.phase==='listening') ? 'listening' : operations.find(item=>item.kind==='speech' && item.phase==='speaking') ? 'speaking' : null;
  setAvatarState(state.recording ? 'listening' : state.speechStarted ? 'speaking' : voice || (state.busy || state.remoteBusy || operations.length ? 'thinking' : 'idle'));
}

function syncAssistantPanel() {
  const panel = $('#copilot-panel');
  panel.classList.toggle('is-expanded', state.panelExpanded);
  panel.classList.toggle('is-collapsed', !state.panelExpanded);
  $('#avatar-collapse').textContent = state.panelExpanded ? '−' : '+';
  $('#avatar-collapse').setAttribute('aria-expanded', String(state.panelExpanded));
  $('#avatar-collapse').setAttribute('aria-label', t(state.panelExpanded ? 'collapseAssistant' : 'expandAssistant'));
}

function setAvatarMode(mode) {
  state.avatarMode = state.avatarCharacter === 'whale' ? '2d' : mode;
  if (state.avatarCharacter === 'robot') localStorage.setItem('finpilot-avatar-mode', state.avatarMode);
  $('#avatar-2d').setAttribute('aria-pressed', String(state.avatarMode === '2d'));
  $('#avatar-3d').setAttribute('aria-pressed', String(state.avatarMode === '3d'));
  $('.avatar-mode-control').hidden = state.avatarCharacter === 'whale';
  $('#avatar-character').value = state.avatarCharacter;
  state.avatar?.setMode?.(state.avatarMode);
  renderAvatarStatus();
}

function setAvatarCharacter(character) {
  if (!['whale','robot'].includes(character)) return;
  state.avatar?.destroy(); state.avatar = null; state.avatarRenderStatus = null;
  state.avatarCharacter = character; localStorage.setItem('finpilot-avatar-character',character);
  state.avatarMode = character === 'whale' ? '2d' : localStorage.getItem('finpilot-avatar-mode') === '2d' ? '2d' : '3d';
  $('#avatar-stage').replaceChildren(); setAvatarMode(state.avatarMode); mountAvatar();
}

function renderAvatarStatus() {
  const status = state.avatarRenderStatus || state.avatar?.getStatus();
  if (!status) return;
  if (state.avatarCharacter === 'whale') {
    $('#avatar-renderer').textContent = status.renderer === 'canvas2d' ? '2D / SPRITE' : status.renderer === 'static-image' ? '2D / STATIC' : '2D / UNAVAILABLE';
    $('#avatar-explanation').textContent = state.language === 'zh' ? '同款鲸鱼娘序列动画；动作表示操作状态，不表示市场判断。' : 'Whale-maid sprite animation; motion represents activity, not market judgment.';
  } else {
    $('#avatar-renderer').textContent = status.renderer === 'webgl2' ? '3D / WEBGL' : '2D / SVG';
    $('#avatar-explanation').textContent = status.fallbackReason && state.avatarMode === '3d' ? t('avatarFallback') : t('avatarExplanation');
  }
}

function mountAvatar() {
  const renderer = state.avatarCharacter === 'whale' ? window.FinPilotCompanion : window.FinPilotAvatar;
  if (state.avatar || !renderer) return;
  try {
    state.avatar = renderer.mount($('#avatar-stage'), { language: state.language, mode: state.avatarMode, reducedMotion:motionStopped() });
    // Expose the documented renderer status for diagnostics and acceptance checks.
    window.finPilotAvatarInstance = state.avatar;
    state.avatar.setReducedMotion(motionStopped());
    state.avatar.setState(state.avatarState);
  } catch {
    $('#avatar-stage').replaceChildren(element('p', 'avatar-load-error', state.language === 'zh' ? '交互形象暂不可用，文字功能仍可使用。' : 'The companion is unavailable. Text features are still available.'));
  }
}

function motionStopped() { return state.reducedMotion || state.osReducedMotion; }
function scrollBehavior() { return motionStopped() ? 'instant' : 'smooth'; }

// Short, interruptible feedback. Content is always present without animation.
function animateElement(target, keyframes, options = {}) {
  if (!target || motionStopped() || document.hidden || !target.animate) return null;
  const animation = target.animate(keyframes, { duration:280, easing:'cubic-bezier(.22,1,.36,1)', ...options });
  activeAnimations.add(animation);
  const cleanup = () => activeAnimations.delete(animation);
  animation.onfinish = cleanup; animation.oncancel = cleanup;
  return animation;
}

function applyMotionPreference() {
  const reduced = motionStopped();
  document.documentElement.classList.toggle('reduced-motion', reduced);
  document.documentElement.dataset.motion = reduced ? 'reduced' : 'full';
  $('#reduce-motion').checked = reduced;
  $('#reduce-motion').disabled = state.osReducedMotion;
  const toggle = $('#workspace-motion-toggle');
  if (toggle) {
    const label = t(state.osReducedMotion ? 'motionSystem' : reduced ? 'motionResume' : 'motionToggle');
    (toggle.querySelector('span') || toggle).textContent = label;
    toggle.setAttribute('aria-pressed', String(reduced));
    toggle.setAttribute('aria-label', label); toggle.disabled = state.osReducedMotion;
  }
  if (reduced) for (const animation of [...activeAnimations]) animation.cancel();
  state.avatar?.setReducedMotion(reduced);
}

function renderModelSwitchStatus() {
  const status = $('#model-switch-status');
  if (status) status.textContent = state.modelChanged ? t('modelSwitched').replace('{model}', $('#model-name').textContent) : '';
}

function changeModel(engine) {
  if (conversationLocked() || !state.models.some(model => model.id === engine && model.available)) { renderModelOptions(); return; }
  if (state.engine === engine) return;
  state.engine = engine; state.modelChanged = true;
  localStorage.setItem('finpilot-engine', engine);
  renderModelOptions(); setHealthBadge(); renderModelSwitchStatus(); renderAnalysisContext();
  animateElement($('.model-detail'), [{ opacity:.6, transform:'translateY(5px)' }, { opacity:1, transform:'translateY(0)' }]);
  animateElement($('.composer-context'), [{ backgroundColor:'rgba(219,168,90,.18)' }, { backgroundColor:'rgba(219,168,90,0)' }], { duration:450 });
  shareCompanionPreferences();
}

function renderModelOptions() {
  const select = $('#model-select'); select.replaceChildren();
  for (const model of state.models) {
    const label = model.id === 'local' ? t(model.available ? 'localModelLabel' : 'localNotReady')
      : model.id === 'deepseek' ? (model.available ? 'DeepSeek' : t('cloudNotReady')) : model.label || model.id;
    const option = element('option', '', label);
    option.value = model.id; option.disabled = !model.available;
    if (!model.available && !['local','deepseek'].includes(model.id)) option.textContent += ` · ${t('modelUnavailable')}`;
    select.append(option);
  }
  select.value = state.engine;
  const selected = state.models.find(model => model.id === state.engine);
  $('#model-name').textContent = selected?.id === 'local' ? t(selected.available ? 'localModelLabel' : 'localNotReady') : 'DeepSeek';
  $('#model-description').textContent = selected?.id === 'local'
    ? t(selected.available ? 'localDescription' : 'localUnavailableDescription')
    : selected?.id === 'deepseek' ? t(selected.available ? 'deepseekDescription' : 'cloudUnavailableDescription')
    : selected?.description || t('modelDefaultDescription');
}

async function loadModels() {
  try {
    const data = await api('/api/models', { timeout: 10000 });
    state.models = data.models || [];
    if (!state.models.some(model => model.id === state.engine && model.available)) state.engine = data.default || 'deepseek';
  } catch {
    state.engine = 'deepseek';
    state.models = [{ id: 'deepseek', label: 'DeepSeek', available: true }];
  }
  renderModelOptions(); setHealthBadge();
}

function applyLanguage() {
  document.documentElement.lang = state.language === 'zh' ? 'zh-CN' : 'en';
  document.title = state.language === 'zh' ? 'FinPilot · 金融知识工作台' : 'FinPilot · Financial Knowledge Workspace';
  $$('[data-i18n]').forEach(el => { el.textContent = t(el.dataset.i18n); });
  ['heroTitle','heroDescription','sidebarNote'].forEach(key => { $(`[data-i18n="${key}"]`).style.whiteSpace = 'pre-line'; });
  $('#message-input').placeholder = t('inputPlaceholder');
  $('#language-toggle').textContent = state.language === 'zh' ? 'EN ⌄' : '中文 ⌄';
  $('#language-toggle').setAttribute('aria-label', state.language === 'zh' ? 'Switch to English' : '切换为中文');
  $('#send-button').setAttribute('aria-label', t('send'));
  $('#mobile-menu').setAttribute('aria-label', t('openNavigation'));
  $('#sidebar-new').setAttribute('aria-label', t('newSession'));
  $('#sidebar-new').title = t('newSession');
  $$('.close-dialog').forEach(button => button.setAttribute('aria-label', t('close')));
  $('#model-select').setAttribute('aria-label', t('modelLabel'));
  applyTheme(); syncAssistantPanel(); renderModelOptions();
  applyMotionPreference(); renderModelSwitchStatus();
  state.avatar?.setLanguage(state.language); setAvatarState(state.avatarState); renderAvatarStatus(); updateSpeechControls();
  setHealthBadge(); renderSessions(); renderMessages(); renderAnalysisContext(); renderCalculatorFields(); updateVoiceUI();
  renderCompanionConnection();
}

function setHealthBadge() {
  const mode = state.health?.mode;
  const isOnline = mode === 'deepseek' || mode === 'online';
  $('#engine-badge').classList.toggle('offline', Boolean(state.health) && !isOnline);
  $('#engine-label').textContent = state.health ? (state.health.status === 'unavailable' ? t('connectionError') : state.engine === 'local' && state.models.some(model => model.id === 'local' && model.available) ? t('localConfigured') : isOnline ? t('online') : t('offline')) : t('connecting');
  $('#engine-badge').title = state.health ? `${state.health.model || 'DeepSeek'} · ${state.health.knowledge_documents ?? 0} ${state.language === 'zh' ? '篇知识文档' : 'knowledge documents'}` : '';
}

async function loadHealth() {
  try { state.health = await api('/api/health', { timeout: 10000 }); }
  catch { state.health = { status: 'unavailable', mode: 'offline' }; }
  setHealthBadge();
}

async function loadSessions() {
  const data = await api('/api/sessions', { timeout: 10000 });
  state.sessions = data.sessions || [];
  renderSessions();
}

function renderSessions() {
  const list = $('#session-list'); list.replaceChildren();
  if (!state.sessions.length) { list.append(element('p', 'session-empty', t('noSessions'))); return; }
  state.sessions.forEach(session => {
    const row = element('div', `session-row${session.id === state.sessionId ? ' active' : ''}`);
    const open = element('button', 'session-open', session.title || t('unnamedSession')); open.type = 'button'; open.title = session.title || t('unnamedSession');
    open.addEventListener('click', () => selectSession(session.id));
    const remove = element('button', 'session-delete', '×'); remove.type = 'button'; remove.title = t('deleteSession'); remove.setAttribute('aria-label', `${t('deleteSession')}: ${session.title || t('unnamedSession')}`);
    remove.addEventListener('click', async () => {
      if (conversationLocked()) return toast(t('sessionBusy'));
      if (!confirm(t('deleteConfirm'))) return;
      try {
        await api(`/api/sessions/${encodeURIComponent(session.id)}`, { method: 'DELETE' });
        if (state.sessionId === session.id) resetConversation();
        await loadSessions(); toast(t('sessionRemoved'));
      } catch (error) { showError(t('errorPrefix') + error.message); }
    });
    open.disabled = conversationLocked(); remove.disabled = conversationLocked();
    row.append(open, remove); list.append(row);
  });
}

function setSidebar(open, restoreFocus = true) {
  const mobile = matchMedia('(max-width: 760px)').matches;
  const wasOpen = state.menuOpen;
  const sidebarHadFocus = $('#sidebar').contains(document.activeElement);
  state.menuOpen = mobile && open;
  $('#sidebar').classList.toggle('open', state.menuOpen);
  $('#sidebar-shade').classList.toggle('visible', state.menuOpen);
  $('#mobile-menu').setAttribute('aria-expanded', String(state.menuOpen));
  $('#sidebar').inert = mobile && !state.menuOpen;
  $('.workspace-main').inert = state.menuOpen;
  document.body.classList.toggle('navigation-open', state.menuOpen);
  if (state.menuOpen && !wasOpen) $('#nav-chat').focus({ preventScroll:true });
  else if (!state.menuOpen && mobile && ((wasOpen && restoreFocus) || sidebarHadFocus)) $('#mobile-menu').focus({ preventScroll:true });
}
function closeSidebar() { setSidebar(false); }

function openToolDialog(dialog) {
  if (dialog.open) return;
  dialog.showModal();
  animateElement(dialog, [{ opacity:0, transform:'translateY(12px) scale(.985)' }, { opacity:1, transform:'translateY(0) scale(1)' }]);
}

async function selectSession(id) {
  if (conversationLocked()) return toast(t('sessionBusy'));
  const sequence = ++state.sessionSequence;
  setContextBusy(true);
  try {
    const session = await api(`/api/sessions/${encodeURIComponent(id)}`);
    if (sequence !== state.sessionSequence) return;
    saveDraft();
    state.sessionId = session.id; state.messages = session.messages || [];
    state.analysisContext = session.active_analysis || null; state.analysisHistory = []; syncAnalysisHistory(session.analysis_history); restoreDraft();
    cancelSpeech(); settleAvatar();
    showError(''); renderMessages(); renderSessions(); closeSidebar();
    localStorage.setItem('finpilot-session', session.id);
    refreshCompanionActivity(); renderCompanionConnection();
  } catch (error) { showError(t('errorPrefix') + error.message); }
  finally { setContextBusy(false); }
}

function resetConversation() {
  saveDraft(); state.sessionSequence += 1;
  state.sessionId = null; state.messages = []; state.lastAnswer = null; state.analysisContext = null; state.analysisHistory = [];
  state.drafts.delete('__new__'); renderAnalysisContext();
  localStorage.removeItem('finpilot-session');
  $('#message-input').value = ''; $('#message-input').style.height = '';
  showError(''); renderMessages(); renderSessions(); closeSidebar();
  cancelSpeech(); settleAvatar();
  refreshCompanionActivity(); renderCompanionConnection();
  window.scrollTo({ top: 0, behavior: scrollBehavior() }); $('#message-input').focus();
}

function newConversation() { if (conversationLocked()) return toast(t('sessionBusy')); resetConversation(); }

function appendInline(parent, text, sources, depth = 0) {
  // Parse a deliberately limited Markdown subset using DOM nodes only.
  // Raw HTML, arbitrary Markdown links and images always remain literal text.
  const pattern = /\*\*([^\n]+?)\*\*|`([^`\n]+)`|\[([A-Za-z][A-Za-z0-9_.-]*)\]|\*([^*\n]+)\*/g;
  let position = 0;
  for (const match of text.matchAll(pattern)) {
    parent.append(document.createTextNode(text.slice(position, match.index)));
    if (match[1] !== undefined && depth < 2) {
      const strong = element('strong'); appendInline(strong, match[1], sources, depth + 1); parent.append(strong);
    } else if (match[2] !== undefined) parent.append(element('code', '', match[2]));
    else if (match[3] !== undefined && sources.get(match[3])?.analysisTarget) {
      const source = sources.get(match[3]);
      const reference = element('button', 'inline-citation analysis-inline-citation', `${t('analysisEvidenceShort')} ${source.number}`); reference.type = 'button'; reference.dataset.evidenceId = match[3];
      reference.title = source.title; reference.setAttribute('aria-label', `${t('analysisEvidence')} · ${source.title}`);
      reference.addEventListener('click', () => { source.catalogue.open = true; source.analysisTarget.scrollIntoView({ block:'center', behavior:scrollBehavior() }); source.analysisTarget.focus({ preventScroll:true }); });
      parent.append(reference);
    } else if (match[3] !== undefined && sources.has(match[3]) && safeURL(sources.get(match[3]).url)) {
      const source = sources.get(match[3]);
      const citationLabel = source.id?.startsWith('expert.') ? `${state.language === 'zh' ? '专家来源' : 'Expert source'} ${source.expertNumber}` : `[${match[3]}]`;
      const link = element('a', 'inline-citation', citationLabel);
      link.href = safeURL(source.url); link.target = '_blank'; link.rel = 'noopener noreferrer';
      link.title = source.title || source.id; link.setAttribute('aria-label', t('sourceCitation') + (source.title || source.id));
      link.dataset.sourceId = match[3]; parent.append(link);
    } else if (match[4] !== undefined) parent.append(element('em', '', match[4]));
    else parent.append(document.createTextNode(match[0]));
    position = match.index + match[0].length;
  }
  parent.append(document.createTextNode(text.slice(position)));
}

function renderAnswer(body, content, sourceList, analysisReferences = new Map()) {
  if (window.FinPilotMessages) return window.FinPilotMessages.renderAnswer(body,content,sourceList,analysisReferences,{language:state.language});
  const sources = new Map(sourceList.map((source, index) => [source.id, { ...source, expertNumber:index + 1 }]));
  for (const [id, record] of analysisReferences) sources.set(id, record);
  let paragraph = [], list = null, fence = null, codeLines = [];
  const flushParagraph = () => {
    if (!paragraph.length) return;
    const p = element('p'); appendInline(p, paragraph.join('\n'), sources); body.append(p); paragraph = [];
  };
  const flushCode = () => {
    const pre = element('pre'); pre.append(element('code', '', codeLines.join('\n'))); body.append(pre); codeLines = [];
  };
  for (const line of content.split('\n')) {
    if (/^\s*```/.test(line)) {
      flushParagraph(); list = null;
      if (fence) { flushCode(); fence = null; } else fence = true;
      continue;
    }
    if (fence) { codeLines.push(line); continue; }
    if (!line.trim()) { flushParagraph(); list = null; continue; }
    const heading = line.match(/^#{1,4}\s+(.+)$/);
    if (heading) { flushParagraph(); list = null; const p = element('p', 'md-heading'); appendInline(p, heading[1], sources); body.append(p); continue; }
    const item = line.match(/^\s*(?:([-*])\s+|(\d+)\.\s+)(.+)$/);
    if (item) {
      flushParagraph(); const kind = item[2] ? 'OL' : 'UL';
      if (!list || list.tagName !== kind) { list = element(kind.toLowerCase()); body.append(list); }
      const li = element('li'); appendInline(li, item[3], sources); list.append(li); continue;
    }
    if (/^>\s?/.test(line)) { flushParagraph(); list = null; const p = element('p', 'md-quote'); appendInline(p, line.replace(/^>\s?/, ''), sources); body.append(p); continue; }
    list = null; paragraph.push(line);
  }
  flushParagraph(); if (fence) flushCode();
}

function renderMessage(message) {
  const isUser = message.role === 'user';
  const projectHelp = !isUser && window.FinPilotMessages?.extractProjectHelp(message);
  const sources = Array.isArray(message.sources) ? message.sources : [];
  const article = element('article', `message ${isUser ? 'user' : 'assistant'}`);
  if (message.id !== undefined) article.dataset.messageId = String(message.id);
  const header = element('div', 'message-header');
  header.append(element('span', 'message-avatar', isUser ? (state.language === 'zh' ? '你' : 'Y') : 'F'), element('span', 'message-author', isUser ? t('user') : t('assistant')));
  if (!isUser && message.mode) {
    let modeLabel;
    if (message.mode === 'project-help') modeLabel = state.language === 'zh' ? '项目指南 · 本地手册' : 'Project guide · Local manual';
    else if (!sources.length && message.mode === 'deepseek') modeLabel = 'DeepSeek';
    else if (!sources.length && message.mode === 'local-lora') modeLabel = state.language === 'zh' ? '本地 LoRA' : 'Local LoRA';
    else if (!sources.length && message.mode === 'offline') modeLabel = state.language === 'zh' ? '本地响应' : 'Local response';
    else modeLabel = t(message.mode === 'deepseek' ? 'modeDeepseek' : message.mode === 'local-lora' ? 'modeLocal' : message.mode === 'calculator' ? 'modeCalculator' : 'modeOffline');
    header.append(element('span', 'message-mode', modeLabel));
  }
  const body = element('div', 'message-body');
  const content = message.content || message.answer || '';
  const analysis = !isUser && !projectHelp && message.analysis_context ? renderAnalysisReply(message.analysis_context) : null;
  if (isUser || projectHelp) body.textContent = content;
  else renderAnswer(body, content, sources, analysis?.references);
  if (projectHelp) { body.hidden=true;body.classList.add('project-help-canonical'); }
  article.append(header, body);
  if (analysis) article.append(analysis.wrapper);
  if (projectHelp) article.append(window.FinPilotMessages.renderProjectHelp(projectHelp,{language:state.language}));
  if (message.warning) article.append(element('div', 'message-warning', projectHelp?(state.language==='en'?'Project-guide matching had a limitation; reviewed manual steps remain available.':'教程主题匹配存在限制；已审阅的本地手册步骤仍然可用。'):warningText(message.warning, Boolean(message.analysis_context))));
  if (!isUser && !projectHelp && sources.length && window.FinPilotMessages) article.append(window.FinPilotMessages.renderSources(sources,{language:state.language}));
  else if (!isUser && !projectHelp && sources.length) {
    const section = element('div', 'message-sources');
    section.append(element('div', 'sources-heading', t('sources')));
    const cards = element('div', 'source-cards');
    sources.forEach((source, index) => {
      const entry = element('div', 'source-entry');
      const url = safeURL(source.url);
      const link = element(url ? 'a' : 'div', 'source-card');
      if (url) { link.href = url; link.target = '_blank'; link.rel = 'noopener noreferrer'; }
      link.title = source.snippet || source.title || '';
      const identifier = element('span', 'source-number', source.id?.startsWith('expert.') ? String(index + 1) : source.id || String(index + 1));
      identifier.title = source.id || String(index + 1);
      link.append(identifier, element('span', '', source.title || source.id || 'Source'), element('span', '', '↗')); entry.append(link);
      if (source.snippet) {
        const preview = element('details', 'source-preview');
        preview.append(element('summary', '', t('previewSource')), element('p', '', source.snippet)); entry.append(preview);
      }
      cards.append(entry);
    });
    section.append(cards); article.append(section);
  }
  if (!isUser) {
    const actions = element('div', 'message-actions');
    const copy = element('button', 'message-action', t('copy')); copy.type = 'button';
    copy.addEventListener('click', async () => { try { await navigator.clipboard.writeText(body.textContent); toast(t('copied')); } catch { toast(t('copyFailed')); } });
    const speak = element('button', 'message-action', t('readAloud')); speak.type = 'button'; speak.dataset.action = 'speak';
    speak.addEventListener('click', () => readAloud(body.textContent));
    actions.append(copy, speak); article.append(actions);
  }
  return article;
}

function renderMessages({ animateLast = false } = {}) {
  const list = $('#chat-messages'); list.replaceChildren(...state.messages.filter(message => ['user','assistant'].includes(message.role)).map(renderMessage));
  document.body.classList.toggle('conversation-started', state.messages.length > 0);
  $('#export-button').disabled = !state.sessionId || state.busy;
  state.lastAnswer = [...state.messages].reverse().find(message => message.role === 'assistant')?.content || null;
  $('#avatar-read-last').disabled = !state.lastAnswer || state.busy;
  if (animateLast) animateElement(list.lastElementChild, [{ opacity:0, transform:'translateY(10px)' }, { opacity:1, transform:'translateY(0)' }]);
}

function setBusy(busy) {
  state.busy = busy;
  const locked = conversationLocked();
  $('#send-button').disabled = locked; $('#message-input').disabled = locked;
  $('#chat-status').hidden = !(busy || state.remoteBusy); $('#export-button').disabled = !state.sessionId || locked;
  $$('.prompt-card').forEach(button => { button.disabled = locked; });
  $('#model-select').disabled = locked;
  $('#language-toggle').disabled = locked;
  $('#sidebar-new').disabled = locked; $('#top-new').disabled = locked;
  $$('.session-open, .session-delete, .analysis-context-actions button, .analysis-refresh-button, .analysis-history-view, .message-analysis-context > button, .options-followup button').forEach(button => { button.disabled = locked; });
  $('#chat-form').classList.toggle('is-busy', busy || state.remoteBusy);
  $('#chat-form').setAttribute('aria-busy', String(busy || state.remoteBusy));
  $('#chat-status [data-i18n]').textContent = t(state.refreshing ? 'analysisRefreshing' : state.engine === 'local' ? 'thinkingLocal' : 'thinkingCloud');
  $('#avatar-read-last').disabled = busy || !state.lastAnswer;
  $$('.message-action[data-action="speak"]').forEach(button => { button.disabled = busy; });
  if (busy || state.remoteBusy) setAvatarState('thinking');
  else if (state.avatarState !== 'error') settleAvatar();
  updateVoiceUI();
  renderCompanionConnection();
}

async function sendMessage(event) {
  event?.preventDefault();
  if (conversationLocked()) return;
  const input = $('#message-input'); const message = input.value.trim();
  if (!message) { input.focus(); return; }
  if (state.recording) state.recognition?.stop();
  cancelSpeech();
  const previousMessages = [...state.messages];
  const sharedRequest = isCurrentSharedSession();
  state.messages.push({ role:'user', content:message });
  showError(''); renderMessages({ animateLast:true }); setBusy(true);
  $('#chat-status').scrollIntoView({ behavior:scrollBehavior(), block:'nearest' });
  try {
    const payload={ message, session_id:state.sessionId, language:state.language, engine:state.engine };
    if (!sharedRequest) payload.analysis_id=state.analysisContext?.analysis_id || null;
    const result = await api('/api/chat', { method:'POST', body:JSON.stringify(payload) });
    state.sessionId = result.session_id;
    if (sharedRequest) {
      const saved=await state.companionClient.sync() || await api(`/api/sessions/${encodeURIComponent(state.sessionId)}`);
      applySharedSession(saved);state.pendingSharedSession=null;
    } else state.messages.push({ role:'assistant', content:result.answer, sources:result.sources || [], mode:result.mode, warning:result.warning, calculation:result.calculation, analysis_context:result.analysis_context || null, project_help:result.project_help || null });
    if (Object.hasOwn(result, 'active_analysis')) state.analysisContext = result.active_analysis || null;
    syncAnalysisHistory(result.analysis_history);
    state.drafts.delete(state.sessionId || '__new__');
    input.value = ''; input.style.height = '';
    localStorage.setItem('finpilot-session', state.sessionId);
    state.lastAnswer = result.answer;
    renderMessages({ animateLast:true }); renderAnalysisContext();
    settleAvatar();
    // Sidebar refresh must not keep the answer and composer in a loading state.
    loadSessions().catch(() => {});
    $('#chat-messages').lastElementChild?.scrollIntoView({ behavior:scrollBehavior(), block:'start' });
  } catch (error) {
    state.messages = previousMessages; renderMessages(); showError(t('errorPrefix') + error.message);
    setAvatarState('error');
    $('#error-banner').scrollIntoView({ behavior:scrollBehavior(), block:'nearest' });
  } finally {
    setBusy(false);
    if(state.pendingSharedSession){const saved=state.pendingSharedSession;state.pendingSharedSession=null;applySharedSession(saved);}
    if (!matchMedia('(pointer: coarse)').matches && !conversationLocked()) input.focus({ preventScroll:true });
  }
}

const fields = {
  compound:[{ name:'principal', label:'principal', value:10000, min:0, max:1000000000, step:'0.01', unit:'currency' },{ name:'annual_rate', label:'annualRate', value:5, min:0, max:100, step:'0.01', unit:'%', hint:'rateHint' },{ name:'years', label:'years', value:10, min:1, max:50, step:1, unit:'yearUnit' },{ name:'monthly_contribution', label:'monthlyContribution', value:500, min:0, max:1000000000, step:'0.01', unit:'currency', hint:'contributionHint' }],
  loan:[{ name:'principal', label:'loanPrincipal', value:100000, min:'0.01', max:1000000000, step:'0.01', unit:'currency' },{ name:'annual_rate', label:'annualRate', value:4, min:0, max:100, step:'0.01', unit:'%', hint:'rateHint' },{ name:'years', label:'years', value:10, min:1, max:50, step:1, unit:'yearUnit', hint:'loanHint' }],
  budget:[{ name:'income', label:'income', value:15000, min:'0.01', max:1000000000, step:'0.01', unit:'currency', hint:'incomeHint' },{ name:'expenses', label:'expenses', value:9000, min:0, max:1000000000, step:'0.01', unit:'currency', hint:'expensesHint' }]
};

function renderCalculatorFields() {
  invalidateCalculation();
  const container = $('#calculator-fields'); container.replaceChildren();
  fields[state.calculatorKind].forEach(field => {
    const row = element('div','calc-field'); const label = element('label','',t(field.label)); label.htmlFor = `calc-${field.name}`;
    const wrap = element('div','input-wrap'); const input = element('input');
    Object.assign(input,{ type:'number', id:`calc-${field.name}`, name:field.name, value:field.value, min:String(field.min), max:String(field.max), step:String(field.step), required:true });
    input.inputMode = 'decimal'; wrap.append(input, element('span','', field.unit === '%' ? '%' : t(field.unit))); row.append(label,wrap);
    if (field.hint) row.append(element('small','field-hint',t(field.hint))); container.append(row);
  });
  $$('.calc-tab').forEach(tab => { const active = tab.dataset.kind === state.calculatorKind; tab.classList.toggle('active',active); tab.setAttribute('aria-selected',String(active)); tab.tabIndex=active?0:-1; });
  $('#calculation-output').hidden = true; $('#calculation-error').hidden = true;
  $('#calculate-button').disabled = false; $('#calculate-button').textContent = t('runCalculation');
  $('#calculator-form').setAttribute('aria-busy', 'false');
}

function invalidateCalculation() {
  state.calculationSequence += 1;
  $('#calculation-output').hidden = true; $('#calculation-error').hidden = true;
  $('#calculate-button').disabled = false; $('#calculate-button').textContent = t('runCalculation');
  $('#calculator-form').setAttribute('aria-busy', 'false');
}

function openCalculator(kind) { if (kind) { state.calculatorKind=kind; renderCalculatorFields(); } closeSidebar(); openToolDialog($('#calculator-dialog')); }

function displayValue(key, value) {
  if (typeof value !== 'number' && typeof value !== 'string') return String(value);
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return String(value);
  const locale = state.language === 'zh' ? 'zh-CN' : 'en-US';
  const percentage = key.includes('rate') || key.includes('percent');
  return numeric.toLocaleString(locale,{ minimumFractionDigits:percentage || key.includes('months') ? 0 : 2, maximumFractionDigits:2 }) + (percentage ? '%' : '');
}

function showCalculation(data) {
  const output = $('#calculation-output'); output.replaceChildren();
  if (data.summary) output.append(element('p','calculation-summary', typeof data.summary === 'string' ? data.summary : JSON.stringify(data.summary)));
  const grid = element('div','result-grid');
  const values = data.values && typeof data.values === 'object' ? data.values : {};
  Object.entries(values).forEach(([key,value]) => {
    if (value === null || typeof value === 'object') return;
    const label = valueLabels[key]?.[state.language === 'zh' ? 0 : 1] || key.replaceAll('_',' ');
    const card = element('div','result-card'); if (Number(value) < 0) card.dataset.tone = 'negative'; card.append(element('div','result-label',label),element('div','result-value',displayValue(key,value))); grid.append(card);
  });
  output.append(grid);
  const series = (data.series || []).filter(item => Number.isFinite(Number(item.balance)));
  if (series.length > 1 && data.kind !== 'budget') {
    const namespace='http://www.w3.org/2000/svg'; const svg=document.createElementNS(namespace,'svg'); svg.setAttribute('viewBox','0 0 500 130'); svg.setAttribute('role','img'); svg.setAttribute('aria-label',state.language === 'zh' ? '期末余额趋势' : 'Balance over time'); svg.classList.add('result-chart');
    const balances=series.map(item=>Number(item.balance)); const minimum=Math.min(0,...balances); const maximum=Math.max(...balances,1); const spread=maximum-minimum || 1;
    [20,65,110].forEach(y => { const line=document.createElementNS(namespace,'line'); line.setAttribute('x1','0');line.setAttribute('x2','500');line.setAttribute('y1',String(y));line.setAttribute('y2',String(y));svg.append(line); });
    const points=balances.map((value,index)=>`${index/(balances.length-1)*496+2},${114-(value-minimum)/spread*102}`).join(' ');
    const line=document.createElementNS(namespace,'polyline'); line.setAttribute('points',points);line.setAttribute('fill','none');line.setAttribute('stroke','#DBA85A');line.setAttribute('stroke-width','2.5');line.setAttribute('pathLength','1');svg.append(line);output.append(svg);
    const caption=element('div','chart-caption');caption.append(element('span','',t('chartStart')),element('span','',t('chartEnd')));output.append(caption);
  }
  if (data.formula) output.append(element('div','result-formula',`${t('formula')}: ${typeof data.formula === 'string' ? data.formula : JSON.stringify(data.formula)}`));
  if (data.assumptions) {
    const assumptions=Array.isArray(data.assumptions) ? data.assumptions.join('\n') : typeof data.assumptions === 'string' ? data.assumptions : Object.entries(data.assumptions).map(([key,value])=>`${key}: ${value}`).join('\n');
    output.append(element('p','result-assumptions',`${t('assumptions')}\n${assumptions}`));
  }
  output.append(element('p','result-assumptions',t('financialNotice')));
  output.hidden=false;
  $$('.result-card', output).forEach((card,index) => animateElement(card, [{ opacity:0, transform:'translateY(7px)' }, { opacity:1, transform:'translateY(0)' }], { delay:Math.min(index * 35, 175) }));
  animateElement($('polyline', output), [{ strokeDasharray:'1', strokeDashoffset:1 }, { strokeDasharray:'1', strokeDashoffset:0 }], { duration:600 });
}

async function calculate(event) {
  event.preventDefault();
  const form=$('#calculator-form'); if (!form.reportValidity()) return;
  const sequence = ++state.calculationSequence;
  const body={ kind:state.calculatorKind };
  new FormData(form).forEach((value,key)=>{ body[key]=Number(value); });
  const button=$('#calculate-button'); button.disabled=true;button.textContent=t('loading');$('#calculation-error').hidden=true;
  form.setAttribute('aria-busy', 'true');
  try { const result=await api('/api/calculate',{ method:'POST',body:JSON.stringify(body) });if(sequence===state.calculationSequence)showCalculation(result); }
  catch(error){if(sequence===state.calculationSequence){$('#calculation-error').textContent=t('errorPrefix')+error.message;$('#calculation-error').hidden=false;$('#calculation-output').hidden=true;}}
  finally {if(sequence===state.calculationSequence){button.disabled=false;button.textContent=t('runCalculation');form.setAttribute('aria-busy','false');}}
}

async function openKnowledge() {
  closeSidebar();openToolDialog($('#knowledge-dialog'));
  const list=$('#knowledge-list');list.replaceChildren(element('p','dialog-description',t('loading')));
  try {
    const data=await api('/api/knowledge');list.replaceChildren();
    if (!data.documents?.length) {list.append(element('p','dialog-description',t('noKnowledge')));return;}
    data.documents.forEach(doc=>{
      const url=safeURL(doc.url);const card=element(url?'a':'div','knowledge-card');if(url){card.href=url;card.target='_blank';card.rel='noopener noreferrer';}
      card.append(element('div','knowledge-category',(doc.category||'FINANCIAL KNOWLEDGE').toUpperCase()),element('h3','',doc.title),element('div','knowledge-url',doc.url||''));
      if(doc.updated_at)card.append(element('div','knowledge-date',t('updateDate')+doc.updated_at));list.append(card);
    });
  }catch(error){list.replaceChildren(element('p','calculation-error',t('errorPrefix')+error.message));}
}

function initVoice() {
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRecognition) { $('#mic-button').setAttribute('aria-disabled','true'); $('#mic-button').title=t('unsupportedVoice'); return; }
  const recognition=new SpeechRecognition();state.recognition=recognition;recognition.continuous=false;recognition.interimResults=false;
  recognition.onstart=()=>{state.recording=true;state.listeningActivity=beginCompanionActivity('speech','listening');updateVoiceUI();setAvatarState('listening');};
  recognition.onend=()=>{state.recording=false;state.listeningActivity?.('completed');state.listeningActivity=null;updateVoiceUI();if(state.avatarState!=='error')settleAvatar();};
  recognition.onerror=()=>{state.recording=false;state.listeningActivity?.('failed');state.listeningActivity=null;updateVoiceUI();setAvatarState('error');toast(t('voiceError'));};
  recognition.onresult=event=>{
    const transcript=Array.from(event.results).map(result=>result[0].transcript).join(' ');
    const input=$('#message-input');input.value=((input.value ? `${input.value} ` : '')+transcript).slice(0,input.maxLength);input.dispatchEvent(new Event('input'));input.focus();
  };
}

function updateVoiceUI() {
  const button=$('#mic-button');button.classList.toggle('recording',state.recording);button.disabled=state.busy;
  button.setAttribute('aria-pressed',String(state.recording));$('span',button).textContent=state.recording?t('listening'):state.recognition?t('voiceInput'):t('voiceUnavailable');
  button.title=state.recognition?(state.recording?t('listening'):t('voiceInput')):t('unsupportedVoice');
}

function toggleVoice() {
  if (!state.recognition) return toast(t('unsupportedVoice'));
  if (state.recording) return state.recognition.stop();
  cancelSpeech();
  state.recognition.lang=state.language==='zh'?'zh-CN':'en-US';
  try {state.recognition.start();}catch{setAvatarState('error');toast(t('voiceError'));}
}

function updateSpeechControls() {
  const label = $('#avatar-read-last [data-i18n]');
  label.textContent = t(state.speechStarted ? 'stopSpeech' : 'readLatest');
  $('#avatar-read-last').setAttribute('aria-pressed', String(state.speechStarted));
  $$('.message-action[data-action="speak"]').forEach(button => { button.textContent = t(state.speechStarted ? 'stopSpeech' : 'readAloud'); });
}

function cancelSpeech() {
  if (state.speech) window.speechSynthesis?.cancel();
  state.speakingActivity?.('cancelled');state.speakingActivity=null;
  state.speech = null; state.speechStarted = false;
  updateSpeechControls();
}

function readAloud(text) {
  if (state.busy) return;
  if (!('speechSynthesis' in window)) return toast(t('unsupportedSpeech'));
  if(state.speech){cancelSpeech();settleAvatar();toast(t('stoppedSpeech'));return;}
  if (state.recording) state.recognition?.stop();
  const utterance=new SpeechSynthesisUtterance(text.replace(/\[[A-Za-z][A-Za-z0-9_-]*\]/g,''));
  utterance.lang=/[\u3400-\u9fff]/.test(text)?'zh-CN':'en-US';utterance.rate=.95;
  utterance.onstart=()=>{if(state.speech!==utterance)return;state.speechStarted=true;state.speakingActivity=beginCompanionActivity('speech','speaking');updateSpeechControls();setAvatarState('speaking');};
  utterance.onend=()=>{if(state.speech!==utterance)return;state.speakingActivity?.('completed');state.speakingActivity=null;state.speech=null;state.speechStarted=false;updateSpeechControls();settleAvatar();};
  utterance.onerror=event=>{if(state.speech!==utterance)return;state.speakingActivity?.(['canceled','interrupted'].includes(event.error)?'cancelled':'failed');state.speakingActivity=null;state.speech=null;state.speechStarted=false;updateSpeechControls();if(['canceled','interrupted'].includes(event.error)){settleAvatar();}else{setAvatarState('error');toast(t('speechError'));}};
  state.speech=utterance;
  try {window.speechSynthesis.speak(utterance);}catch{state.speech=null;state.speechStarted=false;setAvatarState('error');toast(t('speechError'));}
}

function bindEvents() {
  $('#theme-toggle').addEventListener('click',()=>{state.theme=state.theme==='dark'?'light':'dark';localStorage.setItem('finpilot-theme',state.theme);applyTheme();});
  $('#avatar-collapse').addEventListener('click',()=>{state.panelExpanded=!state.panelExpanded;syncAssistantPanel();});
  $('#avatar-2d').addEventListener('click',()=>setAvatarMode('2d'));
  $('#avatar-3d').addEventListener('click',()=>setAvatarMode('3d'));
  $('#avatar-character').addEventListener('change',event=>setAvatarCharacter(event.target.value));
  $('#companion-connect').addEventListener('click',connectCurrentCompanion);
  $('#companion-disconnect').addEventListener('click',()=>state.companionClient?.disconnect().catch(error=>showError(error.message)));
  $('#reduce-motion').addEventListener('change',event=>{state.reducedMotion=event.target.checked;localStorage.setItem('finpilot-reduced-motion',String(state.reducedMotion));applyMotionPreference();});
  $('#workspace-motion-toggle')?.addEventListener('click',()=>{state.reducedMotion=!state.reducedMotion;localStorage.setItem('finpilot-reduced-motion',String(state.reducedMotion));applyMotionPreference();});
  motionMedia.addEventListener('change', event=>{state.osReducedMotion=event.matches;applyMotionPreference();});
  document.addEventListener('visibilitychange',()=>{if(document.hidden)for(const animation of [...activeAnimations])animation.cancel();});
  $('#avatar-read-last').addEventListener('click',()=>{const body=$$('.message.assistant .message-body').at(-1);if(body)readAloud(body.textContent);});
  $('#model-select').addEventListener('change',event=>changeModel(event.target.value));
  window.addEventListener('finpilot-avatar-ready',mountAvatar);
  window.addEventListener('finpilot-companion-ready',mountAvatar);
  $('#avatar-stage').addEventListener('finpilot-avatar-status',event=>{state.avatarRenderStatus=event.detail;renderAvatarStatus();});
  $('#avatar-stage').addEventListener('finpilot-companion-status',event=>{state.avatarRenderStatus=event.detail;renderAvatarStatus();});
  window.addEventListener('resize',()=>{const small=innerWidth<=1180;if(small!==state.smallLayout){state.smallLayout=small;state.panelExpanded=!small;syncAssistantPanel();}setSidebar(state.menuOpen,false);});
  $('#chat-form').addEventListener('submit',sendMessage);
  $('#message-input').addEventListener('keydown',event=>{if(event.key==='Enter'&&!event.shiftKey&&!event.isComposing){event.preventDefault();sendMessage();}});
  $('#message-input').addEventListener('input',event=>{const input=event.target;input.style.height='auto';input.style.height=`${Math.min(200,input.scrollHeight)}px`;});
  $('#language-toggle').addEventListener('click',()=>{if(conversationLocked())return;state.language=state.language==='zh'?'en':'zh';localStorage.setItem('finpilot-language',state.language);applyLanguage();shareCompanionPreferences();toast(t('changedLanguage'));});
  $('#sidebar-new').addEventListener('click',newConversation);$('#top-new').addEventListener('click',newConversation);
  $('#nav-chat').addEventListener('click',()=>{closeSidebar();$('#message-input').focus();});
  $('#nav-calculator').addEventListener('click',()=>openCalculator());$('#quick-calculate').addEventListener('click',()=>openCalculator());
  $('#nav-knowledge').addEventListener('click',openKnowledge);
  $$('[data-help-prompt]').forEach(button=>button.addEventListener('click',()=>{
    if(conversationLocked())return;
    const prompts={history:{zh:'FinPilot 怎么做历史复盘？请说明入口、步骤和限制。',en:'How do I use historical review in FinPilot? Explain the entry point, steps and limits.'},pet:{zh:'FinPilot 怎么连接桌宠和当前会话？',en:'How do I connect the FinPilot desktop pet to the current conversation?'},models:{zh:'FinPilot 怎么切换回答模型？离线模式有什么区别？',en:'How do I switch the answering model in FinPilot, and how is offline mode different?'}};
    const input=$('#message-input');input.value=prompts[button.dataset.helpPrompt][state.language];input.dispatchEvent(new Event('input'));input.focus();
    toast(state.language==='zh'?'教程示例已填入；点击发送才开始提问。':'Guide example filled. Choose Send when ready.');
  }));
  $('#calculator-form').addEventListener('submit',calculate);
  $('#calculator-fields').addEventListener('input', invalidateCalculation);
  $$('.calc-tab').forEach(button=>button.addEventListener('click',()=>{state.calculatorKind=button.dataset.kind;renderCalculatorFields();}));
  $('.calc-tabs').addEventListener('keydown',event=>{
    if(!['ArrowLeft','ArrowRight','Home','End'].includes(event.key))return;
    event.preventDefault(); const tabs=$$('.calc-tab');const current=tabs.findIndex(tab=>tab.dataset.kind===state.calculatorKind);
    const next=event.key==='Home'?0:event.key==='End'?tabs.length-1:(current+(event.key==='ArrowRight'?1:tabs.length-1))%tabs.length;
    state.calculatorKind=tabs[next].dataset.kind;renderCalculatorFields();tabs[next].focus();
  });
  $$('.close-dialog').forEach(button=>button.addEventListener('click',()=>button.closest('dialog').close()));
  $$('dialog').forEach(dialog=>dialog.addEventListener('click',event=>{if(event.target===dialog){const rect=dialog.getBoundingClientRect();if(event.clientX<rect.left||event.clientX>rect.right||event.clientY<rect.top||event.clientY>rect.bottom)dialog.close();}}));
  $('#mobile-menu').addEventListener('click',()=>setSidebar(!state.menuOpen));
  $('#sidebar-shade').addEventListener('click',closeSidebar);
  document.addEventListener('keydown',event=>{
    if(event.key==='Escape'&&state.menuOpen){event.preventDefault();closeSidebar();}
    if(event.key==='Tab'&&state.menuOpen){
      const candidates=[$('#mobile-menu'),...$$('a[href],button:not([disabled]),select:not([disabled]),input:not([disabled]),[tabindex="0"]',$('#sidebar'))].filter(el=>el.getClientRects().length&&!el.closest('[inert]'));
      const first=candidates[0],last=candidates.at(-1);
      if(event.shiftKey&&document.activeElement===first){event.preventDefault();last.focus();}
      else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first.focus();}
    }
  });
  $('#export-button').addEventListener('click',()=>{if(!state.sessionId)return;const a=document.createElement('a');a.href=`/api/sessions/${encodeURIComponent(state.sessionId)}/export`;a.download=`finpilot-${state.sessionId}.json`;document.body.append(a);a.click();a.remove();});
  $('#mic-button').addEventListener('click',toggleVoice);
  $$('.prompt-card').forEach(button=>button.addEventListener('click',()=>{
    if(button.dataset.prompt==='compound'){openCalculator('compound');return;}
    const prompts={risk:{zh:'分散投资为什么能降低风险？有哪些不能消除的风险？请列出参考来源。',en:'How does diversification reduce risk, and which risks cannot be eliminated? Please include your sources.'},budget:{zh:'应急储备金是什么？一般如何估算需要准备多少？请说明局限和参考来源。',en:'What is an emergency fund, and how can I estimate how much to keep? Explain the limitations and include sources.'}};
    const input=$('#message-input');input.value=prompts[button.dataset.prompt][state.language];
    input.dispatchEvent(new Event('input'));input.focus();
    toast(state.language==='zh'?'示例已填入，点击发送开始提问。':'Example ready. Choose Send to ask.');
  }));
}

async function initialize() {
  bindEvents();initVoice();applyLanguage();applyMotionPreference();setAvatarMode(state.avatarMode);mountAvatar();
  setSidebar(false,false);
  await Promise.allSettled([loadHealth(),loadModels(),loadSessions().catch(error=>showError(t('errorPrefix')+error.message))]);
  const saved=localStorage.getItem('finpilot-session');
  if(saved&&state.sessions.some(session=>session.id===saved))await selectSession(saved);
  const requestedSession=new URLSearchParams(location.search).get('session');
  if(requestedSession&&/^[0-9a-f-]{36}$/i.test(requestedSession))await selectSession(requestedSession);
  initializeCompanionConnection();
  const entry = new URLSearchParams(location.search);
  const engine = entry.get('engine');
  if (['deepseek','local'].includes(engine)) {
    if (state.models.some(model=>model.id===engine&&model.available)) {
      state.engine=engine;localStorage.setItem('finpilot-engine',engine);renderModelOptions();setHealthBadge();
    } else toast(state.language==='zh'?'所选模型尚未就绪，请先使用可用引擎。':'The selected model is not ready. Choose an available engine.');
  }
  const prompt = entry.get('prompt');
  if (prompt) {
    const input=$('#message-input');input.value=prompt.slice(0,input.maxLength);
    input.dispatchEvent(new Event('input'));input.focus();
    toast(state.language==='zh'?'示例已填入，点击发送开始提问。':'Example ready. Choose Send to ask.');
  }
  const tool=entry.get('tool');
  if (['compound','loan','budget'].includes(tool))openCalculator(tool);
  else if (entry.get('view')==='calculator')openCalculator('compound');
  else if (entry.get('view')==='history') {
    openToolDialog($('#options-dialog'));
    const panel = $('#history-panel');
    if (panel) { panel.open = true; panel.scrollIntoView({ block:'start', behavior:scrollBehavior() }); }
  }
  else if (entry.get('view')==='knowledge')await openKnowledge();
  // Only the age label changes; no data or model request is made by this timer.
  const ageTimer=setInterval(() => {
    if (document.hidden) return;
    $$('.analysis-snapshot-note[data-captured-at]').forEach(note => {
      if (note.dataset.stale === 'true') return;
      const captured = Date.parse(note.dataset.capturedAt);
      if (Number.isFinite(captured) && Date.now() - captured > 30000) {
        note.append(document.createTextNode(' ' + t('analysisStale'))); note.dataset.stale = 'true';
      }
    });
  }, 15000);
  window.addEventListener('pagehide',()=>{
    clearInterval(ageTimer);clearTimeout(companionActivityErrorTimer);
    for(const item of [...companionLocalActivities.values()])item.finish?.('cancelled');
    state.companionClient?.destroy();state.avatar?.destroy();cancelSpeech();
    for(const animation of [...activeAnimations])animation.cancel();
  },{once:true});
}

initialize();
