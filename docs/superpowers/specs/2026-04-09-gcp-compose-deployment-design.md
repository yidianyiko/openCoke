# GCP Compose Deployment Design

## Goal

Rebuild `gcp-coke` as a clean single-host deployment for Coke using Docker Compose for
application services, host Nginx for TLS termination and path routing, and a systemd unit for
boot-time orchestration.

## Constraints

- Keep the host OS, Docker, Nginx, and existing TLS assets.
- Remove the old ad-hoc deployment shape: PM2, hand-started Python processes, local Mongo logs,
  and stale runtime directories.
- Make future deploys repeatable from the repository.
- Do not depend on the existing remote git checkout being healthy.

## Recommended Approach

### Option A: Docker Compose + Host Nginx + systemd wrapper

This is the chosen approach.

Benefits:

- Handles the mixed Python + Node + MongoDB + Redis + PostgreSQL stack cleanly.
- Eliminates host-level dependency drift like missing `pnpm` or port collisions with host Redis.
- Makes restart behavior, service logs, and startup ordering explicit.
- Keeps TLS and public ingress simple by reusing host Nginx.

Trade-offs:

- Requires container build files for the Python services.
- Requires a production-specific config mount for Coke because the current `conf/config.json`
  uses localhost values.

### Option B: Host processes via systemd

This would replace PM2 with systemd-managed Python and Node services directly on the host.

Benefits:

- Fewer containers.
- Slightly easier interactive debugging on the host.

Trade-offs:

- Still leaves Python, Node, pnpm, Prisma, and service dependencies on the host.
- Harder to keep reproducible and harder to reset cleanly.

### Option C: PM2-centered production deployment

Rejected.

The current PM2 configuration only covers the legacy Python path and does not model the full
bridge + gateway architecture. It would preserve the same class of drift and partial-boot issues
already present on `gcp-coke`.

## Target Runtime Topology

### Host-managed components

- `nginx`
- TLS certificates already present on the server
- `docker` / `docker compose`
- `systemd` unit that runs Compose from the deployment directory

### Compose-managed components

- `mongo`
- `redis`
- `postgres`
- `coke-agent`
- `coke-bridge`
- `ecloud-input`
- `ecloud-output`
- `gateway`

### Optional follow-up component

- `evolution-api`

This remains optional for the first clean redeploy because it adds a second PostgreSQL-backed
WhatsApp stack and depends on QR/bootstrap flow. The compose deployment should leave a clear slot
for it, but the first cut does not require it to validate the main stack.

## Config Strategy

The repository keeps the existing local-development `conf/config.json` untouched.

Production uses a dedicated mounted config file with container-friendly hostnames:

- Mongo host: `mongo`
- Redis host: `redis`
- Gateway API URL: `http://gateway:4041`
- Bridge bind URL / public origin: external HTTPS domain

Secrets remain on the server in an env file that is not committed.

## Ingress Strategy

The public domain remains `coke.keep4oforever.com`.

Host Nginx terminates TLS and routes by path:

- `/` -> gateway web on `127.0.0.1:4040`
- `/api/`, `/auth`, `/gateway`, `/health` -> gateway API on `127.0.0.1:4041`
- exact `/bridge` -> gateway WebSocket bridge on `127.0.0.1:4041`
- `/bridge/`, `/user/`, `/bind/` -> Coke bridge on `127.0.0.1:8090`
- `/message`, `/webhook/creem`, `/webhook/stripe` -> ecloud input on `127.0.0.1:8080`
- `/webhook/whatsapp` -> Coke agent webhook server on `127.0.0.1:8081`

This avoids the path collision between ClawScale WebSocket `/bridge` and Coke bridge
`/bridge/inbound` by splitting exact-match and prefix-match locations.

## Reset Scope On gcp-coke

The clean reset removes Coke/ClawScale deployment state but preserves the machine:

- stop PM2 if present
- stop and remove Coke/ClawScale-related containers and volumes
- remove the old `~/coke` deployment directory
- stop and disable host `redis-server` to avoid port collisions with Compose Redis
- truncate or rotate oversized application logs, especially `/var/log/mongodb`
- replace the old Nginx site config with the new path-routed config

The reset does not remove:

- Ubuntu packages
- Docker engine
- Nginx package
- TLS certificate material

## Verification

The deployment is considered healthy when all of the following succeed:

- `docker compose ps` shows healthy core services
- `curl http://127.0.0.1:4041/health`
- `curl http://127.0.0.1:8090/bridge/healthz`
- `curl -k https://coke.keep4oforever.com/` returns gateway web content
- `curl -k https://coke.keep4oforever.com/api/health` returns gateway API health
- `curl -k https://coke.keep4oforever.com/bridge/healthz` returns Coke bridge health

## Rollout Sequence

1. Add repo-side production deployment assets.
2. Sync the repo to `gcp-coke`.
3. Reset the old remote runtime state.
4. Install the new env/config files on the server.
5. Start the stack with Compose.
6. Reload Nginx and verify path routing.
