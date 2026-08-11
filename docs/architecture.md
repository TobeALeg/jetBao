# JetBao Architecture

## module architecture

### module relationship

- `users`：JetBao 员工档案与业务权限；`email` 预登记企业邮箱，首次统一登录后绑定稳定的 `identity_id`。公司主体和 `admin/employee` 角色只由 JetBao 管理。
- `mentti.work`：统一身份认证中心，通过企业邮箱 OTP 验证员工身份；JetBao 使用短效、单次授权码兑换身份，不共享 MentiHub Cookie、JWT 或用户数据库。
- `company_entities`：系统允许的三个公司主体为 `上海山途远智信息科技有限公司`、`山途远智（上海）企业服务有限公司`、`上海山途远智企业咨询有限公司`；用户创建、用户更新和 bootstrap 管理员都必须使用其中之一。
- `SEED_DEMO_USERS` 默认关闭；真实部署通过 `BOOTSTRAP_ADMIN_*` 在空用户表时创建第一个管理员，不再按固定用户名自动提权。
- `expenses`：花费项目统一事实表，包含 `pending`、`matched` 和 `reviewed` 三种状态。
- `attachments`：上传文件，既可以是花费项目的交易记录，也可以被 OCR 识别为发票凭证；`pool_status = staged` 表示已上传已 OCR 但未入池，`pooled` 表示可进入发票池匹配。
- `expense_attachments`：花费项目自己的交易记录附件，不表示发票抵扣关系。
- `expense_invoice_allocations`：发票条目和花费项目之间的归属关系；同一发票条目只能归属一条花费。
- 员工接口只读写当前用户自己的 `expenses`。
- 管理员接口通过台账查询所有人的 `expenses`，但不切换身份。
- `services/export_package.py`：管理员导出服务，从 `expenses`、`expense_attachments`、`expense_invoice_allocations` 生成多 Sheet Excel 和附件 ZIP。
- Docker 部署由前端 Nginx 容器和后端 FastAPI 容器组成；本地 Compose 支持子路径，生产环境固定由 `jetbao.mentti.work` 根路径提供服务。
- PR 运行后端测试、前端构建和容器构建；合并 `main` 后只发布 commit SHA 镜像到 GHCR，再由 GitHub Actions 通过专用 SSH 用户更新服务器。
- 生产密钥位于服务器 `/opt/jetbao/.env`，SQLite 和附件位于 `/opt/jetbao/data`；镜像和代码发布不能覆盖持久化数据。
- 所有同机 Docker 发布竞争服务器共享锁 `/var/lock/mentti-docker-deploy.lock`；JetBao 发布在上传和拉取前执行 4 GiB/10% 双容量门禁，切换前创建 SQLite 一致性备份，失败时自动回滚应用镜像和部署清单，但不自动覆盖数据库。
- 共享主机通过引用感知的镜像保留器防止 containerd 再次占满根分区：运行中镜像、release current/previous、每仓库最近两个版本和 24 小时内镜像不可删除；删除只作用于其余未引用镜像 ID，不涉及容器、volume 或 `/opt` 业务数据。
- 数据库迁移在后端启动时自动执行，因此 schema 变更必须向后兼容上一个成功版本；需要破坏性迁移时必须单独设计停机迁移和人工恢复方案，不能依赖应用镜像回滚。

### data flow

1. 待处理报销：前端提交项目名称、金额、月份、类别，后端写入 `expenses.status = pending`。
2. 交易记录附件：用户在我的报销页或报销整理工作栏上传付款截图、订单截图等图片，前端先调用 `/api/attachments/batch`，再通过 `/api/expenses/{expense_id}/attachments` 写入 `expense_attachments`。
   员工新建报销工作区使用该接口上传多张佐证，并通过 `/api/attachments/invoices/batch` 上传和 OCR 多份发票文件；发票 OCR 结果按 `attachment_id + invoice_item_index` 展开为独立发票条目，再通过 `/api/expense-allocations/batch` 一次绑定到同一待处理花费。
