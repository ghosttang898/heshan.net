# heshan.net (同鹤汇)

heshan.net is a simple monorepo for a full-stack web application.

## Structure

- `backend`: Spring Boot backend using Maven and Java 17
- `frontend`: React frontend using Vite
- `docs`: project documentation

## Features

- Spring Boot backend with REST APIs
- React frontend with Vite and React Router
- JWT-based user authentication
- Post system for chat and finding old friends
- Comment system
- Admin v0.1: dashboard, paginated user/content search, hide/restore/soft-delete moderation
- Publication-time IP location for posts/comments (local City MMDB; no raw-IP persistence)

## Backend

Main backend APIs include:

- `GET /api/health`
- `GET /api/posts`
- `POST /api/posts`
- `GET /api/posts/{id}`
- `GET /api/posts/{id}/comments`
- `POST /api/posts/{id}/comments`
- `POST /api/auth/register`
- `POST /api/auth/login`
- `GET /api/auth/me` (authenticated current user and role)
- `/api/admin/**` (ADMIN / SUPER_ADMIN daily management; SUPER_ADMIN-only role assignment)

See [Admin API and development account guide](docs/ADMIN.md) for endpoints, filters, schema changes,
and administrator setup. Anonymous comments remain supported. Public APIs only return published content.
See [Administrator roles and founder initialization](docs/ADMIN_ROLES.md) for the three-role policy,
auditing and the explicitly confirmed offline founder command. No founder is promoted automatically.
See [IP location setup and privacy guide](docs/IP_LOCATION.md) for database configuration,
trusted proxies, new response fields, licensing and tests. Unconfigured/local requests show unknown.

## Frontend

The frontend includes:

- `/`: homepage
- `/chat`: chat posts
- `/find`: find old friends posts with filters
- `/login`: login page
- `/register`: register page
- `/privacy`: IP location collection and public-display notice
- `/posts/:id`: post detail page
- `/admin`: administrator dashboard
- `/admin/posts`, `/admin/comments`, `/admin/users`: management pages
- `/admin/administrators`: SUPER_ADMIN-only administrator management

## Local Run

### Backend

```bash
cd backend
mvn spring-boot:run
```

Backend default URL:

```text
http://localhost:8080
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend default URL:

```text
http://localhost:5173
```

## Move To MacBook

Recommended flow:

1. Put this project into Git
2. Push to GitHub or GitLab
3. Clone it on the MacBook
4. Reinstall dependencies on the MacBook

See:

- `docs/MACBOOK_SETUP.md`

## Notes

- Keep the project simple
- No OAuth
- Authentication uses JWT
- H2 is currently in-memory, so data does not persist after restart
- New registrations always have USER role. SUPER_ADMIN can grant/revoke ADMIN; founder setup is server-only.
- H2 Console is disabled by default. See `docs/ADMIN.md` for local administrator setup and JWT configuration.
