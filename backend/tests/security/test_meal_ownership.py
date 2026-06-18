async def test_update_meal_other_owner_403(client, mock_current_user, fake_sb):
    fake_sb.tables["meal_logs"] = [{"food_name": "닭가슴살", "user_id": "other-user"}]
    r = await client.put("/meal/update", json={"meal_id": "m1", "quantity_g": 150})
    assert r.status_code == 403


async def test_delete_meal_other_owner_403(client, mock_current_user, fake_sb):
    fake_sb.tables["meal_logs"] = [{"user_id": "other-user"}]
    r = await client.delete("/meal/delete/m1")
    assert r.status_code == 403


async def test_delete_meal_not_found_404(client, mock_current_user, fake_sb):
    fake_sb.tables["meal_logs"] = []
    r = await client.delete("/meal/delete/m404")
    assert r.status_code == 404


async def test_delete_meal_own_200(client, mock_current_user, fake_sb):
    fake_sb.tables["meal_logs"] = [{"user_id": mock_current_user}]
    r = await client.delete("/meal/delete/m1")
    assert r.status_code == 200
