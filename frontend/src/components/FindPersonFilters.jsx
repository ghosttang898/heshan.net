export default function FindPersonFilters({ filters, onChange }) {
  function handleChange(event) {
    const { name, value } = event.target;
    onChange(name, value);
  }

  return (
    <section className="card filter-grid">
      <h2>查找老朋友</h2>
      <label className="field">
        <span>按昵称搜索</span>
        <input
          name="nickname"
          value={filters.nickname}
          onChange={handleChange}
          placeholder="例如：阿珍"
        />
      </label>
      <label className="field">
        <span>按年份筛选</span>
        <input
          name="year"
          value={filters.year}
          onChange={handleChange}
          placeholder="例如：2001"
        />
      </label>
      <label className="field">
        <span>按地点筛选</span>
        <input
          name="location"
          value={filters.location}
          onChange={handleChange}
          placeholder="例如：鹤山、沙坪"
        />
      </label>
    </section>
  );
}
