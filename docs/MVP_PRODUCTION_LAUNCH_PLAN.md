# 同鹤汇 MVP 正式上线执行计划

> 历史执行计划，现已按阶段批准完成上线。生产 ghost 已初始化，不可重跑。
> 当前版本、待办和操作入口见 [V1 交接](V1_HANDOVER.md)。

检查日期：2026-10-13（America/New_York）。仅检查和本地准备，未执行正式部署。

## 当前证据和限制

- 发布候选：a67f2bf4ad1765abd48c00856c3e9cd9a94efb9a；本地提交尚未推送。
- 用户提供的新版 Staging 报告：应用更新、HTTPS/API/SPA、健康及数据保持 PASS。
  独立恢复和重启持久化此前 PASS，不能替代未来生产数据库的备份检查。
- 本轮 SSH 只读结果：Ubuntu 24.04，物理内存 1967MiB，可用 1218MiB，
  Swap 1023MiB、已用 2MiB，磁盘剩余约 40GiB，load average 0.16/0.14/0.10。
  监听端口为 SSH、系统 DNS 和 127.0.0.1:18443；未见 80/443/8080/5432 监听。
- Docker 实时检查需要 sudo 密码，未完成。宿主机 command -v nginx 未找到程序；
  不能据此认定不存在其他容器、Web 配置或云防火墙限制。
- 本轮 DNS 查询：heshan.net 和 www.heshan.net 的 A 均为 206.189.219.41，
  不是新 VPS 165.232.156.104。NS 为 ns39/ns40.domaincontrol.com。
  根域 HTTP 301 到 www；www HTTP 200、Apache。根域 HTTPS 从本机连接失败，
  外部页面工具也未能访问。旧站 HTTP 有实际服务，不得宣称旧站不存在或可删除。
- 生产 compose 有独立 heshan 项目和 postgres_data 卷、数据库无宿主机端口，
  后端无宿主机端口，proxy 仅映射 127.0.0.1:8080；有资源限制和 unless-stopped。
  但现有生产 nginx.conf 首页返回 404、无 TLS/静态文件/SPA 回退，尚不能直接上线。
- 生产 backup-postgresql.sh 仍强制运行 offsite/rclone，不符合已批准的 MVP 方向。
  需要最小范围补充本地备份入口，不能把仅生成 dump 后的上传失败算完整备份成功。

本轮本地验证：备份脚本 bash -n 通过；现有应用更新脚本 10 项模拟测试通过。
此前该候选的 Maven 测试/打包、前端 23 项测试及生产构建通过；本轮没有重跑全部测试。

## 最简单架构

采用已确认的 Cloudflare 免费 DNS/CDN + 同一 VPS；接入顺序及本地配置见
[Cloudflare MVP 接入方案](MVP_CLOUDFLARE_SETUP.md)。Cloudflare 外部变更尚未执行。
宿主机 Nginx 提供 React 静态文件、SPA 回退、正式 HTTPS；
同源 /api 转发到 127.0.0.1:8080 的生产 proxy，再到 Backend 和独立 PostgreSQL。
不增加 api 子域名、Pages、服务器、云存储或部署控制器，不启用 backup profile。
复用现有容器资源和安全限制；TLS 入口覆盖客户端转发头，不信任任意 X-Forwarded-For。
采用相对 /api，CORS 仅列出正式 HTTPS 域名，保留现有 JWT/三级权限/Analytics 排除规则。

宿主机 Nginx 的 server_name 仅包含批准域名，未知 Host 拒绝；正式根目录不能指向
Staging 静态目录。TLS 私钥 root-only，不复用 localhost 测试 CA。正式页面增加现有
安全响应头；未确认 HTTPS 全路径正确前不启用长期 HSTS/preload。

## 八步执行及批准门禁

1. **补齐并本地测试最小生产配置（需批准）**：宿主机 Nginx 的静态目录、SPA、
   /api、转发头、安全头、TLS 和续期配置；让本地备份不依赖 rclone。
   不修改业务/角色规则。候选 SHA 重新固定；推送 GitHub须单独批准。
2. **只读上线门禁（sudo 由所有者输入）**：重查三容器健康、全部运行容器、
   Docker 网络、Volume、端口、UFW/云防火墙、磁盘、内存；核实生产项目/卷名此前不存在。
   保存旧 A/AAAA/CNAME/TTL/NS、邮件记录、旧站可访问路径和管理方式，不读取公开日志中的密钥。
3. **冻结并备份 Staging，停止其三服务（单独批准）**：停止会中断测试站，保留
   全部容器、Volume、TLS、env 和镜像；不使用 down -v，也不停止其他项目。
4. **创建单套独立生产环境（单独批准）**：新空数据库 heshan_production，项目 heshan，
   卷 heshan_postgres_data（执行前确认真实名称）；root:0600 /etc/heshan/production.env。
   新随机数据库管理员密码、应用密码、JWT；不拷贝 Staging 用户、数据或密码。
   新配置通过 Flyway V1/Hibernate validate，禁用开发 bootstrap；先仅通过隧道验收。
   不在 VPS 构建 Maven/npm，不额外启动第二套完整应用。
