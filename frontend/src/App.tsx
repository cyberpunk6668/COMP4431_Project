import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import gsap from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';
import { ArrowRight, ArrowUpRight, AudioLines, BookOpen, Check, ChevronDown, ExternalLink, Layers3, Pause, ShieldCheck, Volume2 } from 'lucide-react';
import Hero, { Brand } from './components/Hero';

gsap.registerPlugin(ScrollTrigger);

type Source = { id: string; title: string; url: string; category?: string; snippet?: string };
type Showcase = { document_count?: number; knowledge_sources?: Source[]; training?: { completed?: boolean; steps?: number; epochs?: number; trainable_parameters?: number }; evaluation?: { test_prompts?: number; citation_base?: number; citation_lora?: number } };
type Calculation = { values: { future_value: string; total_contributions: string; interest: string }; series: { period: number; balance: string }[] };
type Avatar = { setState: (state: string) => void; setReducedMotion: (value: boolean) => void; setMode: (value: '2d' | '3d') => void; destroy: () => void; getStatus: () => { actualMode: string; renderer: string } };
declare global { interface Window { FinPilotAvatar?: { mount: (container: Element, options: { language: string; mode: string }) => Avatar } } }

const topics = [
  { id: 'diversification', label: '分散投资', prompt: '分散投资能消除所有风险吗？', answer: '分散投资可以降低集中风险，但不能保证盈利，也无法消除市场整体下跌的风险。', note: '先区分「降低风险」和「没有风险」。', url: 'https://www.investor.gov/introduction-investing/getting-started/asset-allocation', authority: 'Investor.gov' },
  { id: 'bond-rate-risk', label: '债券与利率', prompt: '为什么利率变化会影响债券价格？', answer: '市场利率上升时，现有固定利率债券的价格通常下降；期限、信用风险与产品条款同样需要考虑。', note: '一个方向关系，并不等于完整的投资判断。', url: 'https://www.investor.gov/introduction-investing/general-resources/news-alerts/alerts-bulletins/investor-bulletins-86', authority: 'Investor.gov' },
  { id: 'compound-interest', label: '理解复利', prompt: '复利为什么会让时间变得重要？', answer: '复利让已产生的利息继续参与计息。结果取决于本金、投入、期限、利率和计息频率。', note: '用确定的公式，检验一个明确的假设。', url: 'https://www.investor.gov/financial-tools-calculators/calculators/compound-interest-calculator', authority: 'Investor.gov' },
];

const stages = [
  { title: '从一个好问题开始。', kicker: '01 / ASK WITH INTENTION', description: '用自然语言提出问题。先澄清概念，再展开你的财务计划。', short: '提出问题', icon: BookOpen },
  { title: '让答案，有据可循。', kicker: '02 / FOLLOW THE EVIDENCE', description: '每个知识条目都带着来处。展开摘要，打开原文，让信息可以被核查。', short: '核查来源', icon: ShieldCheck },
  { title: '把假设，放进公式。', kicker: '03 / CHECK THE NUMBERS', description: '复利、贷款、预算由确定性代码计算。金额计算有公式，也有清楚的边界。', short: '精确计算', icon: Layers3 },
  { title: '让理解，多一种表达。', kicker: '04 / MAKE IT HUMAN', description: '虚拟教练与真实交互状态联动。可读、可听，也能按你的节奏减少动画。', short: '交互教练', icon: AudioLines },
];

function useMotionPreference() {
  const [reduced, setReduced] = useState(() => window.matchMedia('(prefers-reduced-motion: reduce)').matches);
  useEffect(() => { const media = window.matchMedia('(prefers-reduced-motion: reduce)'); const change = () => setReduced(media.matches); media.addEventListener('change', change); return () => media.removeEventListener('change', change); }, []);
  return reduced;
}

