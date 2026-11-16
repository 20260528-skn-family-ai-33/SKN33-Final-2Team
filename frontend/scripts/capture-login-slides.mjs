/* 로그인 화면 우측 블록에 넣는 화면 그림을 다시 찍는다 (#282).
   설치 없이 이 PC 의 Edge 를 창 없이 띄워 화면을 webp 로 저장한다(Node 22 이상의 내장 WebSocket 사용).

   준비: 운영 DB 가 아닌 따로 띄운 시험용 서버와 그 서버에 붙은 화면 주소, 그리고 장면마다 상태가 맞는 계정.
         - 작성 중 계정: 새 로드맵 작성을 검토·확정 화면까지 만들어 둔 계정(확정은 누르지 않은 상태) → result options review
         - 3안 생성이 막 시작된 계정 → gen
           3안 생성은 역량 테스트를 제출하는 순간 시작해 40~60초 뒤에 끝난다('다음'을 누를 때가 아니다).
           그래서 테마마다 하나씩 미리 띄워 둔다: GP_PORT 를 서로 다르게, --skin 으로 테마 하나씩, GP_WAIT_FILE=<파일 경로> 를 주면
           로그인까지 해 두고 그 파일이 생길 때까지 기다린다. 모두 '준비됨'이 나오면 테스트를 제출하고 몇 초 뒤 그 파일을 만든다
         - 학습 기록 계정: 진행 중인 로드맵과 스킬 뱃지가 있는 계정 → gantt skillmap
         - 보고서 계정: 사후 점검까지 마쳐 결과 보고서가 있는 계정(스킬 3개 이상이어야 방사형 그림이 나온다) → report
   실행: GP_ID=<사번> GP_PW=<비밀번호> node scripts/capture-login-slides.mjs <그림 이름…> [--skin=tm612,tm464]
         계정마다 한 번씩, 그 계정으로 찍을 그림 이름을 적어 실행한다.
         GP_URL(기본 http://localhost:5185) · EDGE(Edge 실행 파일 경로) · GP_PORT(Edge 연결 포트)도 환경변수로 바꾼다. 비밀번호는 파일에 적지 않는다.
   결과: src/features/auth/slides/<테마>/<그림 이름>.webp — 그림 이름·순서는 src/features/auth/loginSlides.ts 와 같아야 한다. */