5. **生产 ghost 归属及初始化（单独批准）**：上线前限制公开注册，所有者在生产环境
   本人注册并成功登录，通过 /api/auth/me 与只读 users 查询核实同一 ID/精确用户名。
   如 ghost 已被他人占用，停止，不靠用户名授予权限，也不删除对方账号。
   核实 founder_identity 为空且无 SUPER_ADMIN 后，由 sudo 一次性服务器命令传入
   founder-id/username 及 confirm-founder-id/username；绝不能沿用 Staging 的 ID=1。
   命令使用 founder-bootstrap 非 Web 入口，事务写保护身份及审计，重复初始化拒绝。
   若需停止生产 Backend 避免同时运行两个 JVM，须明确批准短暂中断；不重启数据库。
   初始化后复查登录、角色、singleton 身份和 INITIALIZE_FOUNDER 审计，不记录 JWT/密码。
   **V1 版本的初始化参数**：prod 防护要求 Flyway 开启，不能传入
   `--spring.flyway.enabled=false`，否则会在连接数据库前以 `prod requires Flyway` 退出。
   对当前仅含 V1 的固定镜像，先只读确认迁移历史恰为成功的 V1，再使用
   `--spring.flyway.enabled=true --spring.flyway.target=1 --spring.jpa.hibernate.ddl-auto=validate`。
   保持 clean 禁用、校验开启，不跳过迁移执行来伪造历史。初始化后迁移历史指纹必须完全不变；
   缺失、失败或额外版本均停止。失败后先查角色、绑定、审计和脱敏日志，不自动重试。
6. **备份与正式 HTTPS（分别批准）**：空库初始化及所有者注册后各生成 pg_dump、SHA256，
   非空/归档检查，目录 0700、文件 0600，并安全下载到 Mac。每日手动备份明确负责人，
   本地至少 7 天，Mac 至少 30 天；没有已验证的另一份副本不删唯一备份。
   不新增云服务。生产备份实际恢复仅在另行批准的独立目标中演练，不覆盖生产库。
   为上线前取得可信证书，建议先批准仅 _acme-challenge TXT 的 DNS-01 验证，
   不改变网站 A/AAAA；签发完成后用 curl --resolve 验证正式域名的证书和页面。
   切换后改用可自动续期的 HTTP-01/webroot，需验证 80 端口挑战路径及续期测试。
7. **域名切换（单独批准）**：确认 HTTPS、备份、所有者和验收通过后，在当前权威 DNS
   管理处修改根域和 www 指向新 VPS。TTL 调整也需批准；不改 NS/MX/无关 TXT，
   复查 AAAA/CNAME，避免 IPv6 或 www 仍到旧服务器。验证多网络解析及首页/API。
   在公开验收前保持写入受限，避免失败回退时出现两站分叉写入。
8. **上线验收后开放（需所有者确认）**：注册/登录/退出/重登、聊天和寻人发布、
   年份交集搜索、详情/匿名及登录评论、移动布局、刷新/SPA、输入错误与草稿保护；
   USER 拒绝 Admin API，ADMIN 边界，SUPER_ADMIN 授权/撤销与审计（用测试账号），
   IP 隐私、Analytics 不统计 auth/admin、HTTPS/重定向/安全头、备份、健康和 OOM。
   清除浏览器测试干扰后观察真实访问。未执行项目必须 NOT TESTED。

正式证书验证依据：[Let's Encrypt challenge types](https://letsencrypt.org/docs/challenge-types/)。
DNS-01 可在 A 记录切换前验证域名；HTTP-01 需验证服务能通过域名的 80 端口访问。
本轮没有签发证书、更改 DNS 或安装 Nginx/证书客户端。

## 资源预算及失败处理

停止 Staging 后，预计释放约 280–400MiB 容器实际内存；宿主机缓存波动会影响可用值。
单套生产 DB/Backend/proxy 上限合计 1216MiB，加宿主机 Nginx 约 10–50MiB；
按此前实测，稳态容器预计约 300–500MiB，冷启动需额外余量，以上是估算，不是生产实测。
部署时至少可用 1GiB RAM、4GiB 磁盘；不让 Staging/Production 两套长期并行。
保留已有 1GiB Swap，只作缓冲，不新增 Swap或把它当稳定容量。保留镜像/静态版本和备份
约多用 1–3GiB（随备份增长）；观察 OOM、CPU 和重启，异常即停止放量，不升级 VPS。

- 切换前失败：不改 DNS，不影响旧站；只停止本轮新生产服务，保留卷/日志/备份，
  如需重新启动 Staging，须批准并始终使用当前含 ingress overlay 的配置。
- 切换后应用失败：优先回滚同一生产数据库上的旧应用镜像与静态目录，验证迁移兼容；
  不自动覆盖数据库，不运行 Flyway clean/repair，不删除任何 Volume。
- 必须恢复旧站时：先限制新版写入、备份新增生产数据，经批准恢复原 DNS 记录及 TTL。
  DNS 缓存不会瞬间回退。旧站必须保持可访问且未经覆盖；新数据留在生产卷中，不自动
  导入旧站或丢弃。记录需要人工协调的数据差异，然后才恢复旧站写入。

## 当前上线阻碍

生产静态/TLS入口及本地备份的模板修正已准备，安装/真实验证未完成；实时 sudo 只读门禁未完成；
旧站及 DNS 回滚访问资料待确认；正式证书与续期未验证；生产数据库及独立凭据未创建；
生产 ghost 账号归属尚无证据；生产备份及新环境验收未执行。
这些不需要复杂新架构，但全部门禁通过前不得正式切换。

本轮结束：没有部署、停止服务、创建生产数据库、修改权限/DNS或推送 GitHub。
