# Projeto Trader de Criptomoedas com Django e Binance API

Este é um projeto Django para criar uma plataforma de compra e venda de criptomoedas, utilizando a API da Binance para dados de mercado e transações.

## Funcionalidades Planejadas
* Autenticação de Usuários
* Dashboard com portfólio de criptomoedas e saldos
* Visualização de preços de criptomoedas em tempo real
* Gráficos de histórico de preços
* Funcionalidade de Compra e Venda de criptomoedas via API da Binance
* Histórico de Transações
* Relatórios de Análise de Performance
* Integração com Gemini para auxílio em tomadas de decisão (a ser detalhado)

## Configuração Inicial

### Pré-requisitos
* Python 3.10 ou superior
* Pip (gerenciador de pacotes Python)
* Virtualenv (recomendado)

### Passos para Configuração
1.  **Clone o repositório (ou crie os arquivos conforme fornecido):**
    Crie uma pasta para o seu projeto e coloque os arquivos dentro dela, mantendo a estrutura de pastas.

2.  **Crie e Ative um Ambiente Virtual:**
    ```bash
    python -m venv venv
    # No Windows
    venv\Scripts\activate
    # No macOS/Linux
    source venv/bin/activate
    ```

3.  **Instale as Dependências:**
    Navegue até a pasta raiz do projeto (onde `requirements.txt` e `manage.py` estão localizados) e execute:
    ```bash
    pip install -r requirements.txt
    ```

4.  **Execute as Migrações Iniciais:**
    ```bash
    python manage.py migrate
    ```

5.  **Crie um Superusuário (para acesso ao Admin):**
    ```bash
    python manage.py createsuperuser
    ```
    Siga as instruções para definir nome de usuário, email e senha.

6.  **Execute o Servidor de Desenvolvimento:**
    ```bash
    python manage.py runserver
    ```
    A aplicação estará disponível em `http://127.0.0.1:8000/`.
    A área administrativa estará disponível em `http://127.0.0.1:8000/admin/`.

## Estrutura do Projeto (Inicial)


crypto_trader_project/
├── manage.py                 # Utilitário de linha de comando do Django
├── crypto_trader/            # Pasta do projeto Django
│   ├── init.py
│   ├── asgi.py               # Configuração ASGI para servidores assíncronos
│   ├── settings.py           # Configurações do projeto
│   ├── urls.py               # URLs do projeto principal
│   └── wsgi.py               # Configuração WSGI para servidores síncronos
├── core/                     # Aplicação 'core' para funcionalidades principais
│   ├── init.py
│   ├── admin.py              # Configuração do Admin para os modelos do app
│   ├── apps.py               # Configuração do app
│   ├── migrations/           # Migrações do banco de dados
│   │   └── init.py
│   ├── models.py             # Modelos do banco de dados do app
│   ├── tests.py              # Testes para o app
│   ├── views.py              # Views (lógica de requisição/resposta) do app
│   └── urls.py               # URLs específicas do app 'core'
├── templates/                # Pasta para templates HTML
│   └── core/
│       ├── base.html         # Template base (com Tailwind CSS)
│       └── index.html        # Página inicial de exemplo
└── requirements.txt          # Dependências do projeto


## Próximos Passos
* Implementar autenticação de usuários.
* Conectar com a API da Binance.
* Definir modelos de dados para portfólio e transações.
* Criar interfaces para visualização de dados e trading.