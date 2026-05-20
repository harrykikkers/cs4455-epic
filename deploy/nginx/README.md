# nginx + Let's Encrypt deployment

This sets up nginx as a TLS-terminating reverse proxy in front of the Node
backend, with an auto-renewing Let's Encrypt certificate.

Target: Ubuntu 22.04 / 24.04 on `zebra.theburkenator.com`.

If your subdomain is different, replace every `zebra.theburkenator.com` below
(and rename `zebra.theburkenator.com.conf`).

---

## 1. Install packages

```bash
sudo apt update
sudo apt install -y nginx certbot python3-certbot-nginx
```

## 2. Drop the configs

From the repo root on the VM:

```bash
# The per-site server block
sudo cp deploy/nginx/zebra.theburkenator.com.conf \
        /etc/nginx/sites-available/zebra.theburkenator.com

# Enable it
sudo ln -sf /etc/nginx/sites-available/zebra.theburkenator.com \
            /etc/nginx/sites-enabled/zebra.theburkenator.com

# Remove the default site so port 80/443 isn't claimed by the boilerplate
sudo rm -f /etc/nginx/sites-enabled/default

# The shared rate-limit zone (used by limit_req in the server block)
sudo cp deploy/nginx/rate-limit.conf /etc/nginx/conf.d/rate-limit.conf
```

## 3. Issue the certificate

The nginx config references cert files that don't exist yet, so we have to
start nginx with the HTTPS server block commented out temporarily — *or* use
certbot's `--nginx` plugin, which handles this for us.

Easier path:

```bash
# Comment out the entire `server { listen 443 ssl; ... }` block first, then:
sudo nginx -t
sudo systemctl reload nginx

# Now certbot can prove ownership over port 80
sudo certbot --nginx -d zebra.theburkenator.com \
    --non-interactive --agree-tos -m your-email@studentmail.ul.ie

# Uncomment the 443 block and reload
sudo nginx -t
sudo systemctl reload nginx
```

Certbot installs a systemd timer that renews automatically. Verify:

```bash
systemctl list-timers | grep certbot
sudo certbot renew --dry-run
```

## 4. Make sure Node is running on loopback

The nginx config proxies to `127.0.0.1:3000`. Confirm the Node app is bound
there (it is by default — `app.listen(config.port)` without a host binds to
all interfaces, but firewall rules below close port 3000 off externally).

```bash
sudo ss -tlnp | grep 3000   # should show node listening
```

## 5. Firewall — close everything except 22/80/443

```bash
sudo ufw allow OpenSSH
sudo ufw allow 'Nginx Full'   # 80 + 443
sudo ufw enable
sudo ufw status
```

Port 3000 (Node) and 3306 (MySQL) are now unreachable from outside the VM.
This is the architectural trust boundary — the only public surface is
nginx :80 (redirect) and nginx :443 (TLS).

## 6. Verify

From your laptop:

```bash
# Cert is valid, chain resolves, modern TLS only
curl -I https://zebra.theburkenator.com/api/health

# HTTP redirects to HTTPS
curl -I http://zebra.theburkenator.com/api/health   # expect 301

# Test cert grade — should be A or A+
# https://www.ssllabs.com/ssltest/analyze.html?d=zebra.theburkenator.com
```

## 7. Run Node under systemd (optional but recommended)

Keep the Node app running across reboots:

```bash
sudo tee /etc/systemd/system/secure-messenger.service >/dev/null <<'EOF'
[Unit]
Description=Secure Messenger Node backend
After=network.target mysql.service

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/cs4455-epic/backend
EnvironmentFile=/home/ubuntu/cs4455-epic/backend/.env
ExecStart=/usr/bin/node src/app.js
Restart=on-failure
RestartSec=5

# Hardening
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/home/ubuntu/cs4455-epic/backend/logs
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now secure-messenger
sudo systemctl status secure-messenger
```

---

## Talking points for the interview

| Question | Answer |
|---|---|
| "How is TLS handled?" | nginx terminates TLS 1.2/1.3 on :443 with a Let's Encrypt cert; proxies cleartext HTTP to Node on loopback :3000. |
| "How do you verify the cert?" | Clients use OS / browser trust stores. nginx serves a full chain (`fullchain.pem`) including the Let's Encrypt R3 intermediate. OCSP stapling is enabled. |
| "What's the trust boundary?" | The VM's network interface. Anything past nginx (Node, MySQL) is one trust domain on loopback. MySQL is `bind-address = 127.0.0.1`. |
| "How are certs renewed?" | certbot's systemd timer renews ≥30 days before expiry; nginx is reloaded post-hook. |
| "Why nginx and not Node-direct TLS?" | Operational: cert renewal without Node restarts, OCSP stapling, edge rate limiting, and HSTS at the edge. Node would have to manage all of that. |
| "What security headers do you set?" | HSTS (2y, preload-eligible), X-Content-Type-Options, X-Frame-Options DENY, Referrer-Policy no-referrer. `server_tokens off` hides the nginx version. |
