# trading_agent/services.py
import requests
import json
from decimal import Decimal
from django.conf import settings
from django.utils import timezone

from .models import TradingSignal
from core.models import UserProfile, Cryptocurrency, Holding
from binance.client import Client
from binance.exceptions import BinanceAPIException
from core.views import get_binance_client, _process_successful_order

def get_gemini_api_url(model_name: str):
    """Constrói a URL da API para o modelo Gemini especificado."""
    return f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent"

def get_gemini_sentiment_analysis(profile: UserProfile, crypto: Cryptocurrency, headlines: str):
    """
    Analisa o sentimento usando o modelo de IA e a chave do perfil do usuário.
    """
    gemini_api_key = profile.gemini_api_key
    if not gemini_api_key or "DECRYPTION_FAILED" in gemini_api_key:
        print(f"Chave da API Gemini não configurada para o usuário {profile.user.username}.")
        return None

    model_name = profile.gemini_model
    api_url = get_gemini_api_url(model_name) + f"?key={gemini_api_key}"
    
    prompt = f"Analise o sentimento das seguintes manchetes sobre {crypto.name} ({crypto.symbol}). Responda com um score de -1.0 (muito negativo) a 1.0 (muito positivo) e um breve resumo.\n\nNotícias:\n{headlines}"
    json_schema = {"type": "OBJECT", "properties": {"sentiment_score": {"type": "NUMBER"}, "summary": {"type": "STRING"}}, "required": ["sentiment_score", "summary"]}
    payload = {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"responseMimeType": "application/json", "responseSchema": json_schema, "temperature": 0.2}}

    try:
        response = requests.post(api_url, headers={'Content-Type': 'application/json'}, json=payload, timeout=45)
        response.raise_for_status()
        return json.loads(response.json()['candidates'][0]['content']['parts'][0]['text'])
    except Exception as e:
        print(f"Erro na API Gemini ({model_name}) para Sentimento: {e}")
    return None

def get_gemini_trade_decision(profile: UserProfile, crypto: Cryptocurrency, tech_data_history: list, sentiment_data_history: list, holding_data: Holding, save_signal=True):
    tech_lines = []
    for i, d in enumerate(reversed(tech_data_history)):
        try:
            # (CORREÇÃO DEFINITIVA) Usa getattr para acessar o atributo de forma segura,
            # funcionando tanto para objetos do modelo quanto para os mocks do backtest.
            rsi = float(getattr(d, 'rsi', 0.0) or 0.0)
            macd_line = float(getattr(d, 'macd_line', 0.0) or 0.0)
            macd_signal = float(getattr(d, 'macd_signal', 0.0) or 0.0)
            atr = float(getattr(d, 'atr', 0.0) or 0.0)
        except (ValueError, TypeError):
            # Fallback seguro caso a estrutura de dados seja inesperada.
            rsi, macd_line, macd_signal, atr = 0.0, 0.0, 0.0, 0.0
        
        macd_diff = macd_line - macd_signal
        
        tech_lines.append(f"  - Dia T-{i}: RSI={rsi:.2f}, MACD_diff={macd_diff:.8f}, ATR={atr:.8f}")
    
    tech_prompt_section = "\n".join(tech_lines)
    sentiment_prompt_section = "\n".join([f"  - Dia T-{i}: Score={getattr(d, 'sentiment_score', 0.5):.2f}, Resumo: \"{getattr(d, 'summary', 'N/A')}\"" for i, d in enumerate(reversed(sentiment_data_history))])
    adaptive_strategy_section = f"**Modificações de Estratégia Ativas:**\n{profile.agent_strategy_prompt}" if profile.agent_strategy_prompt else ""
    
    # (APRIMORADO) Prompt mais direto para incentivar decisões.
    prompt = f"Você é um analista quantitativo. Seu objetivo é identificar e agir em oportunidades de trade claras para {crypto.symbol}. Analise os dados e gere um sinal de 'BUY' ou 'SELL' se houver uma confluência forte de indicadores. Caso contrário, gere 'HOLD'.\n\n**Contexto:**\n- Possui: {holding_data.quantity if holding_data else '0'} {crypto.symbol}\n- Preço Atual: {crypto.current_price}\n\n**Dados Históricos:**\n- Análise Técnica:\n{tech_prompt_section}\n- Análise de Sentimento:\n{sentiment_prompt_section}\n\n{adaptive_strategy_section}\n**Instruções:**\n1. Gere um sinal 'BUY' ou 'SELL' apenas se houver uma oportunidade clara.\n2. Forneça um score de confiança alto (acima de 0.7) para sinais de compra/venda.\n3. Justifique sua decisão com base nos dados."

    gemini_api_key = profile.gemini_api_key
    if not gemini_api_key or "DECRYPTION_FAILED" in gemini_api_key:
        print(f"Chave da API Gemini não configurada para o usuário {profile.user.username}.")
        return None

    model_name = profile.gemini_model
    api_url = get_gemini_api_url(model_name) + f"?key={gemini_api_key}"
    json_schema = {"type": "OBJECT", "properties": {"decision": {"type": "STRING", "enum": ["BUY", "SELL", "HOLD"]},"confidence_score": {"type": "NUMBER"},"stop_loss_price": {"type": "NUMBER"},"take_profit_price": {"type": "NUMBER"},"justification": {"type": "STRING"}}, "required": ["decision", "confidence_score", "justification"]}
    payload = {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"responseMimeType": "application/json", "responseSchema": json_schema, "temperature": 0.3}}

    try:
        response = requests.post(api_url, headers={'Content-Type': 'application/json'}, json=payload, timeout=45)
        response.raise_for_status()
        decision_data = json.loads(response.json()['candidates'][0]['content']['parts'][0]['text'])

        if save_signal:
            TradingSignal.objects.create(
                user_profile=profile, cryptocurrency=crypto,
                decision=decision_data.get('decision'),
                confidence_score=Decimal(str(decision_data.get('confidence_score', '0.0'))),
                stop_loss_price=Decimal(str(decision_data.get('stop_loss_price'))) if decision_data.get('stop_loss_price') else None,
                take_profit_price=Decimal(str(decision_data.get('take_profit_price'))) if decision_data.get('take_profit_price') else None,
                justification=decision_data.get('justification', 'N/A')
            )
        return decision_data
    except Exception as e:
        print(f"Erro na API Gemini ({profile.gemini_model}) para decisão: {e}")
        if 'response' in locals(): print(f"Resposta da API: {response.text}")
    return None

