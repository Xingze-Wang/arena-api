# Deploying arena-api

Hosted on **Fly.io**. CI auto-deploys on push to `main` once the token is set.

> Note: the `Dockerfile` mirrors the verified local install but has not been
> container-build-tested in this environment (no Docker daemon available here).
> First `fly deploy` will surface any image issue; the install steps are identical
> to the working local `pip install -e .`.

## One-time setup

```bash
# install flyctl, then:
fly auth login
fly launch --no-deploy --copy-config --name arena-api      # uses the committed fly.toml
fly volumes create arena_data --size 1 --region iad          # persists SQLite at /data

# secrets (never commit these)
fly secrets set ARENA_HOLDOUT_KEY=$(python3 -c "import os,base64;print(base64.b64encode(os.urandom(32)).decode())")
fly secrets set ANTHROPIC_API_KEY=sk-ant-...                 # omit to use substring-match fallback judge

fly deploy
```

Your API is then at `https://arena-api.fly.dev`. Point the frontend's
`NEXT_PUBLIC_ARENA_API_BASE` at it.

## CI auto-deploy

`.github/workflows/deploy.yml` deploys on every push to `main`. To enable:

1. `fly tokens create deploy` → copy the token.
2. GitHub → repo Settings → Secrets and variables → Actions → New secret:
   `FLY_API_TOKEN` = that token.

Until the secret exists the workflow no-ops (no failed runs).

## Important: key + volume durability

`ARENA_HOLDOUT_KEY` must stay stable across deploys, or previously-encrypted
business uploads become unreadable. It's a Fly secret (persisted), and held-out
data lives on the `/data` volume (persisted) — so both survive redeploys. The
committed dev holdout (`data/holdouts/text.jsonl`) re-encrypts from plaintext at
each boot, which is fine because it's public sample data.

## Scaling note

SQLite + a single Fly machine is the v0 substrate. Before real concurrent eval
load, move to Postgres (Fly Postgres or Neon) and run the eval runner as a
separate worker process. See the repo's `README.md` "Not yet" section.
