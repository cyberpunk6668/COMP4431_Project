/* Shared safe DOM rendering for persisted financial replies. No innerHTML. */
(() => {
  'use strict';
  const labels = {
    user:['你','You'],assistant:['FinPilot','FinPilot'],sources:['参考来源','References'],evidence:['本地数据依据','Local data evidence'],expert:['专家来源','Expert source'],
    missing:['未提供','Not provided'],before:['首记录 / 上次','First / previous'],after:['末记录 / 本次','Last / current'],delta:['变化量','Change'],
    incomparable:['不可比','Incomparable'],comparable:['可在所示样本内比较','Comparable within this sample'],source:['数据来源','Data source'],saved:['本地保存时间（UTC）','Locally saved at (UTC)'],
    period:['历史复盘区间','Historical review period'],scope:['所选合约范围','Selected contract scope'],historical:['历史样本，不代表当前行情或情绪。','Historical sample; not current quotes or sentiment.'],
    quoteNotice:['接收时间不是交易所时间；行情类型不保证当前可成交。','Receipt time is not exchange time; feed type does not guarantee current executable quotes.'],
    stale:['数据已陈旧，不能当作当前行情。','This capture is stale; do not treat it as current quotes.'],view:['在完整工作台查看','View in the full workspace'],
    retrieval:['专家依据怎样选取','How expert sources were selected'],retrievalNote:['BM25 与字符匹配由 RRF 合并；必要主题可从审阅资料补足。排名不是正确率，主题检查不是完整语义证明。','BM25 and character ranks are fused with RRF; reviewed topics can be added. Rank is not accuracy; topic checks are not general semantic entailment.'],
    comparison:['与前次快照的比较','Comparison with the previous capture'],reason:['原因','Reason'],copy:['复制文字','Copy text'],copied:['已复制','Copied'],copyError:['无法复制，请选择文字。','Could not copy. Select the text instead.'],
    warning:['模型或数据存在限制；请结合实际模式、时间和依据阅读。','Model or data limitations apply; read the actual mode, times and evidence.'],
    validation:['模型回答未通过证据核验，当前展示本地数据说明。','The model reply failed evidence checks; showing a local data explanation.'],
    offline:['本地响应','Local response'],calculator:['确定性公式计算','Deterministic calculation'],local:['本地 LoRA','Local LoRA'],
    preview:['查看来源摘要','View source excerpt'],contracts:['合约','contracts'],points:['百分点','percentage points'],volatility:['波动率点','volatility points'],
  };
  const reasons = {
    historical_bar_coverage_unverified:['完整交易时段覆盖未核验','Complete-session coverage is unverified'],
    missing_value_or_oi_asof:['数值或未平仓统计日期缺失','Missing value or open-interest as-of date'],
    oi_asof_not_advanced:['未平仓统计日期没有推进','Open-interest as-of date did not advance'],
    insufficient_days_or_common_sample:['历史日期或共同样本不足','Insufficient dates or common sample'],
    underlying_period_endpoint_missing:['标的的对应区间端点缺失','Matching underlying period endpoints are missing'],
  };
  function element(tag,className,text) { const node=document.createElement(tag);if(className)node.className=className;if(text!==undefined)node.textContent=String(text);return node; }
  function safeURL(value) {try {const url=new URL(value);return ['https:','http:'].includes(url.protocol)&&!url.username&&!url.password?url.href:null;}catch{return null;}}
  // Project navigation is a separate, bounded surface from market references.
  function projectURL(value) {
    if(typeof value!=='string'||!value.startsWith('/')||value.startsWith('//'))return null;
    try {
      const url=new URL(value,location.origin);if(url.origin!==location.origin||url.username||url.password)return null;
      if(url.pathname==='/help'&&!url.search&&(!url.hash||/^#help\.[a-z][a-z0-9_-]*$/.test(url.hash)))return url.pathname+url.hash;
      if(url.hash)return null;
      if(['/','/demo','/pet','/docs'].includes(url.pathname)&&!url.search)return url.pathname;
      if(url.pathname==='/workspace'&&(!url.search||/^\?view=(calculator|history|options|knowledge)$/.test(url.search)||/^\?tool=(compound|loan|budget)$/.test(url.search)))return url.pathname+url.search;
    }catch{/* Invalid navigation remains plain text. */}return null;
  }
  function extractProjectHelp(message) {
    const value=message?.project_help||message?.sources?.find(source=>source?.project_help)?.project_help;
    return value&&typeof value==='object'&&value.intent==='project_help'?value:null;
  }
  function projectLink(label,value,options={}) {
    const url=projectURL(value),link=element(url?'a':'span','project-help-link',label);
    if(url){link.href=url;link.dataset.projectHelpUrl=url;
      if(options.onOpenProjectHelp)link.addEventListener('click',event=>{event.preventDefault();options.onOpenProjectHelp(url);});
      else {link.target='_blank';link.rel='noopener noreferrer';}
    }return link;
  }
  function renderProjectHelp(help,options={}) {
    const en=options.language==='en',card=element('section','project-help-card');card.dataset.manualVersion=String(help?.manual_version||'');
    card.setAttribute('aria-label',en?'Project usage guide':'项目使用指南');
    const top=element('div','project-help-heading');top.append(element('span','project-help-icon','?'),element('strong','',en?'Project usage guide':'项目使用指南'),element('span','project-help-local',en?'LOCAL MANUAL':'本地手册'));card.append(top);
    if(help?.title)card.append(element('h3','project-help-title',help.title));
    if(help?.summary)card.append(element('p','project-help-summary',help.summary));
    const selector=help?.selector||{},engine=selector.engine==='deepseek'?'DeepSeek':selector.engine==='local-lora'?(en?'local LoRA':'本地 LoRA'):null;
    let mode=en?'Reviewed local manual steps; no market data analysis.':'已审阅的本地手册步骤，不是市场数据分析。';
    if(engine&&selector.status==='validated')mode=en?`Local manual steps · ${engine} assisted topic matching. The model does not write these steps.`:`本地手册步骤 · ${engine} 辅助匹配；操作步骤不由模型自由生成。`;
    else if(selector.status==='fallback')mode=en?'Local manual fallback; model matching was not accepted.':'使用本地手册降级；模型主题匹配未被采用。';
    card.append(element('p','project-help-method',mode));
    if(selector.status==='fallback')card.append(element('p','project-help-selection-note',selector.reason==='project_help_selection_invalid'?(en?'The model topic selection failed validation. Reviewed manual steps remain available.':'模型主题匹配未通过校验，仍可阅读已审阅的手册步骤。'):(en?'Model topic matching was unavailable. Reviewed manual steps remain available.':'模型主题匹配暂不可用，仍可阅读已审阅的手册步骤。')));
    if(Array.isArray(help?.steps)&&help.steps.length){const list=element('ol','project-help-steps');for(const step of help.steps.slice(0,20))if(typeof step==='string')list.append(element('li','',step));card.append(list);}
    if(Array.isArray(help?.links)&&help.links.length){const links=element('nav','project-help-links');links.setAttribute('aria-label',en?'Project entry points':'项目功能入口');for(const entry of help.links.slice(0,12))if(typeof entry?.label==='string')links.append(projectLink(entry.label,entry.url,options));card.append(links);}
    if(Array.isArray(help?.restrictions)&&help.restrictions.length){const details=element('details','project-help-restrictions');details.append(element('summary','',en?'Limits and prerequisites':'限制与前提'));const list=element('ul');for(const item of help.restrictions.slice(0,20))if(typeof item==='string')list.append(element('li','',item));details.append(list);card.append(details);}
    const footer=element('div','project-help-provenance');footer.append(element('span','',`${en?'Manual version':'手册版本'} ${help?.manual_version||'—'}`));
    if(help?.followup_used)footer.append(element('span','',en?'Continues the previous guide topic':'沿用上一条教程主题'));
    const sources=Array.isArray(help?.sources)?help.sources:(typeof help?.url==='string'?[{title:help.title||help.id||'FinPilot',url:help.url}]:[]);
    if(sources.length){const list=element('div','project-help-sources');list.append(element('strong','',en?'Manual sources':'手册来源'));for(const source of sources.slice(0,12))if(source&&typeof source.title==='string')list.append(projectLink(source.title,source.url,options));footer.append(list);}
    const files=help?.grounding?.source_files||help?.source_files;if(Array.isArray(files)&&files.length){const audit=element('details','project-help-audit');audit.append(element('summary','',en?'Reviewed implementation basis':'已审阅实现依据'));const list=element('ul');for(const file of files.slice(0,16))if(typeof file?.path==='string')list.append(element('li','',`${file.path}${file.exists===false?(en?' · unavailable':' · 不可用'):''}${file.matches_reviewed===false?(en?' · changed since review':' · 与审阅版本不同'):''}`));audit.append(list);footer.append(audit);}
    if(Number.isSafeInteger(selector.generation_attempts)&&selector.generation_attempts>0)footer.append(element('span','',`${en?'Topic-match generation attempts':'主题匹配生成尝试'}: ${selector.generation_attempts}`));
    card.append(footer);return card;
  }
  function tools(options={}) {
    const language=options.language==='en'?'en':'zh',index=language==='zh'?0:1;
    const t=key=>labels[key]?.[index]||key;
    const number=value=>new Intl.NumberFormat(language==='zh'?'zh-CN':'en-US',{maximumFractionDigits:4}).format(value);
    function value(record) {
      if(record?.value===null||record?.value===undefined)return t('missing');
      if(typeof record.value!=='number'||!Number.isFinite(record.value))return typeof record.value==='object'?JSON.stringify(record.value):String(record.value);
      const unit=record.unit;let text=number(unit==='fraction'?record.value*100:record.value);
      if(['fraction','percent'].includes(unit))return text+'%';
      if(unit==='percentage_points')return text+' '+t('points');
      if(unit==='volatility_points')return text+' '+t('volatility');
      if(unit==='contracts')return text+' '+t('contracts');
      return text+(unit&&!['number','count','ratio'].includes(unit)?' '+unit:'');
    }
    function time(stamp) {const date=new Date(stamp||'');return Number.isNaN(date.getTime())?t('missing'):date.toISOString().replace('T',' ').replace('.000Z',' UTC').replace('Z',' UTC');}
    function reason(record) {
      if(typeof record.reason_text==='string'&&record.reason_text.trim())return record.reason_text;
      return reasons[record.reason]?.[index]||record.reason||t('incomparable');
    }
    return {language,index,t,number,value,time,reason};
  }
  function renderChange(record, options) {
    const {t,value}=tools(options),list=element('dl','analysis-change-values');
    for(const [key,label] of [['before','before'],['after','after'],['delta','delta']]) {
      const field=element('div');let text;
      if(key==='delta'&&record.status!=='comparable')text=t('incomparable');
      else {text=value({value:record[key],unit:key==='delta'?record.delta_unit:record.unit});if(key==='delta'&&Number.isFinite(record.delta)&&record.delta>0)text='+'+text;}
      field.append(element('dt','',t(label)),element('dd','',text));list.append(field);
    }return list;
  }
  function analysisParts(context,options={}) {
    const {t,time,value,reason,language}=tools(options),wrapper=element('section','message-analysis-context');
    wrapper.dataset.analysisId=context.analysis_id||'';
    wrapper.append(element('h3','',context.analysis_kind==='historical_options'?t('period'):t('scope')));
    if(options.renderMetadata)options.renderMetadata(wrapper,context);
    else {
    if(context.period)wrapper.append(element('strong','analysis-history-period',`${context.period.start||'—'} → ${context.period.end||'—'}`));
    wrapper.append(element('p','analysis-source',`${t('source')} · ${context.source_label||context.source||t('missing')}`),element('p','analysis-time',`${t('saved')} · ${time(context.captured_at)}`));
    if(Array.isArray(context.scopes))for(const scope of context.scopes) {
      const text=[scope.symbol,scope.expiry,scope.market_data_status,scope.received_at?time(scope.received_at):null].filter(Boolean).join(' · ');
      wrapper.append(element('p','analysis-scope',text));
      if(scope.reference_basis==='close')wrapper.append(element('small','analysis-reference-note',language==='zh'?'使用历史收盘参考选择样本，不是当前双边报价。':'Historical closing reference selected the sample; it is not current BBO.'));
    }
    const note=element('p','analysis-snapshot-note',context.notice||(context.analysis_kind==='historical_options'?t('historical'):t('quoteNotice')));
    if(context.analysis_kind!=='historical_options'){note.dataset.capturedAt=context.captured_at||'';note.dataset.stale=String(Boolean(context.stale));}wrapper.append(note);
    const stamp=Date.parse(context.captured_at||'');
    if(context.analysis_kind!=='historical_options'&&(context.stale||(Number.isFinite(stamp)&&Date.now()-stamp>30000)))wrapper.append(element('p','analysis-stale',t('stale')));
    }
    const comparison=context.refresh_comparison;
    if(comparison) {
      const section=element('section','analysis-refresh-comparison');section.dataset.status=comparison.status||'incomparable';section.append(element('h4','',t('comparison')));
      if(comparison.summary)section.append(element('p','analysis-comparison-summary',comparison.summary));
      for(const scope of comparison.scopes||[]) {
        const group=element('section','analysis-change-scope');group.dataset.scopeId=scope.id||'';group.append(element('h5','',[scope.symbol,scope.expiry].filter(Boolean).join(' · ')));
        for(const metric of scope.metrics||[]) {
          const card=element('article','analysis-change-metric');card.dataset.status=metric.status||'incomparable';card.dataset.changeId=`${scope.id||''}.${metric.id||''}`;
          card.append(element('strong','',metric.label||metric.id),renderChange(metric,options));
          if(metric.status!=='comparable')card.append(element('p','analysis-change-reason',`${t('incomparable')} · ${reason(metric)}`));
          group.append(card);
        }section.append(group);
      }wrapper.append(section);
    }
    const catalogue=element('details','message-analysis-evidence'),records=Array.isArray(context.evidence)?context.evidence:[],references=new Map();
    catalogue.append(element('summary','',`${t('evidence')} (${records.length})`));const list=element('div','analysis-evidence-list');
    for(const record of records) {
      if(!record||typeof record.id!=='string')continue;
      const item=element('article','analysis-evidence-card');item.dataset.evidenceId=record.id;item.tabIndex=-1;
      item.append(element('strong','',record.label||record.id),element('span','analysis-evidence-id',record.id),element('p','analysis-evidence-value',value(record)));
      if(record.description)item.append(element('p','',record.description));
      if(record.trading_date)item.append(element('small','analysis-evidence-time',record.trading_date));
      if(record.received_at)item.append(element('small','analysis-evidence-time',`${time(record.received_at)} · ${record.market_data_status||''}`));
      if(Object.hasOwn(record,'before')||Object.hasOwn(record,'after')) {
        item.append(renderChange(record,options),element('p','analysis-change-reason',record.status==='comparable'?t('comparable'):`${t('incomparable')} · ${reason(record)}`));
      }
      list.append(item);references.set(record.id,{analysisTarget:item,catalogue,title:record.label||record.id,number:references.size+1});
    }catalogue.append(list);wrapper.append(catalogue);
    if(context.retrieval?.hits?.length) {
      const details=element('details','message-analysis-evidence expert-retrieval');details.append(element('summary','',t('retrieval')),element('p','',t('retrievalNote')));
      const list=element('ol','expert-retrieval-hits');
      for(const hit of context.retrieval.hits.slice(0,6)) {
        const rank=hit.retrieval||hit,row=element('li');row.append(element('strong','',hit.title||hit.id),element('p','',`BM25: ${rank.bm25_rank??'—'} · ${language==='zh'?'字符':'Character'}: ${rank.char_rank??'—'} · ${rank.selection_reason||rank.method||''}`));list.append(row);
      }details.append(list);wrapper.append(details);
    }
    if(options.onOpenAnalysis&&context.analysis_id) {const button=element('button','message-action',t('view'));button.type='button';button.addEventListener('click',()=>options.onOpenAnalysis(context.analysis_id));wrapper.append(button);}
    return {wrapper,references};
  }
  function appendInline(parent,text,sources,options={},depth=0) {
    const {t}=tools(options),pattern=/\*\*([^\n]+?)\*\*|`([^`\n]+)`|\[([A-Za-z][A-Za-z0-9_.-]*)\]|\*([^*\n]+)\*/g;let at=0;
    for(const match of String(text).matchAll(pattern)) {
      parent.append(document.createTextNode(text.slice(at,match.index)));
      if(match[1]!==undefined&&depth<2) {const strong=element('strong');appendInline(strong,match[1],sources,options,depth+1);parent.append(strong);}
      else if(match[2]!==undefined)parent.append(element('code','',match[2]));
      else if(match[3]!==undefined&&sources.get(match[3])?.analysisTarget) {
        const source=sources.get(match[3]),button=element('button','inline-citation analysis-inline-citation',`${t('evidence')} ${source.number}`);button.type='button';button.dataset.evidenceId=match[3];button.title=source.title;
        button.addEventListener('click',()=>{source.catalogue.open=true;source.analysisTarget.scrollIntoView({block:'center',behavior:'auto'});source.analysisTarget.focus({preventScroll:true});});parent.append(button);
      } else if(match[3]!==undefined&&safeURL(sources.get(match[3])?.url)) {
        const source=sources.get(match[3]),link=element('a','inline-citation',source.id?.startsWith('expert.')?`${t('expert')} ${source.expertNumber}`:`[${match[3]}]`);
        link.href=safeURL(source.url);link.target='_blank';link.rel='noopener noreferrer';link.dataset.sourceId=source.id;link.title=source.title||source.id;parent.append(link);
      } else if(match[4]!==undefined)parent.append(element('em','',match[4]));
      else parent.append(document.createTextNode(match[0]));at=match.index+match[0].length;
    }parent.append(document.createTextNode(text.slice(at)));
  }
  function renderAnswer(body,content,sourceList=[],references=new Map(),options={}) {
    const sources=new Map(sourceList.filter(s=>s&&typeof s.id==='string').map((s,i)=>[s.id,{...s,expertNumber:i+1}]));for(const [id,value]of references)sources.set(id,value);
    let lines=[],list=null,fence=false,code=[];
    const flush=()=>{if(lines.length){const p=element('p');appendInline(p,lines.join('\n'),sources,options);body.append(p);lines=[];}};
    const flushCode=()=>{const pre=element('pre');pre.append(element('code','',code.join('\n')));body.append(pre);code=[];};
    for(const line of String(content||'').split('\n')) {
      if(/^\s*```/.test(line)){flush();list=null;if(fence)flushCode();fence=!fence;continue;}
      if(fence){code.push(line);continue;}if(!line.trim()){flush();list=null;continue;}
      const heading=line.match(/^#{1,4}\s+(.+)$/),item=line.match(/^\s*(?:([-*])\s+|(\d+)\.\s+)(.+)$/);
      if(heading){flush();list=null;const p=element('p','md-heading');appendInline(p,heading[1],sources,options);body.append(p);continue;}
      if(item){flush();const kind=item[2]?'OL':'UL';if(!list||list.tagName!==kind){list=element(kind.toLowerCase());body.append(list);}const li=element('li');appendInline(li,item[3],sources,options);list.append(li);continue;}
      if(/^>\s?/.test(line)){flush();list=null;const p=element('p','md-quote');appendInline(p,line.replace(/^>\s?/,''),sources,options);body.append(p);continue;}
      list=null;lines.push(line);
    }flush();if(fence)flushCode();
  }
  function renderSources(sources=[],options={}) {
    const {t}=tools(options),section=element('div','message-sources');section.append(element('div','sources-heading',t('sources')));const cards=element('div','source-cards');
    sources.forEach((source,index)=>{
      const entry=element('div','source-entry'),url=safeURL(source.url),link=element(url?'a':'div','source-card');
      if(url){link.href=url;link.target='_blank';link.rel='noopener noreferrer';}link.dataset.sourceId=source.id||'';
      link.append(element('span','source-number',source.id?.startsWith('expert.')?String(index+1):source.id||String(index+1)),element('span','',source.title||source.id||t('sources')),element('span','','↗'));entry.append(link);
      if(source.snippet){const details=element('details','source-preview');details.append(element('summary','',t('preview')),element('p','',source.snippet));if(source.publisher)details.append(element('small','',source.publisher));entry.append(details);}cards.append(entry);
    });section.append(cards);return section;
  }
  function renderMessage(message,options={}) {
    const {t,language}=tools(options),isUser=message.role==='user',help=!isUser&&extractProjectHelp(message),article=element('article',`fp-message message ${isUser?'user':'assistant'}`),sources=Array.isArray(message.sources)?message.sources:[];
    if(message.id!==undefined)article.dataset.messageId=String(message.id);
    const header=element('div','message-header');header.append(element('strong','message-author',t(isUser?'user':'assistant')));
    if(!isUser&&message.mode)header.append(element('span','message-mode',message.mode==='project-help'?(language==='en'?'Project guide · Local manual':'项目指南 · 本地手册'):message.mode==='deepseek'?'DeepSeek':message.mode==='local-lora'?t('local'):message.mode==='calculator'?t('calculator'):t('offline')));
    const body=element('div','message-body'),analysis=!isUser&&!help&&message.analysis_context?analysisParts(message.analysis_context,options):null,content=message.content||message.answer||'';
    if(isUser||help)body.textContent=content;else renderAnswer(body,content,sources,analysis?.references,options);
    if(help){body.hidden=true;body.classList.add('project-help-canonical');}
    article.append(header,body);if(analysis)article.append(analysis.wrapper);if(help)article.append(renderProjectHelp(help,options));
    if(message.warning){const warning=element('p','message-warning',help?(language==='en'?'Project-guide matching had a limitation; the card identifies the local manual used.':'教程匹配存在限制；下方卡片标明实际采用的本地手册。'):message.warning==='options_answer_validation_failed'?t('validation'):t('warning'));warning.dataset.warning=message.warning;article.append(warning);}
    if(!isUser&&!help&&sources.length)article.append(renderSources(sources,options));
    if(!isUser&&message.calculation?.values){const details=element('details','message-calculation');details.append(element('summary','',t('calculator')));for(const[key,value]of Object.entries(message.calculation.values)){const row=element('p');row.append(element('strong','',key+' · '),document.createTextNode(String(value)));details.append(row);}article.append(details);}
    return article;
  }
  window.FinPilotMessages=Object.freeze({renderMessage,renderAnalysis:(context,options)=>analysisParts(context,options).wrapper,renderAnalysisParts:analysisParts,renderAnswer,renderSources,renderProjectHelp,extractProjectHelp,projectURL,safeURL,version:'16.0.0'});
})();
