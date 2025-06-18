# trading_agent/forms.py
from django import forms
from decimal import Decimal
from core.models import Cryptocurrency

class BacktestForm(forms.Form):
    """
    Formulário para o utilizador configurar e iniciar uma nova simulação de backtesting.
    """
    # (CORRIGIDO) Reintroduzida a opção '1 month ago' (Último Mês).
    PERIOD_CHOICES = [
        ('1 month ago', 'Último Mês'),
        ('3 months ago', 'Últimos 3 Meses'),
        ('6 months ago', 'Últimos 6 Meses'),
        ('1 year ago', 'Último Ano'),
    ]

    # Campo para selecionar a criptomoeda
    symbol = forms.ModelChoiceField(
        queryset=Cryptocurrency.objects.all(),
        label="Criptomoeda",
        widget=forms.Select(attrs={'class': 'form-input'})
    )
    # Campo para selecionar o período
    start_date = forms.ChoiceField(
        choices=PERIOD_CHOICES,
        label="Período do Teste",
        widget=forms.Select(attrs={'class': 'form-input'})
    )
    # Campo para definir o capital inicial da simulação
    initial_capital = forms.DecimalField(
        label="Capital Inicial (USDT)",
        min_value=Decimal('100.0'),
        initial=Decimal('1000.0'),
        widget=forms.NumberInput(attrs={'class': 'form-input', 'step': '100'})
    )
