# JetBao Architecture

## module architecture

### module relationship

- `users`：真实员工身份和权限角色。
- `expenses`：花费项目统一事实表，包含 `draft` 和 `submitted` 两种状态。
- `attachments`：上传文件，既可以是花费项目的交易记录，也可以被 OCR 识别为发票凭证。
- `expense_attachments`：花费项目自己的交易记录附件，不表示发票抵扣关系。
- `expense_invoice_allocations`：发票凭证和花费项目之间的分摊关系。
- 员工接口只读写当前用户自己的 `expenses`。
- 管理员接口通过台账查询所有人的 `expenses`，但不切换身份。

### data flow

1. 花费池：前端提交项目名称、金额、月份、类别，后端写入 `expenses.status = draft`。
2. 交易记录附件：用户上传付款截图、订单截图等图片，后端通过 `/api/expenses/{expense_id}/attachments` 写入 `expense_attachments`。
3. 发票池：用户上传发票附件，OCR 拆出票据条目；`/api/invoice-pool` 只返回未挂到 `expense_attachments` 的附件，并返回票面金额、已分摊金额和剩余可用金额。
4. 匹配区：用户把一个发票条目的一部分金额分摊给一个花费项目，后端写入 `expense_invoice_allocations`。
5. 状态更新：花费项目已分摊金额达到实际金额后，后端把 `expenses.status` 更新为 `submitted`；否则保持 `draft`。
6. 管理台账：管理员按月份、公司、员工、类别、状态等条件查询 `expenses`，同时查看交易记录附件和发票分摊摘要。
7. 导出：后端只导出 `submitted` 记录，同时在预览中返回 matching 条件下的 `draft` 数量。

### status flow

- `draft`：待匹配。可以只有项目名称、金额、月份和类别，也可以已经部分匹配发票；不能进入正式导出。
- `submitted`：已提交。已分摊发票金额覆盖完整花费金额，可以进入正式导出。

状态转换：

- `draft -> submitted`：发票分摊金额覆盖花费项目实际金额。
- `submitted` 当前不回退为 `draft`；如需改错，后续再设计撤回或作废动作。
