import { consoleEnabled, type BrowserOptions, type ConsoleDefaults } from '@/shared/lib/browserOptions';

type Props = { caps: ConsoleDefaults | null | undefined; options: BrowserOptions; demo: boolean };

function Row({ label, value, detail }: { label: string; value: string; detail?: string }) {
  return <div className="console-setting">
    <dt>{label}</dt>
    <dd><strong>{value}</strong>{detail && <small>{detail}</small>}</dd>
  </div>;
}

export function ConsoleStatus({ caps, options, demo }: Props) {
  const state = (on: boolean) => caps ? (on ? '켜짐' : '꺼짐') : caps === null ? '확인 실패' : '확인 중';
  const source = (value?: boolean) => value === undefined ? '기본 설정' : '브라우저 설정';
  const model = (value: number | undefined, unit: string) =>
    value === undefined ? '서버 기본값' : value.toLocaleString('ko-KR') + unit;
  const modelDetail = (value?: number) => value === undefined ? undefined : !caps ? '브라우저 설정 · 적용 여부 미확인'
    : demo ? '브라우저 설정' : '시연 모드가 꺼져 적용되지 않음';

  return <section className="console-status" aria-label="현재 설정">
    <h2>현재 설정</h2>
    <h3>테스트 기능</h3>
    <dl>
      <Row label="로그인 직원 선택" value={state(consoleEnabled('picker', options, caps))} detail={source(options.picker)} />
      <Row label="시연 모드" value={state(demo)} detail={source(options.demo)} />
    </dl>
    <h3>모델 제한</h3>
    <dl>
      <Row label="응답 대기 시간" value={model(options.timeout, '초')} detail={modelDetail(options.timeout)} />
      <Row label="입력 토큰 한도" value={model(options.input, ' 토큰')} detail={modelDetail(options.input)} />
      <Row label="출력 토큰 한도" value={model(options.output, ' 토큰')} detail={modelDetail(options.output)} />
    </dl>
    <h3>RunPod 연결</h3>
    <dl>
      <Row label="서버 주소" value={options.ollamaUrl || '서버 기본값'} />
      <Row label="API 키" value={options.ollamaKey ? '브라우저 키 설정됨' : options.ollamaUrl ? '개인 주소에 키 미설정' : '서버 기본값'} />
    </dl>
  </section>;
}
