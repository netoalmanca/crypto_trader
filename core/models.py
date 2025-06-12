# core/models.py
from django.db import models
from django.contrib.auth.models import User
from django.conf import settings
from decimal import Decimal, ROUND_DOWN
from django.utils import timezone
from .encryption import encrypt, decrypt

FIAT_CURRENCY_CHOICES = [
    ('USD', 'Dólar Americano'),
    ('BRL', 'Real Brasileiro'),
    ('EUR', 'Euro'),
    ('USDT', 'TetherUS'),
]

BASE_RATE_CURRENCY = 'USDT'

class Cryptocurrency(models.Model):
    symbol = models.CharField(max_length=20, unique=True, primary_key=True, help_text="Símbolo da criptomoeda (ex: BTC, ETH)")
    name = models.CharField(max_length=100, help_text="Nome completo da criptomoeda (ex: Bitcoin)")
    logo_url = models.URLField(max_length=255, blank=True, null=True, help_text="URL do logo da criptomoeda")
    current_price = models.DecimalField(
        max_digits=20, decimal_places=8, null=True, blank=True,
        help_text="Preço atual na moeda definida em 'Moeda do Preço', atualizado periodicamente"
    )
    price_currency = models.CharField(
        max_length=5,
        choices=FIAT_CURRENCY_CHOICES,
        default=BASE_RATE_CURRENCY,
        help_text=f"Moeda de cotação para este criptoativo (ex: USDT, BRL). O preço é em relação a esta moeda."
    )
    last_updated = models.DateTimeField(
        null=True, blank=True, default=timezone.now,
        help_text="Data e hora da última atualização do preço"
    )

    class Meta:
        verbose_name = "Criptomoeda"
        verbose_name_plural = "Criptomoedas"
        ordering = ['name']

    def __str__(self):
        price_display = ""
        if self.current_price is not None:
            price_display = f" - {self.current_price:.{self.get_price_decimals()}f} {self.price_currency}"
        return f"{self.name} ({self.symbol}){price_display}"

    def get_price_decimals(self):
        if self.current_price is not None:
            if self.current_price < Decimal('0.0001'): return 8
            elif self.current_price < Decimal('1'): return 4
            elif self.current_price < Decimal('100'): return 2
        return 2

class UserProfile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='profile')
    _binance_api_key = models.TextField(blank=True, help_text="Encrypted Binance API Key")
    _binance_api_secret = models.TextField(blank=True, help_text="Encrypted Binance API Secret")
    preferred_fiat_currency = models.CharField(
        max_length=5, choices=FIAT_CURRENCY_CHOICES, default='BRL',
        help_text="Moeda fiduciária preferida do usuário para exibição de valores"
    )
    use_testnet = models.BooleanField(
        default=True, verbose_name="Usar Ambiente de Teste (Testnet)",
        help_text="Se marcado, todas as operações de trade usarão a Testnet da Binance (sem fundos reais). Desmarque para usar sua conta real (Mainnet)."
    )
    enable_auto_trading = models.BooleanField(
        default=False,
        verbose_name="Ativar Agente de Trading Automático",
        help_text="Se marcado, o agente de IA poderá executar operações automaticamente com base na sua estratégia."
    )
    agent_buy_risk_percentage = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal('5.00'),
        verbose_name="Risco por Compra (%)",
        help_text="Percentual do seu saldo em USDT que o agente usará para cada ordem de compra."
    )
    agent_sell_risk_percentage = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal('100.00'),
        verbose_name="Percentual de Venda (%)",
        help_text="Percentual da sua posse de uma cripto que o agente usará para cada ordem de venda."
    )
    agent_confidence_threshold = models.DecimalField(
        max_digits=3, decimal_places=2, default=Decimal('0.75'),
        verbose_name="Limiar de Confiança do Agente",
        help_text="O agente só executará ordens se a confiança da IA for maior ou igual a este valor (ex: 0.75 = 75%)."
    )
    
    @property
    def binance_api_key(self): return decrypt(self._binance_api_key)
    @binance_api_key.setter
    def binance_api_key(self, value: str): self._binance_api_key = encrypt(value)
    @property
    def binance_api_secret(self): return decrypt(self._binance_api_secret)
    @binance_api_secret.setter
    def binance_api_secret(self, value: str): self._binance_api_secret = encrypt(value)

    class Meta:
        verbose_name = "Perfil de Usuário"
        verbose_name_plural = "Perfis de Usuários"
    def __str__(self): return f"Perfil de {self.user.username}"


