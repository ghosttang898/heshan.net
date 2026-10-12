# 同鹤汇上线前 UI、权限与部署准备检查

## 本次边界

仅修改本地代码、运行本地隔离测试，并通过 SSH 执行 free/df/uptime 只读资源检查。
未重启 VPS 或 Staging 容器，未部署 UI 修改，未恢复服务器数据库，未初始化真实 ghost。
未修改正式网站、DNS、Cloudflare、生产数据库、防火墙或 SSH，未提交或推送 Git。
网站所有者已确认 VPS 中测试用户、帖子、评论及 Flyway 记录存在，三容器 Healthy、OOM=false、Restarts=0；
这属于所有者确认的证据，不冒充本轮自动执行的服务器 SQL/容器检查。

## UI 修改及验证

| 项目 | 结果 | 实际证据 |
| --- | --- | --- |
| 注册页 SiteHeader | PASS | 与登录页一致的 stack/header/form；实际本地浏览器显示导航 |
| 聊天列表 loading | PASS | 初始页面 render 输出 status，不显示空列表或旧记录 |
| 寻人列表 loading | PASS | 初始 loading 与筛选无匹配状态分开 |
| 详情评论 loading | PASS | CommentList loading 优先；页面传入 commentsStatus；评论刷新失败显示错误 |
| 内联回复 loading | PASS | 保留原 loading 分支，增加 role=status |
| 手机布局 | PASS | 本地注册页 320px、390px 实测 scrollWidth 等于 clientWidth；视觉检查通过 |
| 前端回归 | PASS | 12 项 Node 测试通过，无跳过 |
| 生产构建 | PASS | 相同源码/lockfile，在干净临时目录 npm ci 后 npm run build 退出 0 |
| 修复后 Staging 实站 UI | NOT TESTED | 新 UI 尚未部署；不能把本地结果当作 VPS 验收 |

原工作区 node_modules 上的 Vite 构建/预览曾卡住，已停止本次创建的挂起进程。
未删除或替换原依赖目录；使用干净临时目录完成验证。原本地依赖环境还需单独处理。
测试未增加 npm 依赖，复用现有 Vite/esbuild、React SSR 与 node:test。

## 管理员权限验收

全部管理员角色修改只发生在隔离 H2/临时 PostgreSQL 测试夹具中。
临时 PostgreSQL 仅发布 Mac loopback 动态端口，不连接 VPS 或现有 Staging。

| 项目 | 结果 | 验证方式 |
| --- | --- | --- |
| USER/ADMIN/SUPER_ADMIN 后端权限 | PASS | AdministratorIntegrationTest、AdminIntegrationTest |
| ADMIN 帖子与评论隐藏/恢复 | PASS | 两级管理员实际调用 MockMvc 状态 API；公开列表排除隐藏内容 |
| ADMIN 用户权限边界 | PASS | 查询/搜索/详情允许；现有产品没有封禁/删除/资料修改 API，不能假装这些操作已实现 |
| 只有 SUPER_ADMIN 授予/撤销 ADMIN | PASS | ADMIN/USER 请求被拒绝；SUPER_ADMIN 操作成功 |
| 禁止第二个 SUPER_ADMIN/创始人降级 | PASS | 非法角色转换、受保护 founder ID、PostgreSQL 唯一约束 |
| 注册参数提权 | PASS | role=ADMIN/SUPER_ADMIN 被忽略，包括名为 ghost 的隔离注册账号 |
| JWT 篡改与请求头提权 | PASS | 新增篡改 payload/subject 保留旧签名的 JWT 测试返回 401；X-Role 无效 |
| 撤销后的旧 JWT | PASS | 读取数据库当前权限；旧 ADMIN JWT 随即失去后台权限 |
| 审计记录 | PASS | 验证 actor/target、原/新角色、时间、操作类型；审计失败角色变更事务回滚 |
| 创始人一次性初始化 | PASS | 双重 ID/用户名确认；非 ghost 名称可用；内存 DB、错误身份和重复初始化被拒绝 |
| 生产 profile + PostgreSQL 16 | PASS | 两项真实 Testcontainers 测试；Flyway/Hibernate、普通注册、临时创始人审计、应用重启后记录保留 |
| Staging 中 ADMIN/SUPER_ADMIN 浏览器操作 | NOT TESTED | 未向现有 Staging 授权账号，未触碰真实 ghost |

Maven 使用 Java 17.0.19、Spring Boot 4.1.1：40 项，39 通过，0 失败/错误，1 跳过。
跳过项是 LocalDatabaseTest 的可选本地 IP 地理数据库夹具，不是权限或 PostgreSQL 测试。
管理员相关：AdminIntegrationTest 8、AdministratorIntegrationTest 10、FounderBootstrapTest 3、PostgresMigrationIntegrationTest 2，全部通过。
临时 SUPER_ADMIN 是测试夹具，不是本次对服务器创始人初始化的授权或执行。

## 上线准备

