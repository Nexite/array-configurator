FROM node:22-alpine AS ui
WORKDIR /ui
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install
COPY frontend/ .
COPY backend/app /backend/app
COPY samples /samples
RUN node scripts/warm-pyodide.mjs && npm run build

FROM node:22-alpine
RUN apk add --no-cache curl
WORKDIR /srv
COPY --from=ui /ui/dist /srv/dist
COPY frontend/scripts/static-server.mjs /srv/static-server.mjs
ENV PORT=8080
ENV STATIC_DIR=/srv/dist
EXPOSE 8080
CMD ["node", "static-server.mjs"]
