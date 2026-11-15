import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import gsap from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';
import { ArrowRight, ArrowUpRight, AudioLines, BookOpen, Check, ChevronDown, ExternalLink, Layers3, Pause, ShieldCheck, Volume2 } from 'lucide-react';
import Hero, { Brand } from './components/Hero';
import { useLanguage } from './i18n';

gsap.registerPlugin(ScrollTrigger);

type Source = { id: string; title: string; title_zh?: string; title_en?: string; url: string; category?: string; snippet?: string; snippet_zh?: string; snippet_en?: string };
type Showcase = { document_count?: number; knowledge_sources?: Source[]; training?: { completed?: boolean; steps?: number; epochs?: number; trainable_parameters?: number }; evaluation?: { test_prompts?: number; citation_base?: number; citation_lora?: number } };
type Calculation = { values: { future_value: string; total_contributions: string; interest: string }; series: { period: number; balance: string }[] };
type Avatar = { setLanguage: (language: string) => void; setState: (state: string) => void; setReducedMotion: (value: boolean) => void; setMode: (value: '2d' | '3d') => void; destroy: () => void; getStatus: () => { actualMode: string; renderer: string } };
declare global { interface Window { FinPilotAvatar?: { mount: (container: Element, options: { language: string; mode: string }) => Avatar } } }

const getTopics = (t: (zh: string, en: string) => string) => [
  { id: 'diversification', label: t("分散投资", "Diversification"), prompt: t("分散投资能消除所有风险吗？", "Can diversification eliminate all risk?"), answer: t("分散投资可以降低集中风险，但不能保证盈利，也无法消除市场整体下跌的风险。", "Diversification can reduce concentration risk, but it cannot guarantee profits or prevent market-wide losses."), note: t("先区分「降低风险」和「没有风险」。", "Reducing risk is different from having no risk."), url: 'https://www.investor.gov/introduction-investing/getting-started/asset-allocation', authority: 'Investor.gov' },
  { id: 'bond-rate-risk', label: t("债券与利率", "Bonds and rates"), prompt: t("为什么利率变化会影响债券价格？", "Why do interest rates affect bond prices?"), answer: t("市场利率上升时，现有固定利率债券的价格通常下降；期限、信用风险与产品条款同样需要考虑。", "When market interest rates rise, prices of existing fixed-rate bonds generally fall. Maturity, credit risk and product terms also matter."), note: t("一个方向关系，并不等于完整的投资判断。", "A directional relationship is only one part of an investment decision."), url: 'https://www.investor.gov/introduction-investing/general-resources/news-alerts/alerts-bulletins/investor-bulletins-86', authority: 'Investor.gov' },
  { id: 'compound-interest', label: t("理解复利", "Compound interest"), prompt: t("复利为什么会让时间变得重要？", "Why does time matter for compound interest?"), answer: t("复利让已产生的利息继续参与计息。结果取决于本金、投入、期限、利率和计息频率。", "Compounding earns interest on earlier interest. Results depend on principal, contributions, time, rate and compounding frequency."), note: t("用确定的公式，检验一个明确的假设。", "Use a fixed formula to test a clearly stated assumption."), url: 'https://www.investor.gov/financial-tools-calculators/calculators/compound-interest-calculator', authority: 'Investor.gov' },
];

const getStages = (t: (zh: string, en: string) => string) => [
  { title: t("从一个好问题开始。", "Start with a good question."), kicker: '01 / ASK WITH INTENTION', description: t("用自然语言提出问题。先澄清概念，再展开你的财务计划。", "Ask in your own words. Clarify the concepts before developing your financial plan."), short: t("提出问题", "Ask a question"), icon: BookOpen },
  { title: t("让答案，有据可循。", "Follow the evidence."), kicker: '02 / FOLLOW THE EVIDENCE', description: t("每个知识条目都带着来处。展开摘要，打开原文，让信息可以被核查。", "Each knowledge entry has a source. Read the summary and open the original to check the information."), short: t("核查来源", "Check sources"), icon: ShieldCheck },
  { title: t("把假设，放进公式。", "Put assumptions into formulas."), kicker: '03 / CHECK THE NUMBERS', description: t("复利、贷款、预算由确定性代码计算。金额计算有公式，也有清楚的边界。", "Compound interest, loans and budgets use fixed formulas, with clearly stated assumptions and limits."), short: t("精确计算", "Check the numbers"), icon: Layers3 },
  { title: t("让理解，多一种表达。", "Another way to understand."), kicker: '04 / MAKE IT HUMAN', description: t("虚拟教练与真实交互状态联动。可读、可听，也能按你的节奏减少动画。", "The virtual mentor responds to interaction states. Read, listen or reduce animation at your own pace."), short: t("交互教练", "Meet your mentor"), icon: AudioLines },
];

function useMotionPreference() {
  const [reduced, setReduced] = useState(() => window.matchMedia('(prefers-reduced-motion: reduce)').matches);
  useEffect(() => { const media = window.matchMedia('(prefers-reduced-motion: reduce)'); const change = () => setReduced(media.matches); media.addEventListener('change', change); return () => media.removeEventListener('change', change); }, []);
  return reduced;
}

function StoryVisual({ active, paused }: { active: number; paused: boolean }) {
  const { t } = useLanguage();
  return <div className="story-visual" data-stage={active}><div className="story-visual-noise" /><div className="story-visual-top"><span>FINPILOT / THE PROCESS</span><span className="live-label"><i /> {t("示例流程", "Example process")}</span></div><AnimatePresence mode="wait"><motion.div key={active} className="story-frame" initial={{ opacity: paused ? 1 : 0, y: paused ? 0 : 20, filter: paused ? 'blur(0px)' : 'blur(4px)' }} animate={{ opacity: 1, y: 0, filter: 'blur(0px)' }} exit={{ opacity: paused ? 1 : 0, y: paused ? 0 : -15 }} transition={{ duration: paused ? 0 : .45 }}>
    {active === 0 && <div className="question-scene"><div className="question-spark">✦</div><span className="scene-overline">YOUR CURIOSITY, A STARTING POINT.</span><p className="scene-question">{t("分散投资，", "Does diversification")}<br />{t("就能没有风险吗", "remove all risk")}<span className="typing-caret">{t('？', '?')}</span></p><div className="question-input"><span>{t("从一个具体问题开始", "Start with a specific question")}</span><ArrowUpRight size={20} /></div><div className="scene-small-tags"><span>{t("概念解释", "Explain concepts")}</span><span>{t("风险意识", "Understand risk")}</span><span>{t("来源核查", "Check sources")}</span></div></div>}
    {active === 1 && <div className="source-scene"><div className="evidence-center"><ShieldCheck size={29} /><span>{t("依据", "Evidence")}</span></div><svg className="evidence-connections" viewBox="0 0 600 360" aria-hidden="true"><path d="M300 180 120 85M300 180 475 85M300 180 470 285M300 180 115 280" /><circle cx="300" cy="180" r="110" /></svg><div className="evidence-node node-a"><span className="node-small">01 / TOPIC</span><strong>{t("分散投资", "Diversification")}</strong><span>{t("集中风险 ≠ 市场风险", "Concentration risk \u2260 market risk")}</span></div><div className="evidence-node node-b"><span className="node-small">02 / SOURCE</span><strong>Investor.gov <ArrowUpRight size={12} /></strong><span>{t("官方投资者教育来源", "Official investor education")}</span></div><div className="evidence-node node-c"><span className="node-small">03 / BOUNDARY</span><strong>{t("不能保证盈利", "No guaranteed profits")}</strong><span>{t("保留资料的限制条件", "Keep the source limitations")}</span></div><span className="source-scene-caption">{t("追问「依据是什么」，而不只接受一个答案。", "Ask what supports an answer before accepting it.")}</span></div>}
    {active === 2 && <div className="numbers-scene"><span className="scene-overline">A SCENARIO. NOT A PREDICTION.</span><p className="numbers-label">{t("在这些明确假设下，10 年后的期末金额", "Ending balance after 10 years under these assumptions")}</p><div className="scene-number"><span>¥</span>94,111<span>.23</span></div><svg className="scene-sparkline" viewBox="0 0 500 130" aria-hidden="true"><defs><linearGradient id="scene-shade" x1="0" y1="0" x2="0" y2="1"><stop stopColor="#dba85a" stopOpacity=".16" /><stop offset="1" stopColor="#dba85a" stopOpacity="0" /></linearGradient></defs><path d="M0 125 45 119 90 110 135 100 180 90 225 78 270 65 315 51 360 38 405 23 455 9 500 0V130H0Z" fill="url(#scene-shade)" /><path d="M0 125 45 119 90 110 135 100 180 90 225 78 270 65 315 51 360 38 405 23 455 9 500 0" className="draw-line" fill="none" stroke="#dba85a" strokeWidth="2" /></svg><div className="scene-assumptions"><span>{t("本金 10,000", "Principal 10,000")}</span><span>{t("月末投入 500", "Month-end contribution 500")}</span><span>{t("名义年利率 5%", "Nominal annual rate 5%")}</span></div><small>{t("固定月复利示例 · 不含税费与通胀", "Fixed monthly compounding \u00b7 excludes tax, fees and inflation")}</small></div>}
    {active === 3 && <div className="voice-scene"><div className="voice-orbit"><AudioLines size={47} strokeWidth={1} /><span /><span /></div><span className="scene-overline">LEARN IN YOUR OWN RHYTHM.</span><p className="voice-scene-title">{t("有问，有答。", "Questions. Answers.")}<br />{t("也有陪你理解的教练。", "A mentor to help you understand.")}</p><div className="waveform" aria-hidden="true">{Array.from({ length: 27 }, (_, i) => <i key={i} style={{ height: `${8 + Math.sin(i * 1.31) ** 2 * 28}px`, animationDelay: `${i * -.1}s` }} />)}</div><span className="voice-scene-note">{t("支持的浏览器中可朗读回答；嘴部动作是近似演绎。", "Hear answers in supported browsers; mouth movements are approximate.")}</span></div>}
  </motion.div></AnimatePresence><div className="story-visual-bottom"><span>INPUT</span><span className="process-track"><i style={{ width: `${(active + 1) * 25}%` }} /></span><span>CLARITY</span></div></div>;
}

