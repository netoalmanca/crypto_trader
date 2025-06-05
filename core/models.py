# core/models.py
from django.db import models
from django.contrib.auth.models import User
from django.conf import settings
from decimal import Decimal, ROUND_DOWN
from django.utils import timezone
# Remova ou comente a linha abaixo se ela ainda existir de tentativas anteriores:
# from django_cryptography.fields import EncryptedCharField # <--- REMOVA/COMENTE ESTA LINHA

FIAT_CURRENCY_CHOICES = [
    ('USD', 'Dólar Americano'),
    ('BRL', 'Real Brasileiro'),
    ('EUR', 'Euro'),
     ('USDT', 'TetherUS'),
]

class Cryptocurrency(models.Model):
    symbol = models.CharField(max_length=20, unique=True, primary_key=True, help_text="Símbolo da criptomoeda (ex: BTC, ETH)")
    name = models.CharField(max_length=100, help_text="Nome completo da criptomoeda (ex: Bitcoin)")
    logo_url = models.URLField(max_length=255, blank=True, null=True, help_text="URL do logo da criptomoeda")
    current_price = models.DecimalField(
        max_digits=20, decimal_places=2, null=True, blank=True,
        help_text="Preço atual na moeda definida em 'Moeda do Preço', atualizado periodicamente"
    )
    price_currency = models.CharField(
        max_length=5,
        choices=FIAT_CURRENCY_CHOICES,
        default='USD',
        help_text="Moeda do campo 'Preço Atual'"
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
            price_display = f" - {self.current_price} {self.price_currency}"
        return f"{self.name} ({self.symbol}){price_display}"

class UserProfile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='profile')
    # TODO: Revisitar a criptografia das chaves API quando uma biblioteca compatível estiver disponível.
    binance_api_key = models.CharField(max_length=255, blank=True, null=True, help_text="Chave da API da Binance")
    binance_api_secret = models.CharField(max_length=255, blank=True, null=True, help_text="Segredo da API da Binance")
    preferred_fiat_currency = models.CharField(
        max_length=5,
        choices=FIAT_CURRENCY_CHOICES,
        default='BRL',
        help_text="Moeda fiduciária preferida do usuário para exibição de valores"
    )

    class Meta:
        verbose_name = "Perfil de Usuário"
        verbose_name_plural = "Perfis de Usuários"

    def __str__(self):
        return f"Perfil de {self.user.username}"

# ... (Restante dos seus modelos: Holding, Transaction) ...
# Certifique-se que o restante dos modelos Holding e Transaction estão corretos.
class Holding(models.Model):
    user_profile = models.ForeignKey(UserProfile, on_delete=models.CASCADE, related_name='holdings')
    cryptocurrency = models.ForeignKey(Cryptocurrency, on_delete=models.CASCADE, related_name='held_by_users')
    quantity = models.DecimalField(max_digits=28, decimal_places=18, default=Decimal('0.0'), help_text="Quantidade da criptomoeda possuída")
    average_buy_price = models.DecimalField(
        max_digits=20, decimal_places=2, null=True, blank=True,
        help_text="Preço médio de compra na moeda de preço da criptomoeda (ex: USD)"
    )

    class Meta:
        verbose_name = "Posse de Cripto"
        verbose_name_plural = "Posses de Criptos"
        unique_together = ('user_profile', 'cryptocurrency')
        ordering = ['user_profile', 'cryptocurrency__name']

    def __str__(self):
        return f"{self.quantity} {self.cryptocurrency.symbol} de {self.user_profile.user.username}"

    @property
    def cost_basis(self):
        if self.quantity is not None and self.average_buy_price is not None:
            return self.quantity * self.average_buy_price
        return Decimal('0.0')

    @property
    def current_market_value(self):
        if self.cryptocurrency.current_price is not None and self.quantity is not None:
            return self.quantity * self.cryptocurrency.current_price
        return None

    @property
    def profit_loss(self):
        cmv = self.current_market_value
        cb = self.cost_basis
        if cmv is not None and cb is not None:
            return cmv - cb
        return None

    @property
    def profit_loss_percent(self):
        pl = self.profit_loss
        cb = self.cost_basis
        if pl is not None and cb is not None and cb > Decimal('0.0'):
            return (pl / cb) * Decimal('100.0')
        return None


class Transaction(models.Model):
    TRANSACTION_TYPE_CHOICES = [
        ('BUY', 'Compra'),
        ('SELL', 'Venda'),
    ]

    user_profile = models.ForeignKey(UserProfile, on_delete=models.CASCADE, related_name='transactions')
    cryptocurrency = models.ForeignKey(Cryptocurrency, on_delete=models.CASCADE, related_name='transactions')
    transaction_type = models.CharField(max_length=10, choices=TRANSACTION_TYPE_CHOICES, help_text="Tipo da transação")
    quantity_crypto = models.DecimalField(max_digits=28, decimal_places=18, help_text="Quantidade da criptomoeda transacionada")
    price_per_unit = models.DecimalField(
        max_digits=20, decimal_places=2,
        help_text="Preço por unidade da cripto na moeda base da criptomoeda (ex: USD)"
    )
    total_value = models.DecimalField(
        max_digits=20, decimal_places=2, null=True, blank=True,
        help_text="Valor total da transação na moeda base da criptomoeda (calculado)"
    )
    fees = models.DecimalField(
        max_digits=20, decimal_places=2, default=Decimal('0.00'),
        help_text="Taxas da transação na moeda base da criptomoeda"
    )
    transaction_date = models.DateTimeField(default=timezone.now, help_text="Data e hora em que a transação ocorreu")
    timestamp = models.DateTimeField(auto_now_add=True, help_text="Data e hora do registro no sistema")
    binance_order_id = models.CharField(max_length=255, blank=True, null=True, help_text="ID da ordem na Binance (se aplicável)")
    notes = models.TextField(blank=True, null=True, help_text="Notas adicionais sobre a transação")

    class Meta:
        verbose_name = "Transação"
        verbose_name_plural = "Transações"
        ordering = ['-transaction_date', '-timestamp']

    def __str__(self):
        return f"{self.get_transaction_type_display()} de {self.quantity_crypto} {self.cryptocurrency.symbol} por {self.user_profile.user.username} em {self.transaction_date.strftime('%Y-%m-%d %H:%M')}"

    def save(self, *args, **kwargs):
        if self.transaction_type in ['BUY', 'SELL'] and self.quantity_crypto and self.price_per_unit:
            self.total_value = self.quantity_crypto * self.price_per_unit
        super().save(*args, **kwargs)