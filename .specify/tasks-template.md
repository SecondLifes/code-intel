# Tasks: [Feature Name]

## Legend

- `[ ]` — Pending
- `[/]` — In progress
- `[x]` — Completed

## 1. Domain Layer

- [ ] Create entity `[Name]` in `[FILL IN: pattern].Entity.[ext]`
  - [ ] Set domain properties and validations
  - [ ] Create enum/status type if necessary
  - [ ] Add doc comments

- [ ] Create interface `I[Name]Repository` in `[FILL IN: pattern].Repository.Intf.[ext]`
  - [ ] Define CRUD methods (FindById, FindAll, Insert, Update, Delete)
  - [ ] Define specific search methods

## 2. Application Layer

- [ ] Create interface `I[Name]Service` in `[FILL IN: pattern].Service.Intf.[ext]`
  - [ ] Define business methods

- [ ] Create service `[Name]Service` in `[FILL IN: pattern].Service.[ext]`
  - [ ] Constructor injection with `I[Name]Repository`
  - [ ] Implement business validations
  - [ ] Guard clauses in all methods
  - [ ] Functions/methods ≤ [FILL IN] lines

## 3. Infrastructure Layer

- [ ] Create `[Name]Repository` repository in `[FILL IN: pattern].Repository.[ext]`
  - [ ] Implement `I[Name]Repository`
  - [ ] Proper resource cleanup for any temporary connection/query objects
  - [ ] Parameterize all queries (without SQL injection)

- [ ] Update factory in `[FILL IN: pattern].Factory.[ext]`
  - [ ] Add `Create[Name]Repository`
  - [ ] Add `Create[Name]Service`

- [ ] Create SQL migration
  - [ ] Table creation script
  - [ ] Test execution against the database

## 4. Presentation Layer

- [ ] Create listing view `[Name]List` in `[FILL IN: pattern].List.[ext]`
  - [ ] List/grid for display
  - [ ] Search filters
  - [ ] Actions: New, Edit, Delete

- [ ] Create `[Name]Edit` editing view in `[FILL IN: pattern].Edit.[ext]`
  - [ ] Fields bound to the entity
  - [ ] Validation of mandatory fields
  - [ ] Actions: Save, Cancel

## 5. Tests

- [ ] Create Service unit tests
  - [ ] Creation test with valid data
  - [ ] Validation test with invalid data
  - [ ] Duplicate-handling test

- [ ] Create Repository tests (against an in-memory/test database)

## 6. Integration and Review

- [ ] Register the new feature in the application entry point/navigation
- [ ] Test full flow (CRUD)
- [ ] Code review: check SOLID and clean code
- [ ] Check documentation in public APIs
