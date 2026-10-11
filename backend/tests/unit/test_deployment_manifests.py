from pathlib import Path
import json

import yaml


ROOT = Path(__file__).resolve().parents[3]


def _docs(path):
    return list(yaml.safe_load_all((ROOT / path).read_text(encoding="utf-8")))


def test_kind_manifests_split_api_worker_and_mcp_without_inline_secrets():
    docs = _docs("deploy/k8s/metadiet.yaml")
    deployments = {item["metadata"]["name"]: item for item in docs if item.get("kind") == "Deployment"}
    assert set(deployments) == {"metadiet-api", "metadiet-worker", "metadiet-mcp"}
    assert deployments["metadiet-api"]["spec"]["replicas"] == 2
    for deployment in deployments.values():
        pod = deployment["spec"]["template"]["spec"]
        security = pod["containers"][0]["securityContext"]
        assert security["runAsNonRoot"] is True
        assert security["runAsUser"] == 999
        assert security["runAsGroup"] == 999
    assert deployments["metadiet-api"]["spec"]["template"]["spec"]["containers"][0]["envFrom"][0]["secretRef"]["name"] == "metadiet-secrets"
    assert deployments["metadiet-worker"]["spec"]["template"]["spec"]["containers"][0]["envFrom"][0]["secretRef"]["name"] == "metadiet-secrets"
    mcp = deployments["metadiet-mcp"]["spec"]["template"]["spec"]["containers"][0]
    assert mcp["envFrom"][0]["secretRef"]["name"] == "metadiet-mcp-secrets"
    api = deployments["metadiet-api"]["spec"]["template"]["spec"]["containers"][0]
    assert api["readinessProbe"]["httpGet"]["path"] == "/health"
    assert not any(item.get("kind") == "Secret" for item in docs)
    for deployment in deployments.values():
        container = deployment["spec"]["template"]["spec"]["containers"][0]
        assert all("value" not in item for item in container.get("env", []))


def test_compose_has_three_services_and_disables_scheduler_in_api():
    compose = yaml.safe_load((ROOT / "compose.yaml").read_text(encoding="utf-8"))
    assert set(compose["services"]) == {"api", "worker", "mcp"}
    assert compose["services"]["api"]["environment"]["ENABLE_SCHEDULER"] == "false"
    assert compose["services"]["mcp"]["ports"] == ["127.0.0.1:8090:8090"]
    assert "env_file" not in compose["services"]["mcp"]
    assert {
        "GEMINI_API_KEY", "PINECONE_API_KEY", "SUPABASE_URL",
        "SUPABASE_SERVICE_KEY", "SUPABASE_JWT_SECRET",
    }.issubset(compose["services"]["mcp"]["environment"])


def test_compose_healthchecks_cover_api_worker_and_mcp():
    compose = yaml.safe_load((ROOT / "compose.yaml").read_text(encoding="utf-8"))

    for service in ("api", "worker", "mcp"):
        healthcheck = compose["services"][service].get("healthcheck")
        assert healthcheck, f"{service} must declare a healthcheck"
        assert healthcheck["test"][0] == "CMD"


def test_kind_does_not_publish_unauthenticated_mcp_port():
    kind = yaml.safe_load((ROOT / "deploy/kind-config.yaml").read_text(encoding="utf-8"))
    mappings = kind["nodes"][0].get("extraPortMappings", [])
    assert all(item.get("containerPort") != 30090 for item in mappings)
    services = {item["metadata"]["name"]: item for item in _docs("deploy/k8s/metadiet.yaml")
                if item.get("kind") == "Service"}
    assert services["metadiet-mcp"]["spec"]["type"] == "ClusterIP"


def test_container_runs_as_non_root_and_does_not_copy_env_file():
    dockerfile = (ROOT / "backend/Dockerfile").read_text(encoding="utf-8")
    dockerignore = (ROOT / ".dockerignore").read_text(encoding="utf-8")
    assert "USER app" in dockerfile
    assert "backend/.env" in dockerignore
    assert "COPY backend/.env" not in dockerfile


