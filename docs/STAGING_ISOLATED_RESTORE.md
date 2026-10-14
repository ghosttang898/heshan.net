# Staging 独立 PostgreSQL 恢复演练

## 当前状态

本轮仅修改脚本、SQL、文档并运行本地模拟测试。没有 SSH、创建 PostgreSQL 容器、
执行 pg_restore、重启数据库、删除任何 Volume 或修改真实 ghost。
真实 PostgreSQL 16 恢复、SQL 目录指纹和新专用 Volume 启动兼容性仍为 NOT TESTED。
文档中的操作均是待批准方案，不是已执行结果。

## 文件与入口

- `docs/scripts/test-restore-postgresql.sh`：薄包装；旧的单路径调用会被拒绝。
- `docs/scripts/isolated-postgresql-restore.py`：标准库控制器，无新增依赖。
- `docs/scripts/restore-reference.sql`：BEGIN READ ONLY 的完整恢复参考快照。
- `docs/scripts/test_isolated_postgresql_restore.py`：假 Docker 控制流和门禁回归。

脚本仅适用于 Staging，本轮不修改备份机制或自动备份/保留策略。

## 必需的批准与输入

1. 批准低负载时暂停 Staging 测试写入、采集只读快照并生成一份新的独立备份。
   旧 20KB dump 的简单计数基线不能冒充完整参考；新增验收数据也不在旧备份内。
2. 核实目标所有者 ID 与用户名，未来可传 `ghost`，不能仅凭名称认定为创始人。
3. 批准上传审阅过的脚本，再由所有者在 Mac/VPS 终端交互 sudo。
4. 下一轮需重新批准创建随机命名的专用 Docker Volume 和临时 PostgreSQL 16 容器、
   恢复其中的空库，以及结束时停止该临时容器；本轮仅批准本地修改和模拟测试。
   不触碰已有容器、数据库或 Volume。不会创建第二套应用、赋予 SUPER_ADMIN 或自动清理资源。

本轮不执行以上任一服务器步骤。

## 同一备份时点的参考文件

仅接受 `/var/backups/heshan-staging/` 中 root:0600 的 dump，附同名 `.sha256`。
校验文件必须绑定绝对 dump 路径，格式为 `SHA256  /absolute/path.dump`。
reference.json 为 root:0600、非软链接文件，父目录应为 root:0700，不提交 Git、不贴到聊天。

新参考的准备流程（需要批准）：

1. 保持 Staging 空闲，先执行 restore-reference.sql，只读源库固定为 heshan_staging，保存 before 快照。
2. 使用已审阅的 staging-preupdate-backup.sh 创建新 dump，保留其 PASS 报告和 checksum。
3. 再执行同一 SQL 保存 after 快照。
4. 使用控制器的 snapshot_output 解析两份 SQL 输出；compare_snapshot 必须通过。
   该比较覆盖数据、角色/创始人、序列和结构，不将可能变化的物理文件大小当数据指纹。
5. validate_snapshot 必须通过；将 after 快照、明确确认的 ID/用户名和该 dump 的 SHA256 配对。
   有并发变化就保留全部文件并停止，不补写参考、不重建数据库以制造一致结果。

参考格式如下，尖括号是说明性占位符，不是可直接执行的文件：

```json
{
  "format_version": 1,
  "source_project": "heshan-staging",
  "source_database": "heshan_staging",
  "backup_sha256": "<new dump SHA256>",
  "snapshot": "<restore-reference.sql parsed JSON object, not a string>"
}
```

没有完整同一时点参考时，脚本拒绝恢复；不能用现在的源库快照配旧 dump。
用户名/角色会保存在受保护的参考文件中，密码及内容字段只参与指纹，不作为原文输出。
MD5 在这里仅用于完整行一致性对比，不用于认证或替代备份 SHA256。

## 安全门禁

- Linux、root 交互 sudo、显式 `--execute-isolated-restore`，不能通过旧调用隐式执行。
- Docker socket 强制固定为本机 Unix socket，忽略远程 context，不自动下载镜像。
- 已有三服务必须 healthy/OOM=false；记录 ID、重启次数、挂载和端口。
- 使用 root-only 本机锁防止两次演练并发；锁冲突时直接退出，不为获取资源停止其他任务。
- 镜像必须预先存在、Linux AMD64；创建时使用其不可变镜像 ID 与 --pull=never。
- 随机新名称 + docker create；名称冲突失败，不能替换已有容器。
- 所有恢复/SQL命令仅使用 create 返回的完整容器 ID，再核验专属标签与名称。
- 先读取现有 Volume 名称；新名字为 heshan-restore-data- 加随机后缀，已有同名立即拒绝。
- 显式创建 driver=local、无 Options 的新卷，用独立随机所有权 token 检查 create 的幂等竞争。
  标签不匹配即拒绝挂载，绝不删除疑似冲突卷。
- 目标固定 restore_test，network none，无发布端口、无 host bind、只读根文件系统。
  唯一数据 Volume 必须是本次新卷，挂载 /var/lib/postgresql/data 且 volume-nocopy。
  校验名称、标签、Mountpoint、容器实际 Source/Destination；既有卷和既有路径别名均禁止。
- 恢复前确认没有用户表、序列、视图；遇到非空目标立即拒绝，绝不 --clean 或 DROP。
- 冻结并复核备份副本，pg_restore --single-transaction --exit-on-error --no-owner --no-acl。
- 结束只停止核验过的临时容器 ID；不 rm、down、prune、删卷或删备份。
- 不自动重启现有服务；恢复失败、信号中断、停止失败或现有服务状态变化均不能 PASS。
- 未通过目标身份/挂载校验时，不启动或操作该不可信目标，保留记录并要求人工检查。

