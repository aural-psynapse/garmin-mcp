## Context

Currently all users share a single Cloudflare Tunnel endpoint. While API key auth provides logical isolation, there is no network-level separation between users.

## Problem

A single tunnel means all user traffic flows through the same public URL. For privacy-conscious users this is undesirable.

## Proposed solution

Each user gets their own Cloudflare Tunnel with a dedicated public URL and token. Extend `cloudflared` in docker-compose to one instance per user.

## Acceptance criteria

- [ ] Each user config block has its own `cloudflare_tunnel_token`
- [ ] docker-compose spins up one `cloudflared` container per user
- [ ] Each user's MCP connector URL is unique and fully isolated
- [ ] README documents per-user tunnel setup
- [ ] Existing single-tunnel mode still works as a fallback

## Notes

Prerequisite: users must each have a Cloudflare account and create their own tunnel in the dashboard.
