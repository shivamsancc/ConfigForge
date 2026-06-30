export function Spinner({ size = 'md' }: { size?: 'sm' | 'md' | 'lg' }) {
  return <div className={`spinner${size === 'lg' ? ' spinner-lg' : ''}`} />
}

export function LoadingRow({ text = 'Loading…' }: { text?: string }) {
  return (
    <div className="loading-row">
      <Spinner />
      <span>{text}</span>
    </div>
  )
}
