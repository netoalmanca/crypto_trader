from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth.models import User
from django.utils.translation import gettext_lazy as _
from django.utils import timezone 
from .models import Cryptocurrency, Transaction, Holding 
from decimal import Decimal

class CustomUserCreationForm(UserCreationForm):
    email = forms.EmailField(
        required=True, 
        widget=forms.EmailInput(attrs={'class': 'w-full px-4 py-2 border border-gray-700 rounded-lg focus:ring-blue-500 focus:border-blue-500 bg-gray-700 text-white placeholder-gray-400', 'placeholder': 'Seu melhor email'})
    )
    first_name = forms.CharField(
        label=_("Nome"),
        max_length=30, 
        required=False, 
        widget=forms.TextInput(attrs={'class': 'w-full px-4 py-2 border border-gray-700 rounded-lg focus:ring-blue-500 focus:border-blue-500 bg-gray-700 text-white placeholder-gray-400', 'placeholder': 'Nome (Opcional)'})
    )
    last_name = forms.CharField(
        label=_("Sobrenome"),
        max_length=150, 
        required=False, 
        widget=forms.TextInput(attrs={'class': 'w-full px-4 py-2 border border-gray-700 rounded-lg focus:ring-blue-500 focus:border-blue-500 bg-gray-700 text-white placeholder-gray-400', 'placeholder': 'Sobrenome (Opcional)'})
    )
    
    class Meta(UserCreationForm.Meta): 
        model = User
        fields = UserCreationForm.Meta.fields + ('email', 'first_name', 'last_name')
        widgets = {
            'username': forms.TextInput(attrs={'class': 'w-full px-4 py-2 border border-gray-700 rounded-lg focus:ring-blue-500 focus:border-blue-500 bg-gray-700 text-white placeholder-gray-400', 'placeholder': 'Nome de Usuário'}),
        }

class CustomAuthenticationForm(AuthenticationForm):
    username = forms.CharField(widget=forms.TextInput(attrs={'class': 'w-full px-4 py-2 border border-gray-700 rounded-lg focus:ring-blue-500 focus:border-blue-500 bg-gray-700 text-white placeholder-gray-400', 'autofocus': True, 'placeholder': 'Nome de Usuário'}))
    password = forms.CharField(widget=forms.PasswordInput(attrs={'class': 'w-full px-4 py-2 border border-gray-700 rounded-lg focus:ring-blue-500 focus:border-blue-500 bg-gray-700 text-white placeholder-gray-400', 'placeholder': 'Senha'}))


class TransactionForm(forms.ModelForm):
    transaction_date = forms.DateTimeField(
        label=_("Data da Transação"),
        widget=forms.DateTimeInput(attrs={'type': 'datetime-local', 'class': 'form-input bg-gray-700 text-white'}),
        initial=timezone.now
    )
    cryptocurrency = forms.ModelChoiceField(
        queryset=Cryptocurrency.objects.all().order_by('name'),
        widget=forms.Select(attrs={'class': 'form-input bg-gray-700 text-white'}),
        label=_("Criptomoeda")
    )
    transaction_type = forms.ChoiceField(
        choices=[choice for choice in Transaction.TRANSACTION_TYPE_CHOICES if choice[0] in ['BUY', 'SELL']],
        widget=forms.Select(attrs={'class': 'form-input bg-gray-700 text-white'}),
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
            'quantity_crypto': forms.NumberInput(attrs={'class': 'form-input bg-gray-700 text-white', 'placeholder': 'Ex: 0.5', 'step': 'any'}),
            'price_per_unit': forms.NumberInput(attrs={'class': 'form-input bg-gray-700 text-white', 'placeholder': 'Preço na moeda base da cripto', 'step': 'any'}),
            'fees': forms.NumberInput(attrs={'class': 'form-input bg-gray-700 text-white', 'placeholder': 'Taxas na moeda base da cripto', 'step': 'any'}),
            'notes': forms.Textarea(attrs={'class': 'form-input bg-gray-700 text-white', 'rows': 3, 'placeholder': 'Opcional'}),
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