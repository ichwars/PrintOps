"""Trust configuration for verified outbound TLS connections."""

import os
import ssl


def configured_ca_bundle() -> str | None:
    """Return the CA bundle prepared by the Docker entrypoint, if enabled."""
    return os.environ.get("PRINTOPS_CA_BUNDLE") or None


def create_client_ssl_context() -> ssl.SSLContext:
    # Python can run with a file capability in Docker. Pass the bundle
    # explicitly so verification does not depend on OpenSSL honoring its
    # environment variables under secure execution.
    return ssl.create_default_context(cafile=configured_ca_bundle())
