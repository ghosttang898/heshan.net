export default function StatCard({ label, value, Icon, tone }) {
  return <article className={`admin-stat admin-tone-${tone}`}>
    <div><span>{label}</span><Icon size={18} aria-hidden="true" /></div>
    <strong>{value.toLocaleString()}</strong>
  </article>;
}