function Experience({ paused }: { paused: boolean }) {
  const { t } = useLanguage();
  const stages = getStages(t);
  const section = useRef<HTMLElement>(null);
  const [active, setActive] = useState(0);
  const [progress, setProgress] = useState(0);
  useEffect(() => {
    if (paused) { setProgress(value => value || .25); return; }
    let frame = 0;
    const update = () => {
      frame = 0;
      const element = section.current; if (!element) return;
      const rect = element.getBoundingClientRect();
      if (window.innerWidth < 900) return;
      const p = Math.max(0, Math.min(1, (96 - rect.top) / Math.max(1, rect.height - window.innerHeight + 96)));
      setProgress(p); setActive(Math.min(3, Math.floor(p * 4)));
    };
    const scroll = () => { if (!frame) frame = requestAnimationFrame(update); };
    window.addEventListener('scroll', scroll, { passive: true }); window.addEventListener('resize', scroll); update();
    return () => { window.removeEventListener('scroll', scroll); window.removeEventListener('resize', scroll); cancelAnimationFrame(frame); };
  }, [paused]);
  const choose = (index: number) => {
    setActive(index); setProgress((index + 1) / 4);
    if (!paused && window.innerWidth >= 900 && section.current) {
      const element = section.current;
      const y = window.scrollY + element.getBoundingClientRect().top - 96 + (element.offsetHeight - window.innerHeight + 96) * ((index + .08) / 4);
      window.scrollTo({ top: y, behavior: paused ? 'instant' : 'smooth' });
    }
  };
  return <section id="experience" className={`experience ${paused ? 'motion-is-paused' : ''}`} ref={section}><div className="story-sticky wrap"><div className="section-topline"><span className="chapter-label">01 / THE FINPILOT WAY</span><span className="section-side-note">{t("从疑问，到理解", "From questions to understanding")}</span></div><div className="story-layout"><div className="story-copy"><h2>{t("让信息有来处。", "Know the source.")}<br /><span className="muted-title">{t("让理解更清晰。", "Understand more clearly.")}</span></h2><div className="story-tabs" role="tablist" aria-label={t("金融学习路径", "Financial learning path")}>{stages.map((stage, i) => <button key={stage.kicker} data-testid={`story-step-${i}`} id={`story-tab-${i}`} role="tab" aria-selected={active === i} aria-controls="story-panel" onClick={() => choose(i)} onKeyDown={event => { if (event.key === 'ArrowDown' || event.key === 'ArrowRight') { event.preventDefault(); choose((i + 1) % 4); document.getElementById(`story-tab-${(i + 1) % 4}`)?.focus(); } if (event.key === 'ArrowUp' || event.key === 'ArrowLeft') { event.preventDefault(); choose((i + 3) % 4); document.getElementById(`story-tab-${(i + 3) % 4}`)?.focus(); } }}><span className="story-step-number">0{i + 1}</span><span>{stage.short}</span><ArrowUpRight size={16} /></button>)}</div><div className="story-stage-copy" id="story-panel" role="tabpanel" aria-labelledby={`story-tab-${active}`}><span className="scene-overline">{stages[active].kicker}</span><h3>{stages[active].title}</h3><p>{stages[active].description}</p></div><div className="story-pagination" aria-hidden="true"><span>0{active + 1}</span><i /><span>04</span></div></div><StoryVisual active={active} paused={paused} /></div><div className="story-scroll-progress" data-testid="story-progress" role="progressbar" aria-label={t("体验路径滚动进度", "Learning path scroll progress")} aria-valuenow={Math.round(progress * 100)} aria-valuemin={0} aria-valuemax={100}><i style={{ transform: `scaleX(${progress})` }} /></div></div></section>;
}

