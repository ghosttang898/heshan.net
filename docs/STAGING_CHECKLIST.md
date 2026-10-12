# Staging 检查清单

状态范围严格区分：历史 PASS 是旧 artifact 的证据，不是新环境 PASS。
本轮没有连接 VPS，没有 Staging 部署，没有正式 ghost 授权。

## 证据分层

| 证据 | 当前状态 | 范围 |
| --- | --- | --- |
| 5710a89 VPS PostgreSQL 隔离测试 | 所有者报告 PASS / stopped=true / exit=0 | PG16、Flyway、Hibernate、注册/角色/一次性初始化、备份恢复；原始报告未在本轮重新读取 |
| 本轮 Java 17 Maven package | PASS，39 测试、0 失败/错误/跳过 | 业务代码与已验证 SHA 相同，真实本地 PG16；不等于服务器部署 |
| 本轮前端 npm test / npm run build | PASS，8 测试 / build exit=0 | 新鲜 Node24 依赖，API=/api；源码未修改 |
| 新 Staging 配置/安全脚本测试 | PASS，全套 64 项本地脚本测试 | 只在本地，故意失败场景不代表服务器失败 |
| 本地 Nginx TLS/SPA 安全 fixture | PASS（包含在 64 项内） | 非 root、可信临时证书、headers、路由/静态/API边界；fixture 无真实后端 |
| 新 Staging VPS 环境 | **NOT RUN** | 等待批准，包括资源、TLS、运行、浏览器与备份 |

Bash -n、Python 编译与 git diff --check 本轮通过。ShellCheck 本机未安装，未运行。
初次 Nginx fixture 发现默认 fastcgi_temp 在只读根目录创建失败，已把所有临时目录
放入受限 /tmp tmpfs；保留非 root/只读/cap_drop，最终 64 项完整回归通过。

## 上线前 18 项

| 检查 | 已有/本轮本地证据 | 部署后必须重新验证 |
| --- | --- | --- |
| 1 前端加载 | Vite build | 真实页面/JS/图片/CSP/控制台/桌面手机；HTTP smoke + 浏览器 |
| 2 注册 | 后端测试及历史 VPS | HTTP smoke --exercise-test-user，默认 USER |
| 3 登录 | 后端测试及历史 VPS | HTTP smoke，正确/错误凭据/退出 |
| 4 JWT | 生产 guard、数据库当前角色测试 | /auth/me、过期/无效 token、不跨 origin 转发 |
| 5 USER 发帖 | 后端现有测试 | HTTP smoke 合成帖子，聊天/寻人都实测 |
| 6 留言 | 后端现有测试 | HTTP smoke 合成评论，页面中验证 |
| 7 USER 后台拒绝 | 后端 ADMIN 测试 | HTTP 403 + 前端 AdminRoute |
| 8 ADMIN | 完整权限自动测试 | 合成管理员仅在测试环境授权；不能任命管理员/封禁 founder |
| 9 SUPER_ADMIN | 完整权限自动测试 | 合成超级管理员，旧 JWT 撤权、第二 SUPER 拒绝 |
| 10 ghost 初始化安全 | 历史 VPS 一次性确认/失败/重复测试 | 用独立集成项目/合成身份复测；不授权正式 ghost |
| 11 PG 持久化 | 本地 PG + 历史 VPS | 记录 ID/数量，显式 stop/start 同一 Staging Volume 后对照 |
| 12 Flyway | V1/repeat/validate 通过 | 当前 Staging migration history/version/checksum，无 update/clean |
| 13 备份恢复 | 历史 VPS 行级对照 + 本地流式备份测试 | 当前 Staging dump 校验、独立恢复；异地下载/恢复 NOT RUN |
| 14 SPA 回退 | 本地 Nginx fixture | /chat /find /posts/:id /login /register /admin 深链接刷新；API/缺失 assets 不回退 |
| 15 HTTPS | 本地 fixture 验证证书 | Mac 信任、SAN、有效期、实际 TLS1.2/1.3；不使用 -k |
| 16 安全头 | 本地 fixture | HTTPS/错误响应 CSP/nosniff/DENY/no-referrer/noindex；未对 localhost 全局加 HSTS |
| 17 Analytics 排除 | 8 前端测试保留 production allowlist | localhost、测试域名、Pages 不发 beacon；不得污染现有统计；正式 /admin/login/register 排除复测 |
| 18 不泄露凭据 | git diff/ignore、日志脱敏测试 | Network、日志、公开 bundle、错误页；不分享 test.env/完整 inspect |

## 自动命令与人工检查

本地：
```bash
RUN_STAGING_NGINX_TEST=1 python3 -m unittest discover -s docs/scripts -p 'test_*.py'
VITE_API_BASE_URL=/api bash docs/scripts/verify-frontend-build.sh
# Java 17 + local Docker：mvn -f backend/pom.xml -B package
git diff --check
```

服务器/浏览器未来：执行 STAGING_DEPLOYMENT.md 的 preflight/status/HTTPS smoke。
HTTP smoke 没有 ADMIN/SUPER/founder 自动授权功能，不能用其 PASS 代表这些项目通过。
需要角色完整回归时，复用 `run-vps-postgresql-test.sh IMAGE synthetic-staging-owner SHA`
在**另外新建的独立集成项目**测试，先停 Staging 腾出内存；保留其报告/Volume。
当前 Staging 的真实管理员页面仍需合成身份验证与人工浏览器检查；未经批准不运行 founder 命令。

报告至少记录：源 SHA/镜像 ID与架构、Compose 项目、时间、各项 PASS/FAIL/NOT RUN、
HTTP 退出码、容器停止证据、实际内存/CPU/磁盘、证书、备份 checksum及恢复对照。
容器 healthy 不是完整 PASS；IP 属地 localhost=未知是预期，不回填历史属地。

在新 Staging 上采集 `docker stats --no-stream`、`free -h`、`df -h`、OOM/restart状态，
开启页面与注册/发帖/备份等操作期间多次采样。仅记录资源/状态，不输出容器 Env。
认证密码/JWT 不作为命令行实参、URL、日志或截图内容。
