(() => {
  'use strict';
  const pairs = [
    ['跳到分析操作', 'Skip to analysis controls'], ['FinPilot 首页', 'FinPilot home'], ['其他功能', 'Other tools'],
    ['互动学习 ↗', 'Options lab ↗'], ['网关分析 ↗', 'Gateway analysis ↗'],
    ['模拟数据 · 非实时行情', 'Simulated data · Not live market data'], ['AAPL · 波动与风险分析', 'AAPL · Volatility & risk analysis'],
    ['分析隐含波动率、两翼相对定价和平值跨式成本，连接期权定价与标的波动风险。一次分析，获得有依据的整体解读。', 'Analyze implied volatility, relative wing pricing and ATM straddle cost. Connect option prices with an evidence-based view of the underlying’s volatility and risk.'],
    ['分析操作', 'Analysis controls'], ['回答设置', 'Answer settings'], ['回答引擎', 'Answer engine'],
    ['本地规则 · 离线稳定', 'Local rules · Offline'], ['DeepSeek · 真实模型请求', 'DeepSeek · Actual model request'],
    ['分析进度', 'Analysis steps'], ['读取期权数据', 'Read options data'], ['确认范围与定价输入', 'Check scope and pricing inputs'],
    ['理解波动定价', 'Understand volatility pricing'], ['解释波动率与相对成本', 'Explain volatility and relative cost'],
    ['获得风险解读', 'Read the risk explanation'], ['提炼关键结论与背景', 'Summarize key findings and context'],
    ['期权价格里，包含哪些波动信息？', 'What can option prices tell us about volatility?'],
    ['点击「一键分析」，了解波动率如何定价、不同方向的相对成本有何差异，以及标的面临哪些波动风险。', 'Click Analyze to see how volatility is priced, how relative costs differ by direction and what volatility risks are reflected in the underlying’s options.'],
    ['AAPL · 期权分析', 'AAPL · Options analysis'], ['期权与风险定价概览', 'Options and risk pricing overview'],
    ['期权分析概览', 'Analysis overview'], ['首次分析', 'First analysis'],
    ['聚合同一到期日的期权定价输入，解读标的的波动与风险。', 'Combine option pricing inputs for the same expiry to analyze the underlying’s volatility and risk.'],
    ['期权价格反映了什么？', 'What is priced into these options?'],
    ['分析覆盖所选期权范围；事件背景与市场整体判断需要结合更多信息。', 'The analysis covers the selected options. Event context and a broader market view require additional information.'],
    ['理解标的的波动与风险。', 'Understand the underlying’s volatility and risk.'],
    ['结合期权价格分析波动、风险溢价与相对定价，给出关键结论和依据。', 'Analyze volatility, risk premiums and relative pricing through option prices, with clear findings and supporting evidence.'],
    ['分析问答记录', 'Analysis conversation'], ['继续了解（可选）', 'Explore further (optional)'],
    ['本次解读已完成；需要进一步了解时，再主动发送问题。', 'This explanation is complete. Send another question only when you want to explore further.'],
    ['针对当前批次继续提问', 'Ask about the current analysis'], ['你想进一步了解什么？', 'What would you like to understand?'], ['建议问题', 'Suggested questions'],
    ['例如：隐含波动率代表什么，能说明标的的哪些风险？', 'For example: what does implied volatility tell us about the underlying’s risk?'],
    ['回答方式与数据使用', 'Answer mode and data use'],
    ['查看分析依据', 'Review the evidence'], ['汇总指标 · 数据时间 · 分析范围', 'Metrics · Data times · Analysis scope'],
    ['可选更新对比', 'Optional update comparison'], ['更新对比（可选）', 'Compare updates (optional)'],
    ['读取相同范围的更新数据，使用当前引擎分析前后变化。', 'Read updated data with the same scope and analyze the changes using the selected engine.'],
    ['读取更新数据', 'Analyze updated data'], ['数据时间与范围', 'Data times and scope'], ['本次分析范围', 'Analysis scope'],
    ['数据时点（UTC）', 'Data time (UTC)'], ['本次处理时间（北京时间）', 'Processed at (Beijing time)'],
    ['所选数据的本地计算结果', 'Locally calculated metrics'],
    ['指标描述所选期权的风险定价；隐含波动率不是已实现波动率，跨式中价也不是发生概率。', 'Metrics describe risk pricing in the selected options. Implied volatility is not realized volatility, and the straddle midpoint is not a probability.'],
    ['前后变化对比', 'Changes between samples'], ['同标的 / 同到期 / 同合约', 'Same underlying / expiry / contracts'],
    ['仅比较相同范围的合成样本，不能据此判断真实市场走势或因果关系；缺失报价保持缺失。', 'Compare only synthetic samples with matching scope. This does not establish actual market direction or causes; missing quotes remain missing.'],
    ['汇总依据与分析范围', 'Aggregate evidence and scope'], ['模拟数据', 'Simulated data'],
    ['分析适用于所选期权范围；未返回的字段保持缺失。', 'The analysis applies to the selected options. Unavailable fields remain missing.'],
    ['展开本地数值依据', 'Expand local numerical evidence'], ['数据范围与分析限制', 'Data scope and limitations'],
    ['数据来源与网关接入', 'Data source and gateway access'],
    ['当前使用固定模拟数据，未连接 IBKR。链接打开当前服务的网关工作台；实际采集须先启用并配置 IBKR，独立风险页服务默认禁用采集。其他服务请使用其启动器显示的地址。', 'This analysis uses fixed simulated data and is not connected to IBKR. The link opens this service’s gateway workspace. Collection requires IBKR configuration and is disabled in the standalone risk service. Use the address printed by its launcher for another service.'],
    ['打开网关分析 ↗', 'Open gateway analysis ↗'],
    ['分析用于理解波动与风险，不构成交易建议。', 'Analysis helps explain volatility and risk and is not trading advice.'], ['历史资料分析 ↗', 'Historical analysis ↗'],
  ];
  const dictionary = new Map(pairs.map(pair => [pair[0], pair]));
  const textNodes = [], attributes = [];
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  let current;
  while ((current = walker.nextNode())) {
    if (current.parentElement?.closest('script,style')) continue;
    const pair = dictionary.get(current.textContent.trim());
    if (pair) textNodes.push({ element: current, pair });
  }
  document.querySelectorAll('[aria-label],[placeholder]').forEach(element => {
    ['aria-label', 'placeholder'].forEach(attribute => {
      const pair = dictionary.get(element.getAttribute(attribute));
      if (pair) attributes.push({ element, attribute, pair });
    });
  });
  const pick = (language, zh, en) => language === 'en' ? en : zh;
  function apply(language) {
    const index = language === 'en' ? 1 : 0;
    document.documentElement.lang = index ? 'en' : 'zh-CN';
    textNodes.forEach(({ element, pair }) => { if (element.isConnected) element.textContent = pair[index]; });
    attributes.forEach(({ element, attribute, pair }) => element.setAttribute(attribute, pair[index]));
    document.title = pick(language, 'FinPilot · 标的波动与风险解读', 'FinPilot · Volatility and risk insights');
    document.querySelector('meta[name=description]').content = pick(language,
      'FinPilot 标的波动与风险解读：分析期权数据中的隐含波动率、两翼相对定价和平值跨式成本，获得有依据的分析。',
      'FinPilot volatility and risk insights: understand implied volatility, relative wing pricing and ATM straddle cost through an evidence-based explanation.');
    document.querySelector('#page-title').textContent = pick(language, '从期权价格，理解标的波动。', 'Understand volatility through option prices.');
  }
  window.finPilotOptionsDemoI18n = { apply, pick };
})();
