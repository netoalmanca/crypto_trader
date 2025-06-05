# core/forms.py
from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth.models import User
from django.utils.translation import gettext_lazy as _
from django.utils import timezone 
from .models import Cryptocurrency, Transaction, Holding, UserProfile, FIAT_CURRENCY_CHOICES 
from decimal import Decimal

class CustomUserCreationForm(UserCreationForm):
    email = forms.EmailField(
        required=True, 
        widget=forms.EmailInput(attrs={'class': 'form-input', 'placeholder': 'Seu melhor email'})
    )
    first_name = forms.CharField(
        label=_("Nome"),
        max_length=30, 
        required=False, 
        widget=forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Nome (Opcional)'})
    )
    last_name = forms.CharField(
        label=_("Sobrenome"),
        max_length=150, 
        required=False, 
        widget=forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Sobrenome (Opcional)'})
    )
    
    class Meta(UserCreationForm.Meta): 
        model = User
        fields = UserCreationForm.Meta.fields + ('email', 'first_name', 'last_name')
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Nome de Usuário'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if 'password2' in self.fields:
            self.fields['password2'].help_text = None


class CustomAuthenticationForm(AuthenticationForm):
    username = forms.CharField(widget=forms.TextInput(attrs={'class': 'form-input', 'autofocus': True, 'placeholder': 'Nome de Usuário'}))
    password = forms.CharField(widget=forms.PasswordInput(attrs={'class': 'form-input', 'placeholder': 'Senha'}))


class TransactionForm(forms.ModelForm):
    transaction_date = forms.DateTimeField(
        label=_("Data da Transação"),
        widget=forms.DateTimeInput(attrs={'type': 'datetime-local', 'class': 'form-input'}),
        initial=timezone.now
    )
    cryptocurrency = forms.ModelChoiceField(
        queryset=Cryptocurrency.objects.all().order_by('name'),
        widget=forms.Select(attrs={'class': 'form-input'}),
        label=_("Criptomoeda")
    )
    transaction_type = forms.ChoiceField(
        choices=[choice for choice in Transaction.TRANSACTION_TYPE_CHOICES if choice[0] in ['BUY', 'SELL']],
        widget=forms.Select(attrs={'class': 'form-input'}),
        label=_("Tipo de Transação")
    )
    
    class Meta:
        model = Transaction
        fields = [
            'cryptocurrency', 
            'transaction_type', 
            'quantity_crypto', 
            'price_per_unit', 
            'fees',           
            'transaction_date', 
            'notes'
        ]
        widgets = {
            'quantity_crypto': forms.NumberInput(attrs={'class': 'form-input', 'placeholder': 'Ex: 0.5', 'step': 'any'}),
            'price_per_unit': forms.NumberInput(attrs={'class': 'form-input', 'placeholder': 'Preço na moeda base da cripto', 'step': 'any'}),
            'fees': forms.NumberInput(attrs={'class': 'form-input', 'placeholder': 'Taxas na moeda base da cripto', 'step': 'any'}),
            'notes': forms.Textarea(attrs={'class': 'form-input', 'rows': 3, 'placeholder': 'Opcional (Ex: corretora, motivo)'}),
        }
        labels = {
            'quantity_crypto': _("Quantidade (Cripto)"),
            'price_per_unit': _("Preço por Unidade (Moeda Base)"),
            'fees': _("Taxas (Moeda Base)"),
            'notes': _("Notas"),
        }

    def __init__(self, *args, **kwargs):
        self.user_profile = kwargs.pop('user_profile', None) 
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.fees is None:
            self.initial['fees'] = Decimal('0.00')


    def clean_quantity_crypto(self):
        quantity = self.cleaned_data.get('quantity_crypto')
        if quantity is not None and quantity <= 0:
            raise forms.ValidationError(_("A quantidade deve ser maior que zero."))
        return quantity

    def clean_price_per_unit(self):
        price = self.cleaned_data.get('price_per_unit')
        transaction_type = self.cleaned_data.get("transaction_type")
        if transaction_type in ['BUY', 'SELL']: 
            if price is None: 
                 raise forms.ValidationError(_("O preço por unidade é obrigatório para compras e vendas."))
            if price < 0: 
                raise forms.ValidationError(_("O preço por unidade não pode ser negativo."))
        return price
    
    def clean_fees(self):
        fees = self.cleaned_data.get('fees')
        if fees is not None and fees < 0:
            raise forms.ValidationError(_("As taxas não podem ser negativas."))
        return fees if fees is not None else Decimal('0.00') 

    def clean(self):
        cleaned_data = super().clean()
        transaction_type = cleaned_data.get("transaction_type")
        quantity_crypto = cleaned_data.get("quantity_crypto")
        cryptocurrency = cleaned_data.get("cryptocurrency")

        if transaction_type == 'SELL' and self.user_profile and cryptocurrency and quantity_crypto:
            try:
                holding = Holding.objects.get(user_profile=self.user_profile, cryptocurrency=cryptocurrency)
                if holding.quantity < quantity_crypto:
                    self.add_error('quantity_crypto', 
                        _("Você não pode vender mais %(cryptocurrency)s do que possui (Saldo atual: %(current_holding)s).") % 
                        {'cryptocurrency': cryptocurrency.symbol, 'current_holding': holding.quantity }
                    )
            except Holding.DoesNotExist:
                self.add_error('cryptocurrency',
                     _("Você não possui %(cryptocurrency)s para vender.") % {'cryptocurrency': cryptocurrency.symbol}
                )
        
        return cleaned_data

