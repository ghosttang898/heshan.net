import { useEffect, useRef, useState } from "react";
import { X } from "lucide-react";
import { getAdminDetail, setContentStatus } from "../api";
import useAdminError from "../useAdminError";
import { formatUserName } from "../../userName";
import StatusBadge, { statusLabels } from "./StatusBadge";
import { formatIpLocationStatus } from "../../ipLocation";

export default function DetailPanel({ resource, id, onClose, onChanged }) {
  const [item, setItem] = useState(null);
  const [error, setError] = useState("");
  const [pending, setPending] = useState(null);
  const [saving, setSaving] = useState(false);
  const [retry, setRetry] = useState(0);
  const dialog = useRef(null);
  const handleError = useAdminError();
  useEffect(() => {
    const previous = document.activeElement;
    dialog.current.showModal();
    return () => { dialog.current?.close(); previous?.focus(); };
  }, []);
  useEffect(() => {
    let active = true;
    setItem(null); setError("");
    getAdminDetail(resource, id).then(({ data }) => { if (active) setItem(data); })
      .catch((error) => { if (active) setError(handleError(error)); });
    return () => { active = false; };
  }, [resource, id, retry]);

  async function updateStatus() {
    setSaving(true); setError("");
    try {
      const { data } = await setContentStatus(resource, id, pending);
      setItem(data); setPending(null); onChanged();
    } catch (error) { setError(handleError(error)); }
    finally { setSaving(false); }
  }

  const title = resource === "posts" ? "帖子详情" : resource === "comments" ? "评论详情" : "用户详情";
  return <dialog ref={dialog} className="admin-detail" aria-label={title} onCancel={(event) => {
    event.preventDefault(); if (!saving) onClose();
  }}>
    <div className="admin-detail-heading"><h2>{title} <small>#{id}</small></h2>
      <button className="admin-icon-button" disabled={saving} onClick={onClose} aria-label="关闭详情" title="关闭详情"><X size={20} /></button>
    </div>
    {error && <div className="admin-error" role="alert">{error}{!item && <button onClick={() => setRetry(retry + 1)}>重试</button>}</div>}
    {!item && !error ? <p className="admin-state" role="status">正在加载...</p> : item && <>
      {resource === "users" ? <dl className="admin-detail-meta">
        <dt>帐号</dt><dd>{item.username}</dd><dt>显示名</dt><dd>{item.displayName}</dd><dt>角色</dt><dd>{item.role}</dd>
        <dt>帖子数</dt><dd>{item.postCount}</dd><dt>评论数</dt><dd>{item.commentCount}</dd>
        <dt>注册时间</dt><dd>{new Date(item.createdAt).toLocaleString()}</dd>
      </dl> : <>
        <h3>{item.title || item.postTitle}</h3>
        <dl className="admin-detail-meta"><dt>发表人</dt><dd>{formatUserName(item.author?.displayName, item.author?.username)}</dd>
          <dt>状态</dt><dd><StatusBadge status={item.status} /></dd><dt>发表时间</dt><dd>{new Date(item.createdAt).toLocaleString()}</dd>
          <dt>发布国家</dt><dd>{item.ipCountry || "未知"}{item.ipCountryCode ? ` (${item.ipCountryCode})` : ""}</dd>
          <dt>发布地区</dt><dd>{item.ipRegion || "未知"}</dd>
          <dt>发布城市</dt><dd>{item.ipCity || "未知"}</dd>
          <dt>属地查询</dt><dd>{formatIpLocationStatus(item.ipLocationStatus)}</dd>
          {item.type && <><dt>类型</dt><dd>{item.type === "CHAT" ? "聊天广场" : "寻人信息"}</dd></>}
          {item.postId && <><dt>所属帖子</dt><dd>#{item.postId}</dd></>}
          {item.nickname && <><dt>昵称</dt><dd>{item.nickname}</dd></>}
          {item.location && <><dt>地点</dt><dd>{item.location}</dd></>}
          {item.yearRange && <><dt>年份</dt><dd>{item.yearRange}</dd></>}
        </dl>
        <div className="admin-detail-content">{item.content}</div>
        <div className="admin-detail-actions">
          {pending ? <><p>确认将此{resource === "posts" ? "帖子" : "评论"}设为「{statusLabels[pending]}」？</p>
            <button className={`admin-button ${pending === "DELETED" ? "admin-danger" : ""}`} disabled={saving} onClick={updateStatus}>{saving ? "提交中..." : "确认"}</button>
            <button className="admin-button admin-secondary" disabled={saving} onClick={() => setPending(null)}>取消</button>
          </> : <>
            {item.status !== "PUBLISHED" && <button className="admin-button" onClick={() => setPending("PUBLISHED")}>恢复发布</button>}
            {item.status === "PUBLISHED" && <button className="admin-button admin-secondary" onClick={() => setPending("HIDDEN")}>隐藏</button>}
            {item.status !== "DELETED" && <button className="admin-button admin-danger" onClick={() => setPending("DELETED")}>软删除</button>}
          </>}
        </div>
      </>}
    </>}
  </dialog>;
}
