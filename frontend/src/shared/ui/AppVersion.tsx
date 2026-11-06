import './appVersion.css';

/** 빌드가 저장소 VERSION에서 읽은 값을 모든 화면에서 함께 쓴다. */
export function AppVersion() {
  return (
    <p className="app-version" title={`GrowPath v${__APP_VERSION__} · Beta`}>
      <span className="app-version-name">GrowPath </span>
      <span>v{__APP_VERSION__}</span>
      <span className="app-version-channel"> · Beta</span>
    </p>
  );
}
