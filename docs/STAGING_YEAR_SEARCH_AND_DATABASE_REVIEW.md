# 年份搜索修复与数据库安全复核

日期：2026-10-12。已部署版本仍为 `2e176e0de59784297e3253c97806db09989dc7fe`。
本轮修复尚未提交、推送或部署；没有重启、重建数据库或执行恢复/迁移。

## 年份搜索

后端 Post.yearRange 是可空字符串；创建帖子 API 与已有记录格式保持不变。
前端对四位单年和双端年份范围作数值匹配：区间端点均包含，查询范围和记录范围有交集即匹配。
支持 `-`、长横线、`~`、`/`、至、到、可选“年”后缀、空白及全角字符；反向端点自动归一。
旧的自由文本不能可靠解析成区间时继续文字包含搜索，不擅自推断“90年代”或模糊年代。
空查询继续显示所有记录，空年份不匹配非空查询。没有数据回填、Entity/表结构/API 变更。

| 实际验证 | 结果 |
| --- | --- |
| 新增年份回归测试 | PASS，6 项，包括端点、交集、无交集、反向、旧文本、异常输入 |
| 前端完整 npm test | PASS，18 项，0 失败/跳过 |
| 前端 npm run build | PASS，退出码 0 |
| 本地修复版读取现有 Staging 数据 | PASS，只使用 GET，不新建或修改记录 |
| 桌面 1440px：2007、2007-2010、2009-2010 | PASS，前两项命中原 2006-2008 记录，后一项无匹配 |
| 手机 390px：2007、2005-2006、2010-2011 | PASS，包含与端点交集命中，不相交无匹配，无横向溢出 |
| 控制台 | 无 error；开发版 React Router 有两条已有 v7 future-flag 提示，不是生产构建错误 |
| VPS 已部署修复版 | NOT TESTED / 未部署，需先批准应用更新 |

测试在独立本地源码副本完成，使用项目 lockfile/干净依赖，不覆盖现有工作区 node_modules。
本地代理保持 HTTPS 证书验证，信任已有公开 mkcert CA，不读取 CA 私钥，不关闭 TLS 校验。

## 数据库只读复核

deploy/staging/compose.yml 的 db 使用 `staging_data:/var/lib/postgresql/data`。
固定 Compose 项目 heshan-staging 下预期 Volume 名为 heshan-staging_staging_data；
数据存储在 Docker 持久卷，不在后端文件系统或数据库容器可写层。
PostgreSQL 无发布端口、仅加入内部 database 网络，内存上限 384MiB，restart=unless-stopped。
Backend/Web 768/64MiB；web 仅 loopback 18443，持续保留 ingress overlay。

本轮 SSH 成功。free -m：RAM 总量 1967MiB，使用 758MiB，可用 1209MiB；
Swap 总量 1023MiB、使用 1MiB。df -h /：剩余 41GiB。
sudo -n Docker inspect 被拒绝，提示需要密码；已停止该检查，没有绕过认证。
因此当前挂载、Volume 标签、容器健康和备份目录现场复核仍为 NOT TESTED，不能把配置审查当现场 PASS。

## 备份现状和保留策略

已知所有者验证通过的备份：
`/var/backups/heshan-staging/preupdate-20261012T175104Z-1RG89GlK.dump`，附同名 `.sha256`。
报告：`/var/tmp/heshan-staging-preupdate-nbxeiTML`。
备份目录 root:0700、文件 root:0600；脚本使用 pg_dump -Fc，不输出数据库密码。
原备份已经通过非空、checksum、pg_restore --list 及备份前后基线一致检查，但不等于完整恢复 PASS。

Staging 的 staging-preupdate-backup.sh 没有自动删除或保留天数清理逻辑，现有文件全部保留。
生产文档约定的本地 7 天 / 异地 30 天不表示 Staging 已配置该策略。
没有证据确认 Staging 每日任务或异地上传已启用；本轮不创建计划任务、联系外部存储或启动删除策略。
旧备份早于上一轮新增验收帖子和评论，下一步必须生成最新备份与新基线。
不能直接运行生产 backup-postgresql.sh 代替 Staging 备份，它依赖生产 Compose/offsite 服务。

## 下一次只读检查（所有者交互 sudo）

先在 Mac 执行 `ssh -i ~/.ssh/id_ed25519 heshan@165.232.156.104`，然后在 VPS 终端执行：

