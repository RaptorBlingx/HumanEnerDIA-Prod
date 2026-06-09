# HumanEnerDIA EnMS for Industrial Energy Management

## Short Description

HumanEnerDIA EnMS is the standalone industrial energy-management platform. It
provides the portal, analytics API, database initialization, Grafana dashboards,
MQTT/Node-RED data pipeline, simulator, authentication service, and web chatbot
without bundling the OVOS assistant runtime.

## Product Type

Digital download, free/open distribution for the WASABI release.

## Includes

- HumanEnerDIA web portal
- Analytics service and HumanEnerDIA-compatible API
- PostgreSQL + TimescaleDB initialization
- Grafana dashboards
- MQTT and Node-RED pipeline
- Authentication service
- Factory simulator
- Rasa-powered web chatbot components
- Zero-touch setup helper and release verifier
- Separate OVOS integration guide

## Does Not Include

- OVOS runtime
- OVOS skill source
- `docker-compose.ovos.yml`
- `ovos-stack/`
- optional Qwen GGUF model files

Use `HumanEnerDIA-OVOS-skill-v1.0.0` when you want the voice assistant as a
separate runtime, or `HumanEnerDIA-full-stack-v1.0.0` when you want EnMS and
OVOS bundled together.

## Installation Summary

1. Extract `HumanEnerDIA-EnMS-v1.0.0.tar.gz`
2. Run `./setup.sh`
3. Verify portal and analytics health endpoints
4. Optionally run the OVOS product separately and point it at
   `http://<enms-host>:8001/api/v1`

## License/IPR

The HumanEnerDIA EnMS package is distributed under the MIT License. Third-party
services keep their own upstream licenses.

## Production Notes

This artifact is designed as a zero-touch evaluation bundle and a guided
production starting point. Production hardening still requires buyer-specific
DNS, TLS, backup policy, secret rotation, and infrastructure review.

