# core/forms.py
from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth.models import User
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from .models import Cryptocurrency, Transaction, Holding, UserProfile, FIAT_CURRENCY_CHOICES
from decimal import Decimal

class CustomUserCreationForm(UserCreationForm):
    email = forms.EmailField(required=True, widget=forms.EmailInput(attrs={'class': 'form-input', 'placeholder': 'Seu melhor email'}))
    first_name = forms.CharField(label=_("Nome"), max_length=30, required=False, widget=forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Nome (Opcional)'}))
    last_name = forms.CharField(label=_("Sobrenome"), max_length=150, required=False, widget=forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Sobrenome (Opcional)'}))
    class Meta(UserCreationForm.Meta):
        model = User
        fields = UserCreationForm.Meta.fields + ('email', 'first_name', 'last_name')
        widgets = {'username': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Nome de Usuário'})}

class CustomAuthenticationForm(AuthenticationForm):
    username = forms.CharField(widget=forms.TextInput(attrs={'class': 'form-input', 'autofocus': True, 'placeholder': 'Nome de Usuário'}))
    password = forms.CharField(widget=forms.PasswordInput(attrs={'class': 'form-input', 'placeholder': 'Senha'}))

class UserProfileAPIForm(forms.ModelForm):
    binance_api_key = forms.CharField(label=_("Sua Chave API da Binance"), widget=forms.TextInput(attrs={'class': 'form-input'}), required=False)
    binance_api_secret = forms.CharField(label=_("Seu Segredo API da Binance"), widget=forms.PasswordInput(attrs={'class': 'form-input', 'render_value': False}), required=False)
    preferred_fiat_currency = forms.ChoiceField(label=_("Sua Moeda Fiat Preferida"), choices=FIAT_CURRENCY_CHOICES, widget=forms.Select(attrs={'class': 'form-input'}))
    use_testnet = forms.BooleanField(
        label=_("Usar Ambiente de Teste (Testnet)"),
        required=False,
        widget=forms.CheckboxInput(attrs={'class': 'h-5 w-5 rounded border-gray-300 text-cyan-600 focus:ring-cyan-500'})
    )
    class Meta:
        model = UserProfile
        fields = ['binance_api_key', 'binance_api_secret', 'preferred_fiat_currency', 'use_testnet']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            key = self.instance.binance_api_key
            secret_exists = self.instance.binance_api_secret and self.instance.binance_api_secret != 'DECRYPTION_FAILED'
            self.fields['binance_api_key'].widget.attrs['placeholder'] = f"Atual: {key[:4]}...{key[-4:]}" if key and key != 'DECRYPTION_FAILED' else "Nenhuma chave definida"
            self.fields['binance_api_secret'].widget.attrs['placeholder'] = "••••••••••••••••" if secret_exists else "Nenhum segredo definido"
    
    def save(self, commit=True):
        profile = super().save(commit=False)
        new_key = self.cleaned_data.get('binance_api_key')
        new_secret = self.cleaned_data.get('binance_api_secret')
        if new_key: profile.binance_api_key = new_key
        if new_secret: profile.binance_api_secret = new_secret
        if commit: profile.save()
        return profile

# FORMULÁRIO REINSERIDO
class TransactionForm(forms.ModelForm):
    transaction_date = forms.DateTimeField(label=_("Data da Transação"), widget=forms.DateTimeInput(attrs={'type': 'datetime-local', 'class': 'form-input'}), initial=timezone.now)
    cryptocurrency = forms.ModelChoiceField(queryset=Cryptocurrency.objects.all().order_by('name'), widget=forms.Select(attrs={'class': 'form-input'}), label=_("Criptomoeda"))
    transaction_type = forms.ChoiceField(choices=[c for c in Transaction.TRANSACTION_TYPE_CHOICES if c[0] in ['BUY', 'SELL']], widget=forms.Select(attrs={'class': 'form-input'}), label=_("Tipo de Transação"))
    class Meta:
        model = Transaction
        fields = ['cryptocurrency', 'transaction_type', 'quantity_crypto', 'price_per_unit', 'fees', 'transaction_date', 'notes']
        widgets = {'quantity_crypto': forms.NumberInput(attrs={'class': 'form-input', 'placeholder': 'Ex: 0.5', 'step': 'any'}),'price_per_unit': forms.NumberInput(attrs={'class': 'form-input', 'placeholder': 'Preço na moeda base', 'step': 'any'}),'fees': forms.NumberInput(attrs={'class': 'form-input', 'placeholder': 'Taxas na moeda base', 'step': 'any'}),'notes': forms.Textarea(attrs={'class': 'form-input', 'rows': 3, 'placeholder': 'Opcional'})}
    
    def __init__(self, *args, **kwargs):
        self.user_profile = kwargs.pop('user_profile', None)
        super().__init__(*args, **kwargs)

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get("transaction_type") == 'SELL' and self.user_profile:
            quantity, crypto = cleaned_data.get("quantity_crypto"), cleaned_data.get("cryptocurrency")
            if quantity and crypto:
                try:
                    holding = Holding.objects.get(user_profile=self.user_profile, cryptocurrency=crypto)
                    if holding.quantity < quantity: self.add_error('quantity_crypto', _("Saldo insuficiente."))
                except Holding.DoesNotExist: self.add_error('cryptocurrency', _("Você não possui esta cripto."))
        return cleaned_data

class MarketBuyForm(forms.Form):
    BUY_TYPE_CHOICES = [('QUANTITY', 'Quantidade da Cripto'), ('QUOTE_QUANTITY', 'Valor a Gastar')]
    buy_type = forms.ChoiceField(choices=BUY_TYPE_CHOICES, label="Comprar por", widget=forms.RadioSelect, initial='QUANTITY')
    cryptocurrency = forms.ModelChoiceField(queryset=Cryptocurrency.objects.all().order_by('name'), widget=forms.Select(attrs={'class': 'form-input'}), label="Criptomoeda")
    quantity = forms.DecimalField(label="Quantidade (ex: 0.01)", required=False, min_value=Decimal('0.00000001'), widget=forms.NumberInput(attrs={'class': 'form-input', 'step': 'any', 'placeholder': 'Ex: 0.01'}))
    quote_quantity = forms.DecimalField(label="Valor a Gastar (em USDT)", required=False, min_value=Decimal('0.01'), widget=forms.NumberInput(attrs={'class': 'form-input', 'step': 'any', 'placeholder': 'Ex: 100.00'}))

    def __init__(self, *args, **kwargs):
        user_currency = kwargs.pop('user_currency', 'USDT')
        super().__init__(*args, **kwargs)
        self.fields['quote_quantity'].label = _(f"Valor a Gastar (em {user_currency})")

    def clean(self):
        cleaned_data = super().clean()
        buy_type = cleaned_data.get('buy_type')
        if buy_type == 'QUANTITY' and not cleaned_data.get('quantity'):
            self.add_error('quantity', _("Para este tipo de compra, a quantidade é obrigatória."))
        elif buy_type == 'QUOTE_QUANTITY' and not cleaned_data.get('quote_quantity'):
            self.add_error('quote_quantity', _("Para este tipo de compra, o valor a gastar é obrigatório."))
        if buy_type == 'QUANTITY':
            cleaned_data['quote_quantity'] = None
        else:
            cleaned_data['quantity'] = None
        return cleaned_data

class MarketSellForm(forms.Form):
    SELL_TYPE_CHOICES = [('QUANTITY', 'Vender Quantidade'), ('QUOTE_RECEIVE', 'Receber Valor (Aprox.)')]
    sell_type = forms.ChoiceField(choices=SELL_TYPE_CHOICES, label="Vender por", widget=forms.RadioSelect, initial='QUANTITY')
    cryptocurrency = forms.ModelChoiceField(queryset=Cryptocurrency.objects.none(), widget=forms.Select(attrs={'class': 'form-input'}), label="Criptomoeda a Vender")
    quantity = forms.DecimalField(label="Quantidade a Vender", required=False, min_value=Decimal('0.00000001'), widget=forms.NumberInput(attrs={'class': 'form-input', 'step': 'any', 'placeholder': 'Ex: 0.5'}))
    quote_quantity_to_receive = forms.DecimalField(label="Valor a Receber (em USDT)", required=False, min_value=Decimal('0.01'), widget=forms.NumberInput(attrs={'class': 'form-input', 'step': 'any', 'placeholder': 'Ex: 100.00'}))

    def __init__(self, *args, **kwargs):
        self.user_profile = kwargs.pop('user_profile', None)
        quote_currency = kwargs.pop('quote_currency', 'USDT')
        super().__init__(*args, **kwargs)
        self.fields['quote_quantity_to_receive'].label = _(f"Valor a Receber (Aprox. em {quote_currency})")
        if self.user_profile:
            pks = Holding.objects.filter(user_profile=self.user_profile, quantity__gt=0).values_list('cryptocurrency__pk', flat=True)
            self.fields['cryptocurrency'].queryset = Cryptocurrency.objects.filter(pk__in=pks)

    def clean(self):
        cleaned_data = super().clean()
        sell_type = cleaned_data.get('sell_type')
        if sell_type == 'QUANTITY' and not cleaned_data.get('quantity'):
            self.add_error('quantity', _("Para este tipo de venda, a quantidade é obrigatória."))
        elif sell_type == 'QUOTE_RECEIVE' and not cleaned_data.get('quote_quantity_to_receive'):
            self.add_error('quote_quantity_to_receive', _("Para este tipo de venda, o valor a receber é obrigatório."))
        if sell_type == 'QUANTITY':
            cleaned_data['quote_quantity_to_receive'] = None
        else:
            cleaned_data['quantity'] = None
        return cleaned_data

class LimitBuyForm(forms.Form):
    ORDER_TYPE_CHOICES = [('QUANTITY', _('Por Quantidade')), ('TOTAL', _('Por Valor Total'))]
    order_type = forms.ChoiceField(choices=ORDER_TYPE_CHOICES, widget=forms.RadioSelect, initial='QUANTITY', label=_("Tipo de Ordem"))
    cryptocurrency = forms.ModelChoiceField(queryset=Cryptocurrency.objects.all().order_by('name'), widget=forms.Select(attrs={'class': 'form-input'}), label=_("Criptomoeda"))
    quantity = forms.DecimalField(label=_("Quantidade"), required=False, widget=forms.NumberInput(attrs={'class': 'form-input', 'placeholder': 'Ex: 0.01', 'step': 'any'}))
    total_value = forms.DecimalField(label=_("Valor Total"), required=False, widget=forms.NumberInput(attrs={'class': 'form-input', 'placeholder': 'Ex: 500.00', 'step': 'any'}))
    price = forms.DecimalField(label=_("Preço Limite"), required=True, widget=forms.NumberInput(attrs={'class': 'form-input', 'placeholder': 'Ex: 350000.00', 'step': 'any'}))
    def __init__(self, *args, **kwargs):
        user_currency = kwargs.pop('user_currency', 'BRL'); super().__init__(*args, **kwargs)
        self.fields['total_value'].label = _(f"Valor Total a Gastar ({user_currency})")
        self.fields['price'].label = _(f"Preço Limite por Unidade ({user_currency})")
    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get('order_type') == 'QUANTITY' and not cleaned_data.get('quantity'): self.add_error('quantity', _("A quantidade é obrigatória."))
        elif cleaned_data.get('order_type') == 'TOTAL' and not cleaned_data.get('total_value'): self.add_error('total_value', _("O valor total é obrigatório."))
        return cleaned_data

class LimitSellForm(forms.Form):
    ORDER_TYPE_CHOICES = [('QUANTITY', _('Por Quantidade')), ('TOTAL', _('Por Valor a Receber'))]
    order_type = forms.ChoiceField(choices=ORDER_TYPE_CHOICES, widget=forms.RadioSelect, initial='QUANTITY', label=_("Tipo de Ordem"))
    cryptocurrency = forms.ModelChoiceField(queryset=Cryptocurrency.objects.none(), widget=forms.Select(attrs={'class': 'form-input'}), label=_("Criptomoeda para Vender"))
    quantity = forms.DecimalField(label=_("Quantidade a Vender"), required=False, widget=forms.NumberInput(attrs={'class': 'form-input', 'placeholder': 'Ex: 0.5', 'step': 'any'}))
    total_value = forms.DecimalField(label=_("Valor a Receber (Aprox.)"), required=False, widget=forms.NumberInput(attrs={'class': 'form-input', 'placeholder': 'Ex: 500.00', 'step': 'any'}))
    price = forms.DecimalField(label=_("Preço Limite"), required=True, widget=forms.NumberInput(attrs={'class': 'form-input', 'placeholder': 'Ex: 400000.00', 'step': 'any'}))
    def __init__(self, *args, **kwargs):
        self.user_profile = kwargs.pop('user_profile', None); super().__init__(*args, **kwargs)
        if self.user_profile:
            pks = Holding.objects.filter(user_profile=self.user_profile, quantity__gt=0).values_list('cryptocurrency__pk', flat=True)
            self.fields['cryptocurrency'].queryset = Cryptocurrency.objects.filter(pk__in=pks)
            self.fields['total_value'].label = _(f"Valor a Receber ({self.user_profile.preferred_fiat_currency})")
            self.fields['price'].label = _(f"Preço Limite ({self.user_profile.preferred_fiat_currency})")
    def clean(self):
        cleaned_data = super().clean()
        order_type, price, crypto = cleaned_data.get('order_type'), cleaned_data.get('price'), cleaned_data.get('cryptocurrency')
        calc_qty = cleaned_data.get('quantity')
        if order_type == 'QUANTITY':
            if not calc_qty or calc_qty <= 0: self.add_error('quantity', _("Quantidade deve ser positiva."))
        elif order_type == 'TOTAL':
            total_val = cleaned_data.get('total_value')
            if not total_val or total_val <= 0: self.add_error('total_value', _("Valor deve ser positivo."))
            elif price and price > 0: calc_qty = total_val / price
            else: self.add_error('price', _("Preço deve ser positivo."))
        if self.user_profile and crypto and calc_qty and calc_qty > 0:
            try:
                holding = Holding.objects.get(user_profile=self.user_profile, cryptocurrency=crypto)
                if holding.quantity < calc_qty:
                    error_msg = _(f"Saldo insuficiente. Precisa de {calc_qty:.8f}, tem {holding.quantity}.")
                    self.add_error('quantity' if order_type == 'QUANTITY' else 'total_value', error_msg)
            except Holding.DoesNotExist: self.add_error('cryptocurrency', _("Você não possui esta cripto."))
        return cleaned_data
