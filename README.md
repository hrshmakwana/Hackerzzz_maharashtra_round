# Black Box

A flight recorder for AI agents. It records every step an agent takes, ranks which step
actually caused a failure (the "Canon Event"), forks the run from a checkpoint at that step
with a fix, re-runs only what changed, and shows that the outcome flips.

**Record → Blame → Fork → Prove**

## Quick start

```bash
make setup
make test
make api    # http://localhost:8000/api/health
make web    # http://localhost:3000
```

Copy `.env.example` to `.env` (done by `make setup`). A Gemini key is optional; everything
except live Gemini runs and report narration works without it.

## Deploy (free tiers)

**API → Render.** New → Blueprint → pick this repo. `render.yaml` sets up a free Docker
web service. Fill in `ALLOWED_ORIGINS` with the Vercel URL (and the Gemini vars if you have
them). The health check is `/api/health`.

**Web → Vercel.** Add New → Project → pick this repo, set **Root Directory** to `frontend`,
and add `NEXT_PUBLIC_API_URL=https://<render-service>.onrender.com/api`.

Both redeploy on every push to `main`. The free Render instance sleeps after ~15 minutes
idle, so open the API URL a minute before a demo to wake it up.

## Layout

| Path | What |
|------|------|
| `blackbox_sdk/` | recorder SDK |
| `agent_sim/` | ShopOps sandbox world, tasks, policies, fault injection |
| `ml/` | features, baselines, training, evaluation, explanations |
| `backend/` | FastAPI API |
| `frontend/` | Next.js UI |
| `tests/` | pytest suite |

Built by Team Hackerzzz for Bit N Build 2026.
