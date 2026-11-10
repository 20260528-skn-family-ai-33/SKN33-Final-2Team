/** 외부 원본 표지와 앱에서 제공하는 사내교육 표지만 허용한다. */
export function resourceImageUrl(value?: string | null): string {
  if (!value) return '';
  return /^https?:\/\//i.test(value) || /^\/images\/(?:internal-training\/(?:crash|challenge)-\d{2,4}\.webp|resource-(?:course|book|cert)\.svg)$/.test(value)
    ? value : '';
}
