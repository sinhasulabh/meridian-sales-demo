# Thin static client. Build-time env (VITE_AGENT_URL) points at the agent
# service; nginx just serves the resulting bundle (spec §11A, §16.1).

FROM node:22-slim AS build
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm install
COPY . .
ARG VITE_AGENT_URL
ENV VITE_AGENT_URL=${VITE_AGENT_URL}
RUN npm run build

FROM nginx:1.27-alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 8080
