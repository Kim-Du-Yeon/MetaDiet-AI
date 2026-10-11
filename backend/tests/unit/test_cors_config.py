from app.core.cors import allowed_origins


def test_allowed_origins_keep_local_defaults_and_add_trimmed_unique_env_values():
    origins = allowed_origins(
        " https://metadiet-web.onrender.com,https://beta.example.com,"
        "https://metadiet-web.onrender.com "
    )

    assert "http://localhost:3000" in origins
    assert "http://127.0.0.1:3000" in origins
    assert origins[-2:] == [
        "https://metadiet-web.onrender.com",
        "https://beta.example.com",
    ]


def test_allowed_origins_ignore_empty_deployment_setting():
    origins = allowed_origins(" , ")

    assert origins == [
        "http://localhost:3000",
        "http://localhost:8080",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:8080",
    ]
