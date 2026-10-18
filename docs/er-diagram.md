# Database Entity-Relationship (ER) Diagram

This document illustrates the data model and schema relationships for the Customer Support Ticket Management System.

```mermaid
erDiagram
    USERS ||--o{ TICKETS : "creates (customer_id)"
    USERS ||--o{ TICKETS : "assigned to (assigned_agent_id)"
    USERS ||--o{ COMMENTS : "authors (author_id)"
    USERS ||--o{ TICKET_HISTORY : "changed by (changed_by)"
    TICKETS ||--o{ COMMENTS : "contains (ticket_id)"
    TICKETS ||--o{ TICKET_HISTORY : "tracks transitions (ticket_id)"

    USERS {
        int id PK "Autoincrement"
        string name "Max 255 chars"
        string email UK "Unique, indexed"
        string password_hash "Argon2id hash"
        string role "CHECK ('customer', 'agent', 'admin')"
        timestamptz created_at "Defaults to now()"
    }

    TICKETS {
        int id PK "Autoincrement"
        int customer_id FK "users.id (CASCADE)"
        int assigned_agent_id FK "users.id (SET NULL, nullable)"
        string title "Max 255 chars"
        text description "Detailed problem text"
        string status "CHECK ('open', 'in_progress', 'resolved', 'closed')"
        string priority "CHECK ('low', 'medium', 'high', 'urgent')"
        timestamptz created_at "Defaults to now(), indexed"
        timestamptz updated_at "On update now()"
    }

    COMMENTS {
        int id PK "Autoincrement"
        int ticket_id FK "tickets.id (CASCADE)"
        int author_id FK "users.id (CASCADE)"
        text body "1 to 5,000 characters"
        timestamptz created_at "Defaults to now(), indexed"
    }

    TICKET_HISTORY {
        int id PK "Autoincrement"
        int ticket_id FK "tickets.id (CASCADE)"
        int changed_by FK "users.id (CASCADE)"
        string old_status "Previous status (nullable)"
        string new_status "CHECK ('open', 'in_progress', 'resolved', 'closed')"
        timestamptz changed_at "Defaults to now(), indexed"
    }
```

---

## Key Constraints and Indexes

1. **User Constraints**:
   - `users.email`: Unique constraint and B-Tree index.
   - `users.role`: Check constraint `role IN ('customer', 'agent', 'admin')` and B-Tree index.

2. **Ticket Constraints & Cascades**:
   - `tickets.customer_id`: Foreign key referencing `users.id` with `ON DELETE CASCADE`.
   - `tickets.assigned_agent_id`: Foreign key referencing `users.id` with `ON DELETE SET NULL`.
   - `tickets.status`: Check constraint `status IN ('open', 'in_progress', 'resolved', 'closed')` and B-Tree index.
   - `tickets.priority`: Check constraint `priority IN ('low', 'medium', 'high', 'urgent')` and B-Tree index.
   - Composite partial index: `(assigned_agent_id, status) WHERE status IN ('open', 'in_progress')` for agent workload analytics.

3. **Comment Constraints**:
   - `comments.ticket_id`: Foreign key referencing `tickets.id` with `ON DELETE CASCADE`.
   - `comments.author_id`: Foreign key referencing `users.id` with `ON DELETE CASCADE`.
   - Chronological ordering index: `created_at ASC, id ASC`.

4. **Ticket History Constraints**:
   - `ticket_history.ticket_id`: Foreign key referencing `tickets.id` with `ON DELETE CASCADE`.
   - `ticket_history.changed_by`: Foreign key referencing `users.id` with `ON DELETE CASCADE`.
   - `ticket_history.new_status`: Check constraint `new_status IN ('open', 'in_progress', 'resolved', 'closed')`.
   - Audit ordering index: `changed_at ASC, id ASC`.
