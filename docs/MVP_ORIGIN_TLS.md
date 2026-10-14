# Origin CA：生产 HTTPS 准备

当前仅授权生产 TLS 私钥/CSR及证书准备；不启动 Nginx/应用，不创建数据库，不改 DNS/代理。

## 第一步：服务器生成私钥和公开 CSR

所有者通过交互式 sudo 运行经校验的 prepare-origin-csr.sh。
私钥只保存在 /etc/heshan/tls/privkey.pem，root:0600；父目录 root:0700。
公开 CSR 在 /etc/heshan/tls/origin.csr，包含 heshan.net 和 www.heshan.net。
脚本验证 CSR、Staging 健康及状态保持；不覆盖已有 TLS 材料，不自动清理失败现场。
如果命令失败或断线，先只读核对，不能重复生成或自行删除锁/密钥。
终端只显示公开 CSR，不显示私钥；CSR 可提交到 Cloudflare。

## 第二步：所有者在 Cloudflare 签发

进入 heshan.net -> SSL/TLS -> Origin Server -> Create Certificate。
选择 Use my private key and CSR，粘贴完整 BEGIN/END CERTIFICATE REQUEST 内容。
主机名仅 heshan.net、www.heshan.net，移除不需要的通配域名。
建议有效期1年，PEM格式；记下到期日期，Cloudflare不会自动发送Origin CA到期通知。
不要选择由Cloudflare生成私钥；不要截图或粘贴任何私钥/API Token。
下载/保存签发的公开Origin Certificate，之后核验并安装到 /etc/heshan/tls/fullchain.pem。
此步骤不需要改DNS，不启用橙云，不改变SSL模式，不影响旧站。

## 第三步：证书安装与配置核验（另提供实际命令）

只读核验新证书是否匹配服务器私钥、两个主机名、有效期和Cloudflare Origin CA签名。
核验通过才安装证书和未启用的Nginx配置；保留旧模板备份，不启动服务。
生产模板使用独立/etc/heshan/tls路径。nginx -t不代表HTTPS外网已通过。
本阶段结束后等待下一批准；数据库迁移、ghost初始化、生产服务启动均不在本阶段范围。

## 验收和回滚限制

Origin CA仅受Cloudflare信任。DNS-only、直接IP或暂停Cloudflare时，普通浏览器会报证书不可信。
上线前测试需要指定官方Origin CA根证书和正确主机名，不能用curl -k代替证书验证。
上线时再单独批准Cloudflare Full(strict)和代理/网站IP切换，确认边缘证书。
Origin CA模式下，不能把“直接切DNS-only到新VPS”当作无损HTTPS回滚。
要么回到保留的旧站，要么提前准备公开CA证书；不能通过Flexible或忽略验证降级补救。

本地6项测试通过：CSR验证、双主机名、公钥匹配、禁止服务启动/私钥输出、
Nginx模板语法和模拟HTTPS路由。测试证书均为一次性本地夹具，不是已签发生产证书。
依据：https://developers.cloudflare.com/ssl/origin-configuration/origin-ca/
