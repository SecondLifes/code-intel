---
name: qdrant-monitoring
description: "Guides Qdrant monitoring and observability setup. Use when someone asks 'how to monitor Qdrant', 'what metrics to track', 'is Qdrant healthy', 'optimizer stuck', 'why is memory growing', 'requests are slow', or needs to set up Prometheus, Grafana, or health checks. Also use when debugging production issues that require metric analysis."
allowed-tools:
  - Read
  - Grep
  - Glob
---

# Qdrant Monitoring

## Usage

| You say | What happens |
|---|---|
| "Is Qdrant healthy?" / "why is search slow?" / "GPU/memory looks off" | Check `/api/health`'s `gpu` field first (this repo's own indicator for the `onnxruntime-gpu` pin working correctly) before general Qdrant metric analysis — a CodeIntel-specific symptom often traces back to the dependency-pin trap documented in `AGENTS.md`, not a Qdrant server issue. |
| "Set up Prometheus/Grafana for Qdrant" | Follow this skill's monitoring docs directly — no CodeIntel-specific override. |
| Ambiguous/no specific monitoring question | Determine first: setting up new monitoring, or diagnosing an active issue — the two paths differ. |

Qdrant monitoring allows tracking performance and health of your deployment, and identifying issues before they become outages. First determine whether you need to set up monitoring or diagnose an active issue.

- Understand available metrics [Monitoring docs](https://skills.qdrant.tech/md/documentation/ops-monitoring/monitoring/)


## Monitoring Setup

Prometheus scraping, health probes, Hybrid Cloud specifics, alerting, and log centralization. [Monitoring Setup](setup/SKILL.md)


## Debugging with Metrics

Optimizer stuck, memory growth, slow requests. Using metrics to diagnose active production issues. [Debugging with Metrics](debugging/SKILL.md)
