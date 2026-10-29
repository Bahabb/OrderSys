# High-Level Design (HLD) - Order Processing System

## 1. System Overview

This is an order processing distributed system that serves to store and retrieve orders. It routes its traffic through a load balancer and stores the data in a PostgreSQL database. The system is designed to handle multiple concurrent requests by distributing load across replicas and caching frequently accessed data.

## 2. Component Diagram
Client
  ↓
Nginx (Load Balancer)
  ↓           ↓
FastAPI-1   FastAPI-2 
  ↓           ↓
  Redis Cache
  ↓
PostgreSQL


## 3. Component Responsibilities

### Nginx (Load Balancer)
**Responsibility:** Route balanced amounts of traffic to multiple API server instances.

**Why it exists:** Load balancers ensure that heavy traffic is not routed to a single FastAPI server, which would slow it down or crash it, making it unavailable for users. By distributing traffic evenly, we prevent any single replica from becoming a bottleneck.

### FastAPI Services (x2 replicas)
**Responsibility:** Communication layer between the client and the backend database. Handles request validation, business logic, and response serialization.

**Why two replicas:** If one server fails, the other can serve as the primary server that receives all traffic. This way, our system continues working and avoids a single point of failure. If we only had one replica, any failure would bring down the entire system.

### Redis Cache
**Responsibility:** Store frequently accessed order data in memory to reduce latency and database load.

**Why it exists:** Querying the database for every piece of data consumes database connections and requires I/O operations. Redis can serve the same data orders of magnitude faster by keeping it in memory. The trade-off is that Redis cannot hold as much data as PostgreSQL, and cached data can become stale.

### PostgreSQL Database
**Responsibility:** Persistent, durable storage of all order records. Acts as the single source of truth for order data.

**Why it exists:** In-memory storage would lose all data upon system failure or power loss. PostgreSQL persists data to disk, ensuring data survives infrastructure failures and system restarts.

## 4. Data Flow

### For a GET /orders/{id} request:
1. Client sends a GET request to the Nginx load balancer.
2. Nginx routes the request to one of the two FastAPI instances (round-robin).
3. FastAPI receives the request and processes it.
4. FastAPI queries PostgreSQL directly for the order data.
5. PostgreSQL returns the order if it exists in the database. If not, it returns nothing.
6. FastAPI sends the order data or a 404 "Order Not Found" response back to the client.

**Note:** This current flow does NOT use Redis caching. Every request hits the database, creating the bottleneck we will identify and fix with load testing.

### For a POST /orders request:
1. Client sends a POST request with order data to the Nginx load balancer.
2. Nginx routes the request to one of the FastAPI instances.
3. The FastAPI instance receives the request and validates the order data.
4. FastAPI creates a database connection and sends an INSERT query to PostgreSQL.
5. PostgreSQL receives the query, validates constraints, and creates a new row in the Orders table.
6. PostgreSQL returns the newly created order with its auto-generated ID and timestamp.
7. FastAPI sends the complete order object back to the client with a 201 Created status.

## 5. Identified Bottlenecks

1. **Load Balancer Failure (Nginx):** If the Nginx load balancer fails, there is no mechanism to route traffic to the FastAPI instances. This is a single point of failure. (In production, this is solved with a second load balancer in HA mode or DNS-based failover.)

2. **Database Load from Repeated Reads:** GET requests bypass the Redis cache and query PostgreSQL directly on every request. When the same order is requested hundreds of times per second, PostgreSQL is forced to execute identical queries repeatedly, consuming database connections and CPU resources. This becomes the system's primary bottleneck under load.

3. **Database Load from Writes:** POST requests write directly to PostgreSQL with no buffering or batching. Under heavy write traffic, PostgreSQL must maintain many concurrent connections and handle disk I/O for every insertion, limiting throughput.

## 6. Design Decisions & Trade-Offs

| Decision | Choice | Optimizing For | Sacrificing |
|----------|--------|-----------------|-------------|
| Load balancing strategy | Round-robin | Simplicity and even distribution. Round-robin is stateless and doesn't require health monitoring or state synchronization between load balancers. | Optimal performance under variable request latency. If some requests are slow, one replica could become overloaded while the other sits idle. Solved in production with least-connections or adaptive load balancing. |
| Number of replicas | 2 | Fault tolerance with minimal resource cost. If one replica fails, the other continues serving all traffic. Two is the minimum for meaningful redundancy. | Higher availability and better load distribution (which 3+ replicas would provide). Adding a third replica increases costs without providing enough additional benefit for a baseline system. |
| Cache placement | Between FastAPI and PostgreSQL | Reducing database load by intercepting repeated queries after application logic has validated and processed the request. Caching only happens for valid, processed requests. | Caching raw responses at the network layer (e.g., between Nginx and FastAPI), which would skip application logic entirely but risks caching errors and unvalidated requests. |

## 7. Future Considerations

- **Active Cache Invalidation:** Currently, the system relies on TTL-based expiration. If orders are updated via a PUT/PATCH endpoint, stale data could be served for up to 30 seconds. Future versions should implement cache invalidation on updates.
- **High Availability for Nginx:** Add a second load balancer and failover mechanism (e.g., using keepalived or cloud provider failover).
- **Connection Pooling:** The database layer can be optimized with connection pooling to handle bursts more efficiently.
- **Query Optimization:** Indexes on frequently queried fields (e.g., order ID) can improve database performance.