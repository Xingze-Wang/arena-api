# arena-api

Backend for the arena. Not in the `research-to-product` repo on purpose — the repo holds the *protocol* (the contract); this is the *implementation* (the eval runner, the leaderboard, the DB). Eventually deploys to `arena.calistamind.com`.

## What it does

- Researchers register and submit a model (URL to a `paper-to-api` instance speaking [protocol v0](https://github.com/Xingze-Wang/research-to-product/tree/main/protocol/v0)).
- arena-api probes `/health`, kicks a background eval against a held-out `.jsonl`, hits the researcher's `/predict` for each row, and judges with `claude-opus-4-7`.
- Scores write to SQLite. Elo updates from head-to-head votes (vote endpoint coming next).
- Leaderboard endpoint surfaces per-field rankings.

## Run locally

```bash
make install
cp .env.example .env  # paste ANTHROPIC_API_KEY (or skip for fallback substring scoring)

# terminal A
make mock          # a fake paper-to-api on :9001

# terminal B
make backend       # arena-api on :8001
```

Then submit via the [arena-skill](https://github.com/Xingze-Wang/research-to-product/tree/main/arena-skill) or directly:

```bash
# register
TOKEN=$(curl -s -X POST localhost:8001/api/v1/researchers \
  -H 'content-type: application/json' \
  -d '{"email":"you@x.com","name":"You"}' | jq -r .token)

# submit
curl -s -X POST localhost:8001/api/v1/models \
  -H "authorization: Bearer $TOKEN" -H 'content-type: application/json' \
  -d '{"protocol_version":"v0","field":"text","name":"mock-7B","version":"0.0.1","endpoint_url":"http://localhost:9001"}'

# leaderboard
curl -s localhost:8001/api/v1/leaderboard/text | jq
```

## Layout

```
arena_api/
├── main.py            # FastAPI routes
├── config.py          # env + constants
├── db.py              # SQLModel engine
├── models.py          # tables
├── schemas.py         # Pydantic req/resp
├── eval.py            # eval runner + Anthropic judge (prompt cached)
├── elo.py             # K=32 Elo
└── mock_endpoint.py   # fake paper-to-api for testing
data/holdouts/text.jsonl  # 10-row trivia held-out set
```

## Not yet

- Real sandboxing (today: trust the researcher's URL). v1 = Modal/Daytona.
- Vote endpoint for head-to-head Elo updates. The DB column is there; the route lands next.
- Stubs for non-text fields. v1 = hash-based mock scores so leaderboards aren't empty.
- Postgres migration. SQLite breaks at concurrent eval runs > ~4.
