# Staging 上线前功能验收（2026-10-12）

部署版本：`2e176e0de59784297e3253c97806db09989dc7fe`。
范围：现有 SSH Tunnel / `https://localhost:18443`，本地隔离权限测试及备份代码审查。
本轮没有修改 VPS 配置、重启或重建容器、执行恢复、删除 Volume、修改 DNS 或真实 ghost。
本报告不是正式上线许可。没有自动提交或推送 GitHub。

## 实际执行结果

| 项目 | 结果 | 证据和范围 |
| --- | --- | --- |
| 注册页 SiteHeader | PASS | 实际注册页有 Logo、首页/聊天/寻人导航 |
| 普通用户注册、登录、退出、重新登录 | PASS | 浏览器临时账号 stage-check-mv5ktt63；退出后发布入口消失，重新登录成功 |
| 聊天发帖、详情、回复 | PASS | 浏览器创建帖子 6，详情页回复刷新后仍显示 |
| 寻人发布、列表内回复 | PASS | 浏览器创建虚构寻人帖子 9；列表回复在详情页可读取 |
| 昵称和地点组合筛选 | PASS | 虚构昵称和测试地点可筛选出帖子 9 |
| 年份文本筛选 | PASS | 输入 2006 可找到 yearRange=2006-2008 的帖子 |
| 年份区间内年份检索 | FAIL | 输入 2007 无匹配，当前实现是 includes 文本匹配，不是区间比较 |
| Loading 状态 | PASS | 实际观察到帖子、详情、评论、寻人列表及列表回复加载提示，没有提前用空内容提示替代 |
| React 路由及刷新 | PASS | 聊天详情刷新后正确恢复；寻人详情直接加载正常 |
| 手机与桌面布局 | PASS | 320px 注册页、390px 寻人列表/详情、1440px 寻人列表/详情；检查范围内 documentWidth=viewportWidth，截图无横向溢出，Logo 已加载 |
| USER 后台页面 | PASS | 已登录临时 USER 访问 /admin 显示 403 无访问权限 |
| USER 后台 API | PASS | 五类 /api/admin/dashboard、posts、comments、users、administrators 全部返回 403 |
| 注册参数提权 | PASS | 独立 API 临时账号提交 role=SUPER_ADMIN，响应仍为 USER |
| 认证及内容 API | PASS | staging-functional-acceptance.py 实际运行 14 项全部通过；错误密码/未登录被拒绝，两类帖子、评论、作者与列表读取正常 |
| IP 属地与公开数据隐私 | PASS | 隧道/内部出口显示未知，API 状态 NON_PUBLIC；公开帖子/评论接口不含原始 IP 和密码字段。未验证真实公网出口的城市准确度 |
| Staging Analytics | PASS | 实际检查寻人列表与详情 DOM，没有 Cloudflare beacon 脚本 |
| 浏览器控制台 | PASS | 本次绑定标签页捕获的 error/warn 日志为空；不是历史全量日志审计 |
| ADMIN / SUPER_ADMIN 后端边界 | PASS（本地隔离） | Maven AdminIntegrationTest 8、AdministratorIntegrationTest 10、FounderBootstrapTest 3，共 21 项，零失败/错误/跳过 |
| 管理员后台真实浏览器操作 | NOT TESTED | 不使用真实 ghost，不在 Staging 授权管理员；需另行批准独立管理员 UI 测试夹具 |
| 现有备份有效性 | PASS（此前所有者执行） | 非空 pg_dump、SHA256、archive listing 和前后数据基线一致；不是完整恢复验证 |
| 本轮数据库重启持久化 | NOT TESTED | 本轮没有重启 PostgreSQL |
| 本轮独立数据库恢复 | NOT TESTED | 本轮没有启动或恢复临时 PostgreSQL |
| 异地备份及异地恢复 | NOT TESTED | 没有连接外部存储，也没有验证定时任务 |
| 本轮服务器容器/资源复查 | NOT TESTED | 本轮不通过 sudo 操作 VPS；最近所有者报告三服务健康、无 OOM/重启、可用 RAM 1217MiB、Swap 使用 1MiB、磁盘剩余 41GiB |

