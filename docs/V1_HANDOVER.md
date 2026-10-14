# 同鹤汇 V1 上线交接

更新日期：2026-10-14。下一轮首先阅读本文件。本文件汇总历史服务器报告、所有者确认和本轮本地检查，不代表重新执行全部生产验收。

## 当前版本

- V1 已上线：[heshan.net](https://heshan.net/)，www 同样可访问。
- 应用镜像/前端源码：`a67f2bf4ad1765abd48c00856c3e9cd9a94efb9a`。
- 生产基础配置：`c935f3979734d0c096a00a670e65e2c01fc53fa3`。
- 本次 GitHub 归档包含后续测试、脚本和文档，不代表生产镜像已更新到归档提交。
- 单台 Ubuntu 24.04 VPS `165.232.156.104`，2GB/1vCPU，已有约 1GB Swap；不增加服务器。
- Cloudflare Proxied + Full (strict)；宿主机 Nginx 托管 React 静态文件并同源转发 `/api`。
- 生产 project `heshan`，库 `heshan_production`，应用角色 `heshan_prod_app`，Volume `heshan_postgres_data`。
- 数据库和 Backend 不公开端口；内部 API 代理只绑定 `127.0.0.1:8080`。
- Staging project `heshan-staging`，Volume `heshan-staging_staging_data`，入口仅 `127.0.0.1:18443`。
- 生产与 Staging 数据、JWT、配置、证书独立；保留 Staging，不擅自停止、覆盖或删除。

## 已完成与证据边界

| 项目 | 结论 | 证据范围 |
| --- | --- | --- |
| 注册、登录、发帖、寻人、评论、保存、USER 后台拦截 | PASS | 生产 API 报告和所有者最终验收成功 |
| 匿名评论 | 保留 | 既有规则；输入长度/必填校验已进入 a67f2bf |
| 年份搜索 | PASS | 单年包含、区间交集和旧记录兼容；已上线，不是待部署功能 |
| 注册页 SiteHeader、列表/评论 Loading | PASS | 本地测试和已有部署验收 |
| USER/ADMIN/SUPER_ADMIN、JWT 防提权 | PASS | 自动化隔离权限测试，不代替全部真实后台操作 |
| 创始人 | PASS | 生产 ghost ID 2，SUPER_ADMIN；唯一绑定/一次初始化审计，所有者确认后台可进入 |
| 公共 HTTPS、API、SPA、动态 API 不缓存 | PASS | 正式切换报告；本轮额外只读 GET `/api/health` 返回 ok |
| IP 属地 | PASS | 所有者确认正确显示；本轮公开接口只读复查有 2 条评论 RESOLVED，无原始 IP 字段；不回填旧记录 |
| Staging 独立恢复、结构/数据一致性、DB/Backend 重启持久化 | PASS | 已保留实际报告，不等于生产重复实测 |
| 生产逻辑备份、SHA256、归档列表、Mac 副本 | PASS | 已有报告；不等于持续每日备份或生产恢复已验证 |
| 最新实时资源 | READ-ONLY VERIFIED | RAM 可用 868MiB、Swap 使用 7MiB、磁盘约 40GiB；Nginx active/enabled |

本轮未取得 sudo，未重新核验六个容器的 OOM/重启计数；最后证据来自此前受控执行报告。
本轮本地回归：前端 23 项通过，后端含真实 PostgreSQL 和 MMDB 的 51 项全部通过，
脚本测试 175 项中 174 项通过、1 项本地 Staging Nginx opt-in fixture 未启用而跳过。
前后端生产构建均通过，详细范围见 [本轮归档验证记录](V1_RELEASE_VERIFICATION_2026-10-14.md)。
一次默认 Python urllib 公网请求收到 403，而 curl 健康接口/帖子/评论请求成功；
未证明 403 的具体来源，不为测试放宽 Cloudflare 防护，不把此请求标为 PASS。
详见 [切换记录](MVP_LAUNCH_ACCEPTANCE_2026-10-14.md) 和 [IP 属地运行说明](MVP_GEOIP.md)。

## 未完成事项（最多十项）

| 优先级 | 事项 | 当前状态与下一步 |
| --- | --- | --- |
| 尽快人工处理 | 作废暴露的 B2 管理密钥 | 主密钥曾出现在截图，视为已暴露。所有者到 B2 作废/轮换，不在聊天传新密钥；检查不用的受限密钥是否到期/需撤销。尚未核实作废。B2 不接入 MVP。 |
| 日常必做 | 每日人工备份和服务器外副本 | 现有脚本可用，未启用自动调度；明确所有者负责，记录成功和 SHA256。一份历史 Mac 副本不等于持续备份。 |
| 运维收尾 | 实际保留策略 | 建议服务器至少 7 天、Mac 至少 30 天；当前不自动删除。清理前确认另一份完整可恢复副本并单独批准。 |
| 待批准演练 | 生产备份独立恢复 | NOT TESTED。现有恢复工具限 Staging 且要求 ghost 为 USER，禁止直接用于生产或绕过门禁；先审定临时目标和生产 founder 保护检查。 |
| 待批准演练 | 生产 DB/Backend、整机重启 | NOT TESTED。Staging 实测与生产持久 Volume 不代替生产实测；先备份、安排窗口、分阶段检查，不删卷。 |
| 上线后验收 | 真实手机/移动网络、完整管理员操作 | 已有模拟视口、后台入口、权限自动测试；多机型及 ADMIN 管理帖子/评论/用户、授撤权浏览器完整矩阵未逐项记录。仅用临时账号，不动 ghost。 |
| 定期维护 | TLS 与 GeoIP 更新 | Origin 证书 2027-10-14 到期，提前人工续签；DB-IP Lite 按需按月换新版本，不原地覆盖正在映射的文件。 |
| 需要时批准 | Staging 常驻资源 | 两套当前并行且有 Swap；观察余量，确实不用 Staging 时另行批准停止并保留全部数据，不擅自停服务。 |
| 上线后观察 | 匿名评论滥用和真实负载 | 先用现有后台审核并观察日志/资源；有真实问题再做最小修复，不提前新增复杂平台。 |
| 明确暂停 | B2/rclone、自动异地同步、新恢复框架/控制器、Pages/集群 | 非 V1 阻塞项，不继续开发、购买或启用；保留已有成果，不把设计文档当运行状态。 |

截至当前证据，没有已知未修复的 V1 核心功能阻塞。NOT TESTED 仍是真实缺口，不能因已上线就宣称全部运维及设备验收完成。

## 下轮操作规则

- 生产发布目录：`/srv/heshan/releases/c935f3979734d0c096a00a670e65e2c01fc53fa3`。
- 秘密配置 `/etc/heshan/production.env` root-only；不输出 env、完整 inspect/config。
- GeoIP 启用后的 Compose 入口：`sudo bash /etc/heshan/production-compose.sh`，必须包含 `/etc/heshan/compose.geoip.yml`。更新 release 时一并审查包装脚本路径，不回用丢失 overlay 的旧控制器。
- Staging 保留 `/etc/heshan-staging/web-ingress.override.yml`；禁止混用生产配置。
- 备份目录 `/var/backups/heshan`，已确认 Mac 副本目录 `/Users/qizhitang/.heshan-production-backup-iUyQH3A9/`。dump、env、MMDB、密钥均不进入 Git。
- 现有 `docs/scripts/backup-postgresql.sh` 默认本地导出，必须指定正确生产 env、Compose 和备份目录；不会清理旧备份。不要因备份执行 up/down/迁移。
- 创始人已初始化，禁止重跑任何 founder 初始化命令。用户名 ghost 本身不是归属证据。
- sudo 由所有者在终端隐藏输入；不得索要密码或绕过权限。
- 部署、重启/重建、数据库操作/恢复、DNS/Cloudflare/SSH/防火墙变更先说明影响并批准。
- 禁止 down -v、prune、原库覆盖恢复、修改已应用 V1 迁移、自动 Flyway clean/repair。

## 下一轮建议

先完成密钥作废和日常备份责任，再选择一个范围明确的真实用户反馈进行开发。
不要重新安装数据库、初始化 ghost、运行旧上线脚本或扩展暂停的基础设施。
本轮仅归档与本地验证；Git 提交和推送不执行任何 VPS 部署命令。
