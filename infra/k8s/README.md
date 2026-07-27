# Kubernetes manifests

Applied in order by CI on a tagged release:

```bash
kubectl apply -f infra/k8s/deployment.yaml
```

Secrets are **not** in this repository. `matchit-secrets` must exist in the
namespace and carry `MATCHIT_JWT_SECRET`, `MATCHIT_DATABASE_URL`,
`MATCHIT_REDIS_URL`, `MATCHIT_ANTHROPIC_API_KEY`, `MATCHIT_OPENAI_API_KEY`,
`MATCHIT_STRIPE_API_KEY` and the APNs signing key — sourced from the cluster's
secret manager (External Secrets / AWS Secrets Manager), never `kubectl create`
by hand.

Notes on choices that are easy to get wrong:

- **The liveness probe hits `/health`, which touches no dependency.** A probe
  that checked Postgres would turn one slow database into a cluster-wide restart
  loop at exactly the moment the database could least afford it.
- **Migrations are a pre-upgrade Job, not an init container.** An init container
  runs once per pod, so three replicas would race three migrations.
- **The API is stateless**: JWT auth, Redis-shared rate limits and pub/sub, and
  chat sockets that hold no database connection while idle. No session affinity
  is required, which is what lets the HPA scale freely.
