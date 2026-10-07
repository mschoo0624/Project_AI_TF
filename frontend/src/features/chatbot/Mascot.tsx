// 철모를 쓴 법령 도우미 마스코트. mood: idle(눈 깜빡임) / wave(손 흔들기) / thinking(통통 튀기)
export type MascotMood = 'idle' | 'wave' | 'thinking'

export default function Mascot({ size = 48, mood = 'idle' }: { size?: number; mood?: MascotMood }) {
  return <svg className={`mascot is-${mood}`} width={size} height={size} viewBox="0 0 64 64" aria-hidden="true">
    {/* face */}
    <circle cx="32" cy="40" r="18" fill="#ffe2c6" />
    {/* chin strap */}
    <path d="M15.5 35 Q16.5 47 24 54 M48.5 35 Q47.5 47 40 54" fill="none" stroke="#5d763d" strokeWidth="1.6" strokeLinecap="round" />
    {/* helmet */}
    <path d="M9 31 C9 15 19 7 32 7 C45 7 55 15 55 31 Z" fill="#6f8a4c" />
    <ellipse cx="22" cy="20" rx="5" ry="3.2" fill="#58703a" />
    <ellipse cx="42" cy="17" rx="4.2" ry="2.6" fill="#8aa563" />
    <ellipse cx="45" cy="25" rx="3.4" ry="2.2" fill="#58703a" />
    <ellipse cx="17" cy="27" rx="2.6" ry="1.8" fill="#8aa563" />
    {/* 이병 계급장 (작대기 하나) */}
    <rect x="25.5" y="11.5" width="13" height="7.5" rx="1.6" fill="#e3dcb4" stroke="#4a5e32" strokeWidth=".6" />
    <rect x="27.8" y="14.3" width="8.4" height="1.9" rx=".6" fill="#1f2a17" />
    <rect x="6" y="28" width="52" height="7" rx="3.5" fill="#5d763d" />
    {/* eyes */}
    <g className="mascot-eyes">
      <ellipse cx="25" cy="42" rx="2.5" ry="3.1" fill="#2b2b2b" />
      <ellipse cx="39" cy="42" rx="2.5" ry="3.1" fill="#2b2b2b" />
      <circle cx="25.9" cy="40.9" r=".9" fill="#fff" />
      <circle cx="39.9" cy="40.9" r=".9" fill="#fff" />
    </g>
    {/* cheeks + smile */}
    <ellipse cx="20.5" cy="48" rx="3.2" ry="2" fill="#ffb3b3" opacity=".75" />
    <ellipse cx="43.5" cy="48" rx="3.2" ry="2" fill="#ffb3b3" opacity=".75" />
    <path d="M28.5 48.5 Q32 52.5 35.5 48.5" fill="none" stroke="#7a4b3a" strokeWidth="1.8" strokeLinecap="round" />
    {mood === 'wave' && <g className="mascot-hand">
      <circle cx="55" cy="47" r="4.6" fill="#ffe2c6" stroke="#f0c9a6" strokeWidth="1" />
    </g>}
  </svg>
}
