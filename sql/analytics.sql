-- =============================================================================
-- SQL Reporting and Analytics Queries
-- System: Customer Support Ticket Management System
-- Dialect: PostgreSQL 14+
-- =============================================================================
-- This file provides optimized, production-ready, readable SQL queries for:
--   1. Ticket retrieval and parameterized filtering.
--   2. Aggregate ticket status counting (guaranteeing 0 counts for empty statuses).
--   3. Agent workload ranking based on unresolved tickets.
--
-- All queries use strictly parameterized placeholders (:param_name) to prevent
-- SQL injection vulnerabilities and enable query plan caching.
-- =============================================================================


-- =============================================================================
-- SECTION 1: RECOMMENDED PERFORMANCE INDEXES
-- =============================================================================
-- These indexes accelerate the analytics, filtering, and joining queries below.

-- Index for status filtering and status-count aggregation
CREATE INDEX IF NOT EXISTS ix_tickets_status 
    ON tickets (status);

-- Index for priority filtering
CREATE INDEX IF NOT EXISTS ix_tickets_priority 
    ON tickets (priority);

-- Index for customer ticket retrieval
CREATE INDEX IF NOT EXISTS ix_tickets_customer_id 
    ON tickets (customer_id);

-- Index for assigned agent joins and lookups
CREATE INDEX IF NOT EXISTS ix_tickets_assigned_agent_id 
    ON tickets (assigned_agent_id);

-- Deterministic chronological sort order index
CREATE INDEX IF NOT EXISTS ix_tickets_created_at_desc 
    ON tickets (created_at DESC, id DESC);

-- Fast lookup for user roles in agent joins
CREATE INDEX IF NOT EXISTS ix_users_role 
    ON users (role);

-- Partial composite index specifically optimizing unresolved tickets by agent
-- Highly efficient for Query 3 (Agent Workload Ranking)
CREATE INDEX IF NOT EXISTS ix_tickets_agent_unresolved 
    ON tickets (assigned_agent_id, status) 
    WHERE status IN ('open', 'in_progress');


-- =============================================================================
-- SECTION 2: QUERY 1 — RETRIEVING AND FILTERING TICKETS
-- =============================================================================
-- Purpose:
--   Retrieves a paginated list of tickets with customer and assigned agent details,
--   supporting optional filters for status, priority, customer, agent, date range,
--   and text search.
--
-- Query Characteristics:
--   - Joins: INNER JOIN with customer; LEFT JOIN with assigned agent.
--   - Parameterized filters: Pass NULL to bypass any individual filter.
--   - Deterministic Ordering: ORDER BY created_at DESC, id DESC.
--   - Pagination: LIMIT :limit OFFSET :offset.
--
-- Parameters:
--   :status             VARCHAR (e.g., 'open', 'in_progress', 'resolved', 'closed', or NULL)
--   :priority           VARCHAR (e.g., 'low', 'medium', 'high', 'urgent', or NULL)
--   :customer_id        INTEGER (User ID of the customer or NULL)
--   :assigned_agent_id  INTEGER (User ID of the assigned agent or NULL)
--   :created_after      TIMESTAMPTZ (Lower bound creation timestamp or NULL)
--   :created_before     TIMESTAMPTZ (Upper bound creation timestamp or NULL)
--   :search_term        VARCHAR (Search substring for title/description or NULL)
--   :limit              INTEGER (Page size, e.g., 20)
--   :offset             INTEGER (Page offset, e.g., 0)
-- =============================================================================

SELECT 
    t.id AS ticket_id,
    t.title,
    t.description,
    t.status,
    t.priority,
    t.created_at,
    t.updated_at,
    -- Customer details
    c.id AS customer_id,
    c.name AS customer_name,
    c.email AS customer_email,
    -- Assigned agent details (nullable)
    a.id AS agent_id,
    a.name AS agent_name,
    a.email AS agent_email
FROM tickets t
INNER JOIN users c 
    ON c.id = t.customer_id
LEFT JOIN users a 
    ON a.id = t.assigned_agent_id
WHERE 
    (CAST(:status AS VARCHAR) IS NULL OR t.status = :status)
    AND (CAST(:priority AS VARCHAR) IS NULL OR t.priority = :priority)
    AND (CAST(:customer_id AS INTEGER) IS NULL OR t.customer_id = :customer_id)
    AND (CAST(:assigned_agent_id AS INTEGER) IS NULL OR t.assigned_agent_id = :assigned_agent_id)
    AND (CAST(:created_after AS TIMESTAMPTZ) IS NULL OR t.created_at >= :created_after)
    AND (CAST(:created_before AS TIMESTAMPTZ) IS NULL OR t.created_at <= :created_before)
    AND (
        CAST(:search_term AS VARCHAR) IS NULL 
        OR t.title ILIKE '%' || :search_term || '%' 
        OR t.description ILIKE '%' || :search_term || '%'
    )
