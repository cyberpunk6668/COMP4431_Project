# Frontend and companion evidence

Read-only inspection of current repository and saved reports; no tests, paid model calls, broker requests or UI interactions were performed in this subtask.

## frontend_video_fallback

Source: `frontend/src/components/Hero.tsx:137–148`

Caption: A 2.5-second timeout and video errors fall back to a persistent poster.

Purpose: Direct evidence for resilient motion and reduced-motion video gating.

SHA256 of source file: `50200af71d126065340183716627bd4670c52478363728cd5834f0abfa5ab6d3`

```tsx
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
```

12 consecutive original lines. The snippet crosses the effect/render boundary; caption should identify the VideoBackground component.

## frontend_stale_calculation

Source: `web/app.js:1209–1220`

Caption: Only the latest calculation sequence may update the result and controls.

Purpose: Direct request-ID evidence for async response ordering in the actual workspace.

SHA256 of source file: `a8f93a7b1d1b404320968819b64536939cbcbc770e272bfe5a399d1d3ede0960`

```javascript
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
```

12 consecutive original lines; several source lines are long. Enable visual word wrapping in the code image rather than truncating or rewriting them.

## companion_atlas_draw

Source: `web/companion/renderer.js:136–145`

Caption: Canvas draws one exact atlas frame, loading an atlas only when needed.

Purpose: Direct Canvas2D sprite-atlas and lazy-loading evidence, including the real drawImage call.

SHA256 of source file: `8167031081412fa43a9e1b3683cb402252ee97a9e1479b5f883c213d0d98ba46`

```javascript
      const image=this.atlases.get(sprite.atlas);
      if(!image){if(!this.pending.has(sprite.atlas))this.ensureAtlas(sprite.atlas);return;}
      const bounds=this.data.atlases[sprite.atlas].frames[String(sprite.source_index)];
      if(!bounds){this.fallback('frame_missing');return;}
      const key=`${sprite.atlas}:${sprite.source_index}:${clip.flip}`;
      if(!force&&key===this.lastDraw)return;
      const c=this.context,w=this.canvas.width,h=this.canvas.height,size=Math.min(w,h);
      c.clearRect(0,0,w,h);c.save();c.imageSmoothingEnabled=true;c.imageSmoothingQuality='high';
      c.translate(w/2,h/2);if(clip.flip)c.scale(-1,1);
      c.drawImage(image,bounds.x,bounds.y,bounds.w,bounds.h,-size/2,-size/2,size,size);c.restore();
```

10 consecutive original lines; context is draw(now, force=false), beginning at line 133.

## companion_authoritative_sync

Source: `web/companion/client.js:35–44`

Caption: Clients reload the selected saved session and discard responses from older bindings.

Purpose: Direct evidence for authoritative HTTP reread and epoch/generation/session/sequence guard.

SHA256 of source file: `d18bf1f7a16dc164d6f55301fffb3f3c7232a1a2bdb9cf5495b25b6379cf5135`

```javascript
    async function sync() {
      clearTimeout(syncTimer);syncTimer = null;
      const sid = connection?.session_id;
      if (destroyed || !shouldSync(sid)) return null;
      const serial = ++syncSerial, generation = connection.generation, epoch = connection.epoch;
      const controller = new AbortController(); controllers.add(controller);
      try {
        const session = await request(`/api/sessions/${encodeURIComponent(sid)}`, {signal:controller.signal});
        if (destroyed || serial !== syncSerial || connection?.epoch !== epoch || connection?.generation !== generation || connection?.session_id !== sid || !shouldSync(sid)) return null;
        notify('onSession', session); return session;
```

10 consecutive original lines; the guard at line 43 is long, so visual wrapping is recommended.

## SSE transport alternative

`web/companion/client.js:85–94` shows EventSource creation at line 87 and reconnect reconciliation. Use it as a separately labeled range; do not concatenate it with lines 35–44.

## Current report status

```json
{
  "reports/showcase_check_v5.json": {
    "status": "passed",
    "checks": 18,
    "scope": "Saved headless Edge homepage checks; no new execution in this review."
  },
  "reports/workspace_check_v5.json": {
    "status": "passed",
    "checks": 31,
    "scope": "Calculator/isolated session CRUD actual backend; cloud generation skipped, speech hardware untested, selected events mocked."
  },
  "reports/companion_renderer_v15.json": {
    "status": "passed",
    "checks": 17,
    "scope": "Actual Edge Canvas2D pixels, lifecycle, reduced-motion, fallback, three viewports; no model/broker calls."
  },
  "reports/companion_sync_browser_v15.json": {
    "status": "passed",
    "checks": 12,
    "scope": "Real SSE/session HTTP/persistence in separate browser profiles, controlled in-process provider, not actual DeepSeek."
  },
  "reports/native_companion_v15.json": {
    "status": "passed_with_manual_hardware_limits",
    "instrumented_checks": 9,
    "physical_input_certified": false,
    "scope": "Do not claim certified physical drag, click-through or tray recovery."
  },
  "reports/pet_cloud_v15.json": {
    "status": "passed",
    "checked_at_utc": "2026-11-11T12:54:30.678673+00:00",
    "answer_turns": 2,
    "confirmed_deepseek_replies": 2,
    "new_broker_requests": 0,
    "scope": "Actual Edge workspace and actual packaged Electron renderer, real DeepSeek, previously archived IBKR history."
  },
  "reports/companion_acceptance_v15.json": {
    "status": "implemented_and_verified_with_explicit_native_manual_limits",
    "checked_at_utc": "2026-11-11T12:58:23.569584+00:00",
    "python_tests": 717,
    "final_actual_models": {
      "answer_turns": 2,
      "generations": 3,
      "schema_repairs": 1,
      "new_ib_requests": 0
    }
  }
}
```

## Recommended UI evidence without paid calls

- `http://127.0.0.1:8000/` — Capture the loaded homepage hero; then capture a 390px viewport or mobile menu. Real visual/UI evidence; a static screenshot cannot prove GSAP timing, video decode or responsive interaction by itself.
- `http://127.0.0.1:8000/#planning` — Change a local calculator input and capture the result plus visible assumptions. Only deterministic /api/calculate, not LLM or IBKR. Do not frame hypothetical balance as investment performance.
- `http://127.0.0.1:8000/workspace` — Capture the workspace and real companion, without sending a message. Demonstrates actual layout and avatar; avoid claiming this picture proves native OS click-through.
- `http://127.0.0.1:8000/pet` — Capture the pet web preview, ideally a local interaction/state without sending chat. Label browser preview, not native Electron.

## Existing final real-cloud screenshot evidence

- `reports/screenshots/pet-cloud-v15/20261111T125430678673Z/1-workspace.png` — Saved real DeepSeek workspace answer with local and expert citations. Final passed real-cloud run; archived historical data.
- `reports/screenshots/pet-cloud-v15/20261111T125430678673Z/2-native_pet.png` — Saved packaged Electron companion showing the same historical report and source controls. Owned Electron webContents capture with transparency; crop right-side panel and pet, preserve source content. Does not certify OS pointer interaction.

## Correction to earlier deck notes

The earlier failed pet_cloud_v15-20261111T124026586357Z.json is a retained historical failed attempt. It is no longer the latest result. Replace the old guide's claim that current real-cloud two-surface acceptance remains failed with the current passed final run, while retaining explicit physical/native hardware limitations.

Capture-time note: web/app.js changed concurrently after the saved acceptance run. Its unchanged calculation guard moved to line 1217. This evidence package includes full whitelisted source snapshots and does not claim prior tests reran on every concurrent whole-file revision.
