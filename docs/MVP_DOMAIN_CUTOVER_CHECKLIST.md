# MVP 域名切换清单

预检查时间：2026-10-14，约 15:20 UTC。

**实际切换已于 2026-10-14 约 15:34 UTC 经所有者批准完成**：Full (strict)，
根域及 www A 均为 165.232.156.104 / Proxied。_domainconnect 未变。
普通公共 HTTPS、API、SPA 与浏览器只读验收通过，详见
[正式切换验收记录](MVP_LAUNCH_ACCEPTANCE_2026-10-14.md)。下表保留切换前快照，非当前配置。

## 已核对的当前状态

| 项目 | 实际状态 |
| --- | --- |
| 权威 NS | chan.ns.cloudflare.com、rene.ns.cloudflare.com |
| 根域 A | 206.189.219.41，DNS only，控制台 TTL Auto，权威查询 300 秒 |
| www A | 206.189.219.41，DNS only，控制台 TTL Auto，权威查询 300 秒 |
| 其他 DNS | _domainconnect CNAME 指向 _domainconnect.gd.domaincontrol.com；保留不动 |
| AAAA / www CNAME | 此次查询与记录列表中未发现 |
| 邮件 | 当前记录列表无 MX；本轮不新增邮件配置 |
| Cloudflare SSL 模式 | Full，不是 Full (strict) |
| 边缘证书 | Universal Active，heshan.net、*.heshan.net，控制台到期日 2027-01-11 |
| Cloudflare HTTPS 开关 | Always Use HTTPS 未开启；HSTS 未启用；Automatic HTTPS Rewrites 开启 |
| 边缘 TLS | 最低 TLS 1.0（默认）；TLS 1.3 开启；本轮不修改 |
| Cache Rules | 无 Cache Rules、无 Cache Response Rules |
| Page Rules | 无 Page Rules，已用 0/3 |
| 新 VPS | 165.232.156.104，Nginx active / enabled |
| 新站 HTTPS API | Mac 使用 Origin CA、正确域名及 --resolve 直连，/api/health 正常 |
| 端口 | 80/443 为站点入口；8080、18443 仅绑定 127.0.0.1；未见主机 5432 监听 |
| VPS 资源快照 | 可用 RAM 878MiB，Swap 使用 5MiB，磁盘剩余约 40GiB |

上述证书状态是控制台记录，不是 Cloudflare 代理链路已经完成验收。
DNS 切换前必须再次核对实际记录，不能把本清单当作永久快照。

## 备份与验收证据

- 生产应用版本：a67f2bf4ad1765abd48c00856c3e9cd9a94efb9a。
- 部署配置版本：c935f3979734d0c096a00a670e65e2c01fc53fa3。
- 所有者本人确认生产 ghost：ID 2，SUPER_ADMIN；绑定及一次初始化审计已通过。
- 生产备份：`/var/backups/heshan/heshan-20261014T151729Z.dump`。
- Mac 副本：`/Users/qizhitang/.heshan-production-backup-iUyQH3A9/`，SHA256 校验通过。
- 服务器原备份保持 root-only；Mac 目录 0700、文件 0600，均不放入 Git。
- 实际生产 API 注册、登录、发帖、寻人类型发帖、评论及 USER 权限拦截已通过。
- 所有者确认浏览器注册、登录及管理员后台入口可用，不等于全部后台写操作已验收。
- 新生产备份实际恢复、整机重启自动启动、Cloudflare 代理后的验收：NOT TESTED。

## 当前故障处理范围

本次从 Mac 指定旧 IP 检查：旧根域 HTTP 301 到 www，www HTTP 200；
根域和 www 的旧服务器 443 连接均失败。只能证明此次网络路径的检测结果，
未检查旧主机内部配置或管理权限。

所有者已明确旧站只有简单页面、无迁移数据：不继续修复旧 HTTPS，也不研究旧站回滚。
故障处理以保留新 VPS 的 HTTPS 入口、数据库及备份，并在新环境排查修复为主。
不自动改回旧 A，不降低 SSL 安全模式，不用旧备份覆盖新数据。

## 本次已批准的切换顺序

1. 确认新环境故障处理方式、切换时间及最新备份。保留全部 Volume 和 Staging。
2. 再查新站健康、证书、可用资源和当前 DNS。不要通过测试 Chrome 的域名覆盖判断公共解析。
3. 经批准将 SSL 模式改为 Full (strict)。当前 DNS only 不代理流量；不要先给旧 IP 开代理。
4. 分别编辑现有根域和 www A：在同一次保存中将 IP 改为 165.232.156.104、代理改为 Proxied。
   不新增重复 A，不改 NS、_domainconnect 或无关记录；如现场存在新 AAAA/CNAME，先停止评估。
5. 不新增 Cache Everything、Workers、付费功能或长周期 HSTS。最低 TLS 1.2 可作为单独批准的设置项。
6. 用普通浏览器和手机移动网络验证公共 HTTPS，无测试证书例外；确认边缘证书和正确新站内容。
7. 验证 /api/health、SPA 刷新、登录/退出/重登、发帖、评论、寻人页面、普通用户后台拦截及 ghost 后台。
   检查 API/登录响应没有被缓存，不将 JWT、密码或响应正文写入公开报告。
8. 观察错误、OOM、重启和资源，验收通过后再公开通知用户；DNS 缓存可能使新旧站短时并存。

启用代理后公共 A 通常显示 Cloudflare 边缘地址，不能用“解析必须显示新 VPS IP”作为通过标准。

## 失败处理（仅方案）

- 证书错误、重定向循环、持续 5xx 或数据异常：停止宣布上线，保存证据，先定位 DNS/边缘/源站层次。
- 不研究或自动执行旧站回滚。需要维护页面、版本回退或服务重启时，先说明影响并获得批准。
- 新站切换后若有真实用户写入，先保存新生产库备份；版本修复不能丢失这些数据。
- 不还原旧 dump 覆盖新生产库，不删除新数据库、Volume、测试资源或备份。
- 不自动更改 SSL 为 Flexible，也不关闭新源站服务或销毁 Staging。

参考：
- [Cloudflare Full (strict)](https://developers.cloudflare.com/ssl/origin-configuration/ssl-modes/full-strict/)
- [Cloudflare Origin CA](https://developers.cloudflare.com/ssl/origin-configuration/origin-ca/)
- [Universal SSL](https://developers.cloudflare.com/ssl/edge-certificates/universal-ssl/enable-universal-ssl/)
