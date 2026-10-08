import { useEffect, useState } from "react";
import { useSearchParams, useOutletContext } from "react-router-dom";
import { Search, RefreshCw, ChevronLeft, ChevronRight, Eye, UserPlus, UserMinus } from "lucide-react";
import { getAdminList } from "../api";
import useAdminError from "../useAdminError";
import { formatUserName } from "../../userName";
import DataTable from "./DataTable";
import DetailPanel from "./DetailPanel";
import StatusBadge, { statusLabels } from "./StatusBadge";
import { formatIpLocationStatus } from "../../ipLocation";
import RoleChangeDialog from "./RoleChangeDialog";

export default function AdminResourcePage({ resource, title }) {
  const currentUser = useOutletContext();
  const isUserResource = resource === "users" || resource === "administrators";
  const [roleTarget, setRoleTarget] = useState(null);
  const [notice, setNotice] = useState("");
  const [params, setParams] = useSearchParams();
  const queryKey = params.toString();
  const rawPage = Number(params.get("page"));
  const page = Number.isInteger(rawPage) && rawPage >= 0 ? rawPage : 0;
  const size = [10, 20, 50].includes(Number(params.get("size"))) ? Number(params.get("size")) : 20;
  const [search, setSearch] = useState(params.get("search") || "");
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [refresh, setRefresh] = useState(0);
  const [detailId, setDetailId] = useState(null);
  const handleError = useAdminError();

  useEffect(() => { setSearch(params.get("search") || ""); }, [queryKey]);
  useEffect(() => {
    let active = true;
    setLoading(true); setError("");
    const query = { page, size, search: params.get("search") || undefined };
    ["type", "status", "role"].forEach((key) => { if (params.get(key)) query[key] = params.get(key); });
    getAdminList(resource, query).then(({ data }) => {
      if (!active) return;
      if (page > 0 && page >= data.totalPages) {
        const next = new URLSearchParams(params); next.set("page", String(Math.max(0, data.totalPages - 1))); setParams(next, { replace: true });
      } else setData(data);
    }).catch((error) => { if (active) { setData(null); setError(handleError(error)); } })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [resource, queryKey, refresh]);

  function changeParam(key, value) {
    const next = new URLSearchParams(params);
    value ? next.set(key, value) : next.delete(key);
    if (key !== "page") next.delete("page");
    setParams(next);
  }

  const columns = [{ key: "id", label: "ID" }];
  if (isUserResource) {
    columns.push({ key: "username", label: "帐号" }, { key: "displayName", label: "显示名" }, { key: "role", label: "角色" });
    if (resource === "users") columns.push({ key: "postCount", label: "帖子" }, { key: "commentCount", label: "评论" });
  } else {
    columns.push({ key: "content", label: resource === "posts" ? "标题" : "评论内容", render: (row) => <span className="admin-preview" title={row.title || row.content}>{row.title || row.content}</span> },
      { key: "author", label: "发表人", render: (row) => formatUserName(row.author?.displayName, row.author?.username) });
    if (resource === "posts") columns.push({ key: "type", label: "类型", render: (row) => row.type === "CHAT" ? "聊天广场" : "寻人信息" });
    else columns.push({ key: "postTitle", label: "所属帖子", render: (row) => <span className="admin-preview" title={row.postTitle}>#{row.postId} · {row.postTitle}</span> });
    columns.push({ key: "status", label: "状态", render: (row) => <StatusBadge status={row.status} /> });
    columns.push({ key: "ipCountry", label: "发布国家", render: (row) => row.ipCountry || "未知" },
      { key: "ipRegion", label: "发布地区", render: (row) => row.ipRegion || "未知" },
      { key: "ipCity", label: "发布城市", render: (row) => row.ipCity || "未知" },
      { key: "ipLocationStatus", label: "属地查询", render: (row) => formatIpLocationStatus(row.ipLocationStatus) });
  }
  columns.push({ key: "createdAt", label: isUserResource ? "注册时间" : "发表时间", render: (row) => <time className="admin-date">{new Date(row.createdAt).toLocaleString()}</time> },
    { key: "actions", label: "操作", render: (row) => <div className="admin-row-actions"><button className="admin-icon-button" title="查看详情" aria-label={`查看 #${row.id} 详情`} onClick={() => setDetailId(row.id)}><Eye size={18} /></button>
      {isUserResource && currentUser.role === "SUPER_ADMIN" && ["USER", "ADMIN"].includes(row.role) && <button className="admin-icon-button" title={row.role === "USER" ? "授权管理员" : "撤销管理员"} aria-label={`${row.role === "USER" ? "授权" : "撤销"} ${row.username} 的管理员权限`} onClick={() => { setNotice(""); setRoleTarget(row); }}>{row.role === "USER" ? <UserPlus size={18} /> : <UserMinus size={18} />}</button>}</div> });

  return <>
    <div className="admin-page-heading"><div><h1>{title}</h1><p>{data ? `${data.totalElements} 条记录` : "同鹤汇 heshan.net"}</p></div>
      <button className="admin-icon-button" title="刷新列表" aria-label="刷新列表" onClick={() => setRefresh(refresh + 1)}><RefreshCw size={18} /></button>
    </div>
    <div className="admin-filters">
      <form className="admin-search" onSubmit={(event) => { event.preventDefault(); changeParam("search", search.trim()); }}>
        <input aria-label="搜索" value={search} onChange={(event) => setSearch(event.target.value)} placeholder={isUserResource ? "搜索帐号 / 显示名" : resource === "posts" ? "搜索标题 / 内容" : "搜索评论内容"} />
        <button className="admin-icon-button" title="搜索" aria-label="搜索" type="submit"><Search size={18} /></button>
      </form>
      {resource === "posts" && <label>类型<select value={params.get("type") || ""} onChange={(event) => changeParam("type", event.target.value)}><option value="">全部类型</option><option value="CHAT">聊天广场</option><option value="FIND_PERSON">寻人信息</option></select></label>}
      {isUserResource ? <label>角色<select value={params.get("role") || ""} onChange={(event) => changeParam("role", event.target.value)}><option value="">全部角色</option>{resource === "users" && <option value="USER">USER</option>}<option value="ADMIN">ADMIN</option><option value="SUPER_ADMIN">SUPER_ADMIN</option></select></label>
        : <label>状态<select value={params.get("status") || ""} onChange={(event) => changeParam("status", event.target.value)}><option value="">全部状态</option>{Object.entries(statusLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>}
    </div>
    {error && <p className="admin-error" role="alert">{error}<button onClick={() => setRefresh(refresh + 1)}>重试</button></p>}
    {notice && <p className="admin-notice" role="status">{notice}</p>}
    {!error && <div className={isUserResource ? "admin-user-table" : undefined}><DataTable columns={columns} rows={data?.content || []} loading={loading} wide={!isUserResource} /></div>}
    <div className="admin-pagination">
      <label>每页<select value={size} onChange={(event) => changeParam("size", event.target.value)}>{[10, 20, 50].map((value) => <option key={value}>{value}</option>)}</select></label>
      <span>第 {page + 1} / {Math.max(1, data?.totalPages || 0)} 页</span>
      <button className="admin-icon-button" title="上一页" aria-label="上一页" disabled={loading || page === 0 || !data} onClick={() => changeParam("page", String(page - 1))}><ChevronLeft size={18} /></button>
      <button className="admin-icon-button" title="下一页" aria-label="下一页" disabled={loading || !data || page + 1 >= data.totalPages} onClick={() => changeParam("page", String(page + 1))}><ChevronRight size={18} /></button>
    </div>
    {detailId !== null && <DetailPanel key={`${resource}-${detailId}`} resource={isUserResource ? "users" : resource} id={detailId} onClose={() => setDetailId(null)} onChanged={() => setRefresh(refresh + 1)} />}
    {roleTarget && <RoleChangeDialog user={roleTarget} onClose={() => { setRoleTarget(null); setRefresh((value) => value + 1); }} onChanged={(message) => { setRoleTarget(null); setNotice(message); setRefresh((value) => value + 1); }} />}
  </>;
}