class UserProfileAPIForm(forms.ModelForm):
    binance_api_key = forms.CharField(
        label=_("Sua Chave API da Binance (Testnet)"),
        widget=forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Cole sua chave API aqui'}),
        required=False, 
        help_text=_("Certifique-se de que esta chave tem permissões para consulta de saldo e trading na Testnet.")
    )
    binance_api_secret = forms.CharField(
        label=_("Seu Segredo API da Binance (Testnet)"),
        widget=forms.PasswordInput(attrs={'class': 'form-input', 'placeholder': 'Cole seu segredo API aqui', 'render_value': False}),
        required=False, 
        help_text=_("Mantenha seu segredo API seguro. Ele será armazenado aqui (atualmente em texto plano - TODO: Criptografar). Se deixar em branco, o segredo existente não será alterado.")
    )
    preferred_fiat_currency = forms.ChoiceField(
        label=_("Sua Moeda Fiat Preferida"),
        choices=FIAT_CURRENCY_CHOICES, 
        widget=forms.Select(attrs={'class': 'form-input'}),
        help_text=_("Usada para exibir valores totais e, futuramente, para conversões.")
    )

    class Meta:
        model = UserProfile
        fields = ['binance_api_key', 'binance_api_secret', 'preferred_fiat_currency']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def clean_binance_api_secret(self):
        secret = self.cleaned_data.get('binance_api_secret')
        if self.instance and self.instance.pk and not secret:
            return self.instance.binance_api_secret
        return secret

class TradeForm(forms.Form): # Para COMPRA
    BUY_TYPE_CHOICES = [
        ('QUANTITY', 'Comprar pela Quantidade da Cripto'),
        ('QUOTE_QUANTITY', 'Comprar pelo Valor da Moeda de Cotação')
    ]
    buy_type = forms.ChoiceField(
        choices=BUY_TYPE_CHOICES,
        label=_("Tipo de Compra"),
        widget=forms.RadioSelect(attrs={'class': 'mr-2'}), 
        initial='QUANTITY'
    )
    cryptocurrency = forms.ModelChoiceField(
        queryset=Cryptocurrency.objects.all().order_by('name'),
        widget=forms.Select(attrs={'class': 'form-input'}),
        label=_("Criptomoeda para Comprar")
    )
    quantity = forms.DecimalField(
        label=_("Quantidade da Cripto (ex: 0.01 BTC)"),
        min_value=Decimal('0.00000001'), 
        required=False, 
        widget=forms.NumberInput(attrs={'class': 'form-input', 'placeholder': 'Ex: 0.01', 'step': 'any'}),
        help_text=_("Preencha se 'Comprar pela Quantidade da Cripto' estiver selecionado.")
    )
    quote_quantity = forms.DecimalField(
        label=_("Valor a Gastar (ex: 100 USDT)"),
        min_value=Decimal('0.01'), 
        required=False, 
        widget=forms.NumberInput(attrs={'class': 'form-input', 'placeholder': 'Ex: 100'}),
        help_text=_("Preencha se 'Comprar pelo Valor da Moeda de Cotação' estiver selecionado. O valor é na moeda de cotação da cripto (ex: USDT, BRL).")
    )

    def clean(self):
        cleaned_data = super().clean()
        buy_type = cleaned_data.get('buy_type')
        quantity = cleaned_data.get('quantity')
        quote_quantity = cleaned_data.get('quote_quantity')
        cryptocurrency = cleaned_data.get('cryptocurrency')

        if buy_type == 'QUANTITY':
            if not quantity:
                self.add_error('quantity', _("A quantidade da cripto é obrigatória para este tipo de compra."))
            if quantity and quantity <= 0:
                 self.add_error('quantity', _("A quantidade da cripto deve ser positiva."))
            cleaned_data['quote_quantity'] = None
        elif buy_type == 'QUOTE_QUANTITY':
            if not quote_quantity:
                self.add_error('quote_quantity', _("O valor a gastar é obrigatório para este tipo de compra."))
            if quote_quantity and quote_quantity <= 0:
                self.add_error('quote_quantity', _("O valor a gastar deve ser positivo."))
            cleaned_data['quantity'] = None
        
        if not cryptocurrency:
             self.add_error('cryptocurrency', _("Por favor, selecione uma criptomoeda."))

        return cleaned_data