function Evidence({ data, paused }: { data: Showcase | null; paused: boolean }) {
  const { language, t } = useLanguage();
  const topics = getTopics(t);
  const [selected, setSelected] = useState(0);
  const topic = topics[selected];
  const source = data?.knowledge_sources?.find(value => value.id === topic.id);
  const safe = (url: string) => { try { return new URL(url).protocol === 'https:' ? url : topic.url; } catch { return topic.url; } };
  return <section className="evidence-section section-pad" id="evidence"><div className="wrap"><div className="section-topline reveal"><span className="chapter-label">02 / KNOWLEDGE, WITH A SOURCE</span><span className="section-side-note">{t("有出处，才有继续追问的起点。", "A source gives you a starting point for the next question.")}</span></div><div className="evidence-layout"><div className="evidence-intro reveal"><p className="eyebrow">LESS NOISE. MORE CONTEXT.</p><h2>{t("一个答案。", "An answer.")}<br /><span className="gold-text">{t("清晰的来处。", "A clear source.")}</span></h2><p className="section-description">{t("金融知识不该只停留在「听起来合理」。", "Financial knowledge should go beyond sounding plausible.")}<br />{t("从概念走向原文，把依据和边界一同看见。", "Go from concepts to original sources, with evidence and limits in view.")}</p><div className="source-count"><span>{data?.document_count ?? '—'}</span><div><strong>{t("精选知识条目", "Curated knowledge entries")}</strong><small>{t("监管与投资者教育来源 · 固定知识快照", "Regulatory and investor education sources \u00b7 a fixed snapshot")}</small></div></div><a className="text-link" href="/workspace?view=knowledge">{t("在工作台核查来源", "Check sources in the workspace")} <ArrowUpRight size={16} /></a></div><div className="evidence-demo reveal"><div className="demo-toolbar"><span className="toolbar-dots"><i /><i /><i /></span><span>THE EVIDENCE DESK</span><span className="demo-label">{t("内容示例", "Content example")}</span></div><div className="evidence-topics" role="tablist" aria-label={t("选择知识示例", "Choose a knowledge example")}>{topics.map((item, i) => <button key={item.id} data-testid={`evidence-topic-${i}`} role="tab" id={`evidence-tab-${i}`} aria-selected={i === selected} aria-controls="evidence-answer" onClick={() => setSelected(i)} onKeyDown={event => { if (event.key === "ArrowRight" || event.key === "ArrowLeft") { event.preventDefault(); const next = (i + (event.key === "ArrowRight" ? 1 : 2)) % 3; setSelected(next); document.getElementById(`evidence-tab-${next}`)?.focus(); } }}>{item.label}<span>0{i + 1}</span></button>)}</div><AnimatePresence mode="wait"><motion.div key={topic.id} id="evidence-answer" className="evidence-answer" role="tabpanel" aria-labelledby={`evidence-tab-${selected}`} initial={{ opacity: paused ? 1 : 0, y: paused ? 0 : 12 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: paused ? 1 : 0 }} transition={{ duration: paused ? 0 : .25 }}><div className="sample-user"><span>YOU ASK</span><p>{topic.prompt}</p></div><div className="sample-assistant"><span className="sample-avatar">F</span><div><span className="sample-author">FINPILOT <span>{t("参考资料提要", "Source summary")}</span></span><p>{topic.answer}</p><span className="answer-emphasis"><span />{topic.note}</span></div></div><a className="source-reference" href={safe(source?.url || topic.url)} target="_blank" rel="noopener noreferrer"><div className="source-icon"><BookOpen size={19} /></div><div><small>ORIGINAL SOURCE / {topic.authority}</small><strong>{(language === 'en' ? source?.title_en || source?.title?.split(' / ')[1] : source?.title_zh || source?.title?.split(' / ')[0]) || topic.label}</strong></div><ExternalLink size={15} /></a><details className="source-excerpt"><summary>{t("展开知识摘要", "Read the knowledge summary")} <ChevronDown size={14} /></summary><p>{(language === 'en' ? source?.snippet_en : source?.snippet_zh || source?.snippet) || topic.answer}</p><span>{t("这是本地知识资料展示，未在此页面调用语言模型生成回答。", "This displays local knowledge material. No language model is called to generate answers on this page.")}</span></details></motion.div></AnimatePresence><a className="evidence-demo-cta" href={`/workspace?prompt=${encodeURIComponent(topic.prompt)}`}>{t("带着这个问题，继续探索", "Explore this question further")} <ArrowRight size={18} /></a></div></div></div></section>;
}

