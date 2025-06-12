# core/models.py
from django.db import models
from django.contrib.auth.models import User
from django.conf import settings
from decimal import Decimal, ROUND_DOWN
from django.utils import timezone
from .encryption import encrypt, decrypt

FIAT_CURRENCY_CHOICES = [
    ('USD', 'Dólar Americano'), ('BRL', 'Real Brasileiro'),
    ('EUR', 'Euro'), ('USDT', 'TetherUS'),
]
BASE_RATE_CURRENCY = 'USDT'

class Cryptocurrency(models.Model):
    symbol = models.CharField(max_length=20, unique=True, primary_key=True)
    name = models.CharField(max_length=100)
    logo_url = models.URLField(max_length=255, blank=True, null=True)
    current_price = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True)
    price_currency = models.CharField(max_length=5, choices=FIAT_CURRENCY_CHOICES, default=BASE_RATE_CURRENCY)
    last_updated = models.DateTimeField(null=True, blank=True, default=timezone.now)

    class Meta:
        verbose_name, verbose_name_plural, ordering = "Criptomoeda", "Criptomoedas", ['name']
    def __str__(self):
        price = f" - {self.current_price:.{self.get_price_decimals()}f} {self.price_currency}" if self.current_price is not None else ""
        return f"{self.name} ({self.symbol}){price}"
    def get_price_decimals(self):
        if self.current_price and self.current_price < Decimal('0.01'): return 6
        return 2

class UserProfile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='profile')
    _binance_api_key = models.TextField(blank=True)
    _binance_api_secret = models.TextField(blank=True)
    preferred_fiat_currency = models.CharField(max_length=5, choices=FIAT_CURRENCY_CHOICES, default='BRL')
    use_testnet = models.BooleanField(default=True)
    enable_auto_trading = models.BooleanField(default=False)
    agent_buy_risk_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('5.00'))
    agent_sell_risk_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('100.00'))
    agent_confidence_threshold = models.DecimalField(max_digits=3, decimal_places=2, default=Decimal('0.75'))

    # (NOVO) Campo para armazenar as regras personalizadas da estratégia do agente
    agent_strategy_prompt = models.TextField(
        blank=True, null=True,
        verbose_name="Instruções da Estratégia Ativa",
        help_text="Instruções personalizadas para o prompt do agente de IA, aplicadas a partir do Gestor de Estratégia."
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
        verbose_name, verbose_name_plural = "Perfil de Usuário", "Perfis de Usuários"
    def __str__(self): return f"Perfil de {self.user.username}"

class Holding(models.Model):
    user_profile = models.ForeignKey(UserProfile, on_delete=models.CASCADE, related_name='holdings')
    cryptocurrency = models.ForeignKey(Cryptocurrency, on_delete=models.CASCADE, related_name='held_by_users')
    quantity = models.DecimalField(max_digits=28, decimal_places=18, default=Decimal('0.0'))
    average_buy_price = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True)

    class Meta:
        unique_together = ('user_profile', 'cryptocurrency')
    def __str__(self): return f"{self.quantity} {self.cryptocurrency.symbol} de {self.user_profile.user.username}"
    @property
    def cost_basis(self):
        return self.quantity * self.average_buy_price if self.quantity and self.average_buy_price else Decimal('0.0')
    @property
    def current_market_value(self):
        return self.quantity * self.cryptocurrency.current_price if self.quantity and self.cryptocurrency.current_price else None

class Transaction(models.Model):
    TRANSACTION_TYPE_CHOICES = [('BUY', 'Compra'), ('SELL', 'Venda')]
    user_profile = models.ForeignKey(UserProfile, on_delete=models.CASCADE, related_name='transactions')
    cryptocurrency = models.ForeignKey(Cryptocurrency, on_delete=models.CASCADE, related_name='transactions')
    transaction_type = models.CharField(max_length=10, choices=TRANSACTION_TYPE_CHOICES)
    quantity_crypto = models.DecimalField(max_digits=28, decimal_places=18)
    price_per_unit = models.DecimalField(max_digits=20, decimal_places=8)
    total_value = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True)
    fees = models.DecimalField(max_digits=20, decimal_places=8, default=Decimal('0.00'))
    transaction_date = models.DateTimeField(default=timezone.now)
    timestamp = models.DateTimeField(auto_now_add=True)
    binance_order_id = models.CharField(max_length=255, blank=True, null=True)
    notes = models.TextField(blank=True, null=True)
    signal = models.ForeignKey('trading_agent.TradingSignal', on_delete=models.SET_NULL, null=True, blank=True, related_name='transactions')

    class Meta:
        ordering = ['-transaction_date', '-timestamp']
    def save(self, *args, **kwargs):
        if self.quantity_crypto and self.price_per_unit:
            self.total_value = self.quantity_crypto * self.price_per_unit
        super().save(*args, **kwargs)

class ExchangeRate(models.Model):
    from_currency = models.CharField(max_length=5, choices=FIAT_CURRENCY_CHOICES, default=BASE_RATE_CURRENCY)
    to_currency = models.CharField(max_length=5, choices=FIAT_CURRENCY_CHOICES)
    rate = models.DecimalField(max_digits=20, decimal_places=8)
    last_updated = models.DateTimeField(auto_now=True)
    class Meta:
        unique_together = ('from_currency', 'to_currency')

class PortfolioSnapshot(models.Model):
    user_profile = models.ForeignKey(UserProfile, on_delete=models.CASCADE, related_name='snapshots')
    total_value = models.DecimalField(max_digits=20, decimal_places=2)
    currency = models.CharField(max_length=5, choices=FIAT_CURRENCY_CHOICES)
    date = models.DateField(default=timezone.now)
    class Meta:
        unique_together = ('user_profile', 'date')
        ordering = ['-date']
