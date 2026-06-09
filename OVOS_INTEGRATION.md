# Running EnMS And OVOS As Separate Products

This guide explains the supported two-product deployment:

```text
HumanEnerDIA-EnMS-v1.0.0
        ^
        | analytics API
        |
HumanEnerDIA-OVOS-skill-v1.0.0
```

The OVOS product answers energy questions by calling the EnMS analytics API.
The EnMS product can optionally call the OVOS REST bridge when a portal voice
query is sent through the EnMS frontend.

## Ports

Default EnMS ports:

- Portal and Nginx gateway: `8080`
- Analytics API: `8001`
- Grafana direct: `3001`
- Node-RED direct: `1881`
- Auth service direct: `5500`

Default OVOS ports:

- OVOS REST bridge: `5000`
- OVOS messagebus: `8181`

For a normal public deployment, expose the EnMS gateway and analytics API as
needed. Keep database, Redis, MQTT, and internal service ports firewalled.

## Same Laptop

Start EnMS:

```bash
cd HumanEnerDIA-EnMS-v1.0.0
./setup.sh \
  --server-ip localhost \
  --ovos-bridge-host host.docker.internal \
  --ovos-bridge-port 5000
```

Start OVOS:

```bash
cd HumanEnerDIA-OVOS-skill-v1.0.0
./setup.sh --enms-api-url http://host.docker.internal:8001/api/v1
```

Verify:

```bash
curl -fsS http://localhost:8001/api/v1/health
curl -fsS http://localhost:5000/health
curl -sS -X POST http://localhost:5000/query \
  -H 'Content-Type: application/json' \
  -d '{"text":"what is the power of compressor one","session_id":"same-host-smoke"}'
```

## Separate Machines

Start EnMS:

```bash
cd HumanEnerDIA-EnMS-v1.0.0
./setup.sh \
  --server-ip <enms-host> \
  --ovos-bridge-host <ovos-host> \
  --ovos-bridge-port 5000
```

Start OVOS:

```bash
cd HumanEnerDIA-OVOS-skill-v1.0.0
./setup.sh --enms-api-url http://<enms-host>:8001/api/v1
```

Firewall requirements:

- OVOS host must reach `http://<enms-host>:8001/api/v1`
- EnMS host must reach `http://<ovos-host>:5000` only if portal voice proxy is used

## Same Docker Network

Advanced users can attach both products to the same Docker network.

Start EnMS using the default network:

```bash
cd HumanEnerDIA-EnMS-v1.0.0
./setup.sh --server-ip <enms-host>
```

Start OVOS on that network:

```bash
cd HumanEnerDIA-OVOS-skill-v1.0.0
./setup.sh \
  --enms-api-url http://enms-analytics:8001/api/v1 \
  --network enms-network
```

If the EnMS portal should call OVOS over the Docker network, set
`OVOS_BRIDGE_HOST` in the EnMS `.env` to the OVOS service/container name and
restart analytics/chatbot:

```bash
sed -i 's|^OVOS_BRIDGE_HOST=.*|OVOS_BRIDGE_HOST=ovos|' .env
docker compose up -d analytics chatbot
```

## Troubleshooting

Check EnMS API from the OVOS host:

```bash
curl -fsS http://<enms-host>:8001/api/v1/health
curl -fsS http://<enms-host>:8001/api/v1/machines
```

Check OVOS bridge from the EnMS host:

```bash
curl -fsS http://<ovos-host>:5000/health
```

If the OVOS query works from the OVOS host but the EnMS portal voice proxy
fails, update `OVOS_BRIDGE_HOST` and `OVOS_BRIDGE_PORT` in the EnMS `.env`,
then restart:

```bash
docker compose up -d analytics chatbot
```

