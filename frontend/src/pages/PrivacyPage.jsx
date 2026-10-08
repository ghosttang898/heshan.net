import SiteHeader from "../components/SiteHeader";
import GeolocationAttribution from "../components/GeolocationAttribution";

export default function PrivacyPage() {
  return <main className="page"><div className="stack privacy-page">
    <SiteHeader />
    <section>
      <h1>隐私说明</h1>
      <h2>发布内容的 IP 属地</h2>
      <p>发布帖子或评论（包括匿名评论）时，同鹤汇会根据该次请求的公网 IP，在服务器本地查询近似属地，并与内容一起保存国家、地区、城市及查询状态。</p>
      <p>这些属地信息会随帖子或评论向所有访客公开展示，管理员可查看国家、地区、城市和查询状态。记录的是发布当时的查询结果，不会随以后登录、浏览或网络变化而更新；历史内容不回填属地。</p>
      <p>IP 属地不是 GPS 定位，不保证城市准确，也不能用于确定住址或识别个人。VPN、代理和移动网络可能显示其公网出口所在地。我们不记录经纬度或街道地址，也不获取设备定位。</p>
      <p>本功能不持久化完整 IP，也不向前端返回完整 IP；查询不向外部地理位置服务发送访客 IP。原始 IP 仅用于处理当次发布请求。属地快照随内容保留；后台软删除会停止公开展示，但不会物理删除记录。</p>
      <p>私有网络、localhost、数据库未配置或查询失败时显示“未知”。注册、登录及个人资料页面不公开用户 IP 或 IP 属地。</p>
      <p>地理数据来源：<GeolocationAttribution />（CC BY 4.0）。国家名称在本站转换为中文；IP 属地只用于近似位置展示。</p>
      <h2>网站访问统计</h2>
      <p>正式网站的公开页面使用 Cloudflare Web Analytics，了解浏览量、访问来源及页面性能。登录、注册和管理后台页面不加载统计脚本，本地开发也不启用统计。</p>
      <p>本应用不向统计服务提供 JWT、帐号、显示名、邮箱或发帖、评论内容。Cloudflare 的统计脚本不使用 Cookie 或浏览器存储识别访客，发送的页面及来源 URL 会去除查询参数和片段。统计服务会处理访问请求及浏览器、设备和性能信息。</p>
      <p>详见 <a href="https://developers.cloudflare.com/speed/observatory/rum-beacon/" target="_blank" rel="noopener noreferrer">Cloudflare 的数据收集与隐私说明</a>。</p>
      <h2>部署日志</h2>
      <p>本应用的属地功能不会将 IP 或地理查询结果写入日志。反向代理、托管平台的访问日志由部署配置独立控制，不属于本功能的属地记录。</p>
    </section>
  </div></main>;
}
