import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import gsap from 'gsap';
import { ArrowRight, Hexagon, Menu, Pause, Play, Shield, X } from 'lucide-react';
import './hero.css';

const navigation = [
  { label: '首页', href: '#hero' },
  { label: '学习路径', href: '#experience' },
  { label: '知识来源', href: '#evidence' },
  { label: '财务计算', href: '#planning' },
  { label: '期权分析', href: '/workspace?view=options' },
  { label: '模型与教练', href: '#intelligence' },
];

const videoURL = '/static/showcase/media/reference-motion.mp4';
const posterURL = '/static/showcase/media/reference-poster.webp';
const introGroups = ['header', 'eyebrow', 'heading', 'description', 'actions'] as const;
type VideoState = 'loading' | 'ready' | 'fallback' | 'static';

export function Brand() {
  return <a className="brand" href="/" aria-label="FinPilot 首页">
    <Hexagon size={32} strokeWidth={2} aria-hidden="true" />
    <span>FINPILOT</span>
  </a>;
}

function Header({ paused, reduced, toggle }: { paused: boolean; reduced: boolean; toggle: () => void }) {
  const [open, setOpen] = useState(false);
  const menuButton = useRef<HTMLButtonElement>(null);
  const menu = useRef<HTMLDivElement>(null);
  const stopped = paused || reduced;

  useEffect(() => {
    if (!open) return;
    const previous = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    const items = [menuButton.current, ...Array.from(menu.current?.querySelectorAll('a') ?? [])];
    items[1]?.focus();

    const handleKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setOpen(false);
        menuButton.current?.focus();
      }
      if (event.key !== 'Tab') return;
      const first = items[0];
      const last = items.at(-1);
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last?.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first?.focus();
      }
    };
    window.addEventListener('keydown', handleKey);
    return () => {
      document.body.style.overflow = previous;
      window.removeEventListener('keydown', handleKey);
    };
  }, [open]);

  useEffect(() => {
    const desktop = window.matchMedia('(min-width: 1024px)');
    const closeOnDesktop = () => { if (desktop.matches) setOpen(false); };
    desktop.addEventListener('change', closeOnDesktop);
    return () => desktop.removeEventListener('change', closeOnDesktop);
  }, []);

  return <header className="site-header" data-hero-enter="header">
    <div className="header-inner wrap">
      <Brand />
      <nav className="desktop-nav" aria-label="主导航">
        {navigation.map(link => <a key={link.href} href={link.href} aria-current={link.href === '#hero' ? 'page' : undefined}>{link.label}</a>)}
      </nav>
      <div className="header-actions">
        <button className="motion-button" data-testid="motion-toggle" onClick={toggle} disabled={reduced}
          aria-pressed={stopped} aria-label={reduced ? '系统已减少动态效果' : paused ? '恢复动态效果' : '暂停动态效果'}>
          {stopped ? <Play size={16} /> : <Pause size={16} />}
        </button>
        <a className="nav-workspace button-gold" href="/workspace">进入工作台 <ArrowRight size={16} /></a>
        <button className="menu-toggle" ref={menuButton} data-testid="menu-toggle" aria-expanded={open}
          aria-controls="mobile-navigation" aria-label={open ? '关闭导航' : '打开导航'} onClick={() => setOpen(value => !value)}>
          {open ? <X size={24} /> : <Menu size={24} />}
        </button>
      </div>
    </div>
    <AnimatePresence>
      {open && <motion.div ref={menu} id="mobile-navigation" data-testid="mobile-navigation" className="mobile-navigation"
        initial={{ opacity: stopped ? 1 : 0, y: stopped ? 0 : -20 }} animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: stopped ? 0 : -20 }} transition={{ duration: stopped ? 0 : .2 }}>
        <nav aria-label="移动端导航">
          {navigation.map(link => <a key={link.href} href={link.href} onClick={() => { setOpen(false); menuButton.current?.focus({ preventScroll: true }); }}>{link.label}</a>)}
          <a className="mobile-workspace button-gold" href="/workspace">进入工作台 <ArrowRight size={16} /></a>
        </nav>
      </motion.div>}
    </AnimatePresence>
  </header>;
}

