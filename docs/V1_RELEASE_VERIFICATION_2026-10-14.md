# V1 归档前验证

日期：2026-10-14。归档已有成果，不部署新应用、不重启服务、不修改 DNS/数据库/权限。
当前状态和未完成事项见 [V1 交接](V1_HANDOVER.md)。

## 本轮重新执行

| 检查 | 结果 | 说明 |
| --- | --- | --- |
| 前端 `npm test` | PASS | 23 项，0 失败、0 跳过；包括年份交集、Loading、注册页导航、输入校验和 Analytics 排除 |
| 前端 `npm run build` | PASS | Vite 5.4.21，2013 模块，实际生产构建完成；产物不提交 |
| 后端 Java 17 `mvn test` | PASS | 首轮 50 通过、1 个需指定 MMDB 的测试跳过；指定真实 MMDB 后全量 51 通过，0 跳过 |
| PostgreSQL/Flyway/创始人回归 | PASS | 上述后端测试包含本地 Docker 隔离 PostgreSQL；不连接 VPS 数据库 |
| 后端 `mvn package -DskipTests` | PASS | 打包通过；测试单独全量执行，不能将跳过测试的打包当测试结果 |
| Python 脚本 `unittest discover` | PASS | 共 175 项，174 通过，1 个显式 opt-in 的本地 Staging Nginx fixture 跳过；模拟失败场景日志不等于测试失败 |
| 公网健康接口 | PASS | curl 正常证书校验 GET `/api/health` 返回 ok，不使用 -k 或 hosts 覆盖 |
| IP 属地及隐私只读复查 | PASS | 公开评论中 2 条 RESOLVED；帖子/评论未发现原始 IP 字段。旧快照仍有 NON_PUBLIC/DATABASE_UNAVAILABLE，不回填 |
| VPS 无 sudo 只读检查 | PASS | Nginx active/enabled，RAM 可用 868MiB，Swap 使用 7MiB，磁盘剩余约 40GiB，负载 0.24/0.31/0.25 |

Python 默认 urllib 的一次公网请求返回 403，具体来源未证明；curl 后续读取成功。
未调整防护规则以迁就脚本，也未把那次请求标为 PASS。

## 未在本轮执行

- sudo 容器 inspect、数据库查询、备份导出、生产备份恢复、重启/重建及部署。
- 新增生产测试用户、帖子或评论；管理员权限变更与 founder 初始化。
- 新的浏览器交互或真实手机验收；已有验收证据不冒充本轮测试。
- B2/rclone、定时任务和任何自动清理。

## Git 安全边界

检查当前索引和待推送改动，排除真实 env、私钥、数据库备份、MMDB、构建产物及凭据文件。
未发现真实凭据；API 测试中的 `https://user:password@api.heshan.net/api` 是用于验证拒绝
带凭据地址的固定合成反例，不是运行配置。忽略规则覆盖上述敏感文件类型。
模式扫描不能代替长期密钥管理；此前截图中暴露的 B2 管理密钥仍需所有者作废，不因 Git 检查通过而视为安全。

本次提交归档脚本、测试、历史验收和交接文档，并推送此前尚未同步的三个本地发布提交。
仓库中未发现 GitHub Actions 部署工作流；本轮不执行 VPS 发布命令。
生产镜像仍为 a67f2bf，基础配置 c935f39 加现有服务器 GeoIP overlay；新归档 SHA 不是线上镜像版本。
