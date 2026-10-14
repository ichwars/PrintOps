# The digest pins each platform's image through the multiarchitecture index.
FROM node:22-bookworm-slim@sha256:c3de60bf2f9dd0ac6370e6117950ff62d6e339527e7472301c9c78a017978392 AS build
ARG TARGETARCH
RUN apt-get update && apt-get install -y --no-install-recommends python3 ca-certificates \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /build
COPY native_build.py /build/native_build.py
RUN python3 native_build.py wrapper /build
WORKDIR /build/wrapper
# Security-only lock overlay; wrapper source and package.json remain pinned.
COPY package-lock.json /build/wrapper/package-lock.json
RUN echo "edfcdb21e7bfe039641c01d4f9254b67a24c3e950cb9c9c0527084bac272478e  package-lock.json" | sha256sum -c -
RUN npm ci --ignore-scripts && npm run build && npm prune --omit=dev --ignore-scripts && npm audit --omit=dev
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
RUN mkdir -p /app/data
WORKDIR /app
ENV PORT=3000 NODE_ENV=production SLICER_FLAVOR=orca \
    ORCASLICER_PATH=/app/squashfs-root/AppRun DATA_PATH=/app/data
EXPOSE 3000
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:3000/health || exit 1
CMD ["node", "/app/dist/index.js"]