function VideoBackground({ stopped, reduced, onState }: { stopped: boolean; reduced: boolean; onState: (state: VideoState) => void }) {
  const layer = useRef<HTMLDivElement>(null);
  const video = useRef<HTMLVideoElement>(null);
  const [requested, setRequested] = useState(!stopped);
  const [visible, setVisible] = useState(true);
  const [media, setMedia] = useState<'loading' | 'ready' | 'fallback'>('loading');

  useEffect(() => { if (!stopped) setRequested(true); }, [stopped]);
  useEffect(() => { if (reduced) setMedia('loading'); }, [reduced]);
  useEffect(() => {
    if (!layer.current || !('IntersectionObserver' in window)) return;
    const observer = new IntersectionObserver(([entry]) => setVisible(entry.isIntersecting));
    observer.observe(layer.current);
    return () => observer.disconnect();
  }, []);
  useEffect(() => {
    const element = video.current;
    if (!element) return;
    let active = true;
    const sync = () => {
      if (stopped || !visible || document.hidden) {
        element.pause();
      } else {
        element.play().catch(error => {
          if (active && error.name !== 'AbortError') setMedia('fallback');
        });
      }
    };
    sync();
    document.addEventListener('visibilitychange', sync);
    return () => { active = false; document.removeEventListener('visibilitychange', sync); };
  }, [requested, reduced, stopped, visible]);

  const status = stopped ? 'static' : media;
  useLayoutEffect(() => { onState(status); }, [onState, status]);
  useEffect(() => {
    if (status !== 'loading') return;
    const timer = window.setTimeout(() => setMedia('fallback'), 2500);
    return () => window.clearTimeout(timer);
  }, [status]);

  const visibleMedia = stopped && !reduced && requested && media === 'ready' ? 'ready' : status;
  return <div className="hero-background" ref={layer} aria-hidden="true" data-media={visibleMedia}>
    <img className="hero-poster" src={posterURL} alt="" fetchPriority="high" />
    {requested && !reduced && <video ref={video} className="hero-video" data-testid="hero-video"
      src={videoURL} autoPlay={!stopped} loop muted playsInline preload="auto"
      onCanPlay={() => setMedia('ready')} onError={() => setMedia('fallback')} />}
    <div className="hero-wash" />
  </div>;
}

export default function Hero({ paused, reduced, toggle }: { paused: boolean; reduced: boolean; toggle: () => void }) {
  const section = useRef<HTMLElement>(null);
  const timeline = useRef<gsap.core.Timeline | null>(null);
  const completed = useRef(false);
  const stopped = paused || reduced;
  const [videoState, setVideoState] = useState<VideoState>(stopped ? 'static' : 'loading');
  const [introState, setIntroState] = useState<'waiting' | 'playing' | 'ready'>(stopped ? 'ready' : 'waiting');

  useLayoutEffect(() => {
    if (stopped || completed.current) {
      completed.current = true;
      setIntroState('ready');
      return;
    }
    const context = gsap.context(() => {
      const intro = gsap.timeline({
        paused: true,
        defaults: { duration: 1, ease: 'power3.out' },
        onComplete: () => { completed.current = true; setIntroState('ready'); },
      });
      introGroups.forEach((group, index) => {
        const selector = `[data-hero-enter="${group}"]`;
        gsap.set(selector, { y: index === 0 ? -40 : 48, opacity: 0 });
        intro.to(selector, { y: 0, opacity: 1, clearProps: 'transform,opacity' }, (index + 2) / 10);
      });
      timeline.current = intro;
    }, section);
    return () => { timeline.current = null; context.revert(); };
  }, [stopped]);

  useLayoutEffect(() => {
    if (!stopped && !completed.current && timeline.current && videoState !== 'loading') {
      setIntroState('playing');
      timeline.current.play();
    }
  }, [stopped, videoState]);

  return <section id="hero" className="hero" ref={section} data-intro-state={introState} data-video-state={videoState}
    onFocusCapture={() => { if (!completed.current) timeline.current?.progress(1); }}>
    <VideoBackground stopped={stopped} reduced={reduced} onState={setVideoState} />
    <Header paused={paused} reduced={reduced} toggle={toggle} />
    <div className="hero-copy wrap">
      <p className="hero-eyebrow" data-hero-enter="eyebrow"><Shield size={14} /> 有据可查 · 有数可算</p>
      <h1 id="hero-heading" className="hero-title" data-hero-enter="heading" tabIndex={-1}>
        <span className="hero-title-line">把<span className="gold-text">金融</span></span>
        <span className="hero-title-line">看得更清楚</span>
      </h1>
      <p className="hero-description" data-hero-enter="description">探索有来源的金融知识，用真实公式验证你的财务假设。</p>
      <div className="hero-actions" data-hero-enter="actions">
        <a className="button button-gold" href="/workspace">开始学习 <ArrowRight size={18} /></a>
        <a className="button button-ghost" href="#experience">探索功能</a>
      </div>
    </div>
  </section>;
}
