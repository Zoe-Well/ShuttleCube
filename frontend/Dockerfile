FROM node:24-alpine AS build
WORKDIR /app
RUN corepack enable
COPY frontend/package.json ./
RUN pnpm install
COPY frontend .
RUN pnpm build
FROM nginx:1.29-alpine
COPY --from=build /app/dist /usr/share/nginx/html
