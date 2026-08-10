# Technical Plan: [Feature Name]

## Overview

<!-- Summary of how the feature will be technically implemented -->

## Architecture

### Layer Diagram

```
Presentation (UI layer)
    │
    ▼
Application (Service)
    │
    ▼
Domain (Entity + Interface)
    ▲
    │
Infrastructure (Repository)
```

### Operation Sequence

```
[UI] → calls → [Service.Create()] → validates → [Repository.Insert()] → [DB]
```

## Components to Create

### Domain Layer

| File | Type | Description |
|---------|------|-----------|
| `[FILL IN: pattern].Entity.[ext]` | Entity | Class with domain properties and validations |
| `[FILL IN: pattern].Repository.Intf.[ext]` | Interface | Data access contract |

### Application Layer

| File | Type | Description |
|---------|------|-----------|
| `[FILL IN: pattern].Service.Intf.[ext]` | Interface | Service contract |
| `[FILL IN: pattern].Service.[ext]` | Service | Business logic with constructor injection |

### Infrastructure Layer

| File | Type | Description |
|---------|------|-----------|
| `[FILL IN: pattern].Repository.[ext]` | Repository | Concrete implementation of the repository |
| `[FILL IN: pattern].Factory.[ext]` | Factory | Factory method to create service and repository |

### Presentation Layer

| File | Type | Description |
|---------|------|-----------|
| `[FILL IN: pattern].List.[ext]` | View | Listing/search screen |
| `[FILL IN: pattern].Edit.[ext]` | View | Creation/editing screen |

## Dependencies between Components

```
[Edit View] → IService → IRepository → [DB connection]
```

## Database Migration

```sql
-- Migration: YYYY-MM-DD_create_[table]
CREATE TABLE IF NOT EXISTS [table] (
  id INTEGER PRIMARY KEY,
  -- fields
  created_at TIMESTAMP,
  updated_at TIMESTAMP
);
```

## Risks and Considerations

- [Risk 1 and how to mitigate]
- [Risk 2 and how to mitigate]

## Compliance Checklist

- [ ] Follow SOLID (SRP, OCP, LSP, ISP, DIP)
- [ ] Clean code (short functions, descriptive names)
- [ ] This project's naming conventions
- [ ] [FILL IN: doc-comment format] in public APIs
- [ ] [FILL IN: this stack's resource-management rule]
- [ ] Guard clauses instead of nesting
- [ ] No globals, no generic/broad catch
