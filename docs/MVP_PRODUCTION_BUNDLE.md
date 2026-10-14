# MVP 生产发布包准备

应用版本：a67f2bf4ad1765abd48c00856c3e9cd9a94efb9a，已在Staging验收。
本轮仅本地准备，不上传到VPS，不启动服务，不生成真实秘密，不执行迁移。
生产配置修复尚未提交，使用逐文件SHA256固定本次配置；不能声称配置已包含在应用提交中。
后续正式部署前须另行批准提交这部分最小配置；不混入暂停的B2/恢复框架工作。

## 包含与排除

包含指定SHA的linux/amd64非root后端镜像、同SHA前端静态文件、现有生产Compose、
postgres-init.sh、API代理配置、宿主机Nginx模板、Cloudflare信任网段、默认本地备份脚本、
空秘密字段的production.env.example、公开版本元数据和逐文件SHA256清单。
不包含.env、TLS私钥/证书、生产或Staging数据、数据库备份、测试截图、rclone配置及B2凭据。
保留原有offsite profile代码但不启用，不新增任何云服务或控制器。

## 生产隔离

- 项目heshan；数据库heshan_production；应用账号heshan_prod_app。
- 预期卷heshan_postgres_data，禁止挂载heshan-staging_staging_data或任何已有卷。
- DB/Backend无宿主机端口；API proxy仅127.0.0.1:8080。
- 生产.env为root:0600；数据库管理员/应用密码/JWT必须分别随机生成，不复用Staging。
- Compose数据库、后端和proxy禁止自动pull；先核实已有镜像身份，不覆写已有不匹配标签。
- 资源上限384+768+64MiB；不得同时长期运行完整Staging与Production。

## 下一阶段必须逐项批准

1. 上传/安装固定发布包，仍不启动容器；配置及秘密生成在服务器本地完成，禁止输出秘密。
2. 确认生产项目/卷不存在、网段和端口无冲突，备份Staging；如需停止Staging须另行批准，
   保留其容器/Volume/env/TLS/ingress配置。不能为了资源随意停其他服务。
3. 单独批准生产db启动：全新卷上的postgres-init会创建独立应用角色，并修改新数据库权限。
   这不是只读操作，也不是Flyway迁移，不得没有授权直接运行。
4. 单独批准Backend首次启动：prod环境强制PostgreSQL、Flyway V1和Hibernate validate，
   所以启动Backend即授权在新生产库执行迁移。不能拿health检查作为绕过迁移审批的理由。
5. 单独批准proxy和宿主机Nginx启动，验证已准备的Origin CA及同源API；保持DNS/代理不变。
   Origin CA不能在普通浏览器直连时当公开CA使用；隧道测试需指定官方根CA和正确主机名。
6. 用临时生产测试账号验证注册/登录/帖子/评论及权限，随后核验生产逻辑备份并下载到Mac。
   用户身份/帖子/评论验证可能产生生产测试数据，需明确授权，不能擅自清空。
7. 所有者本人注册登录ghost并双重核实ID/用户名，SUPER_ADMIN一次性初始化另行批准。
8. 确认备份后再批准生产重启持久化验收；恢复只能另行批准到独立临时数据库。
9. DNS切换、代理和Full(strict)始终单独批准；本轮不执行，旧站仍保留可回滚。

## 回滚约束

在任何上线切换之前，失败只保留新生产现场/卷/日志，不触碰Staging数据。
重新启动Staging要显式使用现有ingress overlay，先确认内存余量；不同时再起一套生产后端。
应用回滚使用保存的镜像/静态版本，不覆盖数据库、不使用down -v、prune、Flyway clean/repair。
Origin CA不能通过单纯关闭Cloudflare代理无损回退HTTPS；需要旧站或公开CA证书。

## 本轮本地结果（2026-10-14）

- Maven：50项，49通过、1跳过，0失败/错误。跳过项需要可选GeoIP数据库夹具。
  本机隔离PostgreSQL/Flyway/Hibernate、管理员与创始人测试正常。
- 前端23项通过，VITE_API_BASE_URL=/api生产构建退出0。
- 配置/备份/TLS/更新脚本26项通过；生产模型资源、隔离、端口及禁止自动pull验证通过。
- 模型检查仅解析配置，不创建生产容器/数据库。JSON中的内存数字可能为字符串，
  测试按整数规范解析，不修改实际资源限制来迁就工具输出。
- 发布包秘密字段为空，无.env、私钥、数据库备份、Staging数据或测试截图。
- 未上传包、安装服务器配置、运行生产迁移、初始化ghost、改DNS或启动生产服务。