function Planning({ paused }: { paused: boolean }) {
  const { t } = useLanguage();
  const [principal, setPrincipal] = useState(10000), [monthly, setMonthly] = useState(500), [rate, setRate] = useState(5), [years, setYears] = useState(10);
  const [result, setResult] = useState<Calculation | null>(null), [loading, setLoading] = useState(true), [error, setError] = useState(''), [retry, setRetry] = useState(0);
  useEffect(() => {
    const controller = new AbortController(); setLoading(true); setError('');
    const timeout = setTimeout(async () => {
      try { const response = await fetch('/api/calculate', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ kind: 'compound', principal, monthly_contribution: monthly, annual_rate: rate, years }), signal: controller.signal }); if (!response.ok) throw new Error('service'); const value = await response.json(); if (!controller.signal.aborted) { setResult(value); setLoading(false); } }
      catch (reason) { if (!controller.signal.aborted) { setError(reason instanceof Error && reason.message === 'service' ? 'service' : 'network'); setLoading(false); setResult(null); } }
    }, 320);
    return () => { clearTimeout(timeout); controller.abort(); };
  }, [principal, monthly, rate, years, retry]);
  const money = (value: string | number) => Number(value).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const balances = result?.series.map(point => Number(point.balance)) || [];
  const maximum = Math.max(...balances, 1);
  const line = balances.map((value, i) => `${i === 0 ? 'M' : 'L'}${40 + i / Math.max(1, balances.length - 1) * 530},${218 - value / maximum * 170}`).join(' ');
  const area = line ? `${line}L570,220L40,220Z` : '';
  return <section className="planning-section section-pad" id="planning"><div className="planning-glow" aria-hidden="true" /><div className="wrap"><div className="section-topline reveal"><span className="chapter-label">03 / SMALL INPUTS. CLEARER PLANS.</span><span className="section-side-note">{t("把「如果」，算清楚。", "Put numbers to your what-ifs.")}</span></div><div className="planning-heading reveal"><div><p className="eyebrow">A LITTLE CLARITY GOES A LONG WAY.</p><h2>{t("时间的力量，", "The power of time.")}<br /><span className="gold-text">{t("也要看清假设。", "With assumptions in view.")}</span></h2></div><p>{t("调一调月投入、利率和时间。", "Adjust contributions, rate and time.")}<br />{t("看见数字如何变化，", "See how the numbers change,")}<br />{t("也记得数字没有告诉你的部分。", "and remember what they leave out.")}</p></div><div className="planning-lab reveal"><div className="planning-controls"><div className="lab-heading"><span className="tiny-gold-dot" /><span>{t("COMPOUND / 复利实验室", "COMPOUND / COMPOUNDING LAB")}</span><span>LIVE CALCULATION</span></div><label className="principal-label" htmlFor="calc-principal">{t("初始本金", "Initial principal")} <span>{t("统一货币单位", "One consistent currency")}</span><div className="principal-input"><span>¥</span><input id="calc-principal" data-testid="calc-principal" type="number" min="0" max="1000000000" step="1000" value={principal} onChange={event => setPrincipal(Math.min(1000000000, Math.max(0, Number(event.target.value) || 0)))} /></div></label><div className="sliders">{[{ id: 'calc-monthly', label: t("每月月末投入", "Monthly contribution at month-end"), value: monthly, min: 0, max: 3000, step: 100, display: `¥ ${monthly.toLocaleString()}`, set: setMonthly, ends: ['¥ 0', '¥ 3,000'] }, { id: 'calc-rate', label: t("名义年利率", "Nominal annual rate"), value: rate, min: 0, max: 12, step: .25, display: `${rate}%`, set: setRate, ends: ['0%', '12%'] }, { id: 'calc-years', label: t("计划期限", "Time horizon"), value: years, min: 1, max: 30, step: 1, display: `${years} ${t('年', 'years')}`, set: setYears, ends: [t('1 年', '1 year'), t('30 年', '30 years')] }].map(control => <div className="slider-field" key={control.id}><div><label htmlFor={control.id}>{control.label}</label><output htmlFor={control.id}>{control.display}</output></div><input id={control.id} data-testid={control.id} type="range" min={control.min} max={control.max} step={control.step} value={control.value} onChange={event => control.set(Number(event.target.value))} style={{ '--range-progress': `${(control.value - control.min) / (control.max - control.min) * 100}%` } as React.CSSProperties} /><div className="range-labels"><span>{control.ends[0]}</span><span>{control.ends[1]}</span></div></div>)}</div></div><div className={`planning-result ${loading ? 'result-is-loading' : ''}`} aria-busy={loading}><div className="result-head"><div><p>{t("假设情景下的期末金额", "Ending balance in this scenario")}</p><div className="lab-result-value" data-testid="calc-result">{result ? <><span>¥</span>{money(result.values.future_value)}</> : <span className="empty-result">—</span>}</div></div><span className="result-horizon">{years}<small>YEARS</small></span></div><div id="calc-status" className="calculation-status" role="status">{error ? <><span>{error === 'service' ? t('计算服务暂时不可用，请稍后重试。', 'The calculation service is temporarily unavailable. Please retry.') : t('无法连接计算服务', 'Unable to connect to the calculation service.')}</span><button onClick={() => setRetry(value => value + 1)}>{t("重新计算", "Retry calculation")} <ArrowRight size={13} /></button></> : loading ? t('正在依据公式重新计算…', 'Recalculating with the formula…') : t('已按月复利与月末投入计算', 'Calculated with monthly compounding and month-end contributions')}</div><div className="balance-chart" aria-label={t("根据计算结果绘制的期末余额变化图", "Ending balances plotted from the calculation results")}><svg viewBox="0 0 600 260" role="img" aria-label={t("假设余额随年份变化", "Scenario balance over time")}><defs><linearGradient id="planning-area" x1="0" y1="0" x2="0" y2="1"><stop stopColor="#dba85a" stopOpacity=".23" /><stop offset="1" stopColor="#dba85a" stopOpacity="0" /></linearGradient></defs>{[50, 105, 160, 218].map(y => <line key={y} x1="40" y1={y} x2="570" y2={y} className="chart-grid" />)}{area && <path d={area} fill="url(#planning-area)" />}{line && <path key={`${principal}-${monthly}-${rate}-${years}`} d={line} className={`chart-line ${paused ? '' : 'chart-line-animated'}`} fill="none" stroke="#dba85a" strokeWidth="2.3" pathLength="1" />}{balances.length > 0 && <circle cx="570" cy={218 - balances[balances.length - 1] / maximum * 170} r="4" fill="#DBA85A" />}<text x="40" y="247">{t("现在", "Now")}</text><text x="570" y="247" textAnchor="end">{t(`第 ${years} 年`, `Year ${years}`)}</text><text x="40" y="31">{t("余额 / 同一货币单位", "Balance / same currency")}</text></svg></div><div className="result-breakdown"><div><span><i />{t("累计投入", "Total contributions")}</span><strong>{result ? `¥ ${money(result.values.total_contributions)}` : '—'}</strong></div><div><span><i />{t("利息部分", "Interest earned")}</span><strong>{result ? `¥ ${money(result.values.interest)}` : '—'}</strong></div></div><div className="planning-disclaimer"><ShieldCheck size={15} /><p>{t("固定利率假设，按月复利，不含税费、通胀或波动。", "Assumes a fixed rate and monthly compounding; excludes tax, fees, inflation and volatility.")}<br />{t("这是计算情景，不是实际收益预测。", "A calculation scenario, not a forecast of actual returns.")}</p></div></div></div><div className="planning-footer"><span>FUTURE VALUE = PRINCIPAL + CONTRIBUTIONS + COMPOUNDING</span><a className="text-link" href="/workspace?tool=compound">{t("打开完整计算器", "Open the full calculator")} <ArrowUpRight size={16} /></a></div></div></section>;
}

function Mentor({ paused, reduced }: { paused: boolean; reduced: boolean }) {
  const { language, t } = useLanguage();
  const container = useRef<HTMLDivElement>(null), avatar = useRef<Avatar | null>(null), utterance = useRef<SpeechSynthesisUtterance | null>(null);
  const [mode, setMode] = useState<'2d' | '3d'>('3d'), [speaking, setSpeaking] = useState(false), [voiceError, setVoiceError] = useState(''), [renderer, setRenderer] = useState('2D / SVG');
  const preference = useRef({ stopped: paused || reduced, mode, language }); preference.current = { stopped: paused || reduced, mode, language };
  useEffect(() => {
    let disposed = false;
    const mount = () => { if (disposed || !container.current || avatar.current || !window.FinPilotAvatar) return; avatar.current = window.FinPilotAvatar.mount(container.current, { language: preference.current.language, mode: preference.current.mode }); avatar.current.setReducedMotion(preference.current.stopped); };
    const observer = new IntersectionObserver(([entry]) => {
      if (!entry.isIntersecting) return; observer.disconnect();
      if (window.FinPilotAvatar) mount();
      else { const url = '/static/avatar.js'; import(/* @vite-ignore */ url).then(mount).catch(() => { if (!disposed) setVoiceError('avatar'); }); }
    }, { rootMargin: '200px' });
    if (container.current) observer.observe(container.current);
    const status = (event: Event) => { const detail = (event as CustomEvent).detail; if (detail?.actualMode) setRenderer(detail.actualMode === '3d' ? '3D / WEBGL2' : '2D / SVG'); };
    container.current?.addEventListener('finpilot-avatar-status', status);
    const node = container.current;
    return () => { disposed = true; observer.disconnect(); avatar.current?.destroy(); avatar.current = null; node?.removeEventListener('finpilot-avatar-status', status); if (utterance.current) window.speechSynthesis?.cancel(); };
  }, []);
  useEffect(() => { avatar.current?.setReducedMotion(paused || reduced); }, [paused, reduced]);
  useEffect(() => { avatar.current?.setMode(mode); }, [mode]);
  useEffect(() => {
    avatar.current?.setLanguage(language);
    if (utterance.current) { utterance.current = null; window.speechSynthesis?.cancel(); setSpeaking(false); avatar.current?.setState('idle'); }
  }, [language]);
  const speak = () => {
    if (!('speechSynthesis' in window)) { setVoiceError('unsupported'); return; }
    if (utterance.current) { window.speechSynthesis.cancel(); utterance.current = null; setSpeaking(false); avatar.current?.setState('idle'); return; }
    setVoiceError(''); const voice = new SpeechSynthesisUtterance(t('你好，我是 FinPilot。先看依据，再做计算。让我们一起，把复杂金融看得更清楚。', 'Hello, I am FinPilot. Check the evidence, then work through the numbers. Let us make complex financial concepts easier to understand.'));
    voice.lang = language === 'en' ? 'en-US' : 'zh-CN'; voice.rate = .95; utterance.current = voice;
    voice.onstart = () => { if (utterance.current !== voice) return; setSpeaking(true); avatar.current?.setState('speaking'); };
    voice.onend = () => { if (utterance.current !== voice) return; utterance.current = null; setSpeaking(false); avatar.current?.setState('idle'); };
    voice.onerror = event => { if (utterance.current !== voice) return; utterance.current = null; setSpeaking(false); avatar.current?.setState('idle'); if (!['canceled', 'interrupted'].includes(event.error)) setVoiceError('speech'); };
    window.speechSynthesis.speak(voice);
  };
  return <div className="mentor-card"><div className="mentor-card-heading"><span><i /> MEET YOUR PILOT</span><span>{renderer}</span></div><div className="mentor-stage" ref={container} data-testid="mentor-stage" /><div className="mentor-card-bottom"><div><strong>{t("陪你追问，也陪你理解。", "Ask more. Understand more.")}</strong><p>{t("按你的节奏，找到清晰的解释。", "Find clear explanations at your own pace.")}</p></div><div className="mentor-modes" aria-label={t("选择虚拟教练模式", "Choose virtual mentor mode")}><button aria-pressed={mode === '3d'} onClick={() => setMode('3d')}>3D</button><button aria-pressed={mode === '2d'} onClick={() => setMode('2d')}>2D</button></div></div><button className="mentor-listen" onClick={speak} aria-pressed={speaking}>{speaking ? <Pause size={15} /> : <Volume2 size={16} />}{speaking ? t('停止朗读', 'Stop reading') : t('听听 PILOT 的介绍', 'Hear from PILOT')}<ArrowUpRight size={16} /></button><p className="mentor-note" role="status">{voiceError === 'avatar' ? t('形象资源暂不可用，文字功能仍可在工作台使用。', 'Avatar assets are unavailable. You can still use text in the workspace.') : voiceError === 'unsupported' ? t('当前浏览器不支持语音朗读。可以在工作台继续文字交流。', 'This browser does not support speech. Continue with text in the workspace.') : voiceError === 'speech' ? t('未能启动朗读，请检查浏览器声音支持，或继续使用文字。', 'Speech could not start. Check browser audio support or continue with text.') : t('浏览器语音体验 · 嘴部动作是近似演绎', 'Browser speech · mouth movements are approximate')}</p></div>;
}

