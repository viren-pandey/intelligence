---
title: NEXUS
emoji: 🚀
colorFrom: indigo
colorTo: purple
sdk: docker
app_port: 8000
---

# NEXUS — Recruitment Intelligence Middleware

Standalone recruitment intelligence middleware that crawls 100+ sources, scores jobs with ATS matching, trust, freshness, and niche analysis, and returns ranked results via API.

## Environment Variables

Set these as Space secrets:

| Variable | Description |
|----------|-------------|
| `DATABASE_URL` | Neon PostgreSQL connection string |
| `REDIS_URL` | Redis connection string (optional, degrades gracefully) |
| `ADMIN_API_KEY` | Admin panel password (default: `nexus-admin-dev`) |

