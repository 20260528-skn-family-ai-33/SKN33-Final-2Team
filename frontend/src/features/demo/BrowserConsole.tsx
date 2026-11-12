import { useEffect, useRef, useState } from 'react';
import { http } from '@/api/client';
import { accountApi } from '@/api/endpoints/account';
import { useLocation } from 'react-router';
import { limits, storeOptions, useBrowserOptions, type BrowserOptions } from '@/shared/lib/browserOptions';
import { canUseDemo } from '@/shared/lib/demoAccess';
import { ai, applySettings, checkStatus, resetConn, useAi } from '@/shared/state/ai';
import { loadDemoAccounts, signInSeq, useSession } from '@/shared/state/session';
import { useConsoleActions, type ConsoleAction } from './consoleActions';
import { RunpodSettings } from './RunpodSettings';
import { ConsoleStatus, type Capabilities } from './ConsoleStatus';
import './browserConsole.css';

const toggleText = (value: boolean) => value ? '켜짐' : '꺼짐';
const normalize = (text: string) => text.trim().toLowerCase().replace(/\s+/g, ' ');
const toggleNames = { picker: '직원선택', demo: '시연', tools: '도구' } as const;
type Command = ConsoleAction & { needsNumber?: boolean };
const numeric = [
  { name: 'timeout', alias: '대기시간', field: 'timeout', unit: '초' },
  { name: 'inputTokens', alias: '입력토큰', field: 'input', unit: '입력 토큰' },
  { name: 'outputTokens', alias: '출력토큰', field: 'output', unit: '출력 토큰' },
] as const;

export function BrowserConsole() {
  const [openedAt, setOpenedAt] = useState<string>();
  const account = useSession(s => s.account);
  const location = useLocation();
  const scope = location.key + ':' + (account?.accountType ?? 'guest');
  useEffect(() => {
    const keydown = (event: KeyboardEvent) => {
      if (event.ctrlKey && event.altKey && !event.metaKey && !event.shiftKey && event.code === 'KeyK') {
        event.preventDefault();
        if (!event.repeat) setOpenedAt(old => old === scope ? undefined : scope);
      }
    };
    window.addEventListener('keydown', keydown);
    return () => window.removeEventListener('keydown', keydown);
  }, [scope]);

  useEffect(() => {
    let revision = 0;
    return useBrowserOptions.subscribe(({ options }, prev) => {
      if (options.picker !== prev.options.picker) {
        useSession.setState({ demo: null });
        if (!useSession.getState().account) void loadDemoAccounts(true);
      }
      if (options.tools !== prev.options.tools) useAi.setState(s => ({ status: { ...s.status } }));
      const runpodChanged = options.ollamaUrl !== prev.options.ollamaUrl || options.ollamaKey !== prev.options.ollamaKey;
      if (runpodChanged && ai.choice() === 'ollama') resetConn();
      if (useSession.getState().account && (runpodChanged || options.demo !== prev.options.demo)) {
        void checkStatus({ reconnectRunpod: runpodChanged });
      }
      if (options.demo === prev.options.demo || !useSession.getState().account) return;
      if (options.demo === false) useAi.setState(s => ({ status: { ...s.status, demoMode: false }, settings: { ...s.settings, demoMock: false, failSim: {} } }));
      const seq = signInSeq(), request = ++revision;
      void accountApi.me().then(acct => {
        if (seq === signInSeq() && request === revision && acct.accountType === 'employee') applySettings(acct);
      }).catch(() => { /* 서버 응답을 받지 못하면 현재 적용된 설정으로 표시한다. */ });
    });
  }, []);
  return openedAt === scope ? <CommandDialog close={() => setOpenedAt(undefined)} /> : null;
}