function StoryVisual({ active, paused }: { active: number; paused: boolean }) {
  return <div className="story-visual" data-stage={active}><div className="story-visual-noise" /><div className="story-visual-top"><span>FINPILOT / THE PROCESS</span><span className="live-label"><i /> 示例流程</span></div><AnimatePresence mode="wait"><motion.div key={active} className="story-frame" initial={{ opacity: paused ? 1 : 0, y: paused ? 0 : 20, filter: paused ? 'blur(0px)' : 'blur(4px)' }} animate={{ opacity: 1, y: 0, filter: 'blur(0px)' }} exit={{ opacity: paused ? 1 : 0, y: paused ? 0 : -15 }} transition={{ duration: paused ? 0 : .45 }}>
    {active === 0 && <div className="question-scene"><div className="question-spark">✦</div><span className="scene-overline">YOUR CURIOSITY, A STARTING POINT.</span><p className="scene-question">分散投资，<br />就能没有风险吗<span className="typing-caret">？</span></p><div className="question-input"><span>从一个具体问题开始</span><ArrowUpRight size={20} /></div><div className="scene-small-tags"><span>概念解释</span><span>风险意识</span><span>来源核查</span></div></div>}
    {active === 1 && <div className="source-scene"><div className="evidence-center"><ShieldCheck size={29} /><span>依据</span></div><svg className="evidence-connections" viewBox="0 0 600 360" aria-hidden="true"><path d="M300 180 120 85M300 180 475 85M300 180 470 285M300 180 115 280" /><circle cx="300" cy="180" r="110" /></svg><div className="evidence-node node-a"><span className="node-small">01 / TOPIC</span><strong>分散投资</strong><span>集中风险 ≠ 市场风险</span></div><div className="evidence-node node-b"><span className="node-small">02 / SOURCE</span><strong>Investor.gov <ArrowUpRight size={12} /></strong><span>官方投资者教育来源</span></div><div className="evidence-node node-c"><span className="node-small">03 / BOUNDARY</span><strong>不能保证盈利</strong><span>保留资料的限制条件</span></div><span className="source-scene-caption">追问「依据是什么」，而不只接受一个答案。</span></div>}
    {active === 2 && <div className="numbers-scene"><span className="scene-overline">A SCENARIO. NOT A PREDICTION.</span><p className="numbers-label">在这些明确假设下，10 年后的期末金额</p><div className="scene-number"><span>¥</span>94,111<span>.23</span></div><svg className="scene-sparkline" viewBox="0 0 500 130" aria-hidden="true"><defs><linearGradient id="scene-shade" x1="0" y1="0" x2="0" y2="1"><stop stopColor="#dba85a" stopOpacity=".16" /><stop offset="1" stopColor="#dba85a" stopOpacity="0" /></linearGradient></defs><path d="M0 125 45 119 90 110 135 100 180 90 225 78 270 65 315 51 360 38 405 23 455 9 500 0V130H0Z" fill="url(#scene-shade)" /><path d="M0 125 45 119 90 110 135 100 180 90 225 78 270 65 315 51 360 38 405 23 455 9 500 0" className="draw-line" fill="none" stroke="#dba85a" strokeWidth="2" /></svg><div className="scene-assumptions"><span>本金 10,000</span><span>月末投入 500</span><span>名义年利率 5%</span></div><small>固定月复利示例 · 不含税费与通胀</small></div>}
    {active === 3 && <div className="voice-scene"><div className="voice-orbit"><AudioLines size={47} strokeWidth={1} /><span /><span /></div><span className="scene-overline">LEARN IN YOUR OWN RHYTHM.</span><p className="voice-scene-title">有问，有答。<br />也有陪你理解的教练。</p><div className="waveform" aria-hidden="true">{Array.from({ length: 27 }, (_, i) => <i key={i} style={{ height: `${8 + Math.sin(i * 1.31) ** 2 * 28}px`, animationDelay: `${i * -.1}s` }} />)}</div><span className="voice-scene-note">支持的浏览器中可朗读回答；嘴部动作是近似演绎。</span></div>}
  </motion.div></AnimatePresence><div className="story-visual-bottom"><span>INPUT</span><span className="process-track"><i style={{ width: `${(active + 1) * 25}%` }} /></span><span>CLARITY</span></div></div>;
}

