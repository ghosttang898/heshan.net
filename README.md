# TongHeHui (同鹤汇)

TongHeHui is a simple monorepo for a full-stack web application.

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

## Frontend

The frontend includes:

- `/`: homepage
- `/chat`: chat posts
- `/find`: find old friends posts with filters
- `/login`: login page
- `/register`: register page
- `/posts/:id`: post detail page

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
