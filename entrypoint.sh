#!/bin/sh

# Espera a base de dados (se for externa, como PostgreSQL) estar pronta.
# Para o SQLite, este passo não é estritamente necessário, mas é uma boa prática.

echo "A aplicar as migrações da base de dados..."
python manage.py migrate --noinput

echo "A recolher os ficheiros estáticos..."
python manage.py collectstatic --noinput --clear

# Executa o comando principal passado para o contentor
# (ex: gunicorn, celery worker, etc.)
exec "$@"
