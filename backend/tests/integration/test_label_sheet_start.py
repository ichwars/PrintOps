"""Start-position validation applies to every label source before fetching items."""

import pytest


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.parametrize(
    "route,id_key",
    [
        ("inventory", "spool_ids"),
        ("spoolman", "spool_ids"),
        ("small-parts", "small_part_ids"),
    ],
)
@pytest.mark.parametrize(
    "template,position",
    [
        ("avery_l7160", 22),
        ("avery_5160", 31),
        ("avery_l7160", 0),
        ("avery_5160", -1),
        ("box_62x29", 2),
        ("avery_l7160", 1.5),
        ("avery_5160", True),
        ("avery_l7160", "2"),
    ],
)
async def test_invalid_start_position_returns_422(async_client, route, id_key, template, position):
    response = await async_client.post(
        f"/api/v1/{route}/labels",
        json={
            id_key: [99999],
            "template": template,
            "start_position": position,
        },
    )
    assert response.status_code == 422
    assert "start_position" in response.text