function CommandDialog({ close }: { close: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [query, setQuery] = useState('');
  const [editingRunpod, setEditingRunpod] = useState<'url' | 'key'>();
  const commandInput = useRef<HTMLInputElement>(null);
  const [selected, setSelected] = useState<string>();
  const [result, setResult] = useState<{ command?: string; message: string }>();
  const running = useRef(false);
  const [caps, setCaps] = useState<Capabilities | null>();
  const options = useBrowserOptions(s => s.options);
  const screenActions = useConsoleActions(s => s.actions);
  const employee = useSession(s => s.account?.accountType === 'employee');
  useEffect(() => {
    const element = dialog.current!;
    element.showModal();
    let active = true;
    void http.get<Capabilities>('/console/capabilities').then(value => { if (active) setCaps(value); })
      .catch(() => {
        if (active) {
          setCaps(null);
          setResult(previous => previous ?? { message: '서버의 콘솔 허용 상태를 확인하지 못했습니다.' });
        }
      });
    return () => { active = false; element.close(); };
  }, []);
  const demo = caps?.demo === true && options.demo !== false;
  const prefix = normalize(query).replace(/^tokens (input|output)(?= |$)/, (_, direction: string) => direction + 'tokens');
  const commands: Command[] = [];
  const add = (name: string, alias: string, description: string, run: ConsoleAction['run']) => commands.push({ name, alias, description, run });
  function change(label: string, field: keyof BrowserOptions, value: number | boolean | undefined, unit = '') {
    const next = { ...useBrowserOptions.getState().options, [field]: value };
    if (value === undefined) delete next[field];
    storeOptions(next);
    if (typeof value === 'number') return `${label} · ${value}${unit} (브라우저에 저장됨)`;
    return `${label} · ${value === undefined ? '기본값' : toggleText(value)}`;
  }
  add('status', '설정보기', '현재 설정 보기 · 테스트 기능, 모델 제한, RunPod 연결', () => '');
  for (const field of ['picker', 'demo', 'tools'] as const) {
    const label = { picker: '로그인 직원 고르기', demo: '시연 기능', tools: '화면 시연 도구' }[field];
    for (const enabled of [true, false]) {
      add(field + (enabled ? ' on' : ' off'), toggleNames[field] + (enabled ? '켜기' : '끄기'), `이 브라우저에서 ${label}를 ${enabled ? '켭니다' : '끕니다'}.`, () => {
        if (enabled && !(field === 'tools' ? demo : caps?.[field])) return field === 'tools' ? '시연 도구를 켜려면 먼저 demo on을 실행하세요.' : '서버에서 이 기능을 허용해야 켤 수 있습니다.';
        return change(label, field, enabled);
      });
    }
  }
  for (const { name, alias, field, unit } of numeric) {
    const base = [normalize(name) + ' ', alias].find(key => prefix.startsWith(key));
    const suffix = base ? prefix.slice(base.length) : '';
    const digits = /^\d+$/.test(suffix) ? suffix : '';
    commands.push({ name: name + ' ' + (digits || '<숫자>'), alias: alias + digits, needsNumber: !digits,
      description: `명령 뒤에 한 칸 띄우고 원하는 숫자를 입력하세요 (1~${limits[field]} · ${unit}).`, run: () => {
      const number = Number(digits);
      if (!Number.isSafeInteger(number) || number < 1 || number > limits[field]) return `1~${limits[field]} 사이의 정수를 입력하세요.`;
      return change(name, field, number, field === 'timeout' ? '초' : ' 토큰');
    } });
    add(name + ' default', alias + '복원', '이 항목의 서버 기본값을 복원합니다.', () => change(name, field, undefined));
  }
  if (employee && demo) {
    for (const field of ['url', 'key'] as const) {
      add(field === 'url' ? 'runpod url' : 'runpod key', field === 'url' ? '런팟주소' : '런팟키', field === 'url' ? 'OLLAMA_BASE_URL을 입력합니다.' : 'OLLAMA_API_KEY를 가려진 입력란에서 설정합니다.', () => {
        setEditingRunpod(field);
        return '';
      });
    }
    commands.push(...screenActions);
  }
  add('runpod default', '런팟복원', 'RunPod 주소와 키를 서버 기본값으로 복원합니다.', () => {
    const next = { ...useBrowserOptions.getState().options };
    delete next.ollamaUrl;
    delete next.ollamaKey;
    storeOptions(next);
    return 'RunPod 기본값을 복원했습니다.';
  });
  add('reset', '전체초기화', '이 브라우저에 저장한 콘솔 설정을 모두 지웁니다.', () => { storeOptions({}); return '브라우저 기본값을 복원했습니다.'; });
  add('help', '도움말', '사용할 수 있는 명령과 설명을 봅니다.', () => commands.map(c => c.name + '  ' + c.description).join('\n'));
  const matches = commands.filter(c => normalize(c.name).startsWith(prefix) || c.alias.startsWith(prefix));
  const current = matches.find(c => c.name === selected) ?? matches.find(c => normalize(c.name) === prefix || c.alias === prefix) ?? (prefix ? matches[0] : undefined);
  const showOptions = result?.command !== 'status' || !!query || !!selected;
  const canGoBack = Boolean(result || editingRunpod);
  function backToCommands() {
    setResult(undefined);
    setEditingRunpod(undefined);
    setQuery('');
    setSelected(undefined);
    commandInput.current?.focus();
  }
  function complete(command: Command) {
    const [name, argument] = command.name.split(' ');
    const needsArgument = argument && !selected && !/\s/.test(query.trimStart());
    setQuery(command.needsNumber || needsArgument ? name + ' ' : command.name);
    setSelected(undefined);
    commandInput.current?.focus();
  }
  async function execute(command: Command) {
    if (command.needsNumber) {
      complete(command);
      return;
    }
    if (running.current) return;
    running.current = true;
    try {
      const output = await command.run();
      setResult({ command: command.name, message: `${command.name} · ${command.description}\n${output}` });
      setQuery('');
      setSelected(undefined);
    } catch (error) { setResult({ message: error instanceof Error ? error.message : '명령 실행에 실패했습니다.' }); }
    finally { running.current = false; }
  }
  return <dialog ref={dialog} className="browser-console" aria-label="테스트 콘솔" onCancel={event => {
    if (canGoBack) {
      event.preventDefault();
      backToCommands();
    } else close();
  }}>
    <header>
      <strong>테스트 콘솔</strong>
      <div className="console-navigation">
        {canGoBack && <button className="console-back" type="button" onClick={backToCommands}>← 명령어 목록</button>}
        <button type="button" aria-label="닫기" onClick={close}>×</button>
      </div>
    </header>
    {editingRunpod ? <RunpodSettings focus={editingRunpod} onDone={message => {
      setEditingRunpod(undefined);
      setResult({ message });
      requestAnimationFrame(() => commandInput.current?.focus());
    }} /> : <>
    <input ref={commandInput} autoFocus aria-label="명령어" role="combobox" aria-expanded={showOptions} aria-controls="console-options"
      aria-activedescendant={current ? 'console-option-' + matches.indexOf(current) : undefined}
      placeholder="예: timeout 180, inputTokens 8192" value={query} onChange={e => { setQuery(e.target.value); setSelected(undefined); }}
      onKeyDown={e => {
        if (e.nativeEvent.isComposing && e.key !== 'Tab') return;
        if ((e.key === 'Tab' && !e.shiftKey || e.key === 'Enter') && current) {
          e.preventDefault();
          if (e.repeat) return;
          if (e.key === 'Tab' && prefix !== normalize(current.name) && prefix !== current.alias) complete(current);
          else void execute(current);
        } else if (matches.length && ['ArrowUp', 'ArrowDown'].includes(e.key)) {
          e.preventDefault();
          const index = current ? matches.indexOf(current) : e.key === 'ArrowDown' ? -1 : 0;
          const next = (index + (e.key === 'ArrowDown' ? 1 : -1) + matches.length) % matches.length;
          setSelected(matches[next].name);
          document.getElementById('console-option-' + next)?.scrollIntoView({ block: 'nearest' });
        }
      }} />
    <small>↑ ↓ 선택 · Tab 자동완성 · Enter 또는 완성 후 Tab 실행 · {canGoBack ? 'Esc 목록으로' : 'Esc 닫기'}</small>
    <div role="listbox" id="console-options" aria-label="자동완성" hidden={!showOptions}>
      {matches.map((c, i) => <button key={c.name} id={'console-option-' + i} type="button" role="option"
        tabIndex={-1} aria-selected={c === current} onMouseDown={e => e.preventDefault()} onClick={() => void execute(c)}><code>{c.name}</code><span>{c.description}</span></button>)}
      {!matches.length && <span>일치하는 명령이 없습니다.</span>}
    </div>
    </>}
    {!editingRunpod && <div aria-live="polite">
      {result?.command === 'status' ? <ConsoleStatus caps={caps} options={options} demo={demo} tools={canUseDemo(demo)} />
        : result && <pre>{result.message}</pre>}
    </div>}
  </dialog>;
}