# Formulário para realizar uma ordem de VENDA a mercado
class MarketSellForm(forms.Form):
    SELL_TYPE_CHOICES = [
        ('QUANTITY', 'Vender Quantidade Específica da Cripto'),
        ('QUOTE_RECEIVE', 'Vender para Receber Valor X na Moeda de Cotação (Aproximado)')
    ]
    sell_type = forms.ChoiceField(
        choices=SELL_TYPE_CHOICES,
        label=_("Tipo de Venda"),
        widget=forms.RadioSelect(attrs={'class': 'mr-2'}),
        initial='QUANTITY'
    )
    cryptocurrency = forms.ModelChoiceField(
        queryset=Cryptocurrency.objects.none(),
        widget=forms.Select(attrs={'class': 'form-input'}),
        label=_("Criptomoeda para Vender (do seu portfólio)")
    )
    quantity = forms.DecimalField(
        label=_("Quantidade da Cripto a Vender"),
        min_value=Decimal('0.00000001'),
        required=False, # Será condicionalmente obrigatório
        widget=forms.NumberInput(attrs={'class': 'form-input', 'placeholder': 'Ex: 0.5', 'step': 'any'}),
        help_text=_("Preencha se 'Vender Quantidade Específica' estiver selecionado.")
    )
    quote_quantity_to_receive = forms.DecimalField(
        label=_("Valor Desejado a Receber (ex: 100 USDT)"),
        min_value=Decimal('0.01'), # Ajustar conforme MIN_NOTIONAL
        required=False, # Será condicionalmente obrigatório
        widget=forms.NumberInput(attrs={'class': 'form-input', 'placeholder': 'Ex: 100'}),
        help_text=_("Preencha se 'Vender para Receber Valor X' estiver selecionado. Este valor é aproximado, a quantidade de cripto a ser vendida será calculada com base no preço de mercado atual.")
    )

    def __init__(self, *args, **kwargs):
        self.user_profile = kwargs.pop('user_profile', None)
        super().__init__(*args, **kwargs)
        if self.user_profile:
            user_holdings = Holding.objects.filter(user_profile=self.user_profile, quantity__gt=Decimal('0'))
            held_crypto_pks = user_holdings.values_list('cryptocurrency__pk', flat=True)
            self.fields['cryptocurrency'].queryset = Cryptocurrency.objects.filter(pk__in=held_crypto_pks).order_by('name')

    def clean(self):
        cleaned_data = super().clean()
        sell_type = cleaned_data.get('sell_type')
        quantity_to_sell = cleaned_data.get('quantity')
        quote_to_receive = cleaned_data.get('quote_quantity_to_receive')
        cryptocurrency = cleaned_data.get('cryptocurrency')

        if not cryptocurrency:
            self.add_error('cryptocurrency', _("Por favor, selecione uma criptomoeda para vender."))
            # Não precisa continuar a validação se não há criptomoeda selecionada
            return cleaned_data

        # Validação comum de saldo para ambos os tipos de venda (a quantidade final a ser vendida)
        # será determinada na view para 'QUOTE_RECEIVE'
        if sell_type == 'QUANTITY':
            if not quantity_to_sell:
                self.add_error('quantity', _("A quantidade da cripto é obrigatória para este tipo de venda."))
            elif quantity_to_sell <= 0:
                self.add_error('quantity', _("A quantidade a vender deve ser positiva."))
            else: # Verifica saldo apenas se a quantidade for válida
                try:
                    holding = Holding.objects.get(user_profile=self.user_profile, cryptocurrency=cryptocurrency)
                    if holding.quantity < quantity_to_sell:
                        self.add_error('quantity', 
                            _("Você não pode vender %(quantity_to_sell)s %(symbol)s. Seu saldo atual é %(current_holding)s %(symbol)s.") %
                            {'quantity_to_sell': quantity_to_sell, 'symbol': cryptocurrency.symbol, 'current_holding': holding.quantity}
                        )
                except Holding.DoesNotExist:
                     self.add_error('cryptocurrency', _("Você não possui %(symbol)s para vender.") % {'symbol': cryptocurrency.symbol})
            cleaned_data['quote_quantity_to_receive'] = None # Limpa o campo não usado

        elif sell_type == 'QUOTE_RECEIVE':
            if not quote_to_receive:
                self.add_error('quote_quantity_to_receive', _("O valor desejado a receber é obrigatório para este tipo de venda."))
            elif quote_to_receive <= 0:
                self.add_error('quote_quantity_to_receive', _("O valor desejado a receber deve ser positivo."))
            # A verificação de saldo exato para 'QUOTE_RECEIVE' é mais complexa aqui, pois depende do preço.
            # Uma verificação básica de que o usuário tem *alguma* quantidade pode ser feita.
            # A view fará a verificação mais precisa após calcular a quantidade de cripto.
            else:
                try:
                    Holding.objects.get(user_profile=self.user_profile, cryptocurrency=cryptocurrency, quantity__gt=Decimal(0))
                except Holding.DoesNotExist:
                    self.add_error('cryptocurrency', _("Você não possui %(symbol)s para vender.") % {'symbol': cryptocurrency.symbol})

            cleaned_data['quantity'] = None # Limpa o campo não usado
        
        return cleaned_data
