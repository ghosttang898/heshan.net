import { useNavigate } from "react-router-dom";
import { clearAuth } from "../auth";

export default function useAdminError() {
  const navigate = useNavigate();
  return (error) => {
    if (error.response?.status === 401) {
      clearAuth();
      return "登录已过期，请重新登录。";
    }
    if (error.response?.status === 403) {
      navigate("/admin", { replace: true, state: { recheckPermissions: Date.now() } });
      return "此帐号没有管理权限，请刷新页面验证身份。";
    }
    return error.response?.status === 404 ? "记录不存在。" : "请求失败，请稍后重试。";
  };
}
