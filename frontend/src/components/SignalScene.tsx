import { useEffect, useId, useRef } from 'react';
import type * as Three from 'three';
import './signal-scene.css';

type SignalSceneProps = {
  paused: boolean;
  reducedMotion: boolean;
};

type SceneRuntime = { sync: () => void; dispose: () => void };

/** An original kinetic sculpture. Its movement is decorative, never market data. */
export default function SignalScene({ paused, reducedMotion }: SignalSceneProps) {
  const hostRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const runtimeRef = useRef<SceneRuntime | null>(null);
  const flags = useRef({ paused, reducedMotion });
  const gradientId = useId().replace(/:/g, '');

  useEffect(() => {
    flags.current = { paused, reducedMotion };
    runtimeRef.current?.sync();
  }, [paused, reducedMotion]);

  useEffect(() => {
    const hostElement = hostRef.current;
    const canvasElement = canvasRef.current;
    if (!hostElement || !canvasElement) return;
    const host: HTMLDivElement = hostElement;
    const canvas: HTMLCanvasElement = canvasElement;

    let cancelled = false;
    async function initialize() {
      // Loading the rendering engine never blocks the page or its SVG artwork.
      const [THREE, { RoomEnvironment }] = await Promise.all([
        import('three'), import('three/addons/environments/RoomEnvironment.js'),
      ]);
      if (cancelled) return;

      let disposed = false;
      let lost = false;
      let visible = true;
      let frame = 0;
      let frames = 0;
      let lastDraw = 0;
      let elapsed = 0;
      let previousTick = 0;
      let renderer: Three.WebGLRenderer | undefined;
      let environmentTarget: Three.WebGLRenderTarget | undefined;
      const geometrySet = new Set<Three.BufferGeometry>();
      const materialSet = new Set<Three.Material>();
      const textureSet = new Set<Three.Texture>();
      const motionQuery = window.matchMedia('(prefers-reduced-motion: reduce)');
      const finePointerQuery = window.matchMedia('(pointer: fine)');
      const pointer = new THREE.Vector2();
      const easedPointer = new THREE.Vector2();
      const scene = new THREE.Scene();
      const camera = new THREE.PerspectiveCamera(34, 1, 0.1, 40);
      const cameraOrigin = new THREE.Vector3(2.4, 1.05, 8.9);

      const geometry = <T extends Three.BufferGeometry>(value: T) => { geometrySet.add(value); return value; };
      const material = <T extends Three.Material>(value: T) => { materialSet.add(value); return value; };
      const texture = <T extends Three.Texture>(value: T) => { textureSet.add(value); return value; };
      const isReduced = () => flags.current.reducedMotion || motionQuery.matches;
      const isStopped = () => flags.current.paused || isReduced() || document.hidden || !visible || lost;
      const stop = () => {
        if (frame) window.cancelAnimationFrame(frame);
        frame = 0;
        previousTick = 0;
      };

      const fallback = (reason: string) => {
        stop();
        host.dataset.renderer = 'svg';
        host.dataset.fallback = reason;
        host.dataset.paused = 'true';
        host.dataset.reducedMotion = String(isReduced());
        host.dataset.ready = 'true';
      };

      try {
        // Probe first so an unsupported browser keeps the SVG without a console error.
        const context = canvas.getContext('webgl2', {
          alpha: true,
          antialias: true,
          depth: true,
          stencil: false,
          powerPreference: 'low-power',
          preserveDrawingBuffer: false,
        });
        if (!context) {
          fallback('webgl2_unavailable');
          return;
        }
        renderer = new THREE.WebGLRenderer({ canvas, context, alpha: true, antialias: true, powerPreference: 'low-power' });
        renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.5));
        renderer.setClearColor(0x000000, 0);
        renderer.outputColorSpace = THREE.SRGBColorSpace;
        renderer.toneMapping = THREE.ACESFilmicToneMapping;
        renderer.toneMappingExposure = 0.87;
        renderer.transmissionResolutionScale = 0.5;

        // Locally generated studio reflections: no HDR file, texture fetch, or model asset.
        const room = new RoomEnvironment();
        const pmrem = new THREE.PMREMGenerator(renderer);
        environmentTarget = pmrem.fromScene(room, 0.04);
        scene.environment = environmentTarget.texture;
        scene.environmentIntensity = 0.82;
        room.dispose();
        pmrem.dispose();

        scene.add(new THREE.HemisphereLight(0xfff8ec, 0x5a4128, 0.8));
        const key = new THREE.DirectionalLight(0xffedce, 3.2);
        key.position.set(-4, 5, 6);
        scene.add(key);
        const rim = new THREE.DirectionalLight(0xe8b975, 3.6);
        rim.position.set(4, 2, -4);
        scene.add(rim);
        const whiteRim = new THREE.DirectionalLight(0xffffff, 1.8);
        whiteRim.position.set(-3, -0.5, -3);
        scene.add(whiteRim);
        const underLight = new THREE.PointLight(0xffc77e, 8, 8, 2);
        underLight.position.set(0, -3, 1);
        scene.add(underLight);

        const gold = material(new THREE.MeshPhysicalMaterial({
          color: 0xc89145, metalness: 0.96, roughness: 0.27,
          clearcoat: 0.6, clearcoatRoughness: 0.18, envMapIntensity: 1.1,
        }));
        const paleGold = material(new THREE.MeshPhysicalMaterial({
          color: 0xd6b67b, metalness: 0.95, roughness: 0.18,
          clearcoat: 0.7, envMapIntensity: 1.2,
        }));
        const satinGold = material(new THREE.MeshStandardMaterial({ color: 0x9c6b2d, metalness: 0.9, roughness: 0.35 }));
        const darkMetal = material(new THREE.MeshPhysicalMaterial({
          color: 0x14110d, metalness: 0.72, roughness: 0.2, clearcoat: 0.95, clearcoatRoughness: 0.1,
        }));
        const ink = material(new THREE.MeshStandardMaterial({ color: 0x080908, metalness: 0.45, roughness: 0.32 }));
        const lineGold = material(new THREE.MeshBasicMaterial({ color: 0xdba85a, transparent: true, opacity: 0.46 }));
        const glow = material(new THREE.MeshBasicMaterial({ color: 0xffedc8 }));
        const sculpture = new THREE.Group();
        sculpture.position.y = 0.06;
        scene.add(sculpture);

        function torus(radius: number, thickness: number, mat: Three.Material, parent: Three.Object3D) {
          const mesh = new THREE.Mesh(geometry(new THREE.TorusGeometry(radius, thickness, 12, 180)), mat);
          parent.add(mesh);
          return mesh;
        }

        function line(points: number[][], thickness: number, mat: Three.Material, parent: Three.Object3D) {
          const curve = new THREE.CatmullRomCurve3(points.map(p => new THREE.Vector3(...p as [number, number, number])));
          const mesh = new THREE.Mesh(geometry(new THREE.TubeGeometry(curve, 24, thickness, 7, false)), mat);
          parent.add(mesh);
          return mesh;
        }

        function band(radius: number, width: number, depth: number, mat: Three.Material, parent: Three.Object3D) {
          const shape = new THREE.Shape();
          shape.absarc(0, 0, radius, 0, Math.PI * 2, false);
          const hole = new THREE.Path();
          hole.absarc(0, 0, radius - width, 0, Math.PI * 2, true);
          shape.holes.push(hole);
          const geo = geometry(new THREE.ExtrudeGeometry(shape, {
            depth, bevelEnabled: true, bevelSize: 0.028, bevelThickness: 0.022,
            bevelSegments: 5, steps: 1, curveSegments: 110,
          }));
          geo.translate(0, 0, -depth / 2);
          const mesh = new THREE.Mesh(geo, mat);
          parent.add(mesh);
          return mesh;
        }

        // Three intersecting bearings form a continuous, sculptural evidence engine.
        const bearingA = new THREE.Group();
        const bearingB = new THREE.Group();
        const bearingC = new THREE.Group();
        sculpture.add(bearingA, bearingB, bearingC);
        band(1.78, 0.19, 0.065, gold, bearingA);
        torus(1.787, 0.012, paleGold, bearingA).position.z = 0.042;
        torus(1.585, 0.009, satinGold, bearingA).position.z = 0.042;
        band(2.04, 0.075, 0.04, paleGold, bearingB);
        torus(2.065, 0.009, gold, bearingB);
        band(1.46, 0.11, 0.05, gold, bearingC);
        torus(1.47, 0.01, paleGold, bearingC).position.z = 0.04;

        // Fine engraved tick marks catch light without turning the object into a chart.
        const tickGeometry = geometry(new THREE.BoxGeometry(0.012, 0.045, 0.007));
        const ticks = new THREE.InstancedMesh(tickGeometry, satinGold, 48);
        const transform = new THREE.Object3D();
        for (let i = 0; i < 48; i++) {
          const angle = i / 48 * Math.PI * 2;
          transform.position.set(Math.cos(angle) * 1.66, Math.sin(angle) * 1.66, 0.057);
          transform.rotation.z = angle - Math.PI / 2;
          transform.updateMatrix();
          ticks.setMatrixAt(i, transform.matrix);
        }
        ticks.instanceMatrix.needsUpdate = true;
        ticks.computeBoundingSphere();
        bearingA.add(ticks);

        const core = new THREE.Group();
        sculpture.add(core);
        const coreSphere = new THREE.Mesh(geometry(new THREE.IcosahedronGeometry(0.89, 4)), darkMetal);
        coreSphere.scale.set(1, 1, 0.8);
        core.add(coreSphere);
        const face = new THREE.Mesh(geometry(new THREE.CylinderGeometry(0.69, 0.69, 0.07, 96)), [gold, ink, ink]);
        face.rotation.x = Math.PI / 2;
        face.position.z = 0.66;
        core.add(face);
        torus(0.695, 0.022, paleGold, core).position.z = 0.707;
        torus(0.745, 0.006, gold, core).position.z = 0.68;
        // FinPilot's abstract F / evidence-path emblem, built from physical geometry.
        const glyph = new THREE.Group();
        glyph.position.set(0.015, 0, 0.72);
        core.add(glyph);
        line([[-0.17, -0.26, 0], [-0.17, 0.27, 0], [0.2, 0.27, 0]], 0.025, paleGold, glyph);
        line([[-0.17, 0.02, 0], [0.12, 0.02, 0]], 0.025, paleGold, glyph);
        line([[0.035, -0.26, 0], [0.035, 0.27, 0]], 0.015, gold, glyph);
        const corePin = new THREE.Mesh(geometry(new THREE.SphereGeometry(0.026, 12, 8)), glow);
        corePin.position.set(0.205, 0.27, 0.005);
        glyph.add(corePin);

        // A halo of quiet paths. Every point uses a seeded, repeatable position.
        const halo = new THREE.Group();
        sculpture.add(halo);
        const outerTrack = torus(2.34, 0.005, lineGold, halo);
        outerTrack.rotation.set(0.4, -0.3, 0.22);
        outerTrack.scale.y = 0.85;
        const secondTrack = torus(2.34, 0.003, lineGold, halo);
        secondTrack.rotation.set(1.12, 0.28, -0.2);
        secondTrack.scale.y = 0.92;

        const nodes: Three.Group[] = [];
        const nodePositions = [new THREE.Vector3(-1.98, 1.0, 0.3), new THREE.Vector3(1.8, 0.72, 0.55), new THREE.Vector3(1.1, -1.98, 0.1)];
        for (let i = 0; i < 3; i++) {
          const node = new THREE.Group();
          node.position.copy(nodePositions[i]);
          const disc = new THREE.Mesh(geometry(new THREE.CylinderGeometry(0.19, 0.19, 0.065, 48)), [gold, darkMetal, darkMetal]);
          disc.rotation.x = Math.PI / 2;
          node.add(disc);
          torus(0.191, 0.009, paleGold, node).position.z = 0.041;
          if (i === 0) {
            for (let row = 0; row < 3; row++) line([[-0.07, 0.06 - row * 0.06, 0.048], [row === 2 ? 0.015 : 0.07, 0.06 - row * 0.06, 0.048]], 0.007, paleGold, node);
          } else if (i === 1) {
            line([[-0.07, 0, 0.048], [0.07, 0, 0.048]], 0.008, paleGold, node);
            line([[0, -0.07, 0.048], [0, 0.07, 0.048]], 0.008, paleGold, node);
          } else {
            torus(0.066, 0.008, paleGold, node).position.z = 0.048;
          }
          sculpture.add(node);
          nodes.push(node);
        }

        const dustCanvas = document.createElement('canvas');
        dustCanvas.width = dustCanvas.height = 32;
        const brush = dustCanvas.getContext('2d');
        if (!brush) throw new Error('Canvas2D unavailable');
        const dotGradient = brush.createRadialGradient(16, 16, 0, 16, 16, 16);
        dotGradient.addColorStop(0, 'rgba(255,238,205,1)');
        dotGradient.addColorStop(0.25, 'rgba(219,168,90,.7)');
        dotGradient.addColorStop(1, 'rgba(219,168,90,0)');
        brush.fillStyle = dotGradient;
        brush.fillRect(0, 0, 32, 32);
        const dustTexture = texture(new THREE.CanvasTexture(dustCanvas));
        const dustCoordinates: number[] = [];
        for (let i = 0; i < 95; i++) {
          const angle = i * 2.399963;
          const radius = 2.3 + ((i * 37) % 89) / 89 * 0.52;
          dustCoordinates.push(Math.cos(angle) * radius, Math.sin(angle) * radius * 0.8, Math.sin(i * 1.17) * 0.8 - 0.45);
        }
        const dustGeometry = geometry(new THREE.BufferGeometry());
        dustGeometry.setAttribute('position', new THREE.Float32BufferAttribute(dustCoordinates, 3));
        const dust = new THREE.Points(dustGeometry, material(new THREE.PointsMaterial({
          map: dustTexture, color: 0xd9b77f, size: 0.026, transparent: true,
          opacity: 0.7, depthWrite: false, blending: THREE.AdditiveBlending,
        })));
        sculpture.add(dust);

        const currentRenderer = renderer;
        function draw() {
          if (disposed || lost) return;
          const t = isReduced() ? 0 : elapsed;
          easedPointer.lerp(pointer, 0.045);
          sculpture.rotation.set(easedPointer.y * 0.07, easedPointer.x * 0.1, -0.08);
          sculpture.position.y = 0.06 + (isReduced() ? 0 : Math.sin(t * 0.6) * 0.055);
          bearingA.rotation.set(0.85 + Math.sin(t * 0.21) * 0.045, 0.2 + t * 0.055, -0.34);
          bearingB.rotation.set(0.48, -0.69 + Math.sin(t * 0.18) * 0.08, 0.43 - t * 0.045);
          bearingC.rotation.set(0.15, 0.97 + t * 0.06, 0.63);
          core.rotation.set(0.03 + Math.sin(t * 0.32) * 0.02, 0.15 + Math.sin(t * 0.27) * 0.075, -0.04);
          halo.rotation.z = t * 0.014;
          dust.rotation.z = -t * 0.014;
          nodes.forEach((node, index) => {
            node.position.copy(nodePositions[index]);
            node.position.y += Math.sin(t * 0.6 + index * 1.8) * 0.05;
            node.rotation.set(-0.03, 0.1 + Math.sin(t * 0.3 + index) * 0.08, Math.sin(t * 0.23 + index) * 0.12);
          });
          try {
            currentRenderer.render(scene, camera);
            frames++;
            host.dataset.frames = String(frames);
            host.dataset.renderer = 'webgl2';
            host.dataset.ready = 'true';
          } catch {
            lost = true;
            fallback('draw_failed');
          }
        }

        function tick(time: number) {
          frame = 0;
          if (disposed || isStopped()) return;
          if (!previousTick) previousTick = time;
          elapsed += Math.min((time - previousTick) / 1000, 0.05);
          previousTick = time;
          if (time - lastDraw >= 1000 / 30) { draw(); lastDraw = time; }
          frame = window.requestAnimationFrame(tick);
        }

        function sync() {
          if (disposed) return;
          host.dataset.paused = String(isStopped());
          host.dataset.reducedMotion = String(isReduced());
          if (isStopped()) { stop(); return; }
          if (!frame) frame = window.requestAnimationFrame(tick);
        }

        function resize() {
          const width = Math.max(1, host.clientWidth);
          const height = Math.max(1, host.clientHeight);
          const aspect = width / height;
          camera.aspect = aspect;
          camera.position.copy(cameraOrigin).multiplyScalar(Math.max(1, 0.98 / aspect));
          camera.lookAt(0, 0.08, 0);
          camera.updateProjectionMatrix();
          currentRenderer.setSize(width, height, false);
          draw();
        }

        const onPointerMove = (event: PointerEvent) => {
          if (!finePointerQuery.matches || isStopped()) return;
          const bounds = host.getBoundingClientRect();
          pointer.set(Math.max(-1, Math.min(1, (event.clientX - bounds.left) / bounds.width * 2 - 1)), Math.max(-1, Math.min(1, (event.clientY - bounds.top) / bounds.height * 2 - 1)));
        };
        const onPointerLeave = () => pointer.set(0, 0);
        const onContextLost = (event: Event) => { event.preventDefault(); lost = true; fallback('context_lost'); };
        const onMotionChange = () => { pointer.set(0, 0); easedPointer.set(0, 0); draw(); sync(); };
        const resizeObserver = new ResizeObserver(resize);
        const intersectionObserver = new IntersectionObserver(entries => { visible = entries[0]?.isIntersecting !== false; sync(); }, { threshold: 0.01 });
        resizeObserver.observe(host);
        intersectionObserver.observe(host);
        host.addEventListener('pointermove', onPointerMove, { passive: true });
        host.addEventListener('pointerleave', onPointerLeave);
        canvas.addEventListener('webglcontextlost', onContextLost);
        document.addEventListener('visibilitychange', sync);
        motionQuery.addEventListener('change', onMotionChange);
        runtimeRef.current = {
          sync,
          dispose: () => {
            disposed = true;
            stop();
            resizeObserver.disconnect();
            intersectionObserver.disconnect();
            host.removeEventListener('pointermove', onPointerMove);
            host.removeEventListener('pointerleave', onPointerLeave);
            canvas.removeEventListener('webglcontextlost', onContextLost);
            document.removeEventListener('visibilitychange', sync);
            motionQuery.removeEventListener('change', onMotionChange);
            ticks.dispose();
            geometrySet.forEach(value => value.dispose());
            materialSet.forEach(value => value.dispose());
            textureSet.forEach(value => value.dispose());
            environmentTarget?.dispose();
            scene.clear();
            currentRenderer.dispose();
            currentRenderer.forceContextLoss();
          },
        };
        resize();
        sync();
      } catch {
        fallback('renderer_unavailable');
        geometrySet.forEach(value => value.dispose());
        materialSet.forEach(value => value.dispose());
        textureSet.forEach(value => value.dispose());
        environmentTarget?.dispose();
        renderer?.dispose();
        renderer?.forceContextLoss();
      }

    }
    void initialize().catch(() => {
      if (cancelled) return;
      host.dataset.renderer = 'svg';
      host.dataset.fallback = 'engine_unavailable';
      host.dataset.paused = 'true';
      host.dataset.ready = 'true';
    });

    return () => {
      cancelled = true;
      runtimeRef.current?.dispose();
      runtimeRef.current = null;
    };
  }, []);

  return (
    <div ref={hostRef} className="fp-signal" data-testid="signal-scene" data-renderer="svg" data-frames="0" data-paused="true" data-reduced-motion={reducedMotion ? 'true' : 'false'} role="img" aria-label="金色环带围绕证据核心的原创三维雕塑。装饰动画，不代表市场数据。">
      <div className="fp-signal__aura" aria-hidden="true" />
      <svg className="fp-signal__fallback" viewBox="0 0 640 640" aria-hidden="true" focusable="false">
        <defs>
          <linearGradient id={`${gradientId}-gold`} x1="0" y1="0" x2="1" y2="1"><stop offset="0" stopColor="#4e341b" /><stop offset=".26" stopColor="#c08e43" /><stop offset=".5" stopColor="#fff0c9" /><stop offset=".73" stopColor="#c29450" /><stop offset="1" stopColor="#6f4c27" /></linearGradient>
          <radialGradient id={`${gradientId}-core`} cx=".35" cy=".25" r=".8"><stop offset="0" stopColor="#504329" /><stop offset=".3" stopColor="#171711" /><stop offset="1" stopColor="#040504" /></radialGradient>
          <radialGradient id={`${gradientId}-halo`}><stop offset="0" stopColor="#DBA85A" stopOpacity=".16" /><stop offset="1" stopColor="#DBA85A" stopOpacity="0" /></radialGradient>
        </defs>
        <circle cx="320" cy="325" r="245" fill={`url(#${gradientId}-halo)`} />
        <g fill="none" stroke="#DBA85A" strokeOpacity=".2"><ellipse cx="320" cy="320" rx="238" ry="190" transform="rotate(-31 320 320)" /><ellipse cx="320" cy="320" rx="235" ry="140" transform="rotate(64 320 320)" /></g>
        <ellipse cx="320" cy="320" rx="206" ry="130" transform="rotate(-35 320 320)" fill="none" stroke={`url(#${gradientId}-gold)`} strokeWidth="15" />
        <ellipse cx="320" cy="320" rx="198" ry="105" transform="rotate(58 320 320)" fill="none" stroke={`url(#${gradientId}-gold)`} strokeWidth="7" />
        <circle cx="320" cy="320" r="87" fill={`url(#${gradientId}-core)`} stroke={`url(#${gradientId}-gold)`} strokeWidth="2" />
        <circle cx="320" cy="320" r="66" fill="#0b0e0b" stroke="#cfab72" strokeWidth="1.4" />
        <path d="M302 348v-55h38M302 320h30M323 348v-55" fill="none" stroke={`url(#${gradientId}-gold)`} strokeWidth="5" strokeLinecap="round" />
        <path d="M168 410c60 45 169 13 243-61 74-73 99-171 56-219" fill="none" stroke={`url(#${gradientId}-gold)`} strokeWidth="11" strokeLinecap="round" />
        <g fill="#0c100d" stroke="#c7a268"><circle cx="114" cy="231" r="17" /><circle cx="529" cy="307" r="17" /><circle cx="364" cy="535" r="17" /></g>
        <g fill="none" stroke="#e6c58e" strokeWidth="1.7" strokeLinecap="round"><path d="M107 225h14m-14 6h14m-14 6h9M522 307h14m-7-7v14" /><circle cx="364" cy="535" r="6" /></g>
        <g fill="#e1bd83" opacity=".65"><circle cx="224" cy="104" r="2" /><circle cx="554" cy="422" r="1.5" /><circle cx="169" cy="496" r="1.7" /><circle cx="444" cy="125" r="1" /><circle cx="87" cy="344" r="1.4" /></g>
      </svg>
      <canvas ref={canvasRef} className="fp-signal__canvas" aria-hidden="true" />
      <div className="fp-signal__ground" aria-hidden="true" />
    </div>
  );
}
