import { useEffect, useRef, useState } from "react";
import { X } from "lucide-react";
import { setUserRole } from "../api";
import useAdminError from "../useAdminError";

export default function RoleChangeDialog({ user, onClose, onChanged }) {
  const dialog = useRef(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [stale, setStale] = useState(false);
  const handleError = useAdminError();
  const nextRole = user.role === "USER" ? "ADMIN" : "USER";
  useEffect(() => {
    const previous = document.activeElement;
    const element = dialog.current;
    element.showModal();
    return () => { element.close(); previous?.focus(); };
  }, []);

  async function confirm() {
    setSaving(true); setError("");
    try {
      await setUserRole(user.id, nextRole, user.role);
      onChanged(`${user.username} (#${user.id}) 的角色已更新为 ${nextRole}。`);
    } catch (error) {
      const status = error.response?.status;
      if (status === 403) handleError(error);
      if (status === 409 || status === 404) setStale(true);
      setError(status === 409 ? "此帐号角色已变化，请关闭并刷新列表后重新确认。"
        : status === 400 ? "只允许 USER 与 ADMIN 之间的角色变更。"
        : status === 403 ? "没有授权权限，或目标是受保护的创始帐号。"
        : handleError(error));
    } finally { setSaving(false); }
  }

  return <dialog ref={dialog} className="admin-role-dialog" aria-labelledby="role-change-title"
    onCancel={(event) => { event.preventDefault(); if (!saving) onClose(); }}>
    <div className="admin-detail-heading"><h2 id="role-change-title">{nextRole === "ADMIN" ? "授权管理员" : "撤销管理员"}</h2>
      <button className="admin-icon-button" title="关闭" aria-label="关闭角色确认" disabled={saving} onClick={onClose}><X size={18} /></button>
    </div>
    <dl className="admin-detail-meta"><dt>用户 ID</dt><dd>{user.id}</dd><dt>帐号</dt><dd>{user.username}</dd>
      <dt>显示名</dt><dd>{user.displayName}</dd><dt>角色变更</dt><dd>{user.role} → {nextRole}</dd></dl>
    {error && <p className="admin-error" role="alert">{error}</p>}
    <div className="admin-detail-actions"><button className={`admin-button ${nextRole === "USER" ? "admin-danger" : ""}`} disabled={saving || stale} onClick={confirm}>{saving ? "提交中..." : "确认变更"}</button>
      <button className="admin-button admin-secondary" disabled={saving} onClick={onClose}>取消</button></div>
  </dialog>;
}