function Experience({ paused }: { paused: boolean }) {
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
  return <section id="experience" className={`experience ${paused ? 'motion-is-paused' : ''}`} ref={section}><div className="story-sticky wrap"><div className="section-topline"><span className="chapter-label">01 / THE FINPILOT WAY</span><span className="section-side-note">从疑问，到理解</span></div><div className="story-layout"><div className="story-copy"><h2>让信息有来处。<br /><span className="muted-title">让理解更清晰。</span></h2><div className="story-tabs" role="tablist" aria-label="金融学习路径">{stages.map((stage, i) => <button key={stage.kicker} data-testid={`story-step-${i}`} id={`story-tab-${i}`} role="tab" aria-selected={active === i} aria-controls="story-panel" onClick={() => choose(i)} onKeyDown={event => { if (event.key === 'ArrowDown' || event.key === 'ArrowRight') { event.preventDefault(); choose((i + 1) % 4); document.getElementById(`story-tab-${(i + 1) % 4}`)?.focus(); } if (event.key === 'ArrowUp' || event.key === 'ArrowLeft') { event.preventDefault(); choose((i + 3) % 4); document.getElementById(`story-tab-${(i + 3) % 4}`)?.focus(); } }}><span className="story-step-number">0{i + 1}</span><span>{stage.short}</span><ArrowUpRight size={16} /></button>)}</div><div className="story-stage-copy" id="story-panel" role="tabpanel" aria-labelledby={`story-tab-${active}`}><span className="scene-overline">{stages[active].kicker}</span><h3>{stages[active].title}</h3><p>{stages[active].description}</p></div><div className="story-pagination" aria-hidden="true"><span>0{active + 1}</span><i /><span>04</span></div></div><StoryVisual active={active} paused={paused} /></div><div className="story-scroll-progress" data-testid="story-progress" role="progressbar" aria-label="体验路径滚动进度" aria-valuenow={Math.round(progress * 100)} aria-valuemin={0} aria-valuemax={100}><i style={{ transform: `scaleX(${progress})` }} /></div></div></section>;
}

function Evidence({ data, paused }: { data: Showcase | null; paused: boolean }) {
  const [selected, setSelected] = useState(0);
  const topic = topics[selected];
  const source = data?.knowledge_sources?.find(value => value.id === topic.id);
  const safe = (url: string) => { try { return new URL(url).protocol === 'https:' ? url : topic.url; } catch { return topic.url; } };
  return <section className="evidence-section section-pad" id="evidence"><div className="wrap"><div className="section-topline reveal"><span className="chapter-label">02 / KNOWLEDGE, WITH A SOURCE</span><span className="section-side-note">有出处，才有继续追问的起点。</span></div><div className="evidence-layout"><div className="evidence-intro reveal"><p className="eyebrow">LESS NOISE. MORE CONTEXT.</p><h2>一个答案。<br /><span className="gold-text">清晰的来处。</span></h2><p className="section-description">金融知识不该只停留在「听起来合理」。<br />从概念走向原文，把依据和边界一同看见。</p><div className="source-count"><span>{data?.document_count ?? '—'}</span><div><strong>精选知识条目</strong><small>监管与投资者教育来源 · 固定知识快照</small></div></div><a className="text-link" href="/workspace?view=knowledge">在工作台核查来源 <ArrowUpRight size={16} /></a></div><div className="evidence-demo reveal"><div className="demo-toolbar"><span className="toolbar-dots"><i /><i /><i /></span><span>THE EVIDENCE DESK</span><span className="demo-label">内容示例</span></div><div className="evidence-topics" role="tablist" aria-label="选择知识示例">{topics.map((item, i) => <button key={item.id} data-testid={`evidence-topic-${i}`} role="tab" id={`evidence-tab-${i}`} aria-selected={i === selected} aria-controls="evidence-answer" onClick={() => setSelected(i)} onKeyDown={event => { if (event.key === "ArrowRight" || event.key === "ArrowLeft") { event.preventDefault(); const next = (i + (event.key === "ArrowRight" ? 1 : 2)) % 3; setSelected(next); document.getElementById(`evidence-tab-${next}`)?.focus(); } }}>{item.label}<span>0{i + 1}</span></button>)}</div><AnimatePresence mode="wait"><motion.div key={topic.id} id="evidence-answer" className="evidence-answer" role="tabpanel" aria-labelledby={`evidence-tab-${selected}`} initial={{ opacity: paused ? 1 : 0, y: paused ? 0 : 12 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: paused ? 1 : 0 }} transition={{ duration: paused ? 0 : .25 }}><div className="sample-user"><span>YOU ASK</span><p>{topic.prompt}</p></div><div className="sample-assistant"><span className="sample-avatar">F</span><div><span className="sample-author">FINPILOT <span>参考资料提要</span></span><p>{topic.answer}</p><span className="answer-emphasis"><span />{topic.note}</span></div></div><a className="source-reference" href={safe(source?.url || topic.url)} target="_blank" rel="noopener noreferrer"><div className="source-icon"><BookOpen size={19} /></div><div><small>ORIGINAL SOURCE / {topic.authority}</small><strong>{source?.title || topic.label}</strong></div><ExternalLink size={15} /></a><details className="source-excerpt"><summary>展开知识摘要 <ChevronDown size={14} /></summary><p>{source?.snippet || topic.answer}</p><span>这是本地知识资料展示，未在此页面调用语言模型生成回答。</span></details></motion.div></AnimatePresence><a className="evidence-demo-cta" href={`/workspace?prompt=${encodeURIComponent(topic.prompt)}`}>带着这个问题，继续探索 <ArrowRight size={18} /></a></div></div></div></section>;
}

function Planning({ paused }: { paused: boolean }) {
  const [principal, setPrincipal] = useState(10000), [monthly, setMonthly] = useState(500), [rate, setRate] = useState(5), [years, setYears] = useState(10);
  const [result, setResult] = useState<Calculation | null>(null), [loading, setLoading] = useState(true), [error, setError] = useState(''), [retry, setRetry] = useState(0);
  useEffect(() => {
    const controller = new AbortController(); setLoading(true); setError('');
    const timeout = setTimeout(async () => {
      try { const response = await fetch('/api/calculate', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ kind: 'compound', principal, monthly_contribution: monthly, annual_rate: rate, years }), signal: controller.signal }); if (!response.ok) throw new Error('计算服务暂时不可用，请稍后重试。'); const value = await response.json(); if (!controller.signal.aborted) { setResult(value); setLoading(false); } }
      catch (reason) { if (!controller.signal.aborted) { setError(reason instanceof Error ? reason.message : '无法连接计算服务'); setLoading(false); setResult(null); } }
    }, 320);
    return () => { clearTimeout(timeout); controller.abort(); };
  }, [principal, monthly, rate, years, retry]);
  const money = (value: string | number) => Number(value).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const balances = result?.series.map(point => Number(point.balance)) || [];
  const maximum = Math.max(...balances, 1);
  const line = balances.map((value, i) => `${i === 0 ? 'M' : 'L'}${40 + i / Math.max(1, balances.length - 1) * 530},${218 - value / maximum * 170}`).join(' ');
  const area = line ? `${line}L570,220L40,220Z` : '';
  return <section className="planning-section section-pad" id="planning"><div className="planning-glow" aria-hidden="true" /><div className="wrap"><div className="section-topline reveal"><span className="chapter-label">03 / SMALL INPUTS. CLEARER PLANS.</span><span className="section-side-note">把「如果」，算清楚。</span></div><div className="planning-heading reveal"><div><p className="eyebrow">A LITTLE CLARITY GOES A LONG WAY.</p><h2>时间的力量，<br /><span className="gold-text">也要看清假设。</span></h2></div><p>调一调月投入、利率和时间。<br />看见数字如何变化，<br />也记得数字没有告诉你的部分。</p></div><div className="planning-lab reveal"><div className="planning-controls"><div className="lab-heading"><span className="tiny-gold-dot" /><span>COMPOUND / 复利实验室</span><span>LIVE CALCULATION</span></div><label className="principal-label" htmlFor="calc-principal">初始本金 <span>统一货币单位</span><div className="principal-input"><span>¥</span><input id="calc-principal" data-testid="calc-principal" type="number" min="0" max="1000000000" step="1000" value={principal} onChange={event => setPrincipal(Math.min(1000000000, Math.max(0, Number(event.target.value) || 0)))} /></div></label><div className="sliders">{[{ id: 'calc-monthly', label: '每月月末投入', value: monthly, min: 0, max: 3000, step: 100, display: `¥ ${monthly.toLocaleString()}`, set: setMonthly, ends: ['¥ 0', '¥ 3,000'] }, { id: 'calc-rate', label: '名义年利率', value: rate, min: 0, max: 12, step: .25, display: `${rate}%`, set: setRate, ends: ['0%', '12%'] }, { id: 'calc-years', label: '计划期限', value: years, min: 1, max: 30, step: 1, display: `${years} 年`, set: setYears, ends: ['1 年', '30 年'] }].map(control => <div className="slider-field" key={control.id}><div><label htmlFor={control.id}>{control.label}</label><output htmlFor={control.id}>{control.display}</output></div><input id={control.id} data-testid={control.id} type="range" min={control.min} max={control.max} step={control.step} value={control.value} onChange={event => control.set(Number(event.target.value))} style={{ '--range-progress': `${(control.value - control.min) / (control.max - control.min) * 100}%` } as React.CSSProperties} /><div className="range-labels"><span>{control.ends[0]}</span><span>{control.ends[1]}</span></div></div>)}</div></div><div className={`planning-result ${loading ? 'result-is-loading' : ''}`} aria-busy={loading}><div className="result-head"><div><p>假设情景下的期末金额</p><div className="lab-result-value" data-testid="calc-result">{result ? <><span>¥</span>{money(result.values.future_value)}</> : <span className="empty-result">—</span>}</div></div><span className="result-horizon">{years}<small>YEARS</small></span></div><div id="calc-status" className="calculation-status" role="status">{error ? <><span>{error}</span><button onClick={() => setRetry(value => value + 1)}>重新计算 <ArrowRight size={13} /></button></> : loading ? '正在依据公式重新计算…' : '已按月复利与月末投入计算'}</div><div className="balance-chart" aria-label="根据计算结果绘制的期末余额变化图"><svg viewBox="0 0 600 260" role="img" aria-label="假设余额随年份变化"><defs><linearGradient id="planning-area" x1="0" y1="0" x2="0" y2="1"><stop stopColor="#dba85a" stopOpacity=".23" /><stop offset="1" stopColor="#dba85a" stopOpacity="0" /></linearGradient></defs>{[50, 105, 160, 218].map(y => <line key={y} x1="40" y1={y} x2="570" y2={y} className="chart-grid" />)}{area && <path d={area} fill="url(#planning-area)" />}{line && <path key={`${principal}-${monthly}-${rate}-${years}`} d={line} className={`chart-line ${paused ? '' : 'chart-line-animated'}`} fill="none" stroke="#dba85a" strokeWidth="2.3" pathLength="1" />}{balances.length > 0 && <circle cx="570" cy={218 - balances[balances.length - 1] / maximum * 170} r="4" fill="#DBA85A" />}<text x="40" y="247">现在</text><text x="570" y="247" textAnchor="end">第 {years} 年</text><text x="40" y="31">余额 / 同一货币单位</text></svg></div><div className="result-breakdown"><div><span><i />累计投入</span><strong>{result ? `¥ ${money(result.values.total_contributions)}` : '—'}</strong></div><div><span><i />利息部分</span><strong>{result ? `¥ ${money(result.values.interest)}` : '—'}</strong></div></div><div className="planning-disclaimer"><ShieldCheck size={15} /><p>固定利率假设，按月复利，不含税费、通胀或波动。<br />这是计算情景，不是实际收益预测。</p></div></div></div><div className="planning-footer"><span>FUTURE VALUE = PRINCIPAL + CONTRIBUTIONS + COMPOUNDING</span><a className="text-link" href="/workspace?tool=compound">打开完整计算器 <ArrowUpRight size={16} /></a></div></div></section>;
}

