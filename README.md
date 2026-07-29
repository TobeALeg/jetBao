# 内部报销整理系统 MVP

电脑端优先的内部报销系统。员工可以提交报销和上传发票附件，系统用文件 hash 提醒疑似重复；管理员可以按月份、公司主体、员工等条件筛选台账，并导出 Excel。

## 本地开发

### 后端

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

后端默认地址：`http://127.0.0.1:8000`

### 前端

```bash
cd frontend
npm install
npm run dev
```

前端默认地址：`http://127.0.0.1:5173`

## 首次账号

生产或给同事使用时，不会默认创建演示账号。首次部署建议在 `.env` 中设置一次 bootstrap 管理员：

```bash
BOOTSTRAP_ADMIN_USERNAME=your-admin
BOOTSTRAP_ADMIN_PASSWORD=change-this-password
BOOTSTRAP_ADMIN_EMPLOYEE_NAME=管理员姓名
BOOTSTRAP_ADMIN_COMPANY_ENTITY=上海山途远智信息科技有限公司
```

bootstrap 管理员只会在用户表为空时创建；已有用户后再次启动不会覆盖账号。

生产环境完成初始化后使用 `mentti.work` 企业邮箱统一登录。JetBao 只保存员工档案、公司主体和报销角色，不保存或校验企业邮箱密码。旧账号迁移请先使用 `AUTH_MODE=hybrid` 补齐员工邮箱，验证完成后切换为 `AUTH_MODE=sso`。

当前公司主体固定为三个，只能选择：

- `上海山途远智信息科技有限公司`
- `山途远智（上海）企业服务有限公司`
- `上海山途远智企业咨询有限公司`

本地演示如需固定账号，可临时设置 `SEED_DEMO_USERS=true`。此时首次启动后端会创建三个演示账号：

- 管理员：`admin` / `admin123`
- 管理员：`Dandi` / `dandi123`
- 管理员：`Ouyang` / `ouyang123`

演示账号只用于本地演示，不要用于真实部署。

## Docker 启动

```bash
docker compose up --build
```

前端访问：`http://127.0.0.1:8080`

SQLite 数据库和上传文件会挂载到 `backend/data/`，不会提交到 Git。

## 子路径部署

如果部署在服务器子路径，例如 `http://服务器/bx/`，构建前端时需要同步设置页面资源前缀和 API 前缀：

```bash
FRONTEND_BASE_PATH=/bx/ \
FRONTEND_API_BASE_URL=/bx/api \
FRONTEND_PORT=127.0.0.1:18080 \
BACKEND_PORT=127.0.0.1:18000 \
PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple \
docker compose up -d --build
```

主机 Nginx 负责把 `/bx/` 转发到前端容器，把 `/bx/api/` 转发到后端容器。

## 环境变量

可以复制 `.env.example` 为 `.env` 后按需修改。

- `SECRET_KEY`：后端 token 签名密钥，生产环境必须改。
- `AUTH_MODE`：`legacy`、`hybrid` 或 `sso`；生产迁移完成后使用 `sso`。
- `SSO_AUTHORIZE_URL` / `SSO_TOKEN_URL`：MentiHub 授权与后端兑换地址。
- `SSO_CLIENT_ID` / `SSO_CLIENT_SECRET` / `SSO_REDIRECT_URI`：JetBao 在 MentiHub 登记的客户端配置；两端客户端密钥必须一致且不能提交到 Git。
- `SSO_EMAIL_DOMAIN`：允许预登记的企业邮箱域名，当前为 `mentitrek.com`。
- `SSO_LOGOUT_URL`：统一退出入口。
- `SSO_COOKIE_SECURE`：生产 HTTPS 必须为 `true`。
- `DATA_DIR`：SQLite 数据和附件目录。
- `UPLOAD_DIR`：附件上传目录。
- `TENCENT_SECRET_ID` / `TENCENT_SECRET_KEY`：腾讯云访问密钥。未配置时，系统允许手动填写。
- `TENCENT_OCR_REGION`：腾讯云 OCR 地域，默认 `ap-guangzhou`。
- `TENCENT_OCR_ACTION`：OCR 接口，默认 `RecognizeGeneralInvoice`，用于通用票据识别。
- `TENCENT_OCR_ENABLE_MULTIPLE_PAGE`：是否开启 PDF 多页识别，默认 `true`，腾讯云最多返回前 30 页。
- `TENCENT_OCR_PDF_PAGE`：未开启多页识别时的 PDF 页码，默认第 1 页。
- `SEED_DEMO_USERS`：是否自动创建演示账号，默认 `false`。
- `BOOTSTRAP_ADMIN_USERNAME` / `BOOTSTRAP_ADMIN_PASSWORD`：用户表为空时创建第一个管理员。
- `BOOTSTRAP_ADMIN_EMPLOYEE_NAME` / `BOOTSTRAP_ADMIN_COMPANY_ENTITY`：第一个管理员的员工姓名和公司主体；公司主体必须是系统允许的三个主体之一。
