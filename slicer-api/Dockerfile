# The digest pins each platform's image through the multiarchitecture index.
FROM node:22-bookworm-slim@sha256:c3de60bf2f9dd0ac6370e6117950ff62d6e339527e7472301c9c78a017978392 AS build
ARG TARGETARCH
RUN apt-get update && apt-get install -y --no-install-recommends python3 ca-certificates \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /build
COPY native_build.py /build/native_build.py
RUN python3 native_build.py wrapper /build
WORKDIR /build/wrapper
# Security-only metadata overlays; wrapper application source remains pinned.
COPY package.json package-lock.json /build/wrapper/
RUN echo "129702617cc09053039e8ed01e5dccafe73415d83b41eff5d7fb5d5b068ca031  package.json" | sha256sum -c - \
    && echo "cd52e04cd0dde9ffa4b8174fdd9513d401b234d30537dd77a1000df020cd48be  package-lock.json" | sha256sum -c -
RUN npm ci --ignore-scripts && npm audit && npm run build \
    && npx --no-install vitest run tests/unit --maxWorkers=2 \
    && npm prune --omit=dev --ignore-scripts && npm audit --omit=dev
WORKDIR /build
RUN python3 native_build.py engine /build --arch "$TARGETARCH"

FROM ubuntu:24.04@sha256:534baea6a22c03a63003dbc8dbe78fe34bc0d7e595d9a9dc9834884ff530eb55
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates libgl1 libgl1-mesa-dri libegl1 libopengl0 libglu1-mesa \
    libsm6 libice6 libmspack0 libgtk-3-0 libgstreamer1.0-0 \
    libgstreamer-plugins-base1.0-0 libwebkit2gtk-4.1-0 \
    && rm -rf /var/lib/apt/lists/*
COPY --from=build /usr/local/bin/node /usr/local/bin/node
COPY --from=build /build/wrapper/dist/src /app/dist
COPY --from=build /build/wrapper/node_modules /app/node_modules
COPY --from=build /build/wrapper/package.json /app/package.json
# Keep license and the exact corresponding wrapper source available in the image.
COPY --from=build /build/wrapper/src /app/wrapper-source/src
COPY --from=build /build/wrapper/LICENSE /build/wrapper/package*.json /build/wrapper/tsconfig.json /app/wrapper-source/
COPY --from=build /build/squashfs-root /app/squashfs-root
RUN groupadd --gid 10001 orca \
    && useradd --uid 10001 --gid 10001 --create-home --home-dir /home/orca orca \
    && install -d -o 10001 -g 10001 /app/data \
    && install -d -m 0700 -o 10001 -g 10001 /home/orca/.runtime
WORKDIR /home/orca
ENV PORT=3000 NODE_ENV=production SLICER_FLAVOR=orca \
    ORCASLICER_PATH=/app/squashfs-root/AppRun DATA_PATH=/app/data HOME=/home/orca XDG_RUNTIME_DIR=/home/orca/.runtime
EXPOSE 3000
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:3000/health || exit 1
USER 10001:10001
CMD ["node", "/app/dist/index.js"]