import { spawn } from 'node:child_process';
import { existsSync, mkdirSync, mkdtempSync, readdirSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

const BASE = process.env.GP_URL || 'http://localhost:5185';
const EDGE = process.env.EDGE || 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe';
const PORT = Number(process.env.GP_PORT || 9333);
const OUT = fileURLToPath(new URL('../src/features/auth/slides/', import.meta.url));
const SKIN_DIR = fileURLToPath(new URL('../src/skins/', import.meta.url));

/* 찍는 크기: 데스크톱 폭(1440px) 화면에서 장면마다 필요한 부분만 4:3 으로 잘라 1280x960 그림으로 만든다.
   로그인 화면에서는 이 그림을 550px 쯤으로 줄여 보여 주므로, 화면 전체를 담으면 글자가 읽히지 않는다 → 700~900px 폭만 자른다.
   화면 높이는 위에 붙어 다니는 메뉴(테마마다 높이가 다름)가 영역에 걸리지 않을 만큼 넉넉히 둔다 */
const VIEW = { width: 1440, height: 1320 };
const MAX_WIDTH = 1280;
const RATIO = 3 / 4;
const OUT_WIDTH = 1600;
const MARGIN = 20;
const QUALITY = 82;
/** 이보다 작으면 내용 없이 바탕만 찍힌 그림으로 본다 */
const BLANK_BYTES = 8000;

/* 그림마다
   - path: 화면 주소. '@report' 이면 그 계정의 첫 결과 보고서 화면
   - top: 자르기 시작할 요소(여러 개가 맞으면 모두를 한 덩어리로) · ready: 준비됐는지 볼 선택자(없으면 top)
   - width: 자를 폭(px). 없으면 요소 폭 전체 · align: 'left'(요소 왼쪽부터, 기본) 또는 'center'(요소 가운데)
   - lift: 요소 위로 더 보여 줄 높이(px). 음수면 그만큼 아래에서 시작
   - gone: 사라질 때까지 기다릴 요소(AI 가 자료·일정을 다시 준비하는 중 표시)
   - hide: 찍을 때 감출 요소(잘린 채 걸치는 옆 카드 등) · not: 찍는 순간 있으면 안 되는 요소
   - better: 나타나면 다시 찍어 바꿀 모습들(차례대로) */
const SHOTS = [
  // 퀴즈 한 문항의 내 답·정답·해설
  { id: 'result', path: '/new/result', top: '[data-tour="result-review"] section', width: 880 },
  // 만드는 중인 모습이어야 한다: 3안 생성이 시작된 직후의 계정으로, 끝나기 전에 찍는다(끝났으면 실패로 알린다).
  // 먼저 한 장 찍어 두고, 한 안·두 안이 끝난 모습이 되면 그때마다 다시 찍어 바꾼다
  {
    id: 'gen', path: '/new/generating', top: '[data-tour="gen-wait"]', ready: '[data-tour="gen-rows"] > .agent', not: '.gen-progress.done', width: 800,
    better: ['[data-tour="gen-rows"] > .agent.ok', '[data-tour="gen-rows"] > .agent.ok ~ .agent.ok'],
  },
  // 세 코스 가운데 앞의 두 코스
  { id: 'options', path: '/new/options', top: '[data-tour="courses"]', ready: '[data-tour="materials"]', gone: '.step-bar-wait', width: 860 },
  // 주차별 일정의 앞 두 칸
  { id: 'review', path: '/new/review', top: '[data-tour="schedule"]', gone: '.rv-status, .step-bar-wait', width: 860 },
  // 일정표의 활동 이름과 앞쪽 날짜
  { id: 'gantt', path: '/', top: '.gt-card', ready: '.gt-card .gt', width: 900 },
  // 지도 한가운데(뱃지가 모인 곳)
  { id: 'skillmap', path: '/checks', top: '.sm-svg', width: 700, align: 'center', lift: -150 },
  // 사전·사후 비교 가운데 퀴즈 정답 수 카드 하나
  { id: 'report', path: '@report', top: '.rpt-viz:has(.rpt-radar) ~ .rpt-viz:has(.rpt-radar)', width: 720, align: 'center', hide: '.rpt-viz:has(.rpt-radar):has(~ .rpt-viz .rpt-radar)' },
];

/* 그림에 들어가면 안 되는 떠 있는 것들(도우미 버튼 · 테마 상자 · 알림 · 튜토리얼)과 움직임 */
const HIDE_CSS = `
  .fab, .skin-pick, .toast, [class^="tour-"], [class*=" tour-"] { display: none !important; }
  *, *::before, *::after { animation: none !important; transition: none !important; caret-color: transparent !important; }
  html { scroll-behavior: auto !important; }
`;

const args = process.argv.slice(2);
const skinArg = args.find((a) => a.startsWith('--skin='));
const skins = skinArg
  ? skinArg.slice(7).split(',')
  : readdirSync(SKIN_DIR, { withFileTypes: true }).filter((d) => d.isDirectory()).map((d) => d.name).sort();
const names = args.filter((a) => !a.startsWith('--'));
const shots = names.length ? SHOTS.filter((s) => names.includes(s.id)) : SHOTS;
if (!process.env.GP_ID || !process.env.GP_PW) throw new Error('GP_ID 와 GP_PW 환경변수가 필요합니다');
if (!shots.length) throw new Error(`모르는 그림 이름입니다. 쓸 수 있는 이름: ${SHOTS.map((s) => s.id).join(', ')}`);

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const profile = mkdtempSync(join(tmpdir(), 'gp-login-slides-'));
const edge = spawn(EDGE, [
  '--headless=new', `--remote-debugging-port=${PORT}`, `--user-data-dir=${profile}`,
  '--no-first-run', '--hide-scrollbars', `--window-size=${VIEW.width},${VIEW.height}`, 'about:blank',
], { stdio: 'ignore' });

async function connect() {
  for (let i = 0; i < 50; i += 1) {
    try {
      const tabs = await (await fetch(`http://127.0.0.1:${PORT}/json`)).json();
      const tab = tabs.find((t) => t.type === 'page');
      if (tab) return new WebSocket(tab.webSocketDebuggerUrl);
    } catch {
      /* 아직 뜨는 중 */
    }
    await sleep(200);
  }
  throw new Error('Edge 에 연결하지 못했습니다');
}

const ws = await connect();
await new Promise((ok, fail) => {
  ws.addEventListener('open', ok, { once: true });
  ws.addEventListener('error', fail, { once: true });
});
let seq = 0;
const waiting = new Map();
ws.addEventListener('message', (e) => {
  const m = JSON.parse(e.data);
  const w = waiting.get(m.id);
  if (!w) return;
  waiting.delete(m.id);
  if (m.error) w.fail(new Error(m.error.message));
  else w.ok(m.result);
});
const cdp = (method, params = {}) => new Promise((ok, fail) => {
  seq += 1;
  waiting.set(seq, { ok, fail });
  ws.send(JSON.stringify({ id: seq, method, params }));
});
async function evaluate(expression) {
  const r = await cdp('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true });
  if (r.exceptionDetails) throw new Error(r.exceptionDetails.exception?.description || r.exceptionDetails.text);
  return r.result.value;
}
async function open(url) {
  await cdp('Page.navigate', { url });
  for (let i = 0; i < 100; i += 1) {
    await sleep(100);
    if (await evaluate('document.readyState === "complete" && !!document.querySelector("#root > *")').catch(() => false)) return;
  }
  throw new Error(`화면이 열리지 않았습니다: ${url}`);
}
async function waitFor(selector, seconds = 30) {
  const q = JSON.stringify(selector);
  for (let i = 0; i < seconds * 5; i += 1) {
    if (await evaluate(`!!document.querySelector(${q})`)) return;
    await sleep(200);
  }
  throw new Error(`${selector} 가 ${seconds}초 안에 나타나지 않았습니다(${await evaluate('location.pathname')})`);
}

async function waitGone(selector, seconds) {
  const q = JSON.stringify(selector);
  // 잠깐 없다가 다시 나타나는 때가 있어 1초 동안 계속 없을 때 끝난 것으로 본다
  for (let i = 0, quiet = 0; i < seconds * 5; i += 1) {
    quiet = (await evaluate(`!!document.querySelector(${q})`)) ? 0 : quiet + 1;
    if (quiet >= 5) return;
    await sleep(200);
  }
  throw new Error(`${selector} 가 ${seconds}초 안에 사라지지 않았습니다`);
}

let failed = 0;
try {
  await cdp('Page.enable');
  await cdp('Emulation.setDeviceMetricsOverride', { ...VIEW, deviceScaleFactor: 1, mobile: false });
  await open(`${BASE}/login`);
  const status = await evaluate(`fetch('/api/v1/auth/login', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, credentials: 'include',
    body: JSON.stringify({ employeeNo: ${JSON.stringify(process.env.GP_ID)}, password: ${JSON.stringify(process.env.GP_PW)}, keepSignedIn: false }),
  }).then((r) => r.status)`);
  if (status !== 200) throw new Error(`로그인하지 못했습니다(HTTP ${status})`);

  /* 잠깐만 보이는 화면(3안 생성 중)을 여러 테마로 한꺼번에 찍을 때: 브라우저를 띄우고 로그인까지 해 둔 채로 기다렸다가,
     GP_WAIT_FILE 로 정한 파일이 생기는 순간 찍기 시작한다(브라우저가 뜨는 시간 때문에 놓치지 않게) */
  if (process.env.GP_WAIT_FILE) {
    await open(`${BASE}/login?skin=${skins[0]}`);
    console.log(`${skins.join(',')} 준비됨`);
    for (let i = 0; !existsSync(process.env.GP_WAIT_FILE); i += 1) {
      if (i > 6000) throw new Error('GP_WAIT_FILE 을 10분 동안 기다렸지만 생기지 않았습니다');
      await sleep(100);
    }
  }

  for (const skin of skins) {
    mkdirSync(join(OUT, skin), { recursive: true });
    for (const shot of shots) {
      try {
        let path = shot.path;
        if (path === '@report') {
          const id = await evaluate(`fetch('/api/v1/reports', { credentials: 'include' }).then((r) => r.json()).then((a) => a[0]?.id || '')`);
          if (!id) throw new Error('이 계정에는 결과 보고서가 없습니다');
          path = `/reports/${id}`;
        }
        // 작성 화면끼리는 저장된 단계에 따라 서로 넘겨 보낼 때가 있어 한 번 더 열어 본다
        let at = '';
        for (let tries = 0; tries < 2 && at !== path; tries += 1) {
          await open(`${BASE}${path}?skin=${skin}`);
          await sleep(300);
          at = await evaluate('location.pathname');
        }
        if (at !== path) throw new Error(`${path} 대신 ${at} 로 넘어갔습니다(그 단계까지 만들어 둔 계정인지 확인)`);
        await waitFor(shot.top);
        if (shot.ready) await waitFor(shot.ready, 120);
        if (shot.gone) await waitGone(shot.gone, 180);
        await evaluate(`(() => {
          const s = document.createElement('style');
          s.textContent = ${JSON.stringify(HIDE_CSS + (shot.hide ? `${shot.hide} { visibility: hidden !important; }` : ''))};
          document.head.append(s);
          const el = document.querySelector(${JSON.stringify(shot.top)});
          window.scrollTo(0, el.getBoundingClientRect().top + window.scrollY - ${VIEW.height - MAX_WIDTH * RATIO - MARGIN + (shot.lift || 0)});
        })()`);
        // 테마 글꼴과 스크롤에 맞춰 나타나는 덩어리가 자리 잡을 때까지
        await evaluate('document.fonts.ready.then(() => true)');
        await sleep(shot.settle ?? 1500);
        if (shot.not && await evaluate(`!!document.querySelector(${JSON.stringify(shot.not)})`)) throw new Error(`${shot.not} 상태라 찍지 않았습니다`);
        const box = await evaluate(`(() => {
          const rs = [...document.querySelectorAll(${JSON.stringify(shot.top)})].map((e) => e.getBoundingClientRect());
          const left = Math.min(...rs.map((r) => r.left));
          return { top: Math.min(...rs.map((r) => r.top)), left, width: Math.max(...rs.map((r) => r.right)) - left, sx: window.scrollX, sy: window.scrollY };
        })()`);
        // 폭을 정한 장면은 그 폭만, 아니면 요소 폭 전체를 자른다(비율은 그대로)
        const width = Math.min(shot.width || MAX_WIDTH, VIEW.width, shot.width ? VIEW.width : Math.round(box.width) + MARGIN * 2);
        const height = Math.round(width * RATIO);
        const from = shot.width && shot.align !== 'center' ? box.left - MARGIN : box.left + box.width / 2 - width / 2;
        const x = Math.max(0, Math.min(VIEW.width - width, from));
        const y = Math.max(0, Math.min(VIEW.height - height, box.top - MARGIN - (shot.lift || 0)));
        // clip 은 문서 기준 좌표라 스크롤한 만큼 더한다
        const clip = { x: x + box.sx, y: y + box.sy, width, height, scale: OUT_WIDTH / width };
        // 화면이 아직 그려지지 않은 순간에는 거의 빈 그림(수 KB)이 나온다 → 잠깐 뒤에 다시 찍는다
        let bytes = Buffer.alloc(0);
        for (let tries = 0; tries < 4 && bytes.length < BLANK_BYTES; tries += 1) {
          if (tries) await sleep(700);
          const { data } = await cdp('Page.captureScreenshot', { format: 'webp', quality: QUALITY, clip });
          bytes = Buffer.from(data, 'base64');
        }
        if (bytes.length < BLANK_BYTES) throw new Error('빈 그림만 나와 저장하지 않았습니다');
        const file = join(OUT, skin, `${shot.id}.webp`);
        writeFileSync(file, bytes);
        console.log(`${skin}/${shot.id}.webp ${(bytes.length / 1024).toFixed(0)}KB`);
        // 같은 화면이 더 보기 좋은 모습이 되면 다시 찍어 바꾼다. 그 전에 끝나 버리면(not) 앞서 찍은 것을 그대로 둔다
        const over = async () => !!shot.not && evaluate(`!!document.querySelector(${JSON.stringify(shot.not)})`);
        for (const better of shot.better || []) {
          let seen = false;
          for (let i = 0; i < 600 && !seen && !(await over()); i += 1) {
            seen = await evaluate(`!!document.querySelector(${JSON.stringify(better)})`);
            if (!seen) await sleep(150);
          }
          if (!seen) break;
          await sleep(350);
          const { data } = await cdp('Page.captureScreenshot', { format: 'webp', quality: QUALITY, clip });
          const again = Buffer.from(data, 'base64');
          // 찍는 사이에 끝났을 수 있으니 찍은 뒤에 확인하고, 끝났으면 버린다
          if (again.length < BLANK_BYTES || (await over())) break;
          writeFileSync(file, again);
          console.log(`${skin}/${shot.id}.webp ${(again.length / 1024).toFixed(0)}KB (${better})`);
        }
      } catch (error) {
        failed += 1;
        console.error(`${skin}/${shot.id}: ${error.message}`);
      }
    }
  }
} finally {
  await cdp('Browser.close').catch(() => edge.kill());
  await sleep(1500);
  try {
    rmSync(profile, { recursive: true, force: true, maxRetries: 10, retryDelay: 300 });
  } catch {
    // Edge 가 파일을 아직 쥐고 있으면 임시 폴더만 남는다(그림은 이미 저장됨)
    console.warn(`임시 폴더를 지우지 못했습니다: ${profile}`);
  }
}
if (failed) process.exitCode = 1;
