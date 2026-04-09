# Architecture Reference

This document describes the current ClawScale-only runtime wired in this repository.

## 1. Runtime Topology

The production stack consists of:

- `agent/runner/agent_runner.py`
  - runs Coke message workers
  - runs background jobs
- `connector/clawscale_bridge/app.py`
  - handles user auth, bind flow, and Coke-specific bridge APIs
  - dispatches outbound replies to the gateway
- `gateway/`
  - serves the web UI on `4040`
  - serves the API on `4041`
- data services
  - MongoDB for Coke runtime state
  - Redis for stream wake-up / trigger events
  - Postgres for gateway state

```mermaid
flowchart LR
    subgraph Web
        UI[Gateway Web :4040]
        API[Gateway API :4041]
    end

    subgraph Coke
        BRIDGE[ClawScale Bridge :8090]
        RUNNER[agent_runner.py]
        BG[background_handler]
    end

    subgraph Storage
        MONGO[(MongoDB)]
        REDIS[(Redis)]
        PG[(Postgres)]
    end

    UI --> API
    API --> BRIDGE
    BRIDGE --> RUNNER
    BRIDGE --> API
    RUNNER --> MONGO
    RUNNER -. stream trigger .-> REDIS
    BG --> MONGO
    API --> PG
```

## 2. Inbound Path

Current inbound traffic comes through ClawScale:

```text
user channel
  -> gateway
  -> bridge /bridge/inbound
  -> MongoDB inputmessages
  -> optional Redis XADD
  -> agent workers
```

Key points:

- `connector/clawscale_bridge/app.py` validates bridge requests and converts them into Coke input documents.
- `util/redis_stream.py` is only a wake-up path; MongoDB remains the source of truth.
- `agent/runner/message_processor.py` still acquires work from `inputmessages` and conversation locks in MongoDB.

## 3. Worker Runtime

`agent/runner/agent_runner.py` now has only two responsibilities:

1. run N message workers
2. run the background handler loop

Each worker:

1. checks queue mode
2. optionally drains Redis stream triggers
3. executes the shared handler from `create_handler(worker_id)`

`agent/runner/message_processor.py` still handles:

- message acquisition
- conversation locking
- batching pending messages for the same conversation
- final status updates

## 4. Turn Processing Pipeline

The shared turn pipeline remains:

1. `PrepareWorkflow`
2. `StreamingChatWorkflow`
3. `PostAnalyzeWorkflow`

This path is invoked from `agent/runner/agent_handler.py`.

## 5. Outbound Path

Outbound replies now follow:

```text
agent outputmessages
  -> bridge output dispatcher
  -> gateway /api/outbound
  -> ClawScale-managed delivery route
```

This means the Coke repository no longer owns any direct platform connector runtime.

## 6. Deployment Topology

The checked-in production deployment matches the runtime above:

- `docker-compose.prod.yml`
- host Nginx reverse proxy
- `deploy/systemd/coke-compose.service`

The active services are:

- `mongo`
- `redis`
- `postgres`
- `coke-agent`
- `coke-bridge`
- `gateway`
