# Low-Level Design (LLD) - Order Processing System

## 1. API Contract

### Endpoint: POST /orders
**Purpose:** Create a new order

**Request:**
```json
{
  "customer_name": "string (required)",
  "product": "string (required)",
  "quantity": "integer (required, > 0)"
}
```

**Response (201 Created):**
```json
{
  "id": "integer",
  "customer_name": "string",
  "product": "string",
  "quantity": "integer",
  "status": "string (default: 'pending')",
  "created_at": "ISO 8601 datetime"
}
```

**Error Responses:**
- 400 Bad Request: Missing or invalid fields (e.g., quantity <= 0, customer_name is empty)
- 500 Internal Server Error: Database connection failure or unexpected error

---

### Endpoint: GET /orders
**Purpose:** Retrieve all orders

**Request:** No body, no parameters

**Response (200 OK):**
```json
[
  {
    "id": 1,
    "customer_name": "Alice",
    "product": "Widget",
    "quantity": 3,
    "status": "pending",
    "created_at": "2024-01-15T10:30:00Z"
  },
  ...
]
```

**Notes:**
- Returns all orders, unfiltered (to be optimized with pagination later)
- Large payloads expected; not cached initially
- Empty array [] if no orders exist

**Error Responses:**
- 500 Internal Server Error: Database connection failure

---

### Endpoint: GET /orders/{id}
**Purpose:** Retrieve a single order by ID

**Path Parameter:**
- `id` (integer): The order ID

**Response (200 OK):**
```json
{
  "id": 1,
  "customer_name": "Alice",
  "product": "Widget",
  "quantity": 3,
  "status": "pending",
  "created_at": "2024-01-15T10:30:00Z"
}
```

**Caching:**
- Cached in Redis with 30-second TTL
- Cache key: `order:{id}`
- On cache miss: Query PostgreSQL, store result in Redis, return to client

**Error Responses:**
- 404 Not Found: Order with given ID does not exist
- 400 Bad Request: ID is not a valid integer
- 500 Internal Server Error: Database connection failure or cache connection failure

---

## 2. Database Schema

### Table: orders

```sql
CREATE TABLE orders (
  id SERIAL PRIMARY KEY,
  customer_name VARCHAR(255) NOT NULL,
  product VARCHAR(255) NOT NULL,
  quantity INT NOT NULL CHECK (quantity > 0),
  status VARCHAR(50) NOT NULL DEFAULT 'pending',
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**Field Definitions:**

| Field | Type | Constraints | Purpose |
|-------|------|-----------|---------|
| id | SERIAL | PRIMARY KEY, auto-increment | Unique order identifier |
| customer_name | VARCHAR(255) | NOT NULL | Name of the customer placing the order |
| product | VARCHAR(255) | NOT NULL | Name of the product ordered |
| quantity | INT | NOT NULL, CHECK > 0 | Number of units ordered; must be positive |
| status | VARCHAR(50) | NOT NULL, DEFAULT 'pending' | Order status; defaults to 'pending' on creation |
| created_at | TIMESTAMP | DEFAULT CURRENT_TIMESTAMP | Automatically set to creation time; not updatable |

**Indexes:**
- (Baseline) PRIMARY KEY index on `id` for fast lookups
- (Optimization) Future: Index on `created_at` for sorting/filtering by date

**Constraints:**
- Quantity must be > 0 (prevents invalid orders)
- customer_name, product, quantity are NOT NULL (data integrity)
- created_at is immutable (set once on creation, never updated)

---

## 3. Caching Strategy

### Cache-Aside (Lazy-Loading) Pattern

**Flow for GET /orders/{id}:**
1.FastAPI receives GET /orders/{id} request
2.Check Redis cache for key “order:{id}”
3.Cache hit? Return cached data immediately (no DB query)
4.Cache miss? Query PostgreSQL database
5.Store result in Redis with 30-second TTL
6.Return order data to client

**Cache Configuration:**

| Parameter | Value | Reasoning |
|-----------|-------|-----------|
| Key format | `order:{id}` | Simple, predictable, collision-free |
| TTL (Time-to-Live) | 30 seconds | Balances freshness and performance. Orders are read-heavy; 30 seconds of staleness is acceptable. |
| Cache backend | Redis (in-memory) | Sub-millisecond response times; reduces database load significantly |
| Invalidation | TTL expiration only | No active invalidation. If orders are updated, stale data persists for up to 30 seconds. (Future: implement cache-bust on update) |

**Endpoints Cached:**
- ✅ GET /orders/{id} → Cached
- ❌ GET /orders → Not cached (full list is too large; high churn as new orders added)
- ❌ POST /orders → Not applicable (creates new data)

**Cache Miss Scenario:**
- New order created: Not in cache (cache miss on first read)
- Order requested 10 times in 30 seconds: First request hits DB; next 9 hit Redis (90% reduction in DB load)
- After 30 seconds: Cache expires; next request hits DB again

**Data Freshness Trade-Off:**
- **What we gain:** Reduction in database connections and load; faster response times for clients
- **What we sacrifice:** Orders can be up to 30 seconds stale. If an order is updated externally (via admin panel, API, etc.), the cached version won't reflect that change immediately.
- **Acceptable because:** Order lookups are read-heavy. Status changes are infrequent relative to reads. In a payment system for example, where consistency & coherence is crucial, we'd use shorter TTL or stricter invalidation.

---

## 4. Error Handling

| Status Code | Scenario | Example |
|-------------|----------|---------|
| 201 Created | POST request succeeds | Order created and returned with auto-generated ID |
| 200 OK | GET request succeeds | Order(s) returned successfully |
| 400 Bad Request | Invalid input or malformed request | Missing required field, quantity ≤ 0, ID is not a number |
| 404 Not Found | Resource doesn't exist | GET /orders/999 when order 999 doesn't exist |
| 500 Internal Server Error | Server-side failure | Database connection lost, Redis connection lost, unexpected exception |

**Implementation Notes:**
- All errors return JSON with descriptive message: `{"error": "msg"}`
- 500 errors are logged to aid debugging
- 4xx errors are client's responsibility to fix
- Timeouts on DB/Redis queries should return 500, not hang indefinitely

---

## 5. Connection Management (Baseline)

**Database Connections:**
- FastAPI instances connect to PostgreSQL directly
- No connection pooling in baseline (each query creates a new connection)
- Return 500 to client incase of connection error

**Redis Connections:**
- FastAPI instances maintain a persistent connection to Redis
- Connection errors (Redis down) return 500 to client

**Load Balancer:**
- Nginx has no persistent connection to FastAPI (communication over HTTP)
- Each request can go to any FastAPI replica

---

## 6. Future Optimizations

### Connection Pooling
- Reuse connections across requests instead of creating new ones

### Database Indexing
- Index on `id` (PK already indexed)
- Index on `created_at` (for future sorting/filtering)
- Expected improvement: Negligible for single-row lookups (already fast), significant for list operations like GET /orders, which serves    pagination

### Active Cache Invalidation
- Publish events when orders are updated
- Cache consumers listen and invalidate immediately
- Eliminates staleness without reducing cache TTL