"""Exercise the patched standalone renderer and both Brotli copies on Windows."""

import subprocess
import tempfile
from pathlib import Path

from brotli_runtime import stage_brotli_runtime
from build import REPO_ROOT, WEASYPRINT_RUNTIME_SHA256, WEASYPRINT_RUNTIME_URL, download_verified, unzip


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="printops-pdf-security-") as tmp:
        root = Path(tmp)
        archive = download_verified(WEASYPRINT_RUNTIME_URL, root / "weasyprint.zip", WEASYPRINT_RUNTIME_SHA256)
        unzip(archive, root / "runtime")
        renderer = root / "runtime/onedir/weasyprint"
        stage_brotli_runtime(renderer / "_internal", root, download_verified)
        font = (REPO_ROOT / "frontend/public/fonts/inter-latin.woff2").as_uri()
        html = root / "input.html"
        html.write_text(
            f'<style>@font-face {{font-family: decoder; src:url("{font}") format("woff2");}}'
            "body {font-family: decoder;}</style><p>PrintOps Brotli 1.2.1 — äöü 123</p>",
            encoding="utf-8",
        )
        result = subprocess.run(
            [str(renderer / "weasyprint.exe"), str(html), str(root / "output.pdf")],
            check=True,
            capture_output=True,
            text=True,
            timeout=90,
        )
        if "WARNING" in result.stderr or "ERROR" in result.stderr:
            raise RuntimeError(result.stderr)
        assert (root / "output.pdf").read_bytes().startswith(b"%PDF-"), "Renderer did not produce a PDF"
        print("Verified native Brotli 1.2.1 and standalone WOFF2/PDF rendering")


if __name__ == "__main__":
    main()
