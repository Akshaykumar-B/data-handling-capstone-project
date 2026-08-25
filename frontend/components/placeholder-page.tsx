export function PlaceholderPage({ title, description }: { title: string; description: string }) {
  return <section className="placeholder"><span className="eyebrow">SCAFFOLDED VIEW</span><h2>{title}</h2><p>{description}</p><div className="loading-line" aria-label="Loading dashboard data" /><p className="muted">Analytics will appear when the API endpoints are implemented.</p></section>;
}