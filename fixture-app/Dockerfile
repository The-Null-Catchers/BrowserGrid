FROM node:22.14.0-alpine
WORKDIR /app
COPY fixture-app/server.cjs ./
USER node
EXPOSE 8080
CMD ["node","server.cjs"]