| 项目 | 结果 | 说明 |
| --- | --- | --- |
| 备份脚本及失败保护逻辑 | PASS | 代码检查与脚本回归；pg_dump 新文件、校验和、失败留存、不提前清理 |
| 真实异地备份上传/取回 | NOT TESTED | 尚无提供商配置及本轮实际传输证据 |
| 本轮真实备份恢复演练 | NOT TESTED | 未恢复任何数据库；需先说明目标隔离环境并获得批准 |
| 现有 Staging 容器重启后持久化 | NOT TESTED | 当前 SQL 存在不等于重启后验证；不得替代该步骤 |
| 本地 PostgreSQL 应用重启保留权限/迁移 | PASS | 隔离 Testcontainers 实测，不等于 VPS 容器重启测试 |
| ingress 后续流程 | PASS（本地） | 已支持显式 overlay，并对遗漏已安装 overlay 安全退出；75 项脚本测试，74 通过、1 opt-in fixture 跳过 |
| Staging/Production 静态隔离 | PASS | 项目名 heshan-staging/heshan；Volume、网络、DB 用户/库名、环境变量与 TLS 路径独立；数据库不发布公网端口 |
| 生产服务器真实密钥/数据隔离 | NOT TESTED | 未读取生产凭据，也未启动生产服务，不能声称真实配置已验证 |

### 2GB RAM / 无 Swap 风险

本轮 SSH 实际读数：1967 MiB RAM，可用 1197 MiB；1023 MiB Swap，使用 0；磁盘剩余约 41 GiB。
所以当前 VPS 并非无 Swap。但如果移除 Swap，峰值内存更容易导致容器或宿主进程被 OOM 终止。
参考 [Docker 官方资源限制说明](https://docs.docker.com/engine/containers/resource_constraints/)。

单套主服务容器上限：PostgreSQL 384 MiB + Backend 768 MiB + Web/Proxy 64 MiB = 1216 MiB。
异地备份任务还可占 128 MiB。上限不是预留量或实际用量，必须另留宿主、Docker、缓存及运维余量。
两套环境同时达到上限为 2432 MiB，已超过物理内存，不能用 Swap 当作正常并行运行的容量保证。
上线前应批准并执行资源负载验证，确定是否在发布窗口停止 Staging 或调整部署资源；不自动升级收费 VPS。
本次未配置/关闭 Swap，未改变容器内存限制或 OOM 策略。

## 需要所有者确认的下一步

1. 批准将当前安全修复打包、生成新 SHA 镜像并更新 Staging，届时有短暂测试站不可用时间；不影响正式网站。
2. 批准 Staging 持久化演练：先备份并记录用户/帖子/评论数量及测试 ID，再仅停止/重启本项目容器，复核记录及健康状态。
3. 批准隔离恢复演练：新临时数据库、无公网端口、约 384 MiB 内存；只恢复副本，保留现有 Staging 数据和 Volume。
4. 确认异地备份目的地、费用/配额、加密与访问策略、30 天保留策略、失败通知和每日计划；先演练取回及恢复再批准上线。
5. 确认生产随机密钥及凭据、正式 HTTPS/CORS、资源方案、创始人明确用户 ID/用户名及单次初始化窗口；不得以注册用户名自动授权。
6. 单独批准正式生产部署、DNS/网站切换及回滚窗口；本报告不构成上线授权。

### 容器持久化演练命令框架（仅批准后使用）

以下为操作计划，未执行。使用 VPS 现有 release，始终保留 overlay，不调用旧 deploy 控制器。
停止仅影响 Staging 访问；不会删除 Volume 或重建数据库。不得执行 down -v 或全局 prune。

```bash
R=/srv/heshan-staging/releases/eca42d278f39c64415f9946fec9f51aa6c113459
E=/etc/heshan-staging/staging.env
O=/etc/heshan-staging/web-ingress.override.yml
dc() { docker compose -p heshan-staging --env-file "$E" -f "$R/deploy/staging/compose.yml" -f "$O" "$@"; }
# 批准后，先保存备份与 SQL 基线，再执行：
dc stop
dc up -d --wait --wait-timeout 300
dc ps
# 随后复核原测试用户、帖子、评论、Flyway、HTTPS 与 OOM/restarts。
```

更新后的本地控制器支持 `--compose-overlay "$O"`，但尚未替换 VPS 旧版本。
本地控制器 deploy/preflight 是部署前检查，不是在线健康检查：运行中占用 18443 会被端口冲突检查拒绝。
在线检查应使用 status/只读 SQL；不要因此擅自停止服务。

## 本次文件清单

- frontend/src/pages/RegisterPage.jsx
- frontend/src/pages/PostsPage.jsx
- frontend/src/pages/FindPeoplePage.jsx
- frontend/src/pages/PostDetailPage.jsx
- frontend/src/components/PostList.jsx
- frontend/src/components/FindPersonPostList.jsx
- frontend/src/components/CommentList.jsx
- frontend/src/components/PostReplies.jsx
- frontend/src/loadingStates.test.js
- backend/src/test/java/net/tonghehui/backend/admin/AdministratorIntegrationTest.java
- docs/scripts/staging.py
- docs/scripts/test_staging.py
- docs/STAGING_DEPLOYMENT.md
- docs/PRELAUNCH_REVIEW_2026-10-12.md

此前的部署修复和验收文件保持原状，没有回滚或混入新的业务功能。
结论：本地 UI 与权限验收通过，但正式上线准备未全部完成，不能宣布已具备无条件上线资格。
