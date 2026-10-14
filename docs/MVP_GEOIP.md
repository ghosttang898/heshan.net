# MVP IP 属地配置

## 当前状态

2026-10-14 所有者执行修复后确认属地已正确显示。本轮归档经公开接口只读复查，
2 条评论为 RESOLVED，公开帖子/评论未发现原始 IP 字段。旧未知快照仍保留。
本轮没有新增写入测试或读取 sudo result.json，不能扩大为新的逐项服务端验收。
下文保留历史诊断及运行规则，不要重跑一次性启用脚本；全项目状态见 [V1 交接](V1_HANDOVER.md)。

## 2026-10-14 诊断与准备

正式上线后的公开帖子接口中，2 条旧本机测试记录为 NON_PUBLIC，2 条公网记录为
DATABASE_UNAVAILABLE。后者表示公网地址有效，但本地 MMDB 未加载；不等同城市误判。
基础 Compose 没有启用可选 GeoIP overlay。不得据此放宽代理信任或公开完整 IP。

经所有者批准准备最小修复：复用 `deploy/compose.geoip.yml`，同一应用镜像，
只读挂载免费 DB-IP City Lite，不新增数据库、外部查询 API 或付费服务。
本文件是执行说明，不是 VPS 部署已成功的证明；实际结果以 protected result.json 为准。

## 数据来源及本地验证

- [官方来源及许可](https://db-ip.com/db/download/ip-to-city-lite)，October 2026，CC BY 4.0。
- 网站页脚及隐私说明已有 DB-IP 署名链接，继续保留。
- 解压后约 121MiB（126998165 bytes），官方 SHA1：`df17bd24390108ed1d24dcb7718dc60f6b9abd4f`。
- 自行计算的部署 SHA256：`9e250f02722d1ad1780f88192f0e908af285478a33e76b88b349c9181ae9d0f5`。
- 文件由官方 HTTPS 下载；SHA1 用于核对官方文件，SHA256 用于后续上传及安装完整性验证。
- 真实库首轮本地测试有一次失败；独立查询诊断成功，随后完整 12 项属地测试复测通过。
  没有修改业务查询逻辑或放宽超时，首轮失败不能宣称根因已被证明。
- 另有 7 项执行脚本/Compose 检查、3 项 Nginx 检查通过；镜像非 root 只读文件权限检查通过。
- 不提交 MMDB、压缩文件、真实配置或备份到 Git。

## 已批准的生产操作范围

1. 先检查运行中的 Backend GeoIP 配置、固定镜像、Cloudflare/代理信任链、资源及现有服务。
2. 使用现有脚本生成生产备份，校验 SHA256 和归档；保留全部已有备份。
3. 安装不可原地覆盖的版本文件到 `/var/lib/heshan/geoip/dbip-city-lite-2026-10.mmdb`。
4. 新增 `/etc/heshan/compose.geoip.yml`；仅在生产 env 中追加非敏感的 GEOIP_DATABASE_FILE。
   原 env 以 root-only 方式备份，配置合并必须只增加属地文件路径和只读挂载。
5. 同一镜像仅重建生产 Backend。数据库和 Staging 不停止、不重建，数据卷不变。
6. 为重新解析 Backend 地址，对现有容器 API 代理执行 nginx -t 及平滑 reload；不重建代理，
   不修改或重启宿主机 Nginx。检查公网 HTTPS、容器健康、角色和迁移历史不变。
7. 配置失败时恢复原 env 和原 Backend 配置，平滑刷新代理；不恢复数据库、不删除数据文件。
   回退若未确认成功，停止并人工检查，不重复运行安装脚本。

门槛：启动前可用 RAM 至少 768MiB，Docker 所在盘至少 4GiB；过程可用 RAM 至少 384MiB。
Backend 保留既有 768MiB 内存限制、只读根文件系统、cap-drop 等安全配置。
MMDB 使用现有内存映射读取，文件大小不等于固定增加同等 Java 堆；仍需观察实际 RSS/文件缓存。

## 后续操作必须保留 overlay

部署脚本 PASS 后，使用新建的简短 Compose 包装脚本，不再仅传基础 Compose 更新 Backend：

```bash
sudo bash /etc/heshan/production-compose.sh ps
sudo bash /etc/heshan/production-compose.sh logs --tail 50 backend
```

包装脚本固定生产 project、env、当前 release 基础文件及 GeoIP overlay，不是新部署控制器。
重建/更新/停止仍需所有者批准。以后更新应用 release 时需同步审核该包装脚本中的 release 路径。
现有备份脚本仅 exec db，继续使用基础 Compose 不会改变 Backend 挂载。

## 部署后验收

- result.json 的配置通过不等于完整属地端到端通过。还需从 Mac 经 Cloudflare 发表明确标记的
  临时测试评论，确认状态为 RESOLVED，检查国家/地区/城市及前端显示。
- 如测试状态仍为 NON_PUBLIC、DATABASE_UNAVAILABLE 或 LOOKUP_FAILED，保留状态继续排查，
  不伪造属地，不把 Cloudflare 节点当访客位置，不打印或持久化完整客户端 IP。
- 这是公网出口的近似属地，不是 GPS；免费库覆盖和城市准确性有限，VPN/移动网络可能显示出口位置。
- 历史帖子/评论保存发布时快照，不自动回填；未保存原始 IP 时也不能准确重建旧属地。
- 后续每月按需人工更新到新的版本文件，重新校验并审批重建 Backend；不在内存映射期间原地覆盖文件。
- 不自动新增定时下载、异地同步或其他 MVP 之外的基础设施。
