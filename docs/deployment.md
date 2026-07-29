# JetBao 生产部署

生产地址：`https://jetbao.mentti.work`

## 发布模型

- Pull Request：运行后端测试、前端类型检查与构建、前后端镜像构建。
- 合并到 `main`：CI 通过后，将以 commit SHA 标记的前后端镜像推送到 GHCR。
- CD：GitHub Actions 通过专用 SSH 用户把 Compose 清单和 release 元数据上传到服务器，再拉取该 SHA 的镜像并等待容器健康。
- 服务器只保存运行密钥和持久化数据，不保存仓库写权限，也不在生产机编译源码。

## 服务器目录

```text
/opt/jetbao/
├── .env                  # 生产密钥，仅服务器可读
├── app/
│   ├── compose.production.yml
│   └── release.env       # 当前镜像 SHA
└── data/                 # SQLite 与上传附件，必须备份
```

`.env` 至少包含：

```dotenv
SECRET_KEY=<long-random-value>
AUTH_MODE=legacy
SSO_AUTHORIZE_URL=https://mentti.work/sso/authorize
SSO_TOKEN_URL=https://mentti.work/api/sso/token
SSO_CLIENT_ID=jetbao
SSO_CLIENT_SECRET=<same-random-secret-as-mentihub>
SSO_REDIRECT_URI=https://jetbao.mentti.work/api/auth/sso/callback
SSO_EMAIL_DOMAIN=mentitrek.com
SSO_LOGOUT_URL=https://mentti.work/api/auth/logout
SSO_COOKIE_SECURE=true
TENCENT_SECRET_ID=
TENCENT_SECRET_KEY=
BOOTSTRAP_ADMIN_USERNAME=<first-admin>
BOOTSTRAP_ADMIN_PASSWORD=<strong-initial-password>
BOOTSTRAP_ADMIN_EMPLOYEE_NAME=<employee-name>
BOOTSTRAP_ADMIN_COMPANY_ENTITY=上海山途远智信息科技有限公司
```

bootstrap 管理员只在数据库为空时创建。

## 统一登录切换

统一登录必须分两次切换，避免旧员工尚未绑定邮箱时全员被锁在系统外：

1. 先部署 MentiHub 授权码接口，并在其生产 env 设置相同的 `JETBAO_SSO_CLIENT_SECRET` 和固定回调地址。
2. JetBao 设置 `AUTH_MODE=hybrid`，管理员继续用旧账号登录，在“管理”中为每位员工填写唯一企业邮箱。
3. 用至少一个管理员和一个普通员工完成真实邮箱 OTP 登录，确认姓名、公司主体和角色仍来自 JetBao。
4. 全员邮箱补齐后设置 `AUTH_MODE=sso` 并重新部署；此时用户名密码登录和修改密码接口关闭。

不要根据旧用户名自动拼接邮箱。`identity_id` 会在员工第一次成功统一登录时自动绑定，之后同一邮箱返回不同身份会被拒绝。

## GitHub Environment

在仓库的 `production` Environment 中配置：

- `DEPLOY_HOST`：`47.242.14.249`
- `DEPLOY_USER`：服务器专用发布用户
- `DEPLOY_SSH_KEY`：发布用户私钥
- `DEPLOY_KNOWN_HOSTS`：`ssh-keyscan -H 47.242.14.249` 的固定输出

若 GHCR 包不是公开包，需在服务器首次部署时执行一次 `docker login ghcr.io`，使用只具备 `read:packages` 权限的 token。

## 域名与 HTTPS

域名 A 记录必须指向 `47.242.14.249`。宿主机 Nginx 使用
`deploy/nginx/jetbao.mentti.work.conf`，确认 HTTP 可访问后再申请证书：

```bash
sudo certbot --nginx -d jetbao.mentti.work
```

## 回滚

把 `/opt/jetbao/app/release.env` 中的 `IMAGE_TAG` 改为上一个成功发布的 commit SHA，再执行：

```bash
cd /opt/jetbao
docker compose --env-file .env --env-file app/release.env -f app/compose.production.yml pull
docker compose --env-file .env --env-file app/release.env -f app/compose.production.yml up -d --wait
```

回滚应用镜像不会回滚 `/opt/jetbao/data`。涉及数据库结构变化时必须先备份该目录。
