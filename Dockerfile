# Usa uma imagem oficial do Python como base.
# A versão 'slim' é mais leve, ideal para produção.
FROM python:3.10-slim

# Define variáveis de ambiente para o Python
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Define o diretório de trabalho dentro do contentor
WORKDIR /app

# Instala as dependências do sistema, se necessário (nenhuma por agora)
# RUN apt-get update && apt-get install -y ...

# Copia o ficheiro de dependências e instala-as
# Isto é feito primeiro para aproveitar o cache do Docker
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install gunicorn

# Copia o script de entrada
COPY ./entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# Copia todo o código do projeto para o diretório de trabalho
COPY . /app/

# Expõe a porta que o Gunicorn irá usar
EXPOSE 8000

# Define o script de entrada que irá preparar o ambiente e executar o comando principal
ENTRYPOINT ["/app/entrypoint.sh"]

# O comando para iniciar a aplicação será definido no docker-compose.yml
# CMD ["gunicorn", "crypto_trader.wsgi:application", "--bind", "0.0.0.0:8000"]
