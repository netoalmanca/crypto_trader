# trading_agent/services.py
import requests
import json
from decimal import Decimal
from django.conf import settings
from .models import TradingSignal
from binance.client import Client
from binance.exceptions import BinanceAPIException
from core.views import get_binance_client, _process_successful_order, adjust_quantity_to_lot_size
from core.models import Holding

def get_gemini_sentiment_analysis(crypto, headlines):
    # (Lógica existente - sem alterações)
    prompt = f'Analise o sentimento das notícias sobre {crypto.name} e responda em JSON com "sentiment_score" e "summary".\nNotícias:\n{headlines}'
    # ... (resto da lógica)
    pass

def get_gemini_trade_decision(profile, crypto, tech_data_history, sentiment_data_history, holding_data, save_signal=True):
    """
    (FINAL) Monta um prompt adaptativo que inclui as regras personalizadas
    do perfil do usuário, consulta a API Gemini e salva o sinal.
    """
    tech_prompt_section = "\n".join([f"  - Dia T-{i}: RSI={d.rsi:.2f}, MACD_diff={(d.macd_line - d.macd_signal):.8f}, ATR={d.atr:.8f}" for i, d in enumerate(reversed(tech_data_history))])
    sentiment_prompt_section = "\n".join([f"  - Dia T-{i}: Score={d.sentiment_score:.2f}, Resumo: \"{d.summary}\"" for i, d in enumerate(reversed(sentiment_data_history))])

    # (NOVO) Seção de estratégia adaptativa
    adaptive_strategy_section = ""
    if profile.agent_strategy_prompt:
        adaptive_strategy_section = f"""
    **Modificações de Estratégia Ativas (baseadas em aprendizados passados):**
    Siga estas regras ADICIONAIS com prioridade máxima ao tomar sua decisão:
    ---
    {profile.agent_strategy_prompt}
    ---
    """

    prompt = f"""
    Você é um experiente analista quantitativo e trader. Sua tarefa é analisar os dados, incluindo o histórico e as regras de estratégia ativas, para gerar um sinal de trade (BUY, SELL, HOLD) para {crypto.symbol}.

    **Contexto do Portfólio:**
    - Possui: {holding_data.quantity if holding_data else '0'} {crypto.symbol}
    - Preço Atual: {crypto.current_price}

    **Dados Históricos (T-2, T-1, T-0):**
    - Análise Técnica:
    {tech_prompt_section}
    - Análise de Sentimento:
    {sentiment_prompt_section}

    {adaptive_strategy_section}

    **Instruções de Análise Padrão:**
    1.  Analise as **Tendências** dos indicadores.
    2.  Procure por **Confluência** entre sinais técnicos e de sentimento.
    3.  Avalie **Divergências e Riscos** (alta volatilidade no ATR). Se as regras ativas não especificarem o contrário, prefira 'HOLD' em caso de sinais mistos.

    **Sua Resposta:**
    Responda **APENAS** com um objeto JSON com as chaves: "decision", "confidence_score", "stop_loss_price", "take_profit_price", "justification". A justificação deve mencionar como as regras ativas ou a análise de tendência influenciaram a decisão.
    """

    # ... (resto da função de chamada da API, idêntica à versão anterior)
    gemini_api_key = settings.GEMINI_API_KEY
    # ... (o código restante para chamar a API e salvar o sinal permanece o mesmo)
    pass # Placeholder para o resto da lógica da função

def get_gemini_reflection(performance_data_str: str):
    # (Lógica existente - sem alterações)
    pass

def execute_trade_from_signal(signal):
    # (Lógica existente - sem alterações)
    pass
