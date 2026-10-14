# Staging 分阶段更新与回滚计划

## 适用范围和禁止事项

仅更新 heshan-staging 的 Backend/Web，不调用 first-install，不运行 init-env 或 founder 初始化。
保留现有 PostgreSQL Volume、用户/帖子/评论、证书、随机数据库密码/JWT 密钥及 ingress overlay。
不修改生产网站、生产数据库、DNS、Cloudflare、防火墙、SSH 或真实 ghost。
sudo、备份、容器重建、停启和恢复均由网站所有者在终端明确批准后执行。
本文件是操作计划，不表示已经执行部署或完成上线验收。

## 变更清单

- 注册页复用 SiteHeader，保持既有手机布局。
- 聊天、寻人和评论区明确区分 loading/error/ready/empty。
- 增加 JSX 渲染回归和 JWT 篡改测试；无新的后端业务 API。
- 新 Compose 永久包含 web-only ingress；数据库和 Backend 仍不加入入口网络。
- 新控制器支持显式 --compose-overlay；已安装 overlay 却省略参数会拒绝执行。
- 补齐 TLS/public 目录权限及 Nginx 双网络回归、功能验收和上线前报告。
- 数据库迁移文件、实体和角色规则没有变化；不依赖 ddl-auto=update。
- 新增 preupdate 备份门禁：保存只读 SQL 基线、pg_dump、校验和与 archive listing，保留失败报告及文件。

## 阶段 A：本地准备

1. 检查修改/未跟踪文件、敏感信息及生成物；只提交安全源代码和文档。
2. 经授权创建本地发布提交，使用真实完整 Git SHA，不推送 GitHub。
3. Java 17 执行 mvn clean package，包含现有权限和 PostgreSQL 隔离测试。
4. 使用独立 Node 24 构建环境，VITE_API_BASE_URL=/api，执行 npm ci/npm test/npm run build。
5. 根据同一 SHA 构建 linux/amd64 的 heshan-backend:SHA；不覆盖旧标签，不使用 latest/pg-test。
6. 打包镜像、静态文件、SHA 元数据、新 Compose/controller 和校验清单；不包含 TLS 私钥或 .env。
7. 通过普通 heshan 账号上传到新临时目录，不覆盖 release 或服务器配置。

## 阶段 B：备份与门禁（需要所有者终端批准）

仅运行 staging-preupdate-backup.sh --execute-backup。
影响：创建 root-only 的新备份、报告及 SQL 基线；pg_dump 会短暂消耗 CPU/磁盘 I/O 并取得读锁。
不会停服务、重建容器、恢复数据、更换证书或修改账号。
应暂停测试数据写入，避免备份前后基线不一致。脚本发现数据变化会 FAIL 并保留备份。

脚本要求：三服务 healthy、OOM=false、端口仅 127.0.0.1:18443、overlay 存在且 root:0600、
目标库为 heshan_staging、可用 RAM >=512 MiB、备份磁盘空间 >=4 GiB。
输出绝对 report_directory 和 backup 路径；result.json 必须 PASS。
备份存在、非空、可列出 archive contents 并通过 checksum 不等于实际恢复已经通过。

```bash
# UPLOAD 为本轮实际上传的新目录，确认路径后才能执行；密码只在终端输入。
ssh -t -i ~/.ssh/id_ed25519 heshan@165.232.156.104 \
  'sudo bash UPLOAD/docs/scripts/staging-preupdate-backup.sh --execute-backup'
```

收到 result.json、备份路径和门禁输出后，才进入下一阶段。不要从旧控制器直接 deploy。

## 阶段 C：应用更新（另行批准后提供实际命令）

1. 校验完整发布包、源 SHA、AMD64 镜像标签/OCI 身份，确认迁移内容与当前 V1 一致。
2. 创建新的不可覆盖 release 目录；只复制公开静态资源和程序配置，不复制或重建 TLS/env。
3. root:0600 保存当前 env 的回滚副本，记录旧 SHA、旧 release、旧镜像 ID 及 DB 容器 ID/Volume。
4. 新 env 仅变更 STAGING_BACKEND_IMAGE、STAGING_BACKEND_REVISION、STAGING_FRONTEND_REVISION、
   STAGING_STATIC_DIR，其他字段逐项保持原值。秘密只在服务器本地处理，不打印或上传。
