# Crypto Trader Pro com Agente de IA (Gemini)

Este é um projeto Django que cria uma plataforma avançada de gerenciamento e negociação de criptomoedas, utilizando a API da Binance para dados de mercado e transações, e o poder do Google Gemini para análise estratégica e geração de sinais de trading.

## Funcionalidades

* **Autenticação Completa de Usuários:** Registro, login, logout e gerenciamento de perfil.
* **Conectividade Segura com a Binance:** Armazenamento seguro de chaves API com criptografia forte e seleção de ambiente (Testnet/Mainnet).
* **Dashboard Analítico:**
    * Visualização do valor total do portfólio em tempo real.
    * Gráficos interativos com a distribuição de ativos e histórico de valor.
    * Tabela de posses com cálculo de Lucro/Prejuízo.
* **Negociação Manual Completa:**
    * Execução de ordens de **Compra e Venda a Mercado**.
    * Criação de ordens de **Compra e Venda a Limite**.
    * Visualização e cancelamento de ordens abertas.
* **Recursos Inteligentes (Gemini API):**
    * **"Explique este Ativo"**: Análise de criptomoedas sob demanda nas páginas de detalhe.
    * **Análise de Sentimento de Mercado**: Tarefas em segundo plano que analisam notícias e geram scores de sentimento.

## Próximo Grande Passo: Agente de Trading Autônomo

A fase atual de desenvolvimento está focada em construir um **agente de trading semi ou totalmente autônomo**, transformando a plataforma em uma ferramenta de nível profissional.

1.  **Módulo de Análise de Dados**: Implementar tarefas assíncronas (Celery) para calcular e salvar continuamente indicadores de **análise técnica** (RSI, MACD, Bandas de Bollinger) e **sentimento de mercado** (via Gemini).

2.  **Cérebro de Decisão (Gemini Core)**: Desenvolver um ciclo de decisão onde os dados coletados são enviados ao Gemini para obter um **sinal de trade completo** (Comprar/Vender/Manter, score de confiança, sugestões de stop-loss/take-profit e justificativa).

3.  **Interface de Controle do Agente**: Criar uma nova seção no app onde o usuário poderá **ativar/desativar** o agente, configurar seu perfil de risco e visualizar o histórico de decisões tomadas pela IA.

4.  **Execução Automatizada**: Conectar os sinais de alta confiança do agente diretamente com a API da Binance para a execução de ordens.

## Configuração do Ambiente

### Pré-requisitos
* Python 3.10+
* Pip e Virtualenv
* Redis
* **Bibliotecas Adicionais:** `pandas-ta`

### Passos para Configuração
1.  **Clone o repositório.**

2.  **Crie e ative um ambiente virtual.**

3.  **Instale as dependências:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Configure as variáveis de ambiente:**
    * Copie o arquivo `.env.example` para `.env`.
    * Preencha as variáveis, incluindo `DJANGO_SECRET_KEY`, `FIELD_ENCRYPTION_KEY`, suas chaves da **API da Binance** e sua chave da **API do Gemini** (`GEMINI_API_KEY`).

5.  **Execute as migrações e crie um superusuário.**
    ```bash
    python manage.py migrate
    python manage.py createsuperuser
    ```

6.  **Inicie os serviços (em terminais separados):**
    * **Servidor Django:** `python manage.py runserver`
    * **Celery Worker:** `celery -A crypto_trader worker -l info`
    * **Celery Beat (Agendador):** `celery -A crypto_trader beat -l info`

A aplicação estará disponível em `http://127.0.0.1:8000/`.

