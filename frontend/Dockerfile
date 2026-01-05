# syntax=docker/dockerfile:1.6
FROM node:20-alpine AS base

ENV NODE_ENV=development

WORKDIR /app

RUN apk add --no-cache libc6-compat \
    && corepack enable \
    && corepack prepare yarn@1.22.22 --activate

COPY package.json yarn.lock ./

RUN yarn install --frozen-lockfile

COPY . .

EXPOSE 3000

CMD ["yarn", "dev", "--hostname", "0.0.0.0", "--port", "3000"]
