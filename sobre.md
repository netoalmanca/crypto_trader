### **Visão Geral do Projeto: Crypto Trader Pro**

O Crypto Trader Pro é uma plataforma de software completa, desenvolvida em Django, que evoluiu de um painel de controle manual para um sofisticado sistema de trading de criptomoedas assistido por Inteligência Artificial. A aplicação integra-se com a API da Binance para execução de ordens e recolha de dados de mercado, e utiliza a API do Google Gemini como o cérebro estratégico para análise, geração de sinais e, mais importante, otimização e aprendizagem adaptativa. O objetivo é fornecer uma ferramenta robusta que oferece controle sobre o portfólio e uma vantagem competitiva através de um ciclo de automação e aprendizagem.

---

### **Arquitetura e Tecnologias**

A plataforma foi construída sobre uma base de tecnologias modernas e escaláveis para garantir performance e segurança.

* **Backend**: Python 3.10+ e Django.
* **Servidor de Aplicação**: Gunicorn (para produção).
* **Frontend**: Templates Django com Tailwind CSS para estilização, Alpine.js para interatividade e Chart.js para a renderização de gráficos.
* **Base de Dados**: SQLite 3 para desenvolvimento e PostgreSQL para produção.
* **Tarefas Assíncronas**: O Celery é utilizado como orquestrador de tarefas em segundo plano (como a recolha de dados e os ciclos do agente de IA), com o Redis servindo como *message broker*.
* **APIs Externas**:
    * **Exchange**: API da Binance (com suporte para Mainnet e Testnet).
    * **Inteligência Artificial**: Google Gemini.
    * **Notícias**: NewsAPI (para análise de sentimento de mercado).
* **Segurança**: As chaves de API dos utilizadores são armazenadas de forma segura através de criptografia com o algoritmo Fernet, utilizando uma chave derivada por PBKDF2HMAC para proteger os dados sensíveis.

---

### **Funcionalidades da Aplicação Principal (App `core`)**

A aplicação `core` é responsável pela gestão do utilizador, portfólio e interações manuais com o mercado.

* **Gestão de Conta e Perfil**:
    * Sistema completo de autenticação com registo e login de utilizadores (`register.html`, `login.html`).
    * Um `UserProfile` é criado automaticamente para cada novo utilizador através de sinais do Django (`core/signals.py`).
    * Na página de configurações, o utilizador pode guardar as suas chaves de API da Binance (que são criptografadas), definir a sua moeda fiat preferida, e alternar entre os ambientes de Testnet e Mainnet.

* **Dashboard e Gestão de Portfólio**:
    * O dashboard principal (`dashboard.html`) oferece uma visão consolidada do valor total do portfólio, um gráfico de distribuição de ativos (pizza) e um gráfico com o histórico de valor do portfólio (linha).
    * O histórico do portfólio é construído a partir de `PortfolioSnapshot`, que guarda o valor total da carteira diariamente.
    * A plataforma inclui uma função robusta (`recalculate_holdings`) que apaga e reconstrói as posses (`Holdings`) a partir do histórico de transações (`Transactions`), garantindo a consistência dos dados.

* **Trading Manual e Sincronização**:
    * O utilizador pode executar ordens de **Compra e Venda**, tanto **a Mercado** quanto a **Limite**, diretamente pela interface. Os formulários são desenhados para ajustar a quantidade e o preço aos requisitos da Binance (`LOT_SIZE`, `TICK_SIZE`).
    * É possível visualizar e cancelar ordens abertas em tempo real (`open_orders.html`).
    * A funcionalidade "Sincronizar com Binance" (`sync_binance_trades_view`) permite importar o histórico de transações da exchange para a base de dados local, evitando duplicação de registos.
    * O histórico de transações pode ser exportado para um ficheiro CSV (`export_transactions_csv_view`).

---

### **O Agente de IA e o Ciclo de Aprendizagem (App `trading_agent`)**

Esta é a funcionalidade central do projeto, operando através de tarefas agendadas pelo Celery Beat.

