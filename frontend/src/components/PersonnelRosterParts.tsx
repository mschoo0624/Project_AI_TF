import type { ReactNode } from 'react'

export function RosterHeading({ children }: { children: ReactNode }) {
  return <h1 className="rm-roster-title"><svg aria-hidden="true" viewBox="0 0 32 26" width="33" height="27" fill="currentColor"><circle cx="16" cy="6" r="4" /><circle cx="5" cy="11" r="3" /><circle cx="27" cy="11" r="3" /><path d="M7 25v-5c0-5 4-8 9-8s9 3 9 8v5H7ZM0 25v-5c0-3 2-5 5-5 1 0 2 .2 3 .8C6 18 5 21 5 25H0ZM27 25v-4c0-2-.8-4-2-5.2a6 6 0 0 1 3-.8c3 0 4 2 4 5v5h-5Z" /></svg>{children}</h1>
}

type Metric = { label: string; value: string; description: string; color: 'blue' | 'orange' | 'green' }

export function RosterSummary({ metrics }: { metrics: Metric[] }) {
  return <div className="rm-summary-grid">{metrics.map(metric => <section key={metric.label} className="rm-summary-card">
    <h2><span className={`rm-summary-icon ${metric.color}`} aria-hidden="true">●</span>{metric.label}</h2>
    <strong>{metric.value}</strong><p title={metric.description}>{metric.description}</p>
  </section>)}</div>
}

export function RosterPagination({ total, page, pageSize, onPageChange, label }: {
  total: number; page: number; pageSize: number; onPageChange: (page: number) => void; label: string
}) {
  const pages = Math.max(1, Math.ceil(total / pageSize))
  const current = Math.min(Math.max(1, page), pages)
  const first = Math.max(1, Math.min(current - 2, pages - 4))
  return <footer className="rm-person-footer">
    <span>총 {total.toLocaleString('ko-KR')}명 중 {total ? (current - 1) * pageSize + 1 : 0}–{Math.min(current * pageSize, total)}명 표시</span>
    <nav aria-label={label}>
      <button type="button" disabled={current === 1} onClick={() => onPageChange(current - 1)} aria-label="이전 페이지">‹</button>
      {Array.from({ length: Math.min(5, pages) }, (_, index) => first + index).map(number =>
        <button key={number} type="button" className={current === number ? 'is-current' : ''}
          aria-current={current === number ? 'page' : undefined} onClick={() => onPageChange(number)}>{number}</button>)}
      <button type="button" disabled={current === pages} onClick={() => onPageChange(current + 1)} aria-label="다음 페이지">›</button>
    </nav>
  </footer>
}
