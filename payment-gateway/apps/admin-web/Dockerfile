FROM node:18-alpine AS builder

WORKDIR /usr/src/app

COPY package*.json ./
COPY packages/shared/package*.json ./packages/shared/
COPY apps/admin-web/package*.json ./apps/admin-web/

RUN npm install

COPY tsconfig*.json ./
COPY packages/shared ./packages/shared
COPY apps/admin-web ./apps/admin-web

# Build shared package and admin React app
RUN npm run build:shared
WORKDIR /usr/src/app/apps/admin-web
RUN npm run build

FROM nginx:1.25-alpine

COPY --from=builder /usr/src/app/apps/admin-web/dist /usr/share/nginx/html

# Custom Nginx config to proxy /api requests to gospel-pay-api with security headers
COPY <<EOF /etc/nginx/conf.d/default.conf
server {
    listen 80;

    # Security headers (stricter for admin panel)
    add_header X-Frame-Options "DENY" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "no-referrer" always;
    add_header Content-Security-Policy "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; img-src 'self' data:; connect-src 'self'" always;

    location / {
        root /usr/share/nginx/html;
        index index.html index.htm;
        try_files \$uri \$uri/ /index.html;
    }

    location /api {
        proxy_pass http://gospel-pay-api:5000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_cache_bypass \$http_upgrade;
        proxy_read_timeout 60s;
        proxy_connect_timeout 10s;
        client_max_body_size 1m;
    }
}
EOF

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