def test_kind_rag_config_points_to_an_activated_build_shipped_in_the_image():
    docs = _docs("deploy/k8s/metadiet.yaml")
    config = next(item["data"] for item in docs
                  if item.get("kind") == "ConfigMap" and item["metadata"]["name"] == "metadiet-config")
    container_path = config["RAG_CHUNKS_PATH"]
    assert container_path.startswith("/app/app/rag/builds/")
    relative = container_path.removeprefix("/app/")
    chunks_path = ROOT / "backend" / relative
    activation_path = chunks_path.with_name("activation.json")
    assert chunks_path.is_file()
    manifest = json.loads(activation_path.read_text(encoding="utf-8"))
    assert manifest["status"].startswith("activated")
    assert config["PINECONE_NAMESPACE"] == manifest["namespace"]
    assert config["PINECONE_INDEX_NAME"] == manifest["index_name"]
    assert config["EMBEDDING_MODEL"] == manifest["embedding_model"]
    assert int(config["EMBEDDING_DIMENSION"]) == manifest["embedding_dimension"]


def test_kind_api_rollout_preserves_one_ready_replica_and_service_clock():
    docs = _docs("deploy/k8s/metadiet.yaml")
    deployments = {item["metadata"]["name"]: item for item in docs if item.get("kind") == "Deployment"}
    config = next(item["data"] for item in docs
                  if item.get("kind") == "ConfigMap" and item["metadata"]["name"] == "metadiet-config")
    api = deployments["metadiet-api"]["spec"]
    pod = api["template"]["spec"]
    container = pod["containers"][0]
    pdb = next(item for item in docs if item.get("kind") == "PodDisruptionBudget")

    assert config["SERVICE_TIMEZONE"] == "Asia/Seoul"
    assert deployments["metadiet-worker"]["spec"]["template"]["spec"]["containers"][0]["envFrom"][1]["configMapRef"]["name"] == "metadiet-config"
    assert api["strategy"]["rollingUpdate"] == {"maxUnavailable": 0, "maxSurge": 1}
    assert api["minReadySeconds"] >= 5
    assert pod["terminationGracePeriodSeconds"] >= 60
    assert container["startupProbe"]["httpGet"]["path"] == "/health"
    assert pdb["spec"]["minAvailable"] == 1
    assert pdb["spec"]["selector"]["matchLabels"] == {"app": "metadiet-api"}


def test_render_blueprint_defines_free_api_and_static_frontend_without_secrets():
    blueprint = yaml.safe_load((ROOT / "render.yaml").read_text(encoding="utf-8"))
    services = {service["name"]: service for service in blueprint["services"]}

    api = services["metadiet-api"]
    assert api["type"] == "web"
    assert api["runtime"] == "docker"
    assert api["plan"] == "free"
    assert api["dockerfilePath"] == "./backend/Dockerfile"
    assert api["dockerContext"] == "."
    assert api["healthCheckPath"] == "/health"
    api_env = {item["key"]: item for item in api["envVars"]}
    assert api_env["ENABLE_SCHEDULER"]["value"] == "true"
    assert api_env["SERVICE_TIMEZONE"]["value"] == "Asia/Seoul"
    assert api_env["RAG_CHUNKS_PATH"]["value"] == "/app/app/rag/chunks.pkl"
    assert api_env["PINECONE_NAMESPACE"]["value"] == "metadiet-gemini-1157903c493dbb5d759f"
    for key in (
        "GEMINI_API_KEY", "SUPABASE_URL", "SUPABASE_SERVICE_KEY",
        "SUPABASE_JWT_SECRET", "SUPABASE_DB_URL", "PINECONE_API_KEY",
        "LANGSMITH_API_KEY", "CORS_ORIGINS",
    ):
        assert api_env[key] == {"key": key, "sync": False}

    frontend = services["metadiet-web"]
    assert frontend["type"] == "web"
    assert frontend["runtime"] == "static"
    assert frontend["buildCommand"] == "cd frontend && npm ci && npm run build"
    assert frontend["staticPublishPath"] == "./frontend/build"
    frontend_env = {item["key"]: item for item in frontend["envVars"]}
    assert frontend_env["REACT_APP_API_URL"]["sync"] is False
    assert frontend_env["REACT_APP_SUPABASE_URL"]["sync"] is False
    assert frontend_env["REACT_APP_SUPABASE_ANON_KEY"]["sync"] is False
    assert any(route == {"type": "rewrite", "source": "/*", "destination": "/index.html"}
               for route in frontend["routes"])
