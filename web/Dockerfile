# Mission Control in a container: Next.js standalone server on :3000. Build context is web/.
# The server routes reach the API at GROUNDWORK_API_URL and hold the admin token; the browser
# never sees either. Telemetry is off at build and at run time.
FROM node:22-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-fund --no-audit

FROM node:22-alpine AS build
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

FROM node:22-alpine
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT=3000
RUN addgroup -S app && adduser -S app -G app
COPY --from=build --chown=app:app /app/.next/standalone ./
COPY --from=build --chown=app:app /app/.next/static ./.next/static
USER app
EXPOSE 3000
# Bind every interface. Set here, not with ENV, because hosts such as Fly overwrite HOSTNAME with the
# machine's name, and Next's server would then listen on that address only.
CMD ["sh", "-c", "HOSTNAME=0.0.0.0 exec node server.js"]