class Holding(models.Model):
    user_profile = models.ForeignKey(UserProfile, on_delete=models.CASCADE, related_name='holdings')
    cryptocurrency = models.ForeignKey(Cryptocurrency, on_delete=models.CASCADE, related_name='held_by_users')
    quantity = models.DecimalField(max_digits=28, decimal_places=18, default=Decimal('0.0'), help_text="Quantidade da criptomoeda possuída")
    average_buy_price = models.DecimalField(
        max_digits=20, decimal_places=8, null=True, blank=True,
        help_text="Preço médio de compra na moeda de preço da criptomoeda (ex: USD)"
    )
    class Meta:
        verbose_name = "Posse de Cripto"
        verbose_name_plural = "Posses de Criptos"
        unique_together = ('user_profile', 'cryptocurrency')
        ordering = ['user_profile', 'cryptocurrency__name']
    def __str__(self): return f"{self.quantity} {self.cryptocurrency.symbol} de {self.user_profile.user.username}"
    @property
    def cost_basis(self):
        if self.quantity is not None and self.average_buy_price is not None: return self.quantity * self.average_buy_price
        return Decimal('0.0')
    @property
    def current_market_value(self):
        if self.cryptocurrency.current_price is not None and self.quantity is not None: return self.quantity * self.cryptocurrency.current_price
        return None

class Transaction(models.Model):
    TRANSACTION_TYPE_CHOICES = [('BUY', 'Compra'), ('SELL', 'Venda')]
    user_profile = models.ForeignKey(UserProfile, on_delete=models.CASCADE, related_name='transactions')
    cryptocurrency = models.ForeignKey(Cryptocurrency, on_delete=models.CASCADE, related_name='transactions')
    transaction_type = models.CharField(max_length=10, choices=TRANSACTION_TYPE_CHOICES, help_text="Tipo da transação")
    quantity_crypto = models.DecimalField(max_digits=28, decimal_places=18, help_text="Quantidade da criptomoeda transacionada")
    price_per_unit = models.DecimalField(max_digits=20, decimal_places=8, help_text="Preço por unidade da cripto na moeda base da criptomoeda (ex: USDT)")
    total_value = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True, help_text="Valor total da transação na moeda base da criptomoeda (calculado)")
    fees = models.DecimalField(max_digits=20, decimal_places=8, default=Decimal('0.00'), help_text="Taxas da transação na moeda base da criptomoeda")
    transaction_date = models.DateTimeField(default=timezone.now, help_text="Data e hora em que a transação ocorreu")
    timestamp = models.DateTimeField(auto_now_add=True, help_text="Data e hora do registro no sistema")
    binance_order_id = models.CharField(max_length=255, blank=True, null=True, help_text="ID da ordem na Binance (se aplicável)")
    notes = models.TextField(blank=True, null=True, help_text="Notas adicionais sobre a transação")
    
    # (ATUALIZADO) Adiciona a relação com o TradingSignal
    signal = models.ForeignKey(
        'trading_agent.TradingSignal',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='transactions'
    )

    class Meta:
        verbose_name = "Transação"
        verbose_name_plural = "Transações"
        ordering = ['-transaction_date', '-timestamp']
    def __str__(self): return f"{self.get_transaction_type_display()} de {self.quantity_crypto} {self.cryptocurrency.symbol} por {self.user_profile.user.username} em {self.transaction_date.strftime('%Y-%m-%d %H:%M')}"
    def save(self, *args, **kwargs):
        if self.transaction_type in ['BUY', 'SELL'] and self.quantity_crypto and self.price_per_unit: self.total_value = self.quantity_crypto * self.price_per_unit
        super().save(*args, **kwargs)

class ExchangeRate(models.Model):
    from_currency = models.CharField(max_length=5, choices=FIAT_CURRENCY_CHOICES, default=BASE_RATE_CURRENCY)
    to_currency = models.CharField(max_length=5, choices=FIAT_CURRENCY_CHOICES)
    rate = models.DecimalField(max_digits=20, decimal_places=8, help_text=f"Quantos 'TO_CURRENCY' valem 1 'FROM_CURRENCY'. Ex: Se FROM=USDT, TO=BRL, rate é o valor de 1 USDT em BRL.")
    last_updated = models.DateTimeField(auto_now=True)
    class Meta:
        unique_together = ('from_currency', 'to_currency')
        verbose_name = "Taxa de Câmbio"
        verbose_name_plural = "Taxas de Câmbio"
        ordering = ['from_currency', 'to_currency']
    def __str__(self): return f"1 {self.from_currency} = {self.rate:.4f} {self.to_currency} (Atualizado: {self.last_updated.strftime('%Y-%m-%d %H:%M')})"

class PortfolioSnapshot(models.Model):
    user_profile = models.ForeignKey(UserProfile, on_delete=models.CASCADE, related_name='snapshots')
    total_value = models.DecimalField(max_digits=20, decimal_places=2, help_text="Valor total do portfólio na data do snapshot")
    currency = models.CharField(max_length=5, choices=FIAT_CURRENCY_CHOICES, help_text="Moeda em que o valor total foi calculado")
    date = models.DateField(default=timezone.now)

    class Meta:
        verbose_name = "Snapshot do Portfólio"
        verbose_name_plural = "Snapshots do Portfólio"
        unique_together = ('user_profile', 'date')
        ordering = ['-date']

    def __str__(self):
        return f"Snapshot de {self.user_profile.user.username} em {self.date}: {self.total_value} {self.currency}"

