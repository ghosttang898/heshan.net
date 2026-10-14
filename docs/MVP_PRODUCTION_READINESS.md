# MVP 生产条件复核

日期：2026-10-13（America/New_York）。仅只读检查和本地测试，无正式部署。

| 项目 | 状态及证据 |
| --- | --- |
| Cloudflare NS | PASS：公共 DNS 为 rene/chan.ns.cloudflare.com |
| 旧站保护 | PASS：根域/www 仍为 206.189.219.41，www HTTP 200、Apache；未切换 |
| VPS SSH/资源 | PASS：Ubuntu 24.04，1967MiB RAM，可用1212MiB，Swap1023MiB用2MiB，磁盘40GiB；负载0.01/0.09/0.10 |
| 端口余量 | PASS：只读 ss 未见80/443/8080/5432监听；18443仍只绑定127.0.0.1 |
| 生产 Compose | LOCAL PASS：合成环境变量执行config --quiet成功，未创建容器 |
| Nginx/TLS模板、备份/更新安全测试 | LOCAL PASS：19项，包含临时本地Nginx语法及HTTPS/SPA/缓存/防伪检查 |
| Spring Boot、PostgreSQL功能 | 既有Staging/本地测试PASS；生产实例NOT TESTED |
| 宿主机 Nginx | command -v未找到；安装包/完整配置需sudo确认，未安装 |
| 正式证书和续期 | NOT VERIFIED：受保护路径需sudo确认；localhost证书不能用于正式域名 |
| 独立生产库/卷/凭据 | NOT VERIFIED：未见/etc/heshan或/srv/heshan；Docker权限不足，未执行创建或迁移 |
| 生产备份 | NOT TESTED：生产库尚未核实/部署；现有Staging备份不是生产备份 |
| ghost生产账号 | NOT VERIFIED：不得从Staging记录推断归属，未提权 |
| Cloudflare缓存规则/Strict/边缘证书 | NOT VERIFIED：没有读取或修改控制台 |

DNS-only由用户确认；公开解析未显示Cloudflare代理地址与此一致，不能据此核实整个账号规则。
服务器sudo -n请求被密码门禁拒绝，已停止，没有绕过认证。没有读取env、私钥或数据库密码。
本轮未重跑全部Java/React测试；此前候选a67f2bf的测试及Staging更新报告保持为历史证据。
本地生产模板/备份修复尚未提交，实际生产发布包必须固定最终批准的提交，不能将工作区
未提交配置误称为a67f2bf的内容。不要混入暂停的B2/恢复框架工作。

## 最简后续顺序

1. 所有者终端执行sudo只读复核：所有运行容器、健康、Volume/网络、Nginx/证书、UFW、
   备份目录元数据；核对172.30.10.0/24不与现有网络冲突，生产heshan项目及目标卷不存在。
   不输出docker完整inspect、compose渲染或env内容。发生冲突就停止。
2. 批准提交最小生产配置并本地测试/打包，指定SHA镜像与静态版本；不默认推送。
3. 单独批准备份并停止Staging，不删除卷、容器或配置。重新检查空闲RAM，避免两套长期并行。
4. 单独批准Nginx/证书准备和全新生产数据库、卷及秘密文件。DNS仍保持旧IP。
   Flyway会在首次启动生产Backend时执行，所以启动Backend必须包含明确迁移授权。
5. 生产环境通过隧道/指定IP验证，再由所有者本人注册登录ghost并核实真实ID。
   提权和审计初始化另行批准，禁止复用Staging账号数据/ID或按用户名自动授予。
6. 核验生产备份并下载到Mac，正式证书、HTTPS/SPA/API/功能、权限、资源全部验收通过。
7. 最后单独批准网站A记录/代理切换到165.232.156.104及Full(strict)，核对边缘证书，
   保持旧服务器可回退。应用回滚不覆盖数据库；DNS回退前保留新站写入数据。

继续使用单VPS、独立heshan项目和生产数据库、同源/api、不启用rclone或购买服务。
部署上限DB384MiB+Backend768MiB+proxy64MiB，加宿主机Nginx少量内存；停止Staging后可行，
但生产实测仍需执行。模板准备完成不等于正式部署通过。
