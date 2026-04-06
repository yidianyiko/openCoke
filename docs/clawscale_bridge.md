## Environment

- `COKE_BRIDGE_API_KEY`
- `COKE_BIND_BASE_URL`
- `CLAWSCALE_OUTBOUND_API_URL`
- `CLAWSCALE_OUTBOUND_API_KEY`

## Start Coke bridge

Run `python -m connector.clawscale_bridge.app`

## Start proactive dispatcher

Run `python -m connector.clawscale_bridge.output_dispatcher`

## Start Coke workers in poll mode

Run `QUEUE_MODE=poll bash agent/runner/agent_start.sh`

## ClawScale custom backend config

- `baseUrl`: `http://<bridge-host>:8090/bridge/inbound`
- `authHeader`: `Bearer <COKE_BRIDGE_API_KEY>`
- `transport`: `http`
- `responseFormat`: `json-auto`
