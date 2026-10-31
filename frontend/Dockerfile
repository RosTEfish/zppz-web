# 22.23.4 is the October 21, 2026 Node.js security release (CVE-2026-111497).
FROM node:22.23.4-alpine AS build
ARG NPM_CONFIG_REGISTRY=https://registry.npmjs.org
WORKDIR /app
COPY frontend/package*.json ./
RUN npm ci --registry "${NPM_CONFIG_REGISTRY}"
COPY frontend ./
RUN npm run build \
  && npm run precompress

FROM nginx:1.27-alpine
COPY infra/nginx/default.conf /etc/nginx/conf.d/default.conf
COPY infra/nginx/security-headers.conf /etc/nginx/security-headers.conf
COPY --from=build /app/dist /usr/share/nginx/html
