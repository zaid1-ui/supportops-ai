# TODO: Add role-differentiated routes (Admin vs Lead)

## Steps

- [ ] 1. Add `UserCreate` / `UserUpdate` schemas to `backend/app/schemas/api.py`
- [ ] 2. Create `backend/app/api/users.py` — Admin-only user management (GET/POST/PATCH/DELETE)
- [ ] 3. Create `backend/app/api/reports.py` — Lead-only reports (GET list, POST publish)
- [x] 4. Edit `backend/app/api/documents.py` — gate `DELETE /documents/{doc_id}` to Admin
- [x] 5. Edit `backend/app/api/__init__.py` — register `users` and `reports` routers
- [x] 6. Edit `backend/app/api/deps.py` — add `AdminUser` / `LeadUser` convenience aliases
