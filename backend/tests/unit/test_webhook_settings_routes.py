import re
from pathlib import Path

from backend.app.api.routes.webhook import router


def test_settings_list_matches_webhook_routes():
    path = Path(__file__).resolve().parents[3] / "frontend/src/components/settings/WebhookEndpoints.tsx"
    listed = set(re.findall(r"\['(GET|POST)', '(/api/v1/webhook/[^']+)'", path.read_text(encoding="utf-8")))
    routed = {
        (method, "/api/v1" + route.path.replace("{printer_id}", ":id"))
        for route in router.routes
        for method in route.methods - {"HEAD", "OPTIONS"}
    }
    assert listed == routed
