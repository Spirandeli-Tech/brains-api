# AI Service API

A FastAPI application that runs entirely in Docker. No local Python virtual environment required.

## Prerequisites

- Docker
- Docker Compose

That's it! No Python installation or virtual environment needed.

## Quick Start

1. Create the environment file (`.env`) with the following content:
   ```bash
   POSTGRES_USER=postgres
   POSTGRES_PASSWORD=postgres
   POSTGRES_DB=spi-brains-api-db
   DATABASE_URL=postgresql://postgres:postgres@db:5432/spi-brains-api-db
   ```
   
   Or copy from example if available:
   ```bash
   cp .env.example .env
   ```

2. Start the services:
   ```bash
   make up
   ```

3. Run database migrations:
   ```bash
   make migrate
   ```

4. Open the API documentation:
   - Swagger UI: http://localhost:8000/docs
   - ReDoc: http://localhost:8000/redoc

## Why `db` as the database host?

The `DATABASE_URL` in `.env` uses `db` as the hostname (not `localhost`) because the API runs inside a Docker container. Within the Docker Compose network, services can reach each other by their service names. The PostgreSQL service is named `db`, so the API connects to it using `postgresql://postgres:postgres@db:5432/spi-brains-api-db`.

## Connecting to the Database from External Tools (DBeaver, pgAdmin, etc.)

When connecting to the database from your local machine (outside Docker), use `localhost` as the hostname, not `db`. The `db` hostname only works inside the Docker network.

**Connection details for DBeaver/pgAdmin:**
- **Host:** `localhost`
- **Port:** `5432`
- **Database:** `spi-brains-api-db` (or value from `POSTGRES_DB` in `.env`)
- **Username:** `postgres` (or value from `POSTGRES_USER` in `.env`)
- **Password:** `postgres` (or value from `POSTGRES_PASSWORD` in `.env`)

**Connection string for external tools:**
```
postgresql://postgres:postgres@localhost:5432/spi-brains-api-db
```

Note: The port `5432` is exposed to your host machine in `docker-compose.yml`, so you can connect using `localhost`.

## Troubleshooting: Database "spi-brains-api-db" does not exist

If you see the error "FATAL: database 'spi-brains-api-db' does not exist", it means the PostgreSQL container was created before the `.env` file was properly configured. To fix this:

1. **Reset the database** (recommended):
   ```bash
   make reset-db
   make migrate
   ```

2. **Or manually recreate the database container**:
   ```bash
   docker compose stop db
   docker compose rm -f db
   docker volume rm spi-brains-api_postgres_data
   make up
   make migrate
   ```

3. **Or create the database manually** (if PostgreSQL is already running):
   ```bash
   docker compose exec db psql -U postgres -c "CREATE DATABASE spi-brains-api-db;"
   ```

## Makefile Commands

- `make up` - Build and start all containers in detached mode
- `make logs` - Follow logs from all containers
- `make migrate` - Run database migrations (`alembic upgrade head`)
- `make revision msg="description"` - Create a new migration file (autogenerate)
- `make reset-db` - **WARNING**: Delete all data and reset the database
- `make down` - Stop and remove all containers

## Development Workflow

The project is configured for hot-reload development:

1. Code changes are automatically detected
2. The API container will reload when you save files
3. No need to rebuild containers for code changes

## Project Structure

```
brainsapi/
├── app/
│   ├── api/          # API routes
│   ├── core/         # Configuration and database setup
│   ├── models/       # SQLAlchemy models
│   └── main.py       # FastAPI application
├── alembic/          # Database migrations
├── docker-compose.yml
├── Dockerfile
└── Makefile
```

## Database Migrations

All database schema changes are managed through Alembic migrations:

- **Create a migration**: `make revision msg="Add new table"`
- **Apply migrations**: `make migrate`
- **Reset database**: `make reset-db` (destructive!)

The initial migration creates the `system_meta` table as a placeholder.

## Environment Variables

All configuration is managed through `.env` file. Never commit `.env` to version control. Use `.env.example` as a template.

Required variables:
- `POSTGRES_USER` - PostgreSQL username
- `POSTGRES_PASSWORD` - PostgreSQL password
- `POSTGRES_DB` - PostgreSQL database name
- `DATABASE_URL` - Full PostgreSQL connection string (must use `db` as host)
