# JetBao 生产部署

生产地址：`https://jetbao.mentti.work`

## 发布模型

- Pull Request：运行后端测试、前端类型检查与构建、前后端镜像构建。
- 合并到 `main`：CI 通过后，将以 commit SHA 标记的前后端镜像推送到 GHCR。
- CD：GitHub Actions 通过专用 SSH 用户上传候选 Compose 清单和部署脚本；服务器获取同机共享发布锁，有界重试拉取该 SHA 镜像，备份 SQLite，再执行切换。
- 成功定义：Compose 健康检查、本机 API/首页、公网 API/首页全部通过；之后才一致性
  晋升 Compose、SSO 与 release 文件。任一替换失败会先恢复完整的上一契约。
- 失败处理：候选版本启动或健康门禁失败时自动恢复上一个应用镜像、Compose 清单和 SSO 配置。数据库备份只供人工恢复，不会被自动覆盖回线上。
- 服务器只保存运行密钥和持久化数据，不保存仓库写权限，也不在生产机编译源码。

## 服务器目录

```text
/opt/jetbao/
├── .env                  # 生产密钥，仅服务器可读
├── app/
│   ├── compose.production.yml
│   ├── compose.production.yml.previous
│   ├── sso.env
│   ├── sso.env.previous
│   ├── release.env       # 当前成功镜像 SHA
│   └── release.env.previous
├── backups/
│   └── sqlite/           # 部署前一致性备份，默认保留最近 20 份
├── scripts/
│   └── deploy-production.sh
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
- `SSO_CLIENT_SECRET`：与 MentiHub 仓库 `JETBAO_SSO_CLIENT_SECRET` 完全相同的强随机密钥
- Environment variable `AUTH_MODE`：首次设为 `hybrid`，真实统一登录验证后改为 `sso`

流水线会把 SSO 配置写入服务器 `/opt/jetbao/app/sso.env`，权限为 `600`，并在 Compose 启动时作为后置 env 文件覆盖旧配置；密钥不会写入仓库或 Actions 日志。

## 服务器一次性部署契约

同机所有仓库共用一个 Docker 发布锁。Ubuntu 的 `/var/lock` 指向重启后会清空的 `/run/lock`，因此由管理员通过 `systemd-tmpfiles` 一次性配置，部署脚本不会修改其权限：

```bash
echo 'f /run/lock/mentti-docker-deploy.lock 0664 root docker -' \
  | sudo tee /etc/tmpfiles.d/mentti-docker-deploy.conf
sudo systemd-tmpfiles --create /etc/tmpfiles.d/mentti-docker-deploy.conf
```

`jetbao-deploy` 必须属于 `docker` 组，并且能以读写方式打开这个锁文件。锁缺失时
部署直接失败，不允许脚本自行创建。`tmpfiles` 契约保证服务器重启后锁文件仍以
`root:docker 0664` 重建。每次部署通过 `flock` 最多等待 30 分钟，避免和
MentiProbe、MentiHub、GEO 等服务同时操作 containerd/overlayfs。不要在每次部署里
`chown`、`chmod`，也不要自动执行 Docker image prune。

部署前使用 Python `sqlite3.Connection.backup()` 为 `/opt/jetbao/data/jetbao.sqlite3` 创建在线一致性备份，并执行 `PRAGMA integrity_check`。备份写入 `/opt/jetbao/backups/sqlite`，默认保留最近 20 份，可通过 `BACKUP_RETENTION_COUNT` 调整。

JetBao 会在进程启动时自动迁移 SQLite。自动回滚只恢复应用镜像和部署配置，不会自动恢复数据库，以免覆盖切换期间的新业务写入。所有 schema 变更必须至少向后兼容上一个成功版本；如需恢复数据库，应先停止写入并由管理员从已验证备份人工执行。

若 GHCR 包不是公开包，需在服务器首次部署时执行一次 `docker login ghcr.io`，使用只具备 `read:packages` 权限的 token。

## 域名与 HTTPS

域名 A 记录必须指向 `47.242.14.249`。宿主机 Nginx 使用
`deploy/nginx/jetbao.mentti.work.conf`，确认 HTTP 可访问后再申请证书：

```bash
sudo certbot --nginx -d jetbao.mentti.work
```

## 回滚

正常失败会由脚本自动恢复 `/opt/jetbao/app/release.env` 指向的上一个成功应用版本。人工回滚可使用 `/opt/jetbao/app/release.env.previous`、`compose.production.yml.previous` 和 `sso.env.previous`，确认后再替换当前文件并执行：

```bash
cd /opt/jetbao
docker compose --env-file .env --env-file app/sso.env --env-file app/release.env -f app/compose.production.yml pull
docker compose --env-file .env --env-file app/sso.env --env-file app/release.env -f app/compose.production.yml up -d --wait --wait-timeout 180
```

回滚应用镜像不会回滚 `/opt/jetbao/data`。禁止在自动失败处理里直接覆盖线上数据库。
