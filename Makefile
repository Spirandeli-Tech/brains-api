.PHONY: up logs migrate revision reset-db down

up:
	docker compose up -d --build

logs:
	docker compose logs -f

migrate:
	docker compose exec api alembic upgrade head

revision:
	@if [ -z "$(msg)" ]; then \
		echo "Error: msg parameter is required. Usage: make revision msg='your message'"; \
		exit 1; \
	fi
	docker compose exec api alembic revision --autogenerate -m "$(msg)"

reset-db:
	@echo "WARNING: This will delete all database data!"
	@echo "Press Ctrl+C to cancel, or Enter to continue..."
	@read dummy; \
	docker compose down -v; \
	docker compose up -d --build; \
	echo "Database reset complete. Run 'make migrate' to apply migrations."

down:
	docker compose down

check-db:
	docker compose exec db psql -U postgres -c "\l"

check-port:
	@echo "Verificando qual processo está usando a porta 5432..."
	@lsof -i :5432 || echo "Porta 5432 não está em uso (ou lsof não está instalado)"
	@echo ""
	@echo "Verificando se o container está escutando na porta..."
	@docker compose ps db
