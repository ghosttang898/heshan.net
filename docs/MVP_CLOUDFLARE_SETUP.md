# MVP：VPS + Cloudflare 免费 CDN

应用/服务器仍仅本地准备，未安装生产配置或正式上线。保留现有 Staging。
最新只读 DNS 复核：权威 NS 已为 rene.ns.cloudflare.com / chan.ns.cloudflare.com，
根域和 www 均仍指向旧 IP 206.189.219.41。用户确认 DNS-only。
以下步骤1–3的 NS 接入已由用户完成，不得重复修改；仍需确认邮件/DNSSEC等记录完整。

## 本轮文件

- deploy/nginx-site-https.conf.example：宿主机前端、同源 /api、SPA、TLS、安全头模板。
  前端路径 /srv/heshan/frontend-current 仅指向批准的生产静态版本，不能指向 Staging。
- deploy/cloudflare-realip.conf.example：官方 IPv4/IPv6 网段快照，安装前再次核对。
  只有这些来源的 CF-Connecting-IP 被信任；任意来源的 X-Forwarded-For 被覆盖。
- deploy/nginx.conf：内层 proxy 明确标记 https，仅允许来自宿主机 TLS 入口的访问。
- backup-postgresql.sh：默认 BACKUP_OFFSITE=0；生成 dump、SHA256、归档目录并核验，
  不上传、不清理。保留显式 BACKUP_OFFSITE=1 的旧能力，但本方案不使用。

## 域名接入顺序（每个外部变更都需所有者批准）

1. 用户登录 Cloudflare，选择 Free 方案添加 heshan.net，不购买额外功能。
   此时不改 GoDaddy Nameservers，不改网站 A/AAAA；先核对导入的 DNS。
2. 保存 GoDaddy 当前所有业务记录、TTL、NS及 DNSSEC 状态，尤其 MX、SPF、DKIM、
   DMARC、子域名和邮件主机。Cloudflare 自动扫描不是完整备份，需逐项核对。
   根域/www 暂时维持旧 IP 206.189.219.41，DNS-only；邮件记录不启用代理。
3. 经批准迁移权威 NS 到 Cloudflare；如有 DNSSEC/DS，按两个平台的正式迁移流程处理，
   不能把旧 DS 留给新 NS 导致域名解析失败。确认旧站和邮件解析正常后，再准备网站切换。
   本步骤只迁移 DNS 托管，不切换旧网站，不把不确定可用的旧 HTTPS 置于 Strict 代理后。
4. 在新 VPS 正式环境准备完成后，经批准获取 heshan.net/www 的有效源站证书。
   当前所有者已批准Origin CA准备：私钥在VPS生成，Cloudflare使用自有CSR签发，
   无需更改DNS。独立TLS路径及浏览器信任限制见[MVP Origin TLS](MVP_ORIGIN_TLS.md)。
   不使用 localhost CA。安装 Nginx 之前先备份现有配置，nginx -t 成功才允许 reload。
5. Cloudflare 使用 Full (strict)，核对边缘证书已生效；禁止 Flexible。
   不启用 Cache Everything、额外 Analytics 自动注入、付费功能或自定义 Workers。
6. 缓存绕过规则覆盖 /api（含子路径）、/admin（含子路径）、/login、/register，
   含 Authorization 的请求和非 GET/HEAD 请求也绕过缓存。静态 /assets/ 使用默认 CDN。
   模板给动态/HTML响应 no-store，只有成功的版本化资源响应给 immutable 缓存；404不长缓存。
7. 经单独批准，将根域/www 的网站记录指向 165.232.156.104 并开启代理。
   核对冲突的 AAAA/CNAME，不改邮件或其他子域名，保留旧站与所有旧资源。
8. 外网实测根域/www HTTPS、证书、页面、API、登录、缓存命中、属地和权限。
   实测代理必须验证真实访客属地，不以本地防伪测试代替真实 Cloudflare 链路验收。

## 备份与回滚

生产独立数据库/Volume、root:0600 env、独立 JWT、所有者账号验证仍是上线前门禁。
备份示例（尚未执行；实际服务器路径复核后再批准）：

```bash
sudo env ENV_FILE=/etc/heshan/production.env \
  COMPOSE_FILE=/srv/heshan/releases/APPROVED_SHA/deploy/compose.yml \
  BACKUP_DIR=/var/backups/heshan BACKUP_OFFSITE=0 \
  bash /srv/heshan/releases/APPROVED_SHA/docs/scripts/backup-postgresql.sh
```

每日手动执行并核验，安全下载到 Mac 后再次校验 SHA256。本地目标7天、Mac30天，
当前不自动删除，不启用定时任务；归档结构可读不等于恢复验收通过。
如 dump/校验/归档检查失败，保留现场且返回非零，不报告成功。

回滚分开处理：Origin CA不受普通浏览器信任，不能仅切DNS-only到新VPS来恢复HTTPS；
需要回旧站或事先准备公开CA证书。
新版应用问题回滚生产镜像及静态路径；必须回旧站时批准恢复旧网站记录并限制新版写入。
NS迁移回退影响整个域名/邮件，传播不会瞬时完成，不能当成日常应用回滚按钮。
任何回滚都不得删除生产/Staging Volume或用旧 dump 覆盖现有库。

## 核验依据和待验收

Cloudflare 网段：https://www.cloudflare.com/ips-v4 和 https://www.cloudflare.com/ips-v6。
Strict：https://developers.cloudflare.com/ssl/origin-configuration/ssl-modes/full-strict/。
本地自动测试覆盖 Nginx 语法、模拟 HTTPS、SPA/缓存/安全头、未可信来源 IP 防伪及
备份默认不调用 offsite。测试使用一次性自签证书，不代表正式证书有效。
尚未验证：Cloudflare账号/规则、真实源站证书和续期、真实生产 API、生产备份、外网缓存、
邮件/DNSSEC迁移及真实 Cloudflare 客户端 IP 链路。未经验证不得标记 PASS。
