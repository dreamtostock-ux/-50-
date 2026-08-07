# VPS 部署文件

本目录保存当前生产部署使用的服务配置示例：

- `futu-opend.service`：命令行 Futu OpenD，仅监听 `127.0.0.1:11111`。
- `etfscore-web.service`：网页服务，仅监听 `127.0.0.1:3000`。
- `etfscore-sync.service`：Futu 行情与评分同步，默认每 30 秒执行一次。
- `Caddyfile.example`：独立域名、HTTPS、ACME HTTP 验证和反向代理示例。
- `acme-renew.service` / `acme-renew.timer`：公网证书每日续期检查。

复制前请按实际安装路径、域名和用户调整配置。生产环境的 `/etc/515450-scoring.env`、Futu 登录配置、证书私钥和数据库不得提交到仓库。
