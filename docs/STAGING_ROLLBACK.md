# Staging 停止与回滚

本轮仅编写方案，没有在服务器上执行。仅操作 heshan-staging，绝不操作生产或旧网站。

## 部署前准备

保留当前及上一版的完整 Git SHA、镜像 ID/架构/revision label、镜像归档 checksum、
前端静态包及 release.json、独立 staging.env、证书和当前 Flyway history。
env mode0600且 root-owned；密钥放私有目录，不进入 Git/公开日志。
保留 heshan-staging_staging_data 与所有 dump/checksum。不能更改已有数据库 Volume 的
初始化用户名/密码当作“密码轮换”；它只在空 Volume 初始化时生效，轮换需单独 SQL 方案。

## 安全停止

先备份（参见部署文档）。使用已批准、root-owned release 的脚本：

```bash
sudo python3 "$RELEASE/docs/scripts/staging.py" stop --env-file "$ENV" --execute
sudo docker ps --filter label=com.docker.compose.project=heshan-staging
```

没有移除容器、网络、数据或备份；浏览器端断开 SSH Tunnel。stop 失败不能声称已停止。
不执行 down -v、system prune、volume prune、全局 docker stop 或覆盖旧版文件。
资源不足时只能退出、申请评估资源；不能为回滚而停其他服务。

## 同 schema 应用回滚

1. 冻结测试写入，备份当前 Staging DB；记录 IDs/行数/Flyway version/checksum。
2. 停止仅 Staging 项目，保留 Volume；保留失败版本的日志（脱敏）及包。
3. 选择已经留存的上一 SHA 后端镜像和同 SHA 前端包，检查兼容当前数据库 schema。
4. 使用新的 **rollback env 文件**，只改变 backend/frontend revision、SHA 镜像和静态路径；
   DB 密码、JWT、项目名/Volume 不变。不用 init-env 重新生成旧数据库凭据，不覆盖原 env。
5. 以旧版本的 Staging 控制脚本和该文件执行 preflight，再执行 deploy --execute。
6. 验证 API/页面/角色/数据/Flyway/HTTPS，再恢复测试写入。前端和后端必须同时指向匹配 SHA。

Compose 更新可能重建本项目旧的停止容器，必须先保存脱敏日志/状态并得到更新批准；
不是“永久保留每个旧容器”的承诺。原 Volume/备份/版本文件和其他项目不删除。

```bash
# OLD_RELEASE 和 ROLLBACK_ENV 均为已核对的绝对私有路径。
sudo python3 "$OLD_RELEASE/docs/scripts/staging.py" preflight --env-file "$ROLLBACK_ENV"
sudo python3 "$OLD_RELEASE/docs/scripts/staging.py" deploy --env-file "$ROLLBACK_ENV" --execute
```

脚本不会自动判断业务 schema 的向后兼容性。当前 V1 未改 schema 仍应比较迁移列表，
不能因为旧版镜像 healthy 就把跨 schema 回滚标为安全。

## schema 不兼容或数据恢复

暂停回滚，保持 Staging 停止；绝不对现有 Volume 执行 drop/clean/覆盖 restore。
请求所有者批准新恢复项目/新 Volume及数据时间点；在新空数据库中恢复独立备份，
比对数据/权限/审计/Flyway并启动相同备份时代的应用版本。新恢复资源仍无公网 PG 端口。
保留原数据；确认新的命名/端口/密钥隔离及 2GB 内存预算后，才单独批准受控切换。
当前 staging.py 固定 Volume 的限制故意阻止自动切到新恢复 Volume；恢复切换需新审核配置。
不要直接修改它绕过安全检查。明示备份之后测试写入的潜在损失，未经确认不切换。

## 恢复验收

检查旧/新资源都保留、其他容器未受影响、没有新公网入口，记录应用 SHA、数据库历史、
备份 checksum、结果与资源快照。以后清理旧 Staging 版本/Volume/备份必须再单独批准，
本方案不包含自动清理。无论 Staging 回滚是否成功，都不能自动切换 heshan.net 正式流量。
