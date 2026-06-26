import { Link } from "react-router-dom";
import { useEffect, useState } from "react";
import CreatePostForm from "../components/CreatePostForm";
import PostList from "../components/PostList";
import { createPost, getPosts } from "../api";
import { clearAuth, getAuth, isAuthenticated, subscribeAuthChange } from "../auth";

const pageConfig = {
  CHAT: {
    title: "聊天广场",
    emptyText: "还没有聊天帖子，先发布第一条。",
  },
  FIND_PERSON: {
    title: "寻人信息",
    emptyText: "还没有寻人帖子，先发布第一条。",
  },
};

export default function PostsPage({ type }) {
  const [posts, setPosts] = useState([]);
  const [status, setStatus] = useState("loading");
  const [auth, setAuth] = useState(getAuth());
  const config = pageConfig[type];

  async function loadPosts() {
    setStatus("loading");

    try {
      const response = await getPosts();
      const filteredPosts = response.data.filter((post) => post.type === type);
      setPosts(filteredPosts);
      setStatus("ready");
    } catch (error) {
      setStatus("error");
    }
  }

  useEffect(() => {
    loadPosts();
  }, [type]);

  useEffect(() => subscribeAuthChange(() => setAuth(getAuth())), []);

  async function handleCreatePost(payload) {
    await createPost(payload);
    await loadPosts();
  }

  return (
    <main className="page">
      <div className="stack">
        <section className="card toolbar">
          <div>
            <h1>{config.title}</h1>
            <p className="muted">可查看、发布并进入帖子详情。</p>
          </div>
          <div className="nav-links">
            <Link to="/">首页</Link>
            <Link to={type === "CHAT" ? "/find" : "/chat"}>
              {type === "CHAT" ? "寻人信息" : "聊天广场"}
            </Link>
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

        {isAuthenticated() ? (
          <CreatePostForm defaultType={type} onSubmit={handleCreatePost} />
        ) : (
          <section className="card">
            <p className="muted">登录后才能发布帖子。</p>
            <div className="nav-links">
              <Link to="/login">去登录</Link>
              <Link to="/register">去注册</Link>
            </div>
          </section>
        )}

        {status === "error" ? (
          <section className="card">
            <p className="muted">加载帖子失败，请确认后端已启动。</p>
          </section>
        ) : (
          <PostList posts={posts} emptyText={config.emptyText} />
        )}
      </div>
    </main>
  );
}
