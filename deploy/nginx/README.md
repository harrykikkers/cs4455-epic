# nginx deployment — zebra.theburkenator.com

## How TLS works on this infrastructure

TLS is **not** configured on the VM. The hosting provider runs a gateway in
front of all student VMs that:

- Terminates TLS 1.2/1.3 with an A+ rated Let's Encrypt certificate
- Enforces HTTPS — HTTP requests are redirected to HTTPS at the gateway
- Auto-renews certificates via Let's Encrypt
- Forwards plain HTTP to **port 80** on your VM over the internal network

You do not need certbot, cert files, or a 443 server block. nginx listens on
port 80 only.

---

## Architecture

```
[client] ──TLS 1.2/1.3──▶ [provider gateway :443] ──HTTP──▶ [nginx :80] ──loopback──▶ [node :3000]
```

---

## 1. Install nginx

```bash
sudo apt update
sudo apt install -y nginx
```

---

## 2. Drop the config

From the repo root on the VM:

```bash
sudo cp deploy/nginx/zebra.theburkenator.com.conf \
        /etc/nginx/sites-available/zebra.theburkenator.com

sudo ln -sf /etc/nginx/sites-available/zebra.theburkenator.com \
            /etc/nginx/sites-enabled/zebra.theburkenator.com

sudo rm -f /etc/nginx/sites-enabled/default
```

> **Note:** `rate-limit.conf` is not needed — the `limit_req_zone` declaration
> is included directly in `zebra.theburkenator.com.conf`.

---

## 3. Place the verification page

```bash
sudo mkdir -p /var/www/verify
sudo cp verification/verify.html /var/www/verify/verify.html
```

---

## 4. Test and reload nginx

```bash
sudo nginx -t && sudo systemctl reload nginx
```

---

## 5. Make sure Node is running on loopback

The nginx config proxies `/api/` to `127.0.0.1:3000`. Confirm Node is bound
there:

```bash
sudo ss -tlnp | grep 3000   # should show node on 127.0.0.1:3000
```

---

## 6. Run Node under systemd

```bash
sudo tee /etc/systemd/system/secure-messenger.service >/dev/null <<'EOF'
[Unit]
Description=Secure Messenger Node backend
After=network.target mysql.service

[Service]
Type=simple
User=student
WorkingDirectory=/home/student/cs4455-epic/backend
EnvironmentFile=/home/student/cs4455-epic/backend/.env
ExecStart=/usr/bin/node src/app.js
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now secure-messenger
sudo systemctl status secure-messenger
```

> Adjust `User` and the two `/home/student/` paths if your VM username differs.

---

## 7. Firewall — close everything except 22 and 80

```bash
sudo ufw allow 2205/tcp
sudo ufw allow 'Nginx HTTP'
sudo ufw enable
sudo ufw status
```

Port 3000 (Node) and 3306 (MySQL) are unreachable from outside the VM.
The trust boundary is: gateway handles public TLS; nginx on :80 handles
routing; Node and MySQL are loopback-only.

---

## 8. Verify

From your laptop:

```bash
# Verification page loads
curl -I https://zebra.theburkenator.com/

# Backend health check
curl https://zebra.theburkenator.com/api/health
# → {"status":"ok","timestamp":"..."}
```

---

## Security headers

The VM sets the following headers (HSTS is set by the provider gateway):

| Header | Value |
|---|---|
| `X-Content-Type-Options` | `nosniff` |
| `X-Frame-Options` | `DENY` |
| `Referrer-Policy` | `no-referrer` |
| `Permissions-Policy` | `camera=(), microphone=(), geolocation=()` |
| `Content-Security-Policy` | scoped to `location /` (verification page only) |
| `server_tokens` | `off` |