```bash
sudo bash <<'SH'
set -eu
export DOCKER_HOST=unix:///var/run/docker.sock
unset DOCKER_CONTEXT
test "$(docker inspect heshan-staging-db-1 --format '{{index .Config.Labels "com.docker.compose.project"}}')" = heshan-staging
docker inspect heshan-staging-db-1 --format '{{.Name}} Health={{.State.Health.Status}} OOM={{.State.OOMKilled}} Restarts={{.RestartCount}} Ports={{json .NetworkSettings.Ports}} {{range .Mounts}}{{if eq .Type "volume"}}Volume={{.Name}} Destination={{.Destination}} RW={{.RW}}{{end}}{{end}}'
docker volume inspect heshan-staging_staging_data --format 'Name={{.Name}} Driver={{.Driver}} Project={{index .Labels "com.docker.compose.project"}}'
test -d /var/backups/heshan-staging
stat -c '%a %u:%g %n' /var/backups/heshan-staging
find /var/backups/heshan-staging -maxdepth 1 -type f -name '*.dump*' -printf '%f size=%s mode=%m owner=%u\n'
systemctl list-timers --all --no-pager --no-legend | awk '/heshan/ && /backup/ {print}'
SH
```

仅读取元数据、文件名称/大小/权限和计时器名称；不输出环境变量、数据库内容、密钥或日志正文。
计时器列表没有匹配不能排除 cron/外部调度，仍需后续审核；不要贴出含凭据的 crontab、env 或配置。

## 持久化验证计划（尚未批准/执行）

1. 暂停 Staging 写入，核实当前挂载和健康状态，生成新备份和 checksum。
2. 记录用户、帖子、评论、角色、审计、Flyway 的计数/指纹及 Volume 名称；SQL 使用只读事务。
3. 经所有者明确批准，用当前 release 的 Compose 加现有 ingress overlay，仅 restart db。
   不 recreate、down、down -v、删卷、重启整个 VPS 或 Docker daemon。
4. 等待 DB 和 Backend 健康，复核 Volume、数据指纹及 HTTPS/API；预期测试站短暂不可用。
5. 若不健康或数据不一致，停止后续动作，保留日志；不得自动恢复覆盖现有库。

## 独立恢复条件与计划（尚未批准/执行）

当前资源快照满足小数据集恢复的初步门槛，但必须在执行前重新测量，建议 MemAvailable >=768MiB。
临时 PostgreSQL 16 容器采用独立随机名称、network none、无端口、不挂现有 Volume，
384MiB RAM / 0.5 CPU / 独立 tmpfs / 较低 shared_buffers。不能同时运行完整第二套应用。
恢复仅写入临时库，不写 heshan_staging，也不调用 founder 初始化。

现有 test-restore-postgresql.sh 有基本隔离，但缺少自身 checksum 门禁和自动数据指纹一致性断言。
应先补足资源、校验和及结果报告，再将备份计数/指纹、Flyway、约束、角色/审计记录与恢复库比较。
不将仅 pg_restore 返回 0 或表计数可打印视为完整 PASS；所有现有卷、备份和报告必须保留。
未经批准，本轮不创建该临时容器或执行恢复。

## 管理员后台未覆盖项目

上一轮本地隔离后端权限/创始人测试 21 项已通过；本轮没有修改权限逻辑或重跑后端测试。
真实 Staging 的 ADMIN/SUPER_ADMIN UI 仍需验收：Dashboard、帖子/评论审核恢复、用户保护边界、
分页/搜索、管理员任命撤销确认、错误提示、旧 JWT 撤权及审计展示。
应使用另行批准的独立管理员 UI 测试环境和临时夹具，不使用或修改真实 ghost，
不在现有 Staging 擅自授权 SUPER_ADMIN。

## 上线风险及下一步

修复可进入应用更新审批，但尚未部署；现有网站仍使用旧年份搜索。
现场 Volume/备份调度复核需要所有者终端输出；持久化、最新备份独立恢复、异地备份、
管理员真实 UI 和负载下资源稳定性尚未完成。
下一步先取得只读检查结果，再审批仅更新前端的发布包（保留 Backend/DB/TLS/env/overlay）。
不沿用固定旧 SHA 的 update-staging-bundle.py 直接部署新包；新发布需有自己的批准 SHA 与校验和。