def get_gemini_reflection(profile: UserProfile, performance_data_str: str):
    gemini_api_key = profile.gemini_api_key
    if not gemini_api_key or "DECRYPTION_FAILED" in gemini_api_key:
        print(f"Chave da API Gemini não configurada para o usuário {profile.user.username}.")
        return None

    prompt = f"Você é um gestor de risco. Analise o relatório de performance de um agente de IA e forneça uma reflexão e sugestões concretas para melhorar a estratégia.\n\nRelatório:\n{performance_data_str}\n\nSua tarefa:\n1.  **Reflexão (ai_reflection):** O que funcionou e o que não funcionou?\n2.  **Sugestões (suggested_modifications):** Sugira 1-2 regras claras e acionáveis. Exemplo: 'Se RSI > 75, considere vender parte da posição.' ou 'Evite comprar se ATR estiver 50% acima da média.'"
    
    model_name = profile.gemini_model
    api_url = get_gemini_api_url(model_name) + f"?key={gemini_api_key}"
    json_schema = {"type": "OBJECT", "properties": {"ai_reflection": {"type": "STRING"}, "suggested_modifications": {"type": "STRING"}}, "required": ["ai_reflection", "suggested_modifications"]}
    payload = {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"responseMimeType": "application/json", "responseSchema": json_schema, "temperature": 0.5}}

    try:
        response = requests.post(api_url, headers={'Content-Type': 'application/json'}, json=payload, timeout=60)
        response.raise_for_status()
        return json.loads(response.json()['candidates'][0]['content']['parts'][0]['text'])
    except Exception as e:
        print(f"Erro na API Gemini ({profile.gemini_model}) para reflexão: {e}")
    return None

def execute_trade_from_signal(signal: TradingSignal):
    client = get_binance_client(user_profile=signal.user_profile)
    if not client: return

    crypto, api_symbol = signal.cryptocurrency, f"{signal.cryptocurrency.symbol.upper()}{signal.cryptocurrency.price_currency.upper()}"
    
    try:
        if signal.decision == 'BUY':
            balance = client.get_asset_balance(asset=crypto.price_currency)
            cash_to_spend = Decimal(balance['free']) * (signal.user_profile.agent_buy_risk_percentage / Decimal('100.0'))
            if cash_to_spend < 11:
                signal.justification += "\n[Execução Falhou: Saldo insuficiente]"
                signal.save()
                return
            order = client.order_market_buy(symbol=api_symbol, quoteOrderQty=float(cash_to_spend))
            _process_successful_order(signal.user_profile, order, crypto, signal=signal)
        elif signal.decision == 'SELL':
            holding = Holding.objects.get(user_profile=signal.user_profile, cryptocurrency=crypto)
            quantity_to_sell = holding.quantity * (signal.user_profile.agent_sell_risk_percentage / Decimal('100.0'))
            symbol_info = client.get_symbol_info(api_symbol)
            lot_size_filter = next((f for f in symbol_info['filters'] if f['filterType'] == 'LOT_SIZE'), None)
            if lot_size_filter:
                from core.views import adjust_quantity_to_lot_size
                quantity_to_sell = adjust_quantity_to_lot_size(str(quantity_to_sell), lot_size_filter['stepSize'])
            if quantity_to_sell <= 0:
                signal.justification += "\n[Execução Falhou: Quantidade a vender é zero]"
                signal.save()
                return
            order = client.order_market_sell(symbol=api_symbol, quantity=float(quantity_to_sell))
            _process_successful_order(signal.user_profile, order, crypto, signal=signal)
        signal.is_executed = True
        signal.save()
        print(f"Sinal {signal.id} ({signal.decision} {crypto.symbol}) executado com sucesso.")
    except Exception as e:
        signal.justification += f"\n[Execução Falhou: {e}]"
        signal.save()