function Mentor({ paused, reduced }: { paused: boolean; reduced: boolean }) {
  const container = useRef<HTMLDivElement>(null), avatar = useRef<Avatar | null>(null), utterance = useRef<SpeechSynthesisUtterance | null>(null);
  const [mode, setMode] = useState<'2d' | '3d'>('3d'), [speaking, setSpeaking] = useState(false), [voiceError, setVoiceError] = useState(''), [renderer, setRenderer] = useState('2D / SVG');
  const preference = useRef({ stopped: paused || reduced, mode }); preference.current = { stopped: paused || reduced, mode };
  useEffect(() => {
    let disposed = false;
    const mount = () => { if (disposed || !container.current || avatar.current || !window.FinPilotAvatar) return; avatar.current = window.FinPilotAvatar.mount(container.current, { language: 'zh', mode: preference.current.mode }); avatar.current.setReducedMotion(preference.current.stopped); };
    const observer = new IntersectionObserver(([entry]) => {
      if (!entry.isIntersecting) return; observer.disconnect();
      if (window.FinPilotAvatar) mount();
      else { const url = '/static/avatar.js'; import(/* @vite-ignore */ url).then(mount).catch(() => { if (!disposed) setVoiceError('形象资源暂不可用，文字功能仍可在工作台使用。'); }); }
    }, { rootMargin: '200px' });
    if (container.current) observer.observe(container.current);
    const status = (event: Event) => { const detail = (event as CustomEvent).detail; if (detail?.actualMode) setRenderer(detail.actualMode === '3d' ? '3D / WEBGL2' : '2D / SVG'); };
    container.current?.addEventListener('finpilot-avatar-status', status);
    const node = container.current;
    return () => { disposed = true; observer.disconnect(); avatar.current?.destroy(); avatar.current = null; node?.removeEventListener('finpilot-avatar-status', status); if (utterance.current) window.speechSynthesis?.cancel(); };
  }, []);
  useEffect(() => { avatar.current?.setReducedMotion(paused || reduced); }, [paused, reduced]);
  useEffect(() => { avatar.current?.setMode(mode); }, [mode]);
  const speak = () => {
    if (!('speechSynthesis' in window)) { setVoiceError('当前浏览器不支持语音朗读。可以在工作台继续文字交流。'); return; }
    if (utterance.current) { window.speechSynthesis.cancel(); utterance.current = null; setSpeaking(false); avatar.current?.setState('idle'); return; }
    setVoiceError(''); const voice = new SpeechSynthesisUtterance('你好，我是 FinPilot。先看依据，再做计算。让我们一起，把复杂金融看得更清楚。');
    voice.lang = 'zh-CN'; voice.rate = .95; utterance.current = voice;
    voice.onstart = () => { if (utterance.current !== voice) return; setSpeaking(true); avatar.current?.setState('speaking'); };
    voice.onend = () => { if (utterance.current !== voice) return; utterance.current = null; setSpeaking(false); avatar.current?.setState('idle'); };
    voice.onerror = event => { if (utterance.current !== voice) return; utterance.current = null; setSpeaking(false); avatar.current?.setState('idle'); if (!['canceled', 'interrupted'].includes(event.error)) setVoiceError('未能启动朗读，请检查浏览器声音支持，或继续使用文字。'); };
    window.speechSynthesis.speak(voice);
  };
  return <div className="mentor-card"><div className="mentor-card-heading"><span><i /> MEET YOUR PILOT</span><span>{renderer}</span></div><div className="mentor-stage" ref={container} data-testid="mentor-stage" /><div className="mentor-card-bottom"><div><strong>陪你追问，也陪你理解。</strong><p>按你的节奏，找到清晰的解释。</p></div><div className="mentor-modes" aria-label="选择虚拟教练模式"><button aria-pressed={mode === '3d'} onClick={() => setMode('3d')}>3D</button><button aria-pressed={mode === '2d'} onClick={() => setMode('2d')}>2D</button></div></div><button className="mentor-listen" onClick={speak} aria-pressed={speaking}>{speaking ? <Pause size={15} /> : <Volume2 size={16} />}{speaking ? '停止朗读' : '听听 PILOT 的介绍'}<ArrowUpRight size={16} /></button><p className="mentor-note" role="status">{voiceError || '浏览器语音体验 · 嘴部动作是近似演绎'}</p></div>;
}

