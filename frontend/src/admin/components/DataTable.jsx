export default function DataTable({ columns, rows, loading, wide = false }) {
  return <div className="admin-table-scroll" aria-busy={loading}>
    <table className={`admin-table${wide ? " admin-table-wide" : ""}`}><thead><tr>{columns.map((column) => <th key={column.key} scope="col">{column.label}</th>)}</tr></thead>
      <tbody>{loading ? <tr><td colSpan={columns.length} className="admin-state" role="status">正在加载...</td></tr>
        : rows.length === 0 ? <tr><td colSpan={columns.length} className="admin-state">没有符合条件的记录。</td></tr>
          : rows.map((row) => <tr key={row.id}>{columns.map((column) => <td key={column.key}>{column.render ? column.render(row) : row[column.key]}</td>)}</tr>)}
      </tbody>
    </table>
  </div>;
}