可信备份边界：dump 会执行 SQL，只接受所有者确认来源的备份与参考文件。
SHA256 保证文件一致性，不证明来源合法；不恢复来历不明的第三方 dump。

## 数据一致性和权限数据

比较 users、posts、comments、founder_identity、role_change_audit、flyway_schema_history 的
计数及完整行指纹，包含密码哈希、作者、年份、IP 属地、状态等字段但不打印原文。
比较列定义、长度、默认值、identity、约束、索引、序列结构/当前位置，以及 Flyway 版本和 checksum。
检查角色只能 USER/ADMIN/SUPER_ADMIN、身份唯一性、角色计数、外键关系和迁移成功状态。

确认用户 ID+用户名必须一致。已核实 ghost ID=1、角色 USER、founder_identity 为空，
本次脚本要求参考文件符合这个未初始化状态。若状态已变化，拒绝演练并等待重新确认。
恢复后保持原样，报告 PRESERVED_UNINITIALIZED。
不会通过用户名匹配赋权或生成 founder/audit 记录。
管理员授权审计行通过完整指纹比对；不在任何数据库执行提权验证写操作。

限制：--no-owner/--no-acl 不恢复数据库账号/GRANT；报告明确将数据库登录授权与 Web/API 权限标记
NOT TESTED。这些需要独立批准的应用测试，不等同于数据库中的角色数据一致。
目录结构比较不是再次运行 Hibernate validate；真实兼容性须在后续授权阶段验证。

## 资源预算

已知 VPS 可用约 1.2GiB、磁盘剩余约 41GiB，作为参考，不替代执行前检查。
门禁：MemAvailable >=768MiB、/var/tmp 剩余 >=4GiB，源数据库实际大小 <=64MiB，dump <=128MiB。
临时容器：384MiB RAM/禁用额外 Swap、0.25 CPU、64 PID；shared_buffers=32MB、work_mem=1MB。
数据库文件保存在新专用 Volume，停止容器后仍保留；数据库不再使用 tmpfs。
运行目录 8MiB、临时目录 16MiB 仍是 tmpfs，计入容器内存，不用于保留恢复现场。
普通 local Volume 没有可移植的硬磁盘配额；同时检查该卷所在文件系统和 /var/tmp 的剩余空间。
恢复体积/索引膨胀仍可能超限；失败只停止临时目标，不升级 VPS 或占用原 Volume。
控制器读取 dump 最多 128MiB，并保留一份磁盘副本；不同时运行 Maven/npm 或第二套完整服务。
恢复开始至结束持续轮询：操作之间以及长运行命令等待期间，每约 2 秒触发采样，实际间隔受 Docker
命令耗时影响。记录主机 RAM、磁盘、Swap、load average、容器 CPU/内存 stats 和健康状态。
RAM <768MiB、相关文件系统剩余 <4GiB、OOM 或 Staging 状态变化会中止当前 CLI 并停止临时目标。
不会停止、重启或修改现有 Staging 容器；采样不是浏览器延迟或瞬时峰值保证。
停止临时容器前另读其 cgroup 内存 peak；不可用时明确记录 UNAVAILABLE，不以采样最大值冒充真实峰值。
临时容器显式使用 private cgroup namespace，并检查实际配置，避免误读主机级 cgroup 峰值。
就绪检查仅接受最终服务的 TCP listener；只重试 pg_isready 的正常未就绪退出码 1/2，
资源门禁、Docker 错误、超时均直接终止，不被就绪重试吞掉。
容器内薄包装将正常未就绪映射为 11/12，避免将 Docker exec 自身退出码 1 误认为可重试。
物理恢复库大小可因文件布局改变，不要求等于源 pg_database_size；逻辑数据指纹必须相等。

## 待批准的执行模板（本轮禁止执行）

路径、ID、参考 SHA、脚本 SHA 必须在下一轮审批时替换为真实值。

```bash
sudo bash /approved/path/test-restore-postgresql.sh \
  --backup /var/backups/heshan-staging/APPROVED_NEW_BACKUP.dump \
  --reference /approved/private/path/reference.json \
  --expected-owner-id CONFIRMED_USER_ID \
  --expected-owner-username ghost \
  --expected-migration-version 1 \
  --execute-isolated-restore
```

这里只是模板，不授予执行许可；密码只在终端输入。

## 报告和保留

随机报告目录 `/var/tmp/heshan-restore-report-*`，root:0700，文件 root:0600。
包含 result.json、execution.log、resource-samples.jsonl、postgres-log-summary.json 和已核验的 dump 副本。
result.json 包含每步 PASS/FAIL、退出码/失败原因、恢复和一致性状态、表计数、创始人状态、
临时目标 ID、资源快照以及现有服务状态比较。失败也保留报告，并打印绝对路径。
禁止打印环境变量、密码、JWT、完整用户数据或备份内容。
原始 Docker/SQL 错误可能包含 COPY 数据，因此仅记录命令、退出码及正文省略标记。
PostgreSQL 日志只保存行数/错误计数摘要；临时密码、所有权 token 和原始行内容不进入报告。

成功必须同时满足 status=PASS、exit_code=0、restore_success=true、data_consistent=true、
containers_stopped=true、existing_services_unchanged=true。
临时容器被保留但停止，专用 Volume 中的数据库文件仍保留；原备份、参考和报告也保留。
成功或失败均不 rm 容器、删卷或删备份，新卷没有自动清理任务。
后续启动临时库调查现场或清理任何资源必须另行批准，不自动进入下一阶段。

## 尚未验证

真实 PostgreSQL 16 启动、SQL 快照执行、实际恢复、数据一致性、资源峰值与运行期 Staging 延迟，
数据库重启持久化、异地恢复、管理员真实 UI 均没有在本轮执行，不能标为 PASS。