function Intelligence({ data, paused, reduced }: { data: Showcase | null; paused: boolean; reduced: boolean }) {
  const trained = data?.training?.completed;
  return <section className="intelligence-section section-pad" id="intelligence"><div className="wrap"><div className="section-topline reveal"><span className="chapter-label">04 / INTELLIGENCE, WITH INTENTION</span><span className="section-side-note">形象之外，是可检查的实现。</span></div><div className="intelligence-layout"><div className="intelligence-copy reveal"><p className="eyebrow">A HUMAN TOUCH. A CLEAR BOUNDARY.</p><h2>会陪伴的界面。<br /><span className="muted-title">有边界的智能。</span></h2><p className="section-description">用虚拟教练让交互状态变得直观。<br />用两种模型探索，让技术选择有据可查。</p><div className="model-paths"><a href="/workspace?engine=deepseek"><span className="model-symbol">✦</span><div><strong>DeepSeek + 知识检索</strong><p>默认云端引擎，结合知识来源整理回答。</p></div><ArrowUpRight size={17} /></a><a href="/workspace?engine=local"><span className="model-symbol outlined">F</span><div><strong>本地 LoRA 实验 <span>{trained ? '已完成训练' : '实验功能'}</span></strong><p>Qwen3-0.6B 的来源约束与回答格式适配。</p></div><ArrowUpRight size={17} /></a></div><div className="experiment-record"><div><span>{data?.training?.steps ?? '—'}</span><small>实际训练步骤</small></div><div><span>{data?.evaluation?.test_prompts ?? '—'}</span><small>留出测试问题</small></div><div><span>2<span>D</span> / 3<span>D</span></span><small>原创交互角色</small></div></div><p className="experiment-boundary">LoRA 是小样本的来源提取与格式实验，不代表开放金融问答准确率，也未证明优于 DeepSeek。模型输出仍需核查来源。</p></div><div className="reveal mentor-wrap"><Mentor paused={paused} reduced={reduced} /></div></div><div className="principles-row reveal"><div><Check size={15} /><span>金融知识学习</span></div><div><Check size={15} /><span>公式驱动计算</span></div><div><Check size={15} /><span>可核查的资料来源</span></div><div><ShieldCheck size={15} /><span>清楚表达能力边界</span></div></div></div></section>;
}

