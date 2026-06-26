import { Link, useParams } from "react-router-dom";
import { useEffect, useState } from "react";
import { createComment, getComments, getPost } from "../api";
import { getAuth, isAuthenticated, subscribeAuthChange } from "../auth";
import AddCommentForm from "../components/AddCommentForm";
import CommentList from "../components/CommentList";

export default function PostDetailPage() {
  const { id } = useParams();
  const [post, setPost] = useState(null);
  const [status, setStatus] = useState("loading");
  const [comments, setComments] = useState([]);
  const [commentsStatus, setCommentsStatus] = useState("loading");
  const [auth, setAuth] = useState(getAuth());

  useEffect(() => {
    async function loadPost() {
      setStatus("loading");

      try {
        const response = await getPost(id);
        setPost(response.data);
        setStatus("ready");
      } catch (error) {
        setStatus("error");
      }
    }

    loadPost();
  }, [id]);

  useEffect(() => {
    async function loadComments() {
      setCommentsStatus("loading");

      try {
        const response = await getComments(id);
        setComments(response.data);
        setCommentsStatus("ready");
      } catch (error) {
        setCommentsStatus("error");
      }
    }

    loadComments();
  }, [id]);

  useEffect(() => subscribeAuthChange(() => setAuth(getAuth())), []);

  async function handleCreateComment(payload) {
    await createComment(id, payload);
    const response = await getComments(id);
    setComments(response.data);
    setCommentsStatus("ready");
  }

  if (status === "loading") {
    return (
      <main className="page">
        <section className="card">
          <p className="muted">正在加载帖子详情...</p>
        </section>
      </main>
    );
  }

  if (status === "error" || !post) {
    return (
      <main className="page">
        <section className="card">
          <p className="muted">帖子不存在或加载失败。</p>
          <div className="nav-links">
            <Link to="/chat">聊天广场</Link>
            <Link to="/find">寻人信息</Link>
          </div>
        </section>
      </main>
    );
  }

  return (
    <main className="page">
      <div className="stack">
        <section className="card">
          <div className="post-meta">
            <span>{post.type}</span>
            <span> · </span>
            <span>{new Date(post.createdAt).toLocaleString()}</span>
          </div>
          <h1>{post.title}</h1>
          {post.type === "FIND_PERSON" ? (
            <div className="post-tags">
              {post.nickname ? <span className="tag">昵称: {post.nickname}</span> : null}
              {post.location ? <span className="tag">地点: {post.location}</span> : null}
              {post.yearRange ? <span className="tag">年份: {post.yearRange}</span> : null}
            </div>
          ) : null}
          <p className="post-content">{post.content}</p>
        </section>
        <section className="card">
          <h2>评论</h2>
          <AddCommentForm
            onSubmit={handleCreateComment}
            isAuthenticated={isAuthenticated()}
            displayName={auth?.displayName || "匿名用户"}
          />
          {commentsStatus === "error" ? (
            <p className="muted">评论加载失败。</p>
          ) : (
            <CommentList comments={comments} />
          )}
        </section>
        <section className="card">
          <div className="nav-links">
            <Link to="/">首页</Link>
            <Link to={post.type === "CHAT" ? "/chat" : "/find"}>
              返回列表
            </Link>
          </div>
        </section>
      </div>
    </main>
  );
}
