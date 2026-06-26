import { useEffect, useState } from "react";

export default function HomePage() {
  const [health, setHealth] = useState("loading");

  useEffect(() => {
    async function loadHealth() {
      try {
        const response = await fetch("/api/health");
        const data = await response.json();
        setHealth(data.status || "unknown");
      } catch (error) {
        setHealth("error");
      }
    }

    loadHealth();
  }, []);

  return (
    <main className="page">
      <section className="card">
        <h1>同鹤汇 TongHeHui</h1>
        <p>同鹤汇是一个简洁的全栈 Web 应用原型，用于后续功能开发与协作。</p>
        <p>
          后端健康状态: <strong>{health}</strong>
        </p>
      </section>
    </main>
  );
}
