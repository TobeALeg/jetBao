# JetBao Architecture

## module architecture

### module relationship

- `users`：真实员工身份、权限角色和登录密码哈希；员工可通过 `/api/me/password` 修改自己的密码。
- `company_entities`：系统允许的三个公司主体为 `上海山途远智信息科技有限公司`、`山途远智（上海）企业服务有限公司`、`上海山途远智企业咨询有限公司`；用户创建、用户更新和 bootstrap 管理员都必须使用其中之一。
- `SEED_DEMO_USERS` 默认关闭；真实部署通过 `BOOTSTRAP_ADMIN_*` 在空用户表时创建第一个管理员，不再按固定用户名自动提权。
- `expenses`：花费项目统一事实表，包含 `draft` 和 `submitted` 两种状态。
- `attachments`：上传文件，既可以是花费项目的交易记录，也可以被 OCR 识别为发票凭证；`pool_status = staged` 表示已上传已 OCR 但未入池，`pooled` 表示可进入发票池匹配。
- `expense_attachments`：花费项目自己的交易记录附件，不表示发票抵扣关系。
- `expense_invoice_allocations`：发票条目和花费项目之间的归属关系；同一发票条目只能归属一条花费。
- 员工接口只读写当前用户自己的 `expenses`。
- 管理员接口通过台账查询所有人的 `expenses`，但不切换身份。
- `services/export_package.py`：管理员导出服务，从 `expenses`、`expense_attachments`、`expense_invoice_allocations` 生成多 Sheet Excel 和附件 ZIP。
- Docker 部署由前端 Nginx 容器和后端 FastAPI 容器组成；前端构建支持 `VITE_BASE_PATH` 和 `VITE_API_BASE_URL`，用于挂在服务器子路径如 `/bx/`。

### data flow

1. 花费池：前端提交项目名称、金额、月份、类别，后端写入 `expenses.status = draft`；后端不提供无发票匹配的直接 `submitted` 创建入口。
2. 交易记录附件：用户在我的报销页或报销整理工作栏上传付款截图、订单截图等图片，前端先调用 `/api/attachments/batch`，再通过 `/api/expenses/{expense_id}/attachments` 写入 `expense_attachments`。
3. 发票暂存：用户上传发票附件时，后端立即保存文件并 OCR，写入 `attachments.pool_status = staged`。
4. 工作栏匹配：用户为同一条花费选择一张或多张发票，后端写入 `expense_invoice_allocations`；同一发票条目不能再匹配其他花费。发票购买方精确命中任一允许公司主体即可提交；只部分命中时必须带 `buyer_confirmed` 人工确认标记。
5. 发票池：用户点击“加入发票池”后，`/api/attachments/pool` 把附件改成 `pool_status = pooled`；`/api/invoice-pool` 只返回 `pooled` 且未挂到 `expense_attachments` 的附件，并返回票面金额、已匹配金额和剩余可用金额。
6. 同轮按钮驱动：“记录该笔”创建花费并直接用当前 staged 发票调用 `/api/expense-allocations/batch` 写入绑定关系，不需要先进入发票池；票面金额等于报销金额时按真实票提交，不一致时标记为替票提交。
7. 状态更新：花费项目至少关联一张发票后，后端可以把 `expenses.status` 更新为 `submitted`；发票票面合计和报销金额不一致时写入替票标记。员工 UI 不展示金额差额，差异只作为内部计算和导出台账字段。
8. 提交锁定：`submitted` 是正式报销数据，员工接口不能再追加发票匹配、交易记录附件或删除交易记录附件。
9. 删除：员工可以删除 `draft` 花费记录、未匹配发票附件和花费记录里的交易附件；删除部分匹配花费会级联移除 `expense_invoice_allocations`，让已入池发票回到发票池。
10. 管理台账：管理员按月份、公司、员工、类别、状态等条件查询 `expenses`，同时查看交易记录附件和发票匹配摘要。
11. 导出预览：后端只统计 `submitted` 记录，同时返回 matching 条件下的 `draft` 数量。
12. 单 Excel 导出：`/api/admin/export.xlsx` 保留轻量台账文件。
13. 明细包导出：`/api/admin/export-package.zip` 生成 `{月份}报销明细.xlsx` 和 `{月份}报销/{公司}{月份}报销/{员工}{月份}报销/{组ID-报销项-金额}/` 附件目录；交易记录附件来自 `expense_attachments`，发票文件来自 `expense_invoice_allocations`。
14. 导出总览：首页按公司主体和公司+人员两层汇总报销项数、发票张数、票面金额、本次报销金额和差异，供财务先核对主体归属。
15. 子路径部署：浏览器访问 `/bx/`，主机 Nginx 去掉 `/bx/` 前缀后转发静态页面到前端容器；浏览器访问 `/bx/api/*`，主机 Nginx 转发到后端容器的 `/api/*`。

### status flow

- `draft`：待匹配。可以只有项目名称、金额、月份和类别，也可以带交易记录附件；不能进入正式导出。
- `submitted`：已提交。已关联发票，可以进入正式导出；员工侧不可继续修改。发票金额和报销金额不一致时作为替票导出。

状态转换：

- `draft -> submitted`：至少关联一张发票；发票金额和报销金额不一致时标记替票。
- `submitted` 当前不回退为 `draft`；如需改错，后续再设计撤回或作废动作。