function Intelligence({ data, paused, reduced }: { data: Showcase | null; paused: boolean; reduced: boolean }) {
  const { t } = useLanguage();
  const trained = data?.training?.completed;
  return <section className="intelligence-section section-pad" id="intelligence"><div className="wrap"><div className="section-topline reveal"><span className="chapter-label">04 / INTELLIGENCE, WITH INTENTION</span><span className="section-side-note">{t("形象之外，是可检查的实现。", "Behind the avatar, an implementation you can inspect.")}</span></div><div className="intelligence-layout"><div className="intelligence-copy reveal"><p className="eyebrow">A HUMAN TOUCH. A CLEAR BOUNDARY.</p><h2>{t("会陪伴的界面。", "A companion for learning.")}<br /><span className="muted-title">{t("有边界的智能。", "Clear limits to its abilities.")}</span></h2><p className="section-description">{t("用虚拟教练让交互状态变得直观。", "A virtual mentor makes interaction states visible.")}<br />{t("用两种模型探索，让技术选择有据可查。", "Explore two model paths with documented technical choices.")}</p><div className="model-paths"><a href="/workspace?engine=deepseek"><span className="model-symbol">✦</span><div><strong>{t("DeepSeek + 知识检索", "DeepSeek + knowledge retrieval")}</strong><p>{t("默认云端引擎，结合知识来源整理回答。", "The default cloud engine uses knowledge sources to organize answers.")}</p></div><ArrowUpRight size={17} /></a><a href="/workspace?engine=local"><span className="model-symbol outlined">F</span><div><strong>{t("本地 LoRA 实验", "Local LoRA experiment")} <span>{trained ? t('已完成训练', 'Training completed') : t('实验功能', 'Experimental')}</span></strong><p>{t("Qwen3-0.6B 的来源约束与回答格式适配。", "Source grounding and answer format adaptation for Qwen3-0.6B.")}</p></div><ArrowUpRight size={17} /></a></div><div className="experiment-record"><div><span>{data?.training?.steps ?? '—'}</span><small>{t("实际训练步骤", "Recorded training steps")}</small></div><div><span>{data?.evaluation?.test_prompts ?? '—'}</span><small>{t("留出测试问题", "Held-out test questions")}</small></div><div><span>2<span>D</span> / 3<span>D</span></span><small>{t("旧版机器人演示", "Legacy robot demo")}</small></div></div><p className="experiment-boundary">{t("LoRA 是小样本的来源提取与格式实验，不代表开放金融问答准确率，也未证明优于 DeepSeek。模型输出仍需核查来源。", "LoRA is a small-sample source extraction and formatting experiment. It does not measure accuracy on open-ended financial questions or demonstrate superiority to DeepSeek. Model output still needs source checks.")}</p></div><div className="reveal mentor-wrap"><Mentor paused={paused} reduced={reduced} /></div></div><div className="principles-row reveal"><div><Check size={15} /><span>{t("金融知识学习", "Financial education")}</span></div><div><Check size={15} /><span>{t("公式驱动计算", "Formula-based calculations")}</span></div><div><Check size={15} /><span>{t("可核查的资料来源", "Traceable sources")}</span></div><div><ShieldCheck size={15} /><span>{t("清楚表达能力边界", "Clearly stated limitations")}</span></div></div></div></section>;
}

