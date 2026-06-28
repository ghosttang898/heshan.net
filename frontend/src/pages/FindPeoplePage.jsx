import { Link } from "react-router-dom";
import { useEffect, useState } from "react";
import CreateFindPersonPostForm from "../components/CreateFindPersonPostForm";
import FindPersonFilters from "../components/FindPersonFilters";
import FindPersonPostList from "../components/FindPersonPostList";
import { createPost, getPosts } from "../api";
import { clearAuth, getAuth, isAuthenticated, subscribeAuthChange } from "../auth";

export default function FindPeoplePage() {
  const [posts, setPosts] = useState([]);
  const [status, setStatus] = useState("loading");
  const [auth, setAuth] = useState(getAuth());
  const [filters, setFilters] = useState({
    nickname: "",
    year: "",
    location: "",
  });

  async function loadPosts() {
    setStatus("loading");

    try {
      const response = await getPosts();
      const filteredPosts = response.data.filter((post) => post.type === "FIND_PERSON");
      setPosts(filteredPosts);
      setStatus("ready");
    } catch (error) {
      setStatus("error");
    }
  }

  useEffect(() => {
    loadPosts();
  }, []);

  useEffect(() => subscribeAuthChange(() => setAuth(getAuth())), []);

  async function handleCreatePost(payload) {
    await createPost(payload);
    await loadPosts();
  }

  function handleFilterChange(name, value) {
    setFilters((current) => ({
      ...current,
      [name]: value,
    }));
  }

  const visiblePosts = posts.filter((post) => {
    const nickname = (post.nickname || "").toLowerCase();
    const location = (post.location || "").toLowerCase();
    const yearRange = (post.yearRange || "").toLowerCase();
    const nicknameQuery = filters.nickname.trim().toLowerCase();
    const locationQuery = filters.location.trim().toLowerCase();
    const yearQuery = filters.year.trim().toLowerCase();

    return (!nicknameQuery || nickname.includes(nicknameQuery))
      && (!locationQuery || location.includes(locationQuery))
      && (!yearQuery || yearRange.includes(yearQuery));
  });

  return (
    <main className="page">
      <div className="stack">
        <section className="card toolbar">
          <div>
            <h1>寻人信息</h1>
            <p className="muted">按昵称、地点和年份快速筛选，方便找回老朋友。</p>
          </div>
          <div className="nav-links">
            <Link to="/">首页</Link>
            <Link to="/chat">聊天广场</Link>
            {auth ? (
              <button className="button button-secondary" type="button" onClick={clearAuth}>
                退出登录
              </button>
            ) : (
              <>
                <Link to="/login">登录</Link>
                <Link to="/register">注册</Link>
              </>
            )}
          </div>
        </section>

        <FindPersonFilters filters={filters} onChange={handleFilterChange} />

        {status === "error" ? (
          <section className="card">
            <p className="muted">加载帖子失败，请确认后端已启动。</p>
          </section>
        ) : (
          <FindPersonPostList
            posts={visiblePosts}
            emptyText="没有匹配的寻人帖子，试试换个昵称、地点或年份。"
          />
        )}

        {isAuthenticated() ? (
          <CreateFindPersonPostForm onSubmit={handleCreatePost} />
        ) : (
          <section className="card">
            <p className="muted">登录后才能发布寻人帖子。</p>
            <div className="nav-links">
              <Link to="/login">去登录</Link>
              <Link to="/register">去注册</Link>
            </div>
          </section>
        )}
      </div>
    </main>
  );
}
