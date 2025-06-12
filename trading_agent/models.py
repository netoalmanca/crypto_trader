# trading_agent/models.py
from django.db import models
from django.utils import timezone
from core.models import Cryptocurrency, UserProfile

class TechnicalAnalysis(models.Model):
    # ... (código existente inalterado) ...
    cryptocurrency = models.ForeignKey(Cryptocurrency, on_delete=models.CASCADE, related_name='tech_analyses')
    timeframe = models.CharField(max_length=10, default='1d', help_text="Timeframe da análise (ex: 1h, 4h, 1d)")
    rsi = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    macd_line = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True)
    macd_signal = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True)
    bollinger_high = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True)
    bollinger_low = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True)
    timestamp = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = "Análise Técnica"
        verbose_name_plural = "Análises Técnicas"
        ordering = ['-timestamp']
        unique_together = ('cryptocurrency', 'timeframe', 'timestamp')

class MarketSentiment(models.Model):
    # ... (código existente inalterado) ...
    cryptocurrency = models.ForeignKey(Cryptocurrency, on_delete=models.CASCADE, related_name='sentiments')
    sentiment_score = models.DecimalField(max_digits=4, decimal_places=2, help_text="De -1.0 (muito negativo) a +1.0 (muito positivo)")
    summary = models.TextField(help_text="Resumo gerado pela IA sobre as notícias e o sentimento.")
    raw_news_data = models.TextField(blank=True, help_text="Dados brutos (ex: manchetes) usados para a análise.")
    timestamp = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = "Sentimento de Mercado"
        verbose_name_plural = "Sentimentos de Mercado"
        ordering = ['-timestamp']

class TradingSignal(models.Model):
    # ... (código existente inalterado) ...
    DECISION_CHOICES = [('BUY', 'Comprar'), ('SELL', 'Vender'), ('HOLD', 'Manter')]
    user_profile = models.ForeignKey(UserProfile, on_delete=models.CASCADE, related_name='signals')
    cryptocurrency = models.ForeignKey(Cryptocurrency, on_delete=models.CASCADE)
    decision = models.CharField(max_length=4, choices=DECISION_CHOICES)
    confidence_score = models.DecimalField(max_digits=3, decimal_places=2, help_text="Confiança da IA na decisão (0.0 a 1.0)")
    stop_loss_price = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True)
    take_profit_price = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True)
    justification = models.TextField(help_text="Justificativa da IA para a decisão, baseada nos dados analisados.")
    is_executed = models.BooleanField(default=False, help_text="Marca se a ordem baseada neste sinal foi executada.")
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Sinal de Trading"
        verbose_name_plural = "Sinais de Trading"
        ordering = ['-timestamp']

# (NOVO) Modelo para armazenar os resultados do Backtest
class BacktestReport(models.Model):
    STATUS_CHOICES = [
        ('PENDING', 'Pendente'),
        ('RUNNING', 'Em Execução'),
        ('COMPLETED', 'Concluído'),
        ('FAILED', 'Falhou'),
    ]
    user_profile = models.ForeignKey(UserProfile, on_delete=models.CASCADE, related_name='backtests')
    symbol = models.CharField(max_length=20)
    start_date = models.CharField(max_length=50)
    initial_capital = models.DecimalField(max_digits=20, decimal_places=2)
    
    # Campos para os resultados
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='PENDING')
    final_value = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
    profit_loss_percent = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    buy_and_hold_profit_loss_percent = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    total_trades = models.IntegerField(null=True, blank=True)
    error_message = models.TextField(blank=True, null=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Relatório de Backtest"
        verbose_name_plural = "Relatórios de Backtest"
        ordering = ['-created_at']

    def __str__(self):
        return f"Backtest para {self.symbol} de {self.user_profile.user.username} em {self.created_at.strftime('%Y-%m-%d')}"

