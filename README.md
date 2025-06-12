Crypto Trader Pro com Agente de IA (Gemini)
🚀 Sobre o Projeto
O Crypto Trader Pro é uma plataforma avançada de trading de criptomoedas, desenvolvida em Django, que transforma a gestão de ativos digitais através da automação inteligente. A aplicação integra-se diretamente com a API da Binance para dados de mercado e execução de ordens, e utiliza o poder da API Google Gemini como um cérebro estratégico para:

Análise de indicadores técnicos.

Análise de sentimento de mercado com base em notícias reais.

Geração de sinais de trading (Compra/Venda/Manter).

Ciclo de aprendizagem adaptativo, onde o agente aprende com a sua própria performance.

✨ Funcionalidades Principais
Dashboard Analítico: Visualize o seu portfólio, a distribuição de ativos e o histórico de valor com gráficos interativos.

Agente de IA Adaptativo: Um agente autónomo que opera 24/7, aprende com os seus resultados e permite que o utilizador aplique as suas sugestões de melhoria.

Gestor de Estratégia: Interface para gerir e aplicar os aprendizados da IA, personalizando o comportamento do agente.

Trading Manual e via API: Execute ordens a mercado ou a limite diretamente pela interface.

Segurança: As chaves de API são armazenadas com criptografia forte, garantindo a segurança dos seus dados.

Backtesting de Estratégias: Simule a performance da estratégia da IA contra dados históricos para validar a sua eficácia.

📸 Demonstração (Screenshots)
Dashboard Principal

Dashboard do Agente de IA

Gestor de Estratégia

Relatório de Performance do Agente

Backtesting

Histórico de Transações

🛠️ Tecnologias Utilizadas
O projeto foi construído com as seguintes tecnologias:

Backend: Django, Django REST Framework, Celery

Frontend: Templates Django, Tailwind CSS, Alpine.js, Chart.js

Base de Dados: SQLite 3 (Desenvolvimento), PostgreSQL (Produção)

Cache e Mensageria: Redis

APIs Externas: Google Gemini, Binance, NewsAPI

Conteinerização: Docker, Docker Compose

⚙️ Configuração e Execução
Siga os passos abaixo para configurar e executar o projeto no seu ambiente local.

Pré-requisitos
Python 3.10+

Docker e Docker Compose

Git

1. Clonar o Repositório
git clone <URL_DO_SEU_REPOSITORIO>
cd <NOME_DO_PROJETO>

2. Configurar Variáveis de Ambiente
Copie o ficheiro .env.example para .env:

cp .env.example .env

Edite o ficheiro .env e preencha todas as variáveis necessárias, incluindo as suas chaves de API para Binance, Google Gemini e NewsAPI.

3. Executar com Docker Compose
Este é o método recomendado para o ambiente de desenvolvimento, pois gere todos os serviços (web, workers, redis) automaticamente.

Construir e iniciar os contentores:

docker-compose up --build -d

Executar as migrações da base de dados (apenas na primeira vez):

docker-compose exec web python manage.py migrate

Criar um superutilizador (opcional):

docker-compose exec web python manage.py createsuperuser

A aplicação estará disponível em http://127.0.0.1:8000.

4. Execução Local (Sem Docker)
Instale as dependências:

pip install -r requirements.txt

Execute as migrações e crie um superutilizador:

python manage.py migrate
python manage.py createsuperuser

Inicie os serviços (em terminais separados):

# Terminal 1: Servidor Redis
redis-server

# Terminal 2: Servidor Django
python manage.py runserver

# Terminal 3: Celery Worker
celery -A crypto_trader worker -l info

# Terminal 4: Celery Beat (Agendador)
celery -A crypto_trader beat -l info --scheduler django_celery_beat.schedulers:DatabaseScheduler
