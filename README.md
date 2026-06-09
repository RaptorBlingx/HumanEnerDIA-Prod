# HumanEnerDIA EnMS

This package runs the HumanEnerDIA energy-management platform without an
embedded OVOS runtime.

Use this product when you want the EnMS backend, portal, analytics API,
Grafana dashboards, MQTT/Node-RED pipeline, simulator, authentication service,
and web chatbot, and you want to run the OVOS assistant as a separate product.

## Product Split

- `HumanEnerDIA-EnMS-v1.0.0`: EnMS platform only.
- `HumanEnerDIA-OVOS-skill-v1.0.0`: OVOS runtime and HumanEnerDIA skill only.
- `HumanEnerDIA-full-stack-v1.0.0`: EnMS plus embedded OVOS in one bundle.

## Quick Start

```bash
tar -xzf HumanEnerDIA-EnMS-v1.0.0.tar.gz
cd HumanEnerDIA-EnMS-v1.0.0
./setup.sh
./verify-release.sh
```

For browser access from another machine:

```bash
./setup.sh --server-ip <enms-hostname-or-ip>
```

Open:

- Portal: `http://<enms-host>:8080`
- Grafana: `http://<enms-host>:8080/grafana`
- Analytics API health: `http://<enms-host>:8001/api/v1/health`

## Pair With The OVOS Product

Start EnMS first, then run the OVOS package with this EnMS API URL:

```bash
./setup.sh --enms-api-url http://<enms-host>:8001/api/v1
```

If both products run on the same laptop, run the OVOS package with:

```bash
./setup.sh --enms-api-url http://host.docker.internal:8001/api/v1
```

To let the EnMS portal call a separately running OVOS bridge on the same host,
start or re-run this EnMS setup with:

```bash
./setup.sh --ovos-bridge-host host.docker.internal --ovos-bridge-port 5000
```

For a remote OVOS host:

```bash
./setup.sh --ovos-bridge-host <ovos-hostname-or-ip> --ovos-bridge-port 5000
```

Read `OVOS_INTEGRATION.md` for the full two-package wiring guide.

## What Is Not Included

This artifact does not include:

- `ovos-stack/`
- `docker-compose.ovos.yml`
- OVOS runtime containers
- OVOS skill source
- optional GGUF model files
- live `.env` files, Docker volumes, logs, caches, tests, or internal delivery docs

## License

HumanEnerDIA EnMS is distributed under the MIT License. See `LICENSE`.