API 临时账号：`stage-api-683a9cf9355f`；聊天帖子/评论 7/7，寻人帖子/评论 8/8。
所有新增数据仅为 Staging 虚构验收记录，本轮不删除。临时密码和 JWT 没有写入报告。
浏览器刷新后可读取数据，不等于数据库容器重启后的持久化已经验证。

## 问题及修复状态

1. 年份区间检索存在用户体验缺口。建议单独修复单年、区间及自由文本的兼容解析并增加回归测试，
   在本地验证后使用同样的带 overlay 应用更新流程；本轮没有改业务代码或部署此修复。
2. 注册页网站头和列表/评论 Loading 是此前版本已修复的内容，本轮实际验收通过。
3. 详情页桌面标题偏大但没有溢出；这是视觉优化建议，不是数据或权限问题。

## 备份恢复方案审查

- Staging 继续使用独立 preupdate 备份脚本，不能直接套用生产 backup-postgresql.sh：后者使用生产
  Compose/可选 offsite 服务，不能因此遗漏 Staging 的项目名称和 ingress overlay。
- 现有 test-restore-postgresql.sh 使用新 PostgreSQL 16 容器、network none、无端口、384MiB 内存、
  tmpfs 数据，不挂载现有 Volume；cleanup 仅删除该脚本新建容器，不能扩展到其他资源。
- 该恢复脚本本身没有核验 dump checksum，也没有自动断言恢复前后指纹一致；执行者必须补充门禁。
  只看到表数量、Flyway 输出或 pg_restore 退出 0，不能宣布完整恢复一致性 PASS。
- 生产方案文档约定本地 7 天、异地 30 天及私有 rclone 配置，但本轮没有验证定时调度、异地目的地、
  权限/加密、保留策略或恢复。不得运行生产备份脚本来尝试验证 Staging，也不得擅自开启删除策略。
- 本轮新建测试记录发生在旧备份之后。后续重启/恢复验收必须先生成最新备份和新的只读基线，
  不能将旧 dump 与包含新增测试记录的当前库直接比较并要求一致。

## 待批准的安全执行方式

### 数据持久化

先暂停 Staging 测试写入，生成新备份、checksum 和用户/帖子/评论/角色/审计/Flyway 指纹。
核实当前镜像 SHA、数据库 Volume 和两份 Compose 配置。
仅使用新 release 的 compose.yml 加 /etc/heshan-staging/web-ingress.override.yml，
重启本项目 db 服务，不重建数据库或 Docker daemon，不使用 down、down -v 或 prune。
等待 PostgreSQL/Backend 恢复健康，确认数据卷、记录和指纹不变，再运行 HTTPS/API 检查。
预期 Staging 短暂不可用；需网站所有者明确批准并在终端交互 sudo 后才能提供和执行命令。

### 独立恢复演练

先校验最新 dump 和私有报告，再检查当前 MemAvailable（建议至少 768MiB）及磁盘。
创建独立随机命名的临时 PostgreSQL 16，无公网端口、network none、独立 tmpfs，
限制 384MiB RAM、0.5 CPU，并为小数据库配置较低 shared_buffers。
只向该临时库恢复，自动比较备份基线的计数、指纹、Flyway、约束及角色/审计数据。
敏感日志 root-only，保留备份和结果；现有库和所有现有 Volume 均不变。
创建容器及数据库恢复均需另行批准。不得恢复到 heshan_staging 或用失败为由覆盖现有数据。

## 结论

公开站核心交互及 USER 访问限制通过；年份区间检索待修复。
管理员真实 UI、最新数据备份恢复/重启持久化和异地备份仍未完成，不宣称整体上线验收 PASS。