ORDER BY 
    t.created_at DESC, 
    t.id DESC
LIMIT :limit OFFSET :offset;


-- =============================================================================
-- SECTION 3: QUERY 2 — COUNTING TICKETS BY STATUS (INCLUDING ZERO COUNTS)
-- =============================================================================
-- Purpose:
--   Reports the exact count of tickets in every supported status:
--   'open', 'in_progress', 'resolved', and 'closed'.
--
-- Why standard GROUP BY is insufficient:
--   A simple "SELECT status, count(*) FROM tickets GROUP BY status" will omit
--   statuses that currently have 0 tickets, or return an empty set if the
--   tickets table is empty.
--
-- Solution:
--   Use a Common Table Expression (CTE) defining all four supported statuses,
--   and LEFT JOIN the tickets table onto it. This guarantees all 4 statuses
--   are present in the result set with count = 0 when no tickets match.
--
-- Query Characteristics:
--   - Fully deterministic: ORDER BY s.status ASC.
--   - Database-side aggregation: No raw ticket rows are returned across network.
-- =============================================================================

WITH supported_statuses AS (
    SELECT 'open'::varchar AS status
    UNION ALL SELECT 'in_progress'::varchar
    UNION ALL SELECT 'resolved'::varchar
    UNION ALL SELECT 'closed'::varchar
)
SELECT 
    s.status,
    COUNT(t.id) AS ticket_count
FROM supported_statuses s
LEFT JOIN tickets t 
    ON t.status = s.status
GROUP BY s.status
ORDER BY s.status ASC;


-- -----------------------------------------------------------------------------
-- Variant 2B: Status Counts with Parameterized Date Range Filtering
-- -----------------------------------------------------------------------------
-- Parameters:
--   :created_after   TIMESTAMPTZ (or NULL)
--   :created_before  TIMESTAMPTZ (or NULL)
-- -----------------------------------------------------------------------------

WITH supported_statuses AS (
    SELECT 'open'::varchar AS status
    UNION ALL SELECT 'in_progress'::varchar
    UNION ALL SELECT 'resolved'::varchar
    UNION ALL SELECT 'closed'::varchar
)
SELECT 
    s.status,
    COUNT(t.id) AS ticket_count
FROM supported_statuses s
LEFT JOIN tickets t 
    ON t.status = s.status
    AND (CAST(:created_after AS TIMESTAMPTZ) IS NULL OR t.created_at >= :created_after)
    AND (CAST(:created_before AS TIMESTAMPTZ) IS NULL OR t.created_at <= :created_before)
GROUP BY s.status
ORDER BY s.status ASC;


-- =============================================================================
-- SECTION 4: QUERY 3 — FINDING AGENTS WITH THE MOST UNRESOLVED TICKETS (RANKING)
-- =============================================================================
-- Purpose:
--   Ranks support agents by the number of unresolved tickets assigned to them.
--
-- Business Definition of "Unresolved":
--   Strictly tickets with status IN ('open', 'in_progress').
--   Tickets with status 'resolved' or 'closed' are excluded.
--
-- Critical SQL Architecture Decision:
--   The status constraint `t.status IN ('open', 'in_progress')` MUST be placed
--   in the `LEFT JOIN ... ON` clause, NOT in the `WHERE` clause.
--   If placed in the WHERE clause, agents with zero unresolved tickets (or whose
--   assigned tickets are all resolved/closed) would have t.status = NULL and
--   would be filtered out. Placing it in the ON clause ensures agents with 0
--   unresolved tickets are retained with COUNT(t.id) = 0.
--
-- Deterministic Ordering:
--   1. unresolved_count DESC  (Primary ranking metric)
--   2. u.name ASC             (Alphabetical tie-breaker)
--   3. u.id ASC               (Strict unique tie-breaker)
--
-- Parameters:
--   :limit   INTEGER (Maximum number of agents to return, e.g. 50, or NULL)
--   :offset  INTEGER (Offset for pagination, e.g. 0, or NULL)
-- =============================================================================

SELECT 
    u.id AS agent_id,
    u.name AS agent_name,
    u.email AS agent_email,
    COUNT(t.id) AS unresolved_count,
    -- Detailed breakdown using PostgreSQL aggregate FILTER clauses
    COUNT(t.id) FILTER (WHERE t.status = 'open') AS open_count,
    COUNT(t.id) FILTER (WHERE t.status = 'in_progress') AS in_progress_count
FROM users u
LEFT JOIN tickets t 
    ON t.assigned_agent_id = u.id 
    AND t.status IN ('open', 'in_progress')
WHERE u.role = 'agent'
GROUP BY 
    u.id, 
    u.name, 
    u.email
ORDER BY 
    unresolved_count DESC,
    u.name ASC,
    u.id ASC
LIMIT :limit OFFSET :offset;
