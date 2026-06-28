import { Routes, Route } from "react-router-dom";
import FindPeoplePage from "./pages/FindPeoplePage";
import LandingPage from "./pages/LandingPage";
import LoginPage from "./pages/LoginPage";
import PostDetailPage from "./pages/PostDetailPage";
import PostsPage from "./pages/PostsPage";
import RegisterPage from "./pages/RegisterPage";

export default function App() {
  return (
    <>
      <Routes>
        <Route path="/" element={<LandingPage />} />
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register" element={<RegisterPage />} />
        <Route path="/chat" element={<PostsPage type="CHAT" />} />
        <Route path="/find" element={<FindPeoplePage />} />
        <Route path="/posts/:id" element={<PostDetailPage />} />
      </Routes>
      <footer className="site-footer">
        <span>heshan.net</span>
        <strong>Created by GhostTang</strong>
      </footer>
    </>
  );
}
