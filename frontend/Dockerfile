FROM node:22-alpine AS build
ARG NPM_CONFIG_REGISTRY=https://registry.npmjs.org
WORKDIR /app
COPY frontend/package*.json ./
RUN npm ci --registry "${NPM_CONFIG_REGISTRY}"
COPY frontend ./
RUN npm run build

FROM nginx:1.27-alpine
COPY infra/nginx/default.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
