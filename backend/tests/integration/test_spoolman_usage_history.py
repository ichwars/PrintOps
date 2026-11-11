from sqlalchemy import select

from backend.app.models.spool import Spool
from backend.app.models.spool_usage_history import SpoolUsageHistory


async def test_spoolman_and_local_usage_are_distinct_even_with_the_same_spool_id(async_client, db_session):
    local = Spool(material="PLA")
    db_session.add(local)
    await db_session.flush()
    db_session.add_all(
        [
            SpoolUsageHistory(spool_id=local.id, weight_used=12),
            SpoolUsageHistory(spoolman_spool_id=local.id, weight_used=21),
        ]
    )
    await db_session.commit()

    for route in ("/inventory/usage", f"/inventory/spools/{local.id}/usage"):
        for source, grams in (("builtin", 12), ("spoolman", 21)):
            result = await async_client.get(f"/api/v1{route}", params={"source": source})
            assert result.status_code == 200, result.text
            assert [row["weight_used"] for row in result.json()] == [grams]

    result = await async_client.delete(f"/api/v1/inventory/spools/{local.id}/usage", params={"source": "spoolman"})
    assert result.status_code == 200, result.text
    assert list(await db_session.scalars(select(SpoolUsageHistory.weight_used))) == [12]