function Closing() {
  return <>
    <section className="closing-section" id="start">
      <div className="wrap closing-content">
        <h2>从你的第一个问题开始</h2>
        <a href="/workspace" className="button button-gold">进入金融学习工作台 <ArrowUpRight size={20} /></a>
      </div>
    </section>
    <footer className="site-footer wrap">
      <div className="footer-main">
        <Brand />
        <nav aria-label="页脚导航">
          <a href="/workspace">知识工作台</a>
          <a href="/workspace?tool=compound">财务计算器</a>
          <a href="/docs">API 文档</a>
        </nav>
      </div>
      <div className="footer-bottom">
        <p>COMP4431 课程项目 · 仅供金融教育</p>
        <a href="#hero">回到顶部 ↑</a>
      </div>
    </footer>
  </>;
}

export default function App() {
  const root = useRef<HTMLDivElement>(null);
  const reduced = useMotionPreference();
  const [paused, setPaused] = useState(() => localStorage.getItem('finpilot-showcase-paused') === 'true');
  const [data, setData] = useState<Showcase | null>(null);
  const stopped = paused || reduced;
  useEffect(() => { const controller = new AbortController(); fetch('/api/showcase', { signal: controller.signal }).then(response => { if (!response.ok) throw new Error('metadata unavailable'); return response.json(); }).then(value => setData(value)).catch(() => {}); return () => controller.abort(); }, []);
  useEffect(() => { document.documentElement.dataset.motion = stopped ? 'reduced' : 'full'; localStorage.setItem('finpilot-showcase-paused', String(paused)); return () => { delete document.documentElement.dataset.motion; }; }, [paused, stopped]);
  useLayoutEffect(() => {
    if (stopped) return;
    const context = gsap.context(() => {
      gsap.utils.toArray<HTMLElement>('.reveal').forEach(element => gsap.fromTo(element, { y: 30, opacity: 0 }, { y: 0, opacity: 1, duration: 1, ease: 'power3.out', scrollTrigger: { trigger: element, start: 'top 90%', once: true } }));
    }, root);
    return () => context.revert();
  }, [stopped]);
  return <div ref={root} className={`showcase ${stopped ? 'animation-paused' : ''}`}>
    <a className="skip-link" href="#hero-heading">跳到主要内容</a>
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
