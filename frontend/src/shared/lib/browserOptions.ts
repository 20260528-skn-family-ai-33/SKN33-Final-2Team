import { create } from 'zustand';

export const limits = { timeout: 900, input: 131072, output: 32768 } as const;
export type BrowserOptions = Partial<Record<'picker' | 'demo', boolean> & Record<keyof typeof limits, number> & Record<'ollamaUrl' | 'ollamaKey', string>>;
export type ConsoleDefaults = { picker: boolean; demo: boolean; browserOverrides?: boolean };
const key = 'growpath.browser-console.v1';

function read(): BrowserOptions {
  try {
    const raw = JSON.parse(localStorage.getItem(key) || '{}');
    const options: BrowserOptions = {};
    if (typeof raw.picker === 'boolean') options.picker = raw.picker;
    if (typeof raw.demo === 'boolean') options.demo = raw.demo;
    else if (typeof raw.tools === 'boolean') options.demo = raw.tools;
    for (const name of ['timeout', 'input', 'output'] as const) {
      if (Number.isSafeInteger(raw[name]) && raw[name] > 0 && raw[name] <= limits[name]) options[name] = raw[name];
    }
    if (typeof raw.ollamaUrl === 'string' && /^https?:\/\/[a-zA-Z0-9.:-]{1,255}$/.test(raw.ollamaUrl)) options.ollamaUrl = raw.ollamaUrl;
    if (typeof raw.ollamaKey === 'string' && /^[!-~]{1,1024}$/.test(raw.ollamaKey)) options.ollamaKey = raw.ollamaKey;
    return options;
  } catch { return {}; }
}

export const useBrowserOptions = create<{ options: BrowserOptions }>(() => ({ options: read() }));
export function storeOptions(options: BrowserOptions) {
  if (Object.keys(options).length) localStorage.setItem(key, JSON.stringify(options));
  else localStorage.removeItem(key);
  useBrowserOptions.setState({ options });
}
if (typeof window !== 'undefined' && window.addEventListener) window.addEventListener('storage', event => {
  if (event.key === key || event.key === null) useBrowserOptions.setState({ options: read() });
});

export function browserDemoEnabled(options: BrowserOptions): boolean {
  return options.demo ?? ((import.meta.env.VITE_DEMO_TOOLS ?? '').trim().toLowerCase() === 'on');
}

export function consoleEnabled(field: 'picker' | 'demo', options: BrowserOptions, defaults?: ConsoleDefaults | null): boolean {
  if (!defaults) return false;
  const override = options[field];
  if (override !== undefined) return override && (defaults.browserOverrides === true || defaults[field]);
  return defaults[field] && (field === 'picker' || browserDemoEnabled(options));
}

export function activeRunpodSettings(options: BrowserOptions): Pick<BrowserOptions, 'ollamaUrl' | 'ollamaKey'> {
  return browserDemoEnabled(options) ? options : {};
}

export function browserHeaders(): Record<string, string> {
  const { options } = useBrowserOptions.getState();
  const headers: Record<string, string> = {};
  if (options.picker !== undefined) headers['X-GrowPath-picker'] = options.picker ? 'on' : 'off';
  if (!browserDemoEnabled(options)) {
    headers['X-GrowPath-demo'] = 'off';
    return headers;
  }
  if (options.demo === true) headers['X-GrowPath-demo'] = 'on';
  for (const name of ['input', 'output', 'timeout'] as const) {
    if (options[name] !== undefined) headers['X-GrowPath-' + name] = String(options[name]);
  }
  const { ollamaUrl, ollamaKey } = options;
  if (ollamaUrl) headers['X-GrowPath-Ollama-Url'] = ollamaUrl;
  if (ollamaKey) headers['X-GrowPath-Ollama-Key'] = ollamaKey;
  return headers;
}
