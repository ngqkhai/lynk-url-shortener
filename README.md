# 🔗 Lynk — Production-Grade Distributed URL Shortener

[![CI & Docker Build](https://github.com/ngqkhai/lynk-url-shortener/actions/workflows/ci.yml/badge.svg)](https://github.com/ngqkhai/lynk-url-shortener/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Kubernetes](https://img.shields.io/badge/Kubernetes-kind-326ce5?logo=kubernetes&logoColor=white)](https://kubernetes.io/)
[![ArgoCD](https://img.shields.io/badge/GitOps-ArgoCD-orange?logo=argo&logoColor=white)](https://argo-cd.readthedocs.io/)
[![Traefik](https://img.shields.io/badge/Ingress-Traefik-24a1c1?logo=traefik&logoColor=white)](https://traefik.io/)

> **Lynk** là một hệ thống rút gọn liên kết (URL Shortener) phân tán chuẩn Production, được thiết kế theo phương pháp **"Build ➔ Deploy ➔ Measure ➔ Explain"** nhằm phục vụ mục tiêu portfolio cho các vị trí **Software Engineer / Backend / DevOps Intern**.

---

## 🏛️ Kiến trúc hệ thống tổng thể (System Architecture)

```mermaid
graph TB
    Client["Client (Browser / Postman / curl)"]

    subgraph "Edge / Ingress Layer"
        GW["Traefik API Gateway<br/>• Path Routing & Rate Limiting<br/>• X-Request-ID Injection & CORS"]
    end

    subgraph "Microservices Layer"
        URL_SVC["URL Service<br/>(TypeScript / Fastify)<br/>Port 3001"]
        RED_SVC["Redirect Service<br/>(TypeScript / Fastify)<br/>Port 3002"]
        ANA_SVC["Analytics Service<br/>(Python / FastAPI)<br/>Port 3003"]
    end

    subgraph "Data Storage Layer (Decoupled Ownership)"
        PG_URL[("PostgreSQL: lynk_urls<br/>Source-of-Truth URL Data")]
        PG_RED[("PostgreSQL: lynk_redirects<br/>Optimized Read Replica")]
        Redis[("Redis 8 Cache<br/>Low-latency Read Path")]
        PG_ANA[("PostgreSQL: lynk_analytics<br/>Raw Clicks & Daily Aggregates")]
    end

    subgraph "Event Streaming (KRaft Mode)"
        Kafka["Apache Kafka (KRaft Mode)<br/>• Topic: url.created (Data Sync)<br/>• Topic: url.clicked (Click Stream)"]
    end

    subgraph "Observability Layer"
        Otel["OpenTelemetry SDK (W3C traceparent)"]
        Jaeger["Jaeger (Distributed Traces)"]
        Prom["Prometheus (RED Metrics)"]
        Grafana["Grafana (System Dashboards)"]
    end

    Client -->|HTTP Request| GW
    GW -->|POST /api/v1/urls| URL_SVC
    GW -->|GET /:shortCode| RED_SVC
    GW -->|GET /api/v1/analytics/*| ANA_SVC

    URL_SVC -->|Write Master| PG_URL
    URL_SVC -->|Publish url.created| Kafka

    Kafka -->|Consume url.created| RED_SVC
    RED_SVC -->|Sync Local Replica| PG_RED
    RED_SVC -->|Warm Hot Cache| Redis
    RED_SVC -.->|Fallback HTTP on Cache Miss| URL_SVC
    RED_SVC -->|Publish url.clicked + Trace Headers| Kafka

    Kafka -->|Consume url.clicked| ANA_SVC
    ANA_SVC -->|Write Clicks & Stats| PG_ANA

    URL_SVC -.->|Traces & Metrics| Otel
    RED_SVC -.->|Traces & Metrics| Otel
    ANA_SVC -.->|Traces & Metrics| Otel
    Otel --> Jaeger
    Otel --> Prom
    Prom --> Grafana
```

---

## 🚀 Tính năng nổi bật & Công nghệ sử dụng

| Lĩnh vực                   | Công nghệ                                       | Mục đích sử dụng                                                          |
| :------------------------- | :---------------------------------------------- | :------------------------------------------------------------------------ |
| **Backend & Polyglot**     | TypeScript, Fastify, Python 3.12, FastAPI       | URL CRUD, High-performance redirect, Analytics processing.                |
| **Data & Caching**         | PostgreSQL 16, Redis 8, Drizzle ORM, SQLAlchemy | Lưu trữ bền vững, Hybrid caching, Schema migrations.                      |
| **Event Streaming**        | Apache Kafka (KRaft mode)                       | Xử lý click stream bất đồng bộ và đồng bộ dữ liệu giữa các services.      |
| **Edge & Ingress**         | Traefik v3                                      | Reverse proxy, Ingress Controller, Rate limiting, Request ID propagation. |
| **Observability**          | OpenTelemetry, Prometheus, Grafana, Jaeger      | RED metrics, Distributed tracing xuyên qua HTTP & Kafka headers.          |
| **Orchestration & GitOps** | Docker, Kubernetes (`kind`), Helm, ArgoCD       | Tự động hóa triển khai, declarative infrastructure, self-healing.         |
| **CI/CD**                  | GitHub Actions, GHCR (`ghcr.io`)                | Lint, Unit/Integration tests, multi-stage Docker build, image scanning.   |

---

## ⚡ Khởi động nhanh (Quickstart)

```bash
# 1. Cài đặt dependencies và kiểm tra code
make setup
make lint
make test

# 2. Deploy working tree hiện tại vào kind (PostgreSQL + Redis trong cluster)
make k8s-local-deploy

# 3. Kiểm tra readiness qua Ingress
curl -i --resolve lynk.localhost:80:127.0.0.1 http://lynk.localhost/health/ready
```

Chi tiết hướng dẫn xem tại: [Local Setup Runbook](docs/runbook/local-setup.md).

---

## 🗺️ Lộ trình phát triển 6 Sprints

- [x] **Sprint 0: Foundation & Walking Skeleton** — Monorepo, Fastify Skeleton, K8s (`kind`), Traefik, ArgoCD, Day-1 CI/CD.
- [x] **Sprint 1: Core URL Shortening Capability** — NanoID base62, PostgreSQL, Drizzle ORM, 302 redirect, TTL handling.
- [ ] **Sprint 2: High-Performance Redirect Path** — Redis cache-aside, tách `redirect-service`, k6 caching benchmark; chờ số liệu staging.
- [ ] **Sprint 3: Non-Blocking Event-Driven Analytics** — Kafka KRaft, `analytics-service` (Python), async click tracking.
- [ ] **Sprint 4: End-to-End Observability** — Prometheus RED metrics, Grafana dashboards, OpenTelemetry + Jaeger tracing.
- [ ] **Sprint 5: Production Hardening & Portfolio** — Rate limiting, Trivy security scan, backup scripts, hoàn thiện 8 ADRs.

---

## 📜 Tài liệu kỹ thuật & ADRs (Architecture Decision Records)

- [ADR-000: Walking Skeleton & Day-1 Continuous Delivery](docs/adr/000-walking-skeleton-and-ci-cd.md)
- [ADR-001: NanoID Base62 Short Code Strategy](docs/adr/001-short-code-strategy.md)
- [ADR-002: 302 Redirect Status Code](docs/adr/002-redirect-status-code.md)
- [ADR-003: Redis Cache-Aside](docs/adr/003-redis-cache-aside.md)
- [ADR-004: Redirect Service Decomposition](docs/adr/004-redirect-service-decomposition.md)
- [Experiment 01: Caching Benchmark](docs/experiments/01-caching.md)
- [Runbook: Local Development Setup](docs/runbook/local-setup.md)
- [Master Engineering Plan](docs/lynk-project-plan.md)
