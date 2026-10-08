import { Routes, Route, Link, useLocation } from "react-router-dom";
import PrivacyPage from "./pages/PrivacyPage";
import GeolocationAttribution from "./components/GeolocationAttribution";
import FindPeoplePage from "./pages/FindPeoplePage";
import LandingPage from "./pages/LandingPage";
import LoginPage from "./pages/LoginPage";
import PostDetailPage from "./pages/PostDetailPage";
import PostsPage from "./pages/PostsPage";
import RegisterPage from "./pages/RegisterPage";
import AdminRoute from "./admin/components/AdminRoute";
import AdminLayout from "./admin/components/AdminLayout";
import AdminDashboardPage from "./admin/pages/AdminDashboardPage";
import AdminPostsPage from "./admin/pages/AdminPostsPage";
import AdminCommentsPage from "./admin/pages/AdminCommentsPage";
import AdminUsersPage from "./admin/pages/AdminUsersPage";
import AdminAdministratorsPage from "./admin/pages/AdminAdministratorsPage";
import "./admin/styles/admin.css";

export default function App() {
  const isAdminPage = useLocation().pathname.startsWith("/admin");
  return (
    <>
      <Routes>
        <Route path="/" element={<LandingPage />} />
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register" element={<RegisterPage />} />
        <Route path="/privacy" element={<PrivacyPage />} />
        <Route path="/chat" element={<PostsPage type="CHAT" />} />
        <Route path="/find" element={<FindPeoplePage />} />
        <Route path="/posts/:id" element={<PostDetailPage />} />
        <Route path="/admin" element={<AdminRoute />}>
          <Route element={<AdminLayout />}>
            <Route index element={<AdminDashboardPage />} />
            <Route path="posts" element={<AdminPostsPage />} />
            <Route path="comments" element={<AdminCommentsPage />} />
            <Route path="users" element={<AdminUsersPage />} />
            <Route path="administrators" element={<AdminAdministratorsPage />} />
            <Route path="*" element={<p className="admin-state">页面不存在。</p>} />
          </Route>
        </Route>
      </Routes>
      {!isAdminPage && <footer className="site-footer">
        <span>heshan.net</span>
        <strong>Created by GhostTang</strong>
        <Link to="/privacy">隐私说明</Link>
        <GeolocationAttribution />
      </footer>}
    </>
  );
}