function Closing() {
  const { t } = useLanguage();
  return <>
    <section className="closing-section" id="start">
      <div className="wrap closing-content">
        <h2>{t("从你的第一个问题开始", "Start with your first question")}</h2>
        <a href="/workspace" className="button button-gold">{t("进入金融学习工作台", "Open the learning workspace")} <ArrowUpRight size={20} /></a>
      </div>
    </section>
    <footer className="site-footer wrap">
      <div className="footer-main">
        <Brand />
        <nav aria-label={t("页脚导航", "Footer navigation")}>
          <a href="/workspace">{t("知识工作台", "Knowledge workspace")}</a>
          <a href="/workspace?tool=compound">{t("财务计算器", "Financial calculator")}</a>
          <a href="/learn">{t("期权互动演示", "Interactive options demo")}</a>
          <a href="/help">{t("使用指南", "User guide")}</a>
          <a href="/demo">{t("历史证据演示", "Historical evidence demo")}</a>
          <a href="/docs">{t("API 文档", "API documentation")}</a>
        </nav>
      </div>
      <div className="footer-bottom">
        <p>{t("COMP4431 课程项目 · 仅供金融教育", "COMP4431 course project \u00b7 financial education only")}</p>
        <a href="#hero">{t("回到顶部 ↑", "Back to top \u2191")}</a>
      </div>
    </footer>
  </>;
}

export default function App() {
  const { language, t } = useLanguage();
  const root = useRef<HTMLDivElement>(null);
  const reduced = useMotionPreference();
  const [paused, setPaused] = useState(() => localStorage.getItem('finpilot-showcase-paused') === 'true');
  const [data, setData] = useState<Showcase | null>(null);
  const stopped = paused || reduced;
  useEffect(() => { const controller = new AbortController(); fetch('/api/showcase', { signal: controller.signal }).then(response => { if (!response.ok) throw new Error('metadata unavailable'); return response.json(); }).then(value => setData(value)).catch(() => {}); return () => controller.abort(); }, []);
  useEffect(() => { document.documentElement.dataset.motion = stopped ? 'reduced' : 'full'; localStorage.setItem('finpilot-showcase-paused', String(paused)); return () => { delete document.documentElement.dataset.motion; }; }, [paused, stopped]);
  useLayoutEffect(() => {
    const frame = requestAnimationFrame(() => ScrollTrigger.refresh());
    return () => cancelAnimationFrame(frame);
  }, [language]);
  useLayoutEffect(() => {
    if (stopped) return;
    const context = gsap.context(() => {
      gsap.utils.toArray<HTMLElement>('.reveal').forEach(element => gsap.fromTo(element, { y: 30, opacity: 0 }, { y: 0, opacity: 1, duration: 1, ease: 'power3.out', scrollTrigger: { trigger: element, start: 'top 90%', once: true } }));
    }, root);
    return () => context.revert();
  }, [stopped]);
  return <div ref={root} className={`showcase ${stopped ? 'animation-paused' : ''}`}>
    <a className="skip-link" href="#hero-heading">{t("跳到主要内容", "Skip to main content")}</a>
    <main id="main-content">
      <Hero paused={paused} reduced={reduced} toggle={() => setPaused(value => !value)} />
      <Experience paused={stopped} />
      <Evidence data={data} paused={stopped} />
      <Planning paused={stopped} />
      <Intelligence data={data} paused={paused} reduced={reduced} />
    </main>
    <Closing />
  </div>;
}
