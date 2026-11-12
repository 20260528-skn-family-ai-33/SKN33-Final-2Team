import { create } from 'zustand';

export const limits = { timeout: 900, input: 131072, output: 32768 } as const;
export type BrowserOptions = Partial<Record<'picker' | 'demo' | 'tools', boolean> & Record<keyof typeof limits, number> & Record<'ollamaUrl' | 'ollamaKey', string>>;
const key = 'growpath.browser-console.v1';

function read(): BrowserOptions {
  try {
    const raw = JSON.parse(localStorage.getItem(key) || '{}');
    const options: BrowserOptions = {};
    for (const name of ['picker', 'demo', 'tools'] as const) {
      if (typeof raw[name] === 'boolean') options[name] = raw[name];
    }
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

export function browserHeaders(): Record<string, string> {
  const { options } = useBrowserOptions.getState();
  const headers: Record<string, string> = {};
  for (const name of ['picker', 'demo'] as const) {
    if (options[name] === false) headers['X-GrowPath-' + name] = 'off';
  }
  for (const name of ['input', 'output', 'timeout'] as const) {
    if (options[name] !== undefined) headers['X-GrowPath-' + name] = String(options[name]);
  }
  if (options.demo !== false) {
    if (options.ollamaUrl) headers['X-GrowPath-Ollama-Url'] = options.ollamaUrl;
    if (options.ollamaKey) headers['X-GrowPath-Ollama-Key'] = options.ollamaKey;
  }
  return headers;
}
