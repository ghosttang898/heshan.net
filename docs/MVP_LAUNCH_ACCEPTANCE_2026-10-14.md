# 同鹤汇 MVP 正式切换记录

后续更新：所有者已确认最终验收成功、后台可进入，IP 属地修复后显示正常。
下文保留切换当轮的测试范围；仍未逐项实测的项目不自动改为 PASS。
当前未完成事项以 [V1 交接](V1_HANDOVER.md) 为准。

时间：2026-10-14，约 15:34 UTC（纽约约 11:34）。所有者明确批准后执行。

## 实际变更

- Cloudflare SSL/TLS：Full 改为 Full (strict)。
- heshan.net / www.heshan.net：各自现有 A 改为 165.232.156.104，并开启 Proxied，TTL Auto。
- _domainconnect CNAME 未变；未改 NS、SSH、防火墙、数据库、管理员权限或 Staging。
- 未新增付费服务、缓存规则或自动任务，未重启服务器服务，未删除资源。
- 所有者确认不再修复旧服务器 HTTPS、不研究旧站回滚；新站故障在新环境处理并保留数据。

## 本轮实测

| 项目 | 结果 | 证据及范围 |
| --- | --- | --- |
| Cloudflare 设置 | PASS | 控制台保存后显示 Full (strict)，两条 A 均为新 IP / Proxied |
| 公共 DNS | PASS | 权威查询返回 172.67.215.55、104.21.37.237；这些是当时的边缘地址，不能固定使用 |
| 根域及 www HTTPS API | PASS | 不用 --resolve、私有 CA 或 -k，均 HTTP/2 200，正常证书校验，server: cloudflare |
| API 缓存 | PASS | /api/health、/api/posts 为 no-store、CF-Cache-Status: DYNAMIC |
| 首页及 SPA 地址 | PASS | 两个域名的 /、/chat、/find、/login、/register 均 200，TLS 校验通过 |
| 未登录权限 | PASS | 两域 /api/auth/me、/api/admin/dashboard 均 401 |
| HTTP 跳转 | PASS | 根域 /login 与 www /find 均 308 到正确的 https://heshan.net 路径 |
| 普通 Chrome | PASS | 新开普通窗口，无测试解析或证书例外；首页和后端状态正常 |
| 寻人导航及刷新 | PASS | 浏览器导航、直接刷新、测试寻人记录加载正常 |
| 年份筛选 | PASS | 1980-1990 记录匹配 1985、1988-1992；不匹配 1995 |
| 手机尺寸布局 | PASS | Chrome 390x844 模拟；寻人、登录页文档宽度均 390，无横向溢出 |
| 浏览器控制台 | PASS | 本轮访问首页、寻人及登录页未捕获 warning/error |
| Nginx / 资源 | PASS | SSH 只读确认 active/enabled；可用 RAM 872MiB，Swap 用 5MiB，约 40GiB 磁盘剩余 |

完整手机硬件、移动网络访问未执行；手机尺寸模拟不等同真实手机网络验收。
本轮没有 sudo 容器 inspect，容器 OOM/重启计数的最后证据来自切换前已通过的服务器报告。

## 已有证据，不冒充切换后测试

- 切换前已通过生产注册、登录、发帖、评论、PostgreSQL 保存及 USER 管理员接口拦截。
- ghost 生产 ID 2，一次性 SUPER_ADMIN 初始化与绑定、审计通过；所有者确认可进入后台。
- 新备份位于 `/var/backups/heshan/heshan-20261014T151729Z.dump`。
- Mac 副本目录 `/Users/qizhitang/.heshan-production-backup-iUyQH3A9/`，SHA256 通过，目录 0700 / 文件 0600，未加入 Git。
- Staging 独立恢复、重启持久化通过，但不代替新生产备份的恢复演练。

## 尚需所有者完成

1. 用普通浏览器或手机移动网络打开 https://heshan.net/，不用专用验收 Chrome 或 SSH Tunnel。
2. 重新登录 ghost，确认后台；用临时普通账号验证注册、登录、发帖及评论经过 Cloudflare 仍正常。
   本轮这些认证及写入操作标为 NOT TESTED，没有代取所有者密码或新增测试账号。
3. 测试帖仍保留；需要隐藏或删除时由所有者明确决定，不自动清理数据库。
4. 继续每日手动备份并保存一份到 Mac；没有启用自动调度或 B2。
5. 新生产备份独立恢复、整机重启验证仍为 NOT TESTED，需另行批准。

## 结论

域名、代理、Full (strict) 与公共 HTTPS 基础链路切换成功。
不将此结论扩大为全部生产功能和移动网络验收已通过。保留现有数据、Volume 和备份。
本轮本地文档未自动提交或推送 GitHub。
