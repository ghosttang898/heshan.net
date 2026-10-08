import { Link } from "react-router-dom";
import logoLockup from "../assets/logo-heshan-lockup.png";
import AdminLink from "./AdminLink";

export default function SiteHeader() {
  return (
    <nav className="site-nav detail-header" aria-label="网站导航">
      <Link className="brand-mark" to="/" aria-label="返回同鹤汇首页">
        <img src={logoLockup} alt="同鹤汇 heshan.net" />
      </Link>
      <div className="nav-links">
        <Link to="/">首页</Link>
        <Link to="/chat">聊天广场</Link>
        <Link to="/find">寻人信息</Link>
        <AdminLink />
      </div>
    </nav>
  );
}
