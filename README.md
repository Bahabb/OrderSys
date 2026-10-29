# Order Processing Distributed System

A production-like distributed order-processing system demonstrating bottleneck identification, caching optimization, and performance tuning under load.

## Problem Statement

Most developers understand that caching improves performance. Few have actually instrumented a system from scratch, identified *where* the bottleneck lives, and measured the impact of a fix with real data.

This project shows the full workflow:

1. **Design** a distributed system with documented trade-offs
2. **Build** a multi-container deployment that mimics production constraints
3. **Load test** to identify the real bottleneck (not the assumed one)
4. **Optimize** based on data, not intuition
5. **Measure** the improvement with before/after metrics

## What This Demonstrates

### System Design Thinking
- High-Level Design (HLD) and Low-Level Design (LLD) documentation before implementation
- Component responsibilities and architectural trade-offs
- Fault tolerance reasoning (replicas, load balancing, persistence)
- Identification of single points of failure and mitigation strategies

### Load Testing & Bottleneck Analysis
- Writing realistic k6 load tests that simulate user behavior
- Using metrics to identify which layer fails first (database, cache, load balancer)
- Understanding the difference between assumed and actual bottlenecks
- Measuring performance impact with statistical rigor (p95 latency, throughput, error rates)

### Caching Strategy & Trade-Offs
- Implementing cache-aside (lazy-loading) pattern
- TTL-based expiration vs. active invalidation
- Understanding staleness trade-offs for read-heavy vs. real-time systems
- Connection pooling and query optimization as secondary fixes

### Production Architecture Concepts
- Load balancing with round-robin distribution
- Horizontal scaling (replicas) vs. vertical scaling
- Persistence and failure recovery
- Resource constraints and bottleneck propagation

## Architecture

```
Client
  ↓
Nginx (Load Balancer - Round-robin across replicas)
  ↓           ↓
FastAPI-1   FastAPI-2 (Identical replicas for fault tolerance)
  ↓           ↓
  Redis Cache (In-memory store for hot data)
  ↓
PostgreSQL (Persistent source of truth)
```

**Components:**
- **Nginx:** Distributes traffic evenly across FastAPI replicas using round-robin
- **FastAPI Replicas (x2):** Application layer handling business logic, validation, and orchestration
- **Redis:** In-memory cache for frequently accessed orders (30-second TTL)
- **PostgreSQL:** Persistent relational database for all order records

## Key Design Decisions

| Decision | Choice | Reasoning |
|----------|--------|-----------|

| **Load balancing** | *Round-robin* | **WHY?** Stateless, predictable distribution. Replicas are identical, so even distribution is optimal.
| **Number of replicas** | *2* | **WHY?** Minimum for meaningful fault tolerance. If one fails, the other serves 100% of traffic. |
| **Cache placement** | *Between FastAPI and database* | **WHY?** Intercepts repeated queries after validation. Avoids caching errors or malformed requests. |
| **Cache invalidation** | *TTL-based (30 seconds)* | **WHY?** Simplicity over strict consistency. Acceptable for read-heavy order lookups; payment/inventory would require stricter guarantees. |
| **Data persistence** | *PostgreSQL* | **WHY?** Durability across restarts. Relational schema enforces data integrity. |

## Performance Results
