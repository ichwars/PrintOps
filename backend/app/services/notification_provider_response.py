"""Identify provider responses that need a specific delivery diagnostic."""

import httpx


def _looks_like_cloudflare_challenge(response: httpx.Response) -> bool:
    """Identify Cloudflare mitigation interstitials in provider responses.

    Detection deliberately does NOT rely on ``Server: cloudflare`` alone
    — Cloudflare adds that header to every response it proxies (success
    AND legitimate origin errors), so a real 401 "wrong token" from a
    CF-fronted ntfy would false-positive into a misleading "your CF is
    blocking" message. Reliable signals: the ``cf-mitigated`` header
    (set only when CF actively mitigates) and the challenge body shape.
    """
    if response.headers.get("cf-mitigated"):
        return True
    content_type = (response.headers.get("content-type") or "").lower()
    if "html" not in content_type:
        return False
    body = (response.text or "")[:1024].lower()
    # "Just a moment..." is Cloudflare's universal challenge-page title
    # (managed challenge, JS challenge, Under Attack mode). Combined with
    # an HTML content-type this is unambiguous — no legitimate ntfy or
    # webhook backend returns HTML with that title. ``cf-chl-*`` and
    # ``challenge-platform`` cover newer / non-default CF templates.
    return "just a moment" in body or "cf-chl-bypass" in body or "cf-chl-opt" in body or "challenge-platform" in body
