# HumanEnerDIA EnMS Installation

This guide is for the EnMS-only product. It runs HumanEnerDIA without bundling
the OVOS assistant runtime.

## Requirements

- Linux server or workstation
- Docker Engine 20.10+ and Docker Compose v2
- 8 GB RAM recommended
- 15 GB free disk space recommended
- Network access for pulling Docker images during first startup

No manual secret editing is required for a local evaluation install. The setup
helper creates `.env`, generates first-run secrets, validates Docker Compose,
builds the images, and starts the EnMS stack.

## Bundle Layout

After extraction, the bundle root contains:

- `docker-compose.yml` for the EnMS services
- `setup.sh`
- `verify-release.sh`
- `README.md`, `INSTALL.md`, `PRODUCT.md`, and `OVOS_INTEGRATION.md`
- `.env.example`

There is intentionally no `docker-compose.ovos.yml` and no `ovos-stack/`
directory in this product.

## Zero-Touch Deployment

```bash
tar -xzf HumanEnerDIA-EnMS-v1.0.0.tar.gz
cd HumanEnerDIA-EnMS-v1.0.0
./setup.sh
```

For access from another machine:

```bash
./setup.sh --server-ip <enms-hostname-or-ip>
```

For an EnMS that should call a separate OVOS bridge on the same host:

```bash
./setup.sh \
  --server-ip <enms-hostname-or-ip> \
  --ovos-bridge-host host.docker.internal \
  --ovos-bridge-port 5000
```

For an EnMS that should call a remote OVOS host:

```bash
./setup.sh \
  --server-ip <enms-hostname-or-ip> \
  --ovos-bridge-host <ovos-hostname-or-ip> \
  --ovos-bridge-port 5000
```

Generated first-run credentials are stored in `.env`. Keep that file private.

## Verification

```bash
./verify-release.sh
```

Manual checks:

```bash
curl -fsS http://localhost:8080/health
curl -fsS http://localhost:8001/api/v1/health
```

Expected result:

- the Nginx health endpoint returns `healthy`
- analytics returns JSON with `"status":"healthy"`
- OVOS checks are skipped unless a separate OVOS bridge is reachable

## Pair With The OVOS Skill Product

On the OVOS package machine, point OVOS at this EnMS analytics API:

```bash
./setup.sh --enms-api-url http://<enms-host>:8001/api/v1
```

If both packages run on the same laptop:

```bash
./setup.sh --enms-api-url http://host.docker.internal:8001/api/v1
```

Then verify the OVOS package:

```bash
curl -fsS http://localhost:5000/health
curl -sS -X POST http://localhost:5000/query \
  -H 'Content-Type: application/json' \
  -d '{"text":"what is the power of compressor one","session_id":"enms-ovos-smoke"}'
```

## Clean Reinstall

From the extracted EnMS bundle:

```bash
docker compose down -v --remove-orphans || true
docker rm -f enms-nginx enms-postgres enms-mqtt enms-redis enms-simulator enms-nodered enms-grafana enms-analytics enms-auth-service enms-rasa-actions enms-rasa enms-chatbot 2>/dev/null || true
docker volume rm enms-postgres-data enms-grafana-data enms-mqtt-data enms-mqtt-logs enms-redis-data enms-nodered-data postgres-data grafana-data mqtt-data mqtt-logs redis-data nodered-data 2>/dev/null || true
docker network rm enms-network 2>/dev/null || true
docker builder prune -af
```

For a dedicated test laptop where all unused Docker state can be removed:

```bash
docker compose down -v --remove-orphans || true
docker system prune -af --volumes
docker builder prune -af
```

`docker system prune -af --volumes` is global Docker cleanup. Do not run it on
a host that has other Docker projects or volumes you need to keep.

## Production Notes

- Rotate generated `.env` secrets before production exposure.
- Set DNS and TLS-specific URLs.
- Review exposed ports, firewall rules, backup policy, and host monitoring.
- Configure backups for PostgreSQL/TimescaleDB and Grafana volumes.