3. 发票暂存：用户上传发票附件时，后端立即保存文件并 OCR，写入 `attachments.pool_status = staged`。
4. 工作栏匹配：用户为同一条花费选择一张或多张发票，后端写入 `expense_invoice_allocations`；每张 OCR 发票条目按票面全额原子绑定，不能拆分，也不能再匹配其他花费。同一上传文件识别出多张发票时，每个 `invoice_item_index` 都是独立发票条目。发票购买方精确命中任一允许公司主体即可提交；只部分命中时必须带 `buyer_confirmed` 人工确认标记。
5. 发票池：用户点击“加入发票池”后，`/api/attachments/pool` 把附件改成 `pool_status = pooled`；`/api/invoice-pool` 只返回 `pooled` 且未挂到 `expense_attachments` 的附件，并返回票面金额、已匹配金额和剩余可用金额。
6. 同轮按钮驱动：“记录该笔”创建花费并直接用当前 staged 发票调用 `/api/expense-allocations/batch` 写入绑定关系，不需要先进入发票池；票面金额等于报销金额时按真实票提交，不一致时标记为替票提交。
7. 发票匹配：匹配只更新票面合计，不自动提交；票面不足时继续待补，票面超出时必须填写替票说明。
8. 员工提交：票面合计覆盖报销金额后，员工主动提交，状态从 `pending` 变为 `matched`。
9. 管理审核：管理员可逐笔通过，或一键通过当前台账筛选范围内全部 `matched` 记录；审核在单事务中完成且可安全重试，`pending`/`reviewed` 不会被批量改写。通过后状态从 `matched` 变为 `reviewed`；员工撤回或管理员打回会回到 `pending` 并保留已匹配材料。
10. 删除：员工可以删除 `pending` 花费记录、未匹配发票附件和花费记录里的交易附件；删除部分匹配花费会级联移除 `expense_invoice_allocations`，让已入池发票回到发票池。
11. 管理台账：管理员按月份、公司、员工、类别、状态等条件查询 `expenses`，同时查看交易记录附件和发票匹配摘要。
12. 导出预览：后端统计 `matched` 和 `reviewed` 记录，同时返回筛选条件下的 `pending` 数量。
13. 单 Excel 导出：`/api/admin/export.xlsx` 保留轻量台账文件。
14. 明细包导出：`/api/admin/export-package.zip` 生成 `{期间}报销明细.xlsx`，附件按 `{公司}{期间}报销/{员工}{期间}报销/{报销类别}/{发票或佐证文件}` 归档；例如 `山途远智全部报销/夏莺萁全部报销/办公采购/快递发票20元.pdf`。外层压缩包按上海时区的当前月份命名为 `山途远智{当前月}月报销明细.zip`。交易记录附件来自 `expense_attachments`，发票文件来自 `expense_invoice_allocations`。
15. 导出总览：首页按公司主体和公司+人员两层汇总报销项数、发票张数、票面金额、本次报销金额和差异，供财务先核对主体归属。
16. 本地子路径部署：浏览器访问 `/bx/` 时，主机 Nginx 去掉 `/bx/` 前缀后转发静态页面到前端容器；浏览器访问 `/bx/api/*` 时转发到后端容器的 `/api/*`。
17. 生产域名部署：`jetbao.mentti.work` 由宿主机 Nginx 终止 HTTPS，并转发到只监听 `127.0.0.1:18080` 的前端容器；前端容器把 `/api/*` 转发给 Compose 内部的后端服务。
18. 自动发布：PR 只验证；`main` 的成功流水线发布不可变镜像。Actions 和服务器分别做容量门禁；服务器串行获取共享锁，有界重试拉取镜像，对 SQLite 做一致性备份，再以候选清单切换；本机和公网健康门禁都通过后才更新 `release.env`，失败则恢复上一个应用版本。成功后在同一锁内清理 JetBao 自身的过期镜像，主机级定时任务按同一保留规则覆盖其他仓库。
19. 统一登录：JetBao 生成随机 `state` 后跳转 MentiHub；MentiHub 验证企业邮箱并返回一次性授权码；JetBao 后端兑换 `sub/email`，只允许本地已预登记且启用的员工进入，并通过 host-only HttpOnly Cookie 建立 12 小时会话。
20. 登录迁移：`AUTH_MODE=hybrid` 时保留旧用户名密码入口供管理员补齐企业邮箱；全部员工绑定后切换 `AUTH_MODE=sso`，密码登录和修改密码接口随即关闭。
21. 返回主站：前端构建参数 `VITE_HOME_URL`（Compose/流水线对应 `FRONTEND_HOME_URL`）控制侧栏“回到 dashboard”地址；使用普通导航且不调用退出接口，因此 JetBao 与 MentiHub 各自的 host-only 会话均保留。

### status flow

- `pending`：待处理。可以没有发票、部分匹配或材料已齐但尚未提交；不能进入正式导出。
- `matched`：已提交待审核。员工已确认提交，可由管理员审核、打回，也可由员工撤回。
- `reviewed`：已审核完成。作为正式终态进入导出。

状态转换：

- `pending -> matched`：票面合计覆盖实际报销金额，员工主动提交。
- `matched -> reviewed`：管理员审核通过。
- `matched -> pending`：员工撤回或管理员打回，保留发票与佐证材料。
- `reviewed -> matched`：管理员撤销审核。