#### **1. Ciclo de Recolha de Dados (A cada hora)**
* **Análise Técnica**: Uma tarefa Celery (`calculate_technical_indicators_for_all_cryptos`) utiliza a biblioteca `pandas-ta` para calcular indicadores como RSI, MACD, Bandas de Bollinger e ATR a partir de dados históricos da Binance, guardando os resultados no modelo `TechnicalAnalysis`.
* **Análise de Sentimento**: Outra tarefa (`analyze_market_sentiment_for_all_cryptos`) recolhe notícias relevantes através da NewsAPI e utiliza o Gemini para realizar uma análise de sentimento, guardando um *score* e um resumo no modelo `MarketSentiment`.

#### **2. Ciclo de Decisão (A cada 15 minutos)**
* A tarefa principal (`run_trading_cycle_for_all_users`) é executada para cada utilizador que tem o agente ativo.
* **Prompt Adaptativo**: Para cada utilizador, é construído um prompt detalhado para o Gemini. Este prompt não inclui apenas os dados técnicos e de sentimento mais recentes, mas também as **regras de estratégia ativas** que o próprio utilizador aplicou a partir de aprendizados passados. Estas regras ficam guardadas no campo `agent_strategy_prompt` do `UserProfile`.
* O Gemini analisa este contexto completo e gera uma resposta em JSON contendo uma decisão (`BUY`, `SELL` ou `HOLD`), um *score* de confiança e uma justificação detalhada. Este resultado é guardado como um `TradingSignal`.

#### **3. Ciclo de Execução (A cada 15 minutos)**
* A tarefa `process_unexecuted_signals` verifica os sinais pendentes.
* Se o *score* de confiança de um sinal for superior ao limiar definido pelo utilizador (`agent_confidence_threshold`), a ordem é executada na Binance. As transações bem-sucedidas são registadas e associadas ao sinal que as originou.

#### **4. Ciclo de Aprendizagem (Semanalmente)**
* **Reflexão sobre a Performance**: A tarefa `reflect_on_performance` analisa todos os *trades* executados pelo agente na última semana, calculando lucros, prejuízos e a taxa de acerto.
* **Geração de Aprendizado**: Um relatório de performance é enviado ao Gemini, que atua como um analista de risco, identifica padrões e sugere **modificações concretas para a estratégia**.
* **Aplicação pelo Utilizador**: As sugestões são guardadas num `StrategyLog`. No "Gestor de Estratégia" (`strategy_manager.html`), o utilizador pode rever estas sugestões e, com um clique, aplicá-las. Esta ação atualiza o `agent_strategy_prompt` do seu perfil, fechando o ciclo de aprendizagem e influenciando as futuras decisões da IA.

### **Ferramentas Adicionais do Agente**

* **Dashboard do Agente**: Uma interface dedicada (`agent_dashboard.html`) mostra o estado do agente, estatísticas de sinais gerados e o histórico de decisões.
* **Relatórios de Performance**: A página de relatórios do agente (`agent_reports.html`) detalha o Lucro/Prejuízo total e a taxa de acerto das operações automáticas, com uma análise por cada ativo.
* **Backtesting**: A ferramenta de backtesting (`backtest.html`) permite ao utilizador simular a performance da estratégia de IA do seu perfil em dados históricos, comparando o resultado com uma estratégia de *Buy and Hold*.

### **Conclusão**

O Crypto Trader Pro é um projeto extremamente bem arquitetado e abrangente. Ele vai além de um simples *bot* de trading ao implementar um sofisticado **ciclo de aprendizagem adaptativo**. A capacidade do agente de IA de refletir sobre a sua própria performance e sugerir melhorias, que são então validadas e aplicadas pelo utilizador, cria um sistema dinâmico e potencialmente auto-otimizável. A separação clara de responsabilidades entre as apps `core` e `trading_agent`, o uso de tarefas assíncronas para operações pesadas e a atenção à segurança fazem desta uma plataforma robusta e de nível profissional.