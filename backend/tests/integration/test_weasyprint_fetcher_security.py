"""CVE-2026-55073: auxiliary resources must retain the original fetch policy.

Only test-owned temporary files are used; no external service is contacted.
Explicit trusted filename/file-object inputs are not URL policy inputs.
"""

from __future__ import annotations

import pytest


@pytest.fixture
def resources(tmp_path):
    from weasyprint import HTML
    from weasyprint.urls import FatalURLFetchingError, URLFetcher, URLFetcherResponse

    blocked = tmp_path / "blocked.css"
    blocked.write_text("@page { size: 1234px 5678px }", encoding="utf-8")
    outer = tmp_path / "outer.css"
    outer.write_text(f'@import url("{blocked.as_uri()}");', encoding="utf-8")
    metadata = tmp_path / "metadata.xmp"
    marker = b"printops-owned-metadata-canary"
    metadata.write_bytes(
        b'<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">'
        b'<rdf:Description xmlns:fixture="urn:printops:test" fixture:marker="' + marker + b'"/></rdf:RDF>'
    )

    class Policy(URLFetcher):
        def __init__(self, allowed=()):
            super().__init__()
            self.allowed = set(allowed)
            self.calls = []

        def fetch(self, url, headers=None):
            self.calls.append(url)
            for path in (blocked, outer, metadata):
                if url == path.as_uri() and url in self.allowed:
                    mime = "text/css" if path.suffix == ".css" else "application/rdf+xml"
                    return URLFetcherResponse(url, path.read_bytes(), {"Content-Type": mime})
            raise FatalURLFetchingError("fixture resource denied by original fetcher")

    return HTML, Policy, FatalURLFetchingError, blocked, outer, metadata, marker


@pytest.mark.parametrize("channel", ["html-link", "stylesheet", "import", "xmp"])
def test_auxiliary_resources_cannot_bypass_original_fetcher(resources, channel):
    HTML, Policy, Denied, blocked, outer, metadata, _ = resources
    policy = Policy([outer.as_uri()] if channel == "import" else [])
    source = f'<link rel="stylesheet" href="{blocked.as_uri()}">' if channel == "html-link" else ""
    html = HTML(string=f"{source}<p>Control document</p>", url_fetcher=policy)
    with pytest.raises(Denied, match="original fetcher"):
        if channel == "xmp":
            html.write_pdf(xmp_metadata=[metadata.as_uri()], pdf_variant="pdf/a-3b")
        elif channel in {"stylesheet", "import"}:
            html.render(stylesheets=[(outer if channel == "import" else blocked).as_uri()])
        else:
            html.render()
    assert (metadata if channel == "xmp" else blocked).as_uri() in policy.calls


def test_original_fetcher_still_allows_approved_stylesheets_and_metadata(resources):
    HTML, Policy, _, blocked, _, metadata, marker = resources
    policy = Policy([blocked.as_uri(), metadata.as_uri()])
    html = HTML(string="<p>Allowed document</p>", url_fetcher=policy)
    document = html.render(stylesheets=[blocked.as_uri()])
    assert (document.pages[0].width, document.pages[0].height) == (1234, 5678)
    pdf = document.write_pdf(xmp_metadata=[metadata.as_uri()], pdf_variant="pdf/a-3b", uncompressed_pdf=True)
    assert marker in pdf
    assert policy.calls == [blocked.as_uri(), metadata.as_uri()]
