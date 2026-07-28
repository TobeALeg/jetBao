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
TENCENT_SECRET_ID=
TENCENT_SECRET_KEY=
BOOTSTRAP_ADMIN_USERNAME=<first-admin>
BOOTSTRAP_ADMIN_PASSWORD=<strong-initial-password>
BOOTSTRAP_ADMIN_EMPLOYEE_NAME=<employee-name>
BOOTSTRAP_ADMIN_COMPANY_ENTITY=上海山途远智信息科技有限公司
```

bootstrap 管理员只在数据库为空时创建。首次登录后应立即修改密码。

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