5. 显式使用新 release 的 Compose + 现有 /etc/heshan-staging/web-ingress.override.yml。
   先配置校验；新控制器不作为在线 preflight 使用，避免误把当前 18443 当作可回收端口。
6. 先仅重建 Backend，等待 healthy；再仅重建 Web，等待 healthy（--no-deps，绝不 up/recreate db）。
7. 检查 DB 容器 ID、数据卷名及只读基线；TLS 路径、凭据和所有记录都应保持。

预期短暂 Staging 不可用，通常数十秒到数分钟；不影响旧正式站。可能出现启动失败、
短暂 502 或依赖配置错误，因此必须保留旧镜像/release/env 和已验证的备份。
允许应用启动时 Flyway validate/migrate，但本次没有新 migration，不能重建数据库。

## 回滚（只回滚应用，不覆盖数据库）

更新失败则保留新版本日志，恢复 root-only 的旧 env（含旧静态文件路径/镜像 SHA），
始终使用包含 ingress overlay 的 Compose，仅重建旧 Backend，再重建旧 Web。
确认 DB 容器、Volume 和数据不变，并重新检查 HTTPS/API。
旧 release 和旧镜像不删除；不从 dump 覆盖现有数据库，不自动回滚 SQL。
如果发现 DB/schema 与预期不一致，停止后续操作，报告证据并等待所有者决定。
保存备份是事故防线，不是自动执行数据库覆盖恢复的授权。

## 阶段 D：部署后验收

实际验证三个 healthy、无 OOM/异常重启、仅 loopback 18443、HTTPS/API/SPA 和新注册页。
用临时 USER 检查注册/登录/退出、帖子/寻人/评论、Admin route/API 拒绝、IP 隐私、Analytics 不加载。
管理员授权测试继续使用隔离夹具；不在现有 Staging 创建 SUPER_ADMIN 或修改 ghost。
检查 320/390px 布局和浏览器控制台；加载状态使用受控延迟或渲染回归，不以截图时间猜测。
所有未实际执行项目必须 NOT TESTED。

## 阶段 E：容器持久化和独立恢复（各自另行批准）

持久化：已确认备份和基线后，仅 stop/up 本项目，始终两个 -f 文件，保留 Volume；
复核原用户/帖子/评论/角色/审计/Flyway 及 fingerprints。这会导致短暂测试站不可用。
不重启整个 VPS、Docker daemon 或其他项目，不执行 down -v。

恢复：先验证 dump checksum，再创建新的临时 PostgreSQL 16，network none、无发布端口、
384 MiB memory、0.25 CPU、全新随机命名的专用 Volume；只恢复备份副本并比较记录/约束/迁移/关键字段。
执行前 RAM 至少可用 768MiB、磁盘至少剩余 4GiB，过程中持续采样，不足则停止临时目标。
恢复测试约额外消耗 384 MiB RAM 和短暂 CPU/磁盘 I/O。必须在低负载时核对内存余量。
保留备份和结果；现有数据库和所有现有 Volume 不触碰。
加固后的 test-restore-postgresql.sh 要求显式批准、同一备份时点的完整参考及确认的所有者 ID/用户名。
它仅停止自己核验过的临时容器，不删除容器、Docker Volume、备份或报告。
执行前须按 [独立恢复方案](STAGING_ISOLATED_RESTORE.md) 复核新的资源上限和参数；
不能沿用旧单路径调用，也不能把 archive listing 当成恢复 PASS。

## 2GB VPS 资源策略

单套主服务 memory 上限 384+768+64=1216 MiB，备份上传可再用 128 MiB，另留宿主机余量。
两套完整环境上限 2432 MiB 超过物理 RAM；Swap 只作峰值缓冲，不作为稳定容量承诺。
低负载更新时顺序替换 Backend/Web，不并行跑 Maven/npm 或临时恢复测试。
不为了部署停止其他服务、不关闭 OOM 保护、不自动增加收费资源。
有 OOM、重启循环或资源不足就停止本轮应用更新/恢复，保留证据并等待确认。

## 当前验收状态

本地准备有实际测试证据；服务器更新、备份、重启持久化、独立恢复和部署后验收尚未执行。
因此整体仍为 NOT TESTED / 等待批准，不是上线成功或正式切换许可。
