# MetaDiet local deployment

The deployment keeps external state in Supabase and Pinecone while splitting
the application into API, scheduler worker, and read-only MCP processes.

For the no-cost public beta, use the root `render.yaml` and follow
[`RENDER_BETA.md`](RENDER_BETA.md). That profile uses one free API instance
with its scheduler enabled plus one static frontend; local Compose and kind
continue to use the split API/worker/MCP topology below.

## Docker Compose

```powershell
docker compose --env-file backend/.env up -d --build
docker compose ps
docker compose logs --tail 100 api worker mcp
```

The API container disables its scheduler so scheduled work runs only in the
worker. `backend/.env` is injected at runtime and is excluded from the image.

## kind

The demo manifest uses the current Kubernetes namespace (the `default`
namespace on a fresh kind cluster). Run the secret, apply, rollout, and
inspection commands with the same context and namespace.

```powershell
kind create cluster --name metadiet --config deploy/kind-config.yaml
docker build -f backend/Dockerfile -t metadiet:local .
kind load docker-image metadiet:local --name metadiet
kubectl create secret generic metadiet-secrets --from-env-file=backend/.env
$mcpKeys = @('GEMINI_API_KEY', 'PINECONE_API_KEY')
Get-Content backend/.env | Where-Object { $mcpKeys -contains ($_ -split '=', 2)[0] } | Set-Content backend/.env.mcp.tmp
kubectl create secret generic metadiet-mcp-secrets --from-env-file=backend/.env.mcp.tmp
Remove-Item backend/.env.mcp.tmp
kubectl apply -f deploy/k8s/metadiet.yaml
kubectl rollout status deployment/metadiet-api --timeout=180s
kubectl rollout status deployment/metadiet-worker --timeout=180s
kubectl rollout status deployment/metadiet-mcp --timeout=180s
```

The manifest starts two API replicas and one worker and MCP replica. The MCP
pod receives only Gemini and Pinecone credentials and is exposed inside the
cluster with a `ClusterIP`. For local inspection, use
`kubectl port-forward service/metadiet-mcp 8090:8090`; port-forward binds to
localhost by default. All containers run as UID/GID 999 with no added
capabilities. The API rollout uses `maxUnavailable: 0`, a startup probe, a
60-second termination grace period, and a PodDisruptionBudget that keeps at
least one replica available. `SERVICE_TIMEZONE=Asia/Seoul` is supplied through
the non-secret ConfigMap to API and worker. To exercise recovery:

```powershell
kubectl rollout restart deployment/metadiet-api
kubectl rollout status deployment/metadiet-api --timeout=180s
kubectl logs -l app=metadiet-api --prefix --tail=50
```

Successful recovery requires both replacement pods to become Ready and log
successful `AsyncPostgresSaver` setup. Durable call-budget and idempotent
proposal behavior are covered by the backend regression suite.

The progress-event journal is intentionally pod-local. If an SSE reconnect lands
on another pod while the durable checkpoint still says `running`, the API resumes
the same `stream_run_id` from `AsyncPostgresSaver`; terminal checkpoints are only
replayed and are not executed again. Run the synthetic-user recovery check against
an already-running kind deployment with:

```powershell
C:\Users\bok7z\AppData\Local\Programs\Python\Python312\python.exe backend/scripts/check_sse_rollout_recovery.py
```

The check deletes the API pod that emitted the first progress event, reconnects
through the Service, confirms the recovered proposal twice, verifies one meal row,
and removes its synthetic user.
