import './WorkspaceTabs.css'

export default function WorkspaceTabs<T extends string>({ label, items, value, onChange }: {
  label: string; items: readonly { id: T; label: string }[]; value: T; onChange: (value: T) => void
}) {
  return <nav className="workspace-subtabs" aria-label={label}>
    {items.map(item => <button key={item.id} type="button" className={`workspace-subtab${value === item.id ? ' active' : ''}`}
      aria-current={value === item.id ? 'page' : undefined} onClick={() => onChange(item.id)}>{item.label}</button>)}
  </nav>
}
