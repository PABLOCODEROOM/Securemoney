# SecureMoney Deployment Guide

## Local Development

### Option 1: Manual Setup (XAMPP / MySQL)

```bash
# 1. Start MySQL in XAMPP
# macOS:  open /Applications/XAMPP/xamppfiles/htdocs
# Linux:  sudo service mysql start
# Windows: Start MySQL from XAMPP Control Panel

# 2. Create .env from template
cp .env.example .env

# 3. Generate secrets
python -c "import secrets; print('SECRET_KEY=' + secrets.token_hex(32))" >> .env
python -c "import secrets; print('MASTER_KEY_HEX=' + secrets.token_hex(32))" >> .env

# 4. Create Python venv
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 5. Install dependencies
pip install -r requirements.txt

# 6. Initialize database
mysql -u root -p < scripts/setup_db.sql

# 7. Seed demo data
python scripts/seed_demo.py

# 8. Run application
python run.py
```

Visit: https://localhost:5000

---

### Option 2: Docker Compose (Recommended for Development)

```bash
# 1. Create .env from template
cp .env.example .env

# 2. Generate secrets in .env
# (docker-compose.yml provides defaults; override in .env for production)

# 3. Start containers
docker-compose up --build

# 4. Initialize database and seed
docker-compose exec web python scripts/seed_demo.py
```

Visit: http://localhost:5000

**Demo credentials:**
- User: Esau.magaro@securemoney.tz / Esau.magaro
- Admin: admin / Admin@SecureMoney2026!

---

## Production Deployment

### Requirements

