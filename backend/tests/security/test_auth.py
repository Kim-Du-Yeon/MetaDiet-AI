async def test_health_no_auth_required(client):
    r = await client.get("/health")
    assert r.status_code == 200


async def test_nutrition_lookup_no_auth_required(client):
    r = await client.post("/nutrition/lookup", json={"foods": []})
    assert r.status_code == 200


async def test_protected_endpoint_without_token_401(client):
    r = await client.get("/strategy/current")
    assert r.status_code == 401


async def test_protected_endpoint_with_forged_token_401(client):
    r = await client.get("/strategy/current", headers={"Authorization": "Bearer not-a-real-jwt"})
    assert r.status_code == 401


async def test_protected_endpoint_with_mocked_auth_200(client, mock_current_user, fake_sb):
    fake_sb.tables["diet_strategies"] = []
    r = await client.get("/strategy/current")
    assert r.status_code == 200
