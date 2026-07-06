# JetBao Architecture

## module architecture

### module relationship

- `users`：真实员工身份和权限角色。
- `expenses`：花费项目统一事实表，包含 `draft` 和 `submitted` 两种状态。
- `attachments`：上传文件，既可以是花费项目的交易记录，也可以被 OCR 识别为发票凭证。
- `expense_attachments`：花费项目自己的交易记录附件，不表示发票抵扣关系。
- `expense_invoice_allocations`：发票条目和花费项目之间的归属关系；同一发票条目只能归属一条花费。
- 员工接口只读写当前用户自己的 `expenses`。
- 管理员接口通过台账查询所有人的 `expenses`，但不切换身份。
- `services/export_package.py`：管理员导出服务，从 `expenses`、`expense_attachments`、`expense_invoice_allocations` 生成多 Sheet Excel 和附件 ZIP。

### data flow

1. 花费池：前端提交项目名称、金额、月份、类别，后端写入 `expenses.status = draft`。
2. 交易记录附件：用户上传付款截图、订单截图等图片，后端通过 `/api/expenses/{expense_id}/attachments` 写入 `expense_attachments`。
3. 发票池：用户上传发票附件，OCR 拆出票据条目；`/api/invoice-pool` 只返回未挂到 `expense_attachments` 的附件，并返回票面金额、已匹配金额和剩余可用金额。
4. 匹配区：用户为同一条花费选择一张或多张发票，后端写入 `expense_invoice_allocations`；同一发票条目不能再匹配其他花费。
5. 状态更新：花费项目已匹配票面合计达到实际金额后，后端把 `expenses.status` 更新为 `submitted`；否则保持 `draft`。如果票面合计超过实际金额，必须填写说明并标记为替票。
6. 删除：员工可以删除 `draft` 花费记录、未匹配发票附件和花费记录里的交易附件；删除部分匹配花费会级联移除 `expense_invoice_allocations`，让发票回到发票池。
7. 管理台账：管理员按月份、公司、员工、类别、状态等条件查询 `expenses`，同时查看交易记录附件和发票匹配摘要。
8. 导出预览：后端只统计 `submitted` 记录，同时返回 matching 条件下的 `draft` 数量。
9. 单 Excel 导出：`/api/admin/export.xlsx` 保留轻量台账文件。
10. 明细包导出：`/api/admin/export-package.zip` 生成 `{月份}报销明细.xlsx` 和 `{月份}报销/{公司}{月份}报销/{员工}{月份}报销/{组ID-报销项-金额}/` 附件目录；交易记录附件来自 `expense_attachments`，发票文件来自 `expense_invoice_allocations`。
11. 导出总览：首页按公司主体和公司+人员两层汇总报销项数、发票张数、票面金额、本次报销金额和差异，供财务先核对主体归属。

### status flow

- `draft`：待匹配。可以只有项目名称、金额、月份和类别，也可以已经部分匹配发票；不能进入正式导出。
- `submitted`：已提交。已匹配发票金额达到完整花费金额，可以进入正式导出。

状态转换：

- `draft -> submitted`：发票匹配金额达到花费项目实际金额；超过时必须有说明并标记替票。
- `submitted` 当前不回退为 `draft`；如需改错，后续再设计撤回或作废动作。