- Python 3.10+
- MySQL 8.0+
- gunicorn or uWSGI
- Reverse proxy: nginx or Apache
- SSL/TLS certificate (Let's Encrypt recommended)
- Environment: Linux (Ubuntu 20.04+, CentOS 8+, etc.)

### Step 1: Clone and Setup

```bash
# Clone repository
git clone https://github.com/yourname/SecureMoney.git
cd SecureMoney

# Create Python venv
python3 -m venv venv
source venv/bin/activate

# Install production dependencies
pip install -r requirements.txt gunicorn

# Create production .env (NEVER commit this)
cp .env.example .env.production
```

### Step 2: Configure Environment

Edit `.env.production`:

```ini
FLASK_ENV=production
SECRET_KEY=<generate: python -c "import secrets; print(secrets.token_hex(32))">
MASTER_KEY_HEX=<generate: python -c "import secrets; print(secrets.token_hex(32))">

# Database
DB_HOST=127.0.0.1
DB_PORT=3306
DB_NAME=securemoney_prod
DB_USER=securemoney_app
DB_PASSWORD=<generate strong password>

# Email (for real OTP sending)
EMAIL_SIMULATE=false
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USER=noreply@yourdomain.com
EMAIL_PASSWORD=<app-specific password>

# Security
SESSION_COOKIE_SECURE=true
PBKDF2_ITERATIONS=600000
```

### Step 3: Database Setup

```bash
# Create MySQL database and user
mysql -u root -p <<EOF
CREATE DATABASE securemoney_prod
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;

CREATE USER 'securemoney_app'@'localhost' IDENTIFIED BY '<password>';

# Grant privileges (principle of least privilege)
GRANT SELECT, INSERT, UPDATE ON securemoney_prod.* TO 'securemoney_app'@'localhost';
GRANT INSERT ON securemoney_prod.audit_log TO 'securemoney_app'@'localhost';

# Revoke dangerous privileges
REVOKE UPDATE, DELETE ON securemoney_prod.audit_log FROM 'securemoney_app'@'localhost';
REVOKE DROP ON securemoney_prod.* FROM 'securemoney_app'@'localhost';

FLUSH PRIVILEGES;
EOF

# Initialize schema
mysql -u securemoney_app -p securemoney_prod < scripts/setup_db.sql

# Create bootstrap admin
python scripts/seed_demo.py --admin-only --password="<change-this-immediately>"
```

### Step 4: Run Application with Gunicorn

```bash
# Create systemd service: /etc/systemd/system/securemoney.service
[Unit]
Description=SecureMoney Flask Application
After=network.target mysql.service

[Service]
User=www-data
WorkingDirectory=/var/www/securemoney
Environment="PATH=/var/www/securemoney/venv/bin"
EnvironmentFile=/var/www/securemoney/.env.production
ExecStart=/var/www/securemoney/venv/bin/gunicorn \
    --workers=4 \
    --worker-class=gthread \
    --threads=2 \
    --bind=127.0.0.1:8000 \
    --timeout=30 \
    --access-logfile=/var/log/securemoney/access.log \
    --error-logfile=/var/log/securemoney/error.log \
    wsgi:app
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target

# Enable and start
sudo systemctl daemon-reload
sudo systemctl enable securemoney
sudo systemctl start securemoney
```

### Step 5: Configure Nginx Reverse Proxy

```nginx
# /etc/nginx/sites-available/securemoney
upstream securemoney_backend {
    server 127.0.0.1:8000;
}

server {
    listen 80;
    server_name yourdomain.com www.yourdomain.com;

    # Redirect HTTP to HTTPS
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name yourdomain.com www.yourdomain.com;

    # SSL certificates (Let's Encrypt)
    ssl_certificate /etc/letsencrypt/live/yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/yourdomain.com/privkey.pem;

    # Security headers
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;

    # Rate limiting
    limit_req_zone $binary_remote_addr zone=login_limit:10m rate=10r/m;
    limit_req_zone $binary_remote_addr zone=api_limit:10m rate=100r/m;

    location /auth/login {
        limit_req zone=login_limit burst=5 nodelay;
        proxy_pass http://securemoney_backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /auth/verify-otp {
        limit_req zone=login_limit burst=5 nodelay;
        proxy_pass http://securemoney_backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location / {
        limit_req zone=api_limit burst=20 nodelay;
        proxy_pass http://securemoney_backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 30s;
        proxy_connect_timeout 30s;
    }

    # Static files (if serving via nginx)
    location /static/ {
        alias /var/www/securemoney/app/static/;
        expires 30d;
    }
}
```

### Step 6: SSL Certificate (Let's Encrypt)

```bash
# Install certbot
sudo apt-get install certbot python3-certbot-nginx

# Obtain certificate
sudo certbot certonly --nginx -d yourdomain.com -d www.yourdomain.com

# Auto-renewal (runs daily via cron)
sudo certbot renew --quiet
```

---

## Monitoring & Maintenance

### Logs

```bash
# Application logs
tail -f /var/log/securemoney/error.log
tail -f /var/log/securemoney/access.log

# Systemd logs
journalctl -u securemoney -n 100 -f
```

### Health Check

```bash
# Test application is responding
curl -k https://yourdomain.com/auth/login

# Check database connection
python -c "from app.models import get_user_by_id; print('DB OK' if get_user_by_id(1) else 'User not found')"
```

### Performance Monitoring

```bash
# Run benchmark
python scripts/benchmark.py

# Monitor gunicorn workers
ps aux | grep gunicorn
```

### Database Backups

```bash
# Daily backup
0 2 * * * mysqldump -u securemoney_app -p$DB_PASSWORD securemoney_prod | \
    gzip > /backups/securemoney_$(date +\%Y\%m\%d).sql.gz

# Keep 30 days of backups
find /backups -name "securemoney_*.sql.gz" -mtime +30 -delete
```

### Key Rotation

When rotating `MASTER_KEY_HEX`:

```bash
# 1. Generate new key
NEW_KEY=$(python -c "import secrets; print(secrets.token_hex(32))")

# 2. Run migration (encrypt all values with new key)
python scripts/rotate_keys.py --old-key=$OLD_KEY --new-key=$NEW_KEY

# 3. Update .env.production
sed -i "s/MASTER_KEY_HEX=.*/MASTER_KEY_HEX=$NEW_KEY/" .env.production

# 4. Restart application
sudo systemctl restart securemoney
```

---

## Cloud Deployments

### Heroku

```bash
# Create heroku.yml
cat > heroku.yml <<EOF
build:
  docker:
    web: Dockerfile
release:
  image: web
  command: python scripts/seed_demo.py
EOF

# Deploy
git push heroku main

# Configure env
heroku config:set MASTER_KEY_HEX=<secret>
heroku config:set SECRET_KEY=<secret>
```

### AWS (ECS + RDS)

1. Push Docker image to ECR
2. Create RDS MySQL instance
3. Create ECS task definition with environment variables
4. Load balance with ALB (Application Load Balancer)
5. Configure security groups (port 3306 for RDS, port 8000 for app)

### DigitalOcean App Platform

1. Connect GitHub repository
2. Create MySQL managed database
3. Set environment variables in app settings
4. Deploy

---

## Security Checklist

- [ ] Change all demo credentials immediately
- [ ] Update MASTER_KEY_HEX with a cryptographically random 64-hex-char string
- [ ] Update SECRET_KEY with a cryptographically random 64-hex-char string
- [ ] Enable HTTPS with valid SSL certificate
- [ ] Configure firewall (only allow 80, 443 from internet; 3306 only from app)
- [ ] Set `DB_PASSWORD` to a strong, randomly generated password
- [ ] Review audit log regularly for suspicious activity
- [ ] Set up daily database backups
- [ ] Configure log rotation to prevent disk fills
- [ ] Disable debug mode (`FLASK_DEBUG=0`)
- [ ] Set session timeouts appropriately (`SESSION_TIMEOUT_MINUTES`)
- [ ] Implement DDoS protection (Cloudflare, AWS Shield, etc.)
- [ ] Monitor database query logs for SQL injection attempts
- [ ] Review admin account access logs regularly
- [ ] Schedule key rotation annually or after any compromise

---

## Support & Troubleshooting

### Application won't start

```bash
# Check logs
journalctl -u securemoney -n 50 | grep ERROR

# Verify MySQL connection
mysql -u securemoney_app -p -h 127.0.0.1 securemoney_prod -e "SELECT 1"

# Check env vars are set
env | grep SECRET_KEY
env | grep MASTER_KEY_HEX
```

### High memory usage

- Increase gunicorn workers gradually (4 → 6 → 8)
- Monitor with: `ps aux | grep gunicorn`
- Check database connection pooling

### Slow transfers

- Run benchmark: `python scripts/benchmark.py`
- Check MySQL slow query log: `SET GLOBAL slow_query_log = 'ON'`
- Monitor network latency to MySQL

### OTP not sending

- Check EMAIL_SIMULATE in .env (should be `false` for production)
- Verify SMTP credentials work: `telnet smtp.gmail.com 587`
- Check application logs for SMTP errors
- Monitor email service quotas

---

## References

- [OWASP Production Readiness Checklist](https://cheatsheetseries.owasp.org)
- [Flask Deployment Options](https://flask.palletsprojects.com/en/latest/deploying/)
- [Gunicorn Documentation](https://gunicorn.org)
- [Nginx Configuration Best Practices](https://nginx.org/en/docs/)
