export const statusLabels = { PUBLISHED: "已发布", HIDDEN: "已隐藏", DELETED: "已删除" };

export default function StatusBadge({ status }) {
  return <span className={`admin-badge admin-status-${status?.toLowerCase()}`}>{statusLabels[status] || status}</span>;
}
