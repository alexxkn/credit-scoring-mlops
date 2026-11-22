# syntax=docker/dockerfile:1.7
# Сборка статики в node, раздача через nginx без root: в итоговом образе нет node и исходников

FROM docker.io/library/node:24-alpine AS build
WORKDIR /build
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY src src
RUN npm run build

FROM docker.io/nginxinc/nginx-unprivileged:1.29-alpine AS runtime
ENV API_UPSTREAM=http://credit-scoring-api:8000
COPY nginx.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /build/dist /usr/share/nginx/html
USER 101
EXPOSE 8080
