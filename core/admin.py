# core/admin.py
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User

from .models import Cryptocurrency, UserProfile, Holding, Transaction

class UserProfileInline(admin.StackedInline):
    model = UserProfile
    can_delete = False
    verbose_name_plural = 'Perfil do Usuário'
    fk_name = 'user'
    # Excluir os campos brutos criptografados da visualização inline
    exclude = ('_binance_api_key', '_binance_api_secret')


class CustomUserAdmin(BaseUserAdmin):
    inlines = (UserProfileInline,)
    list_display = ('username', 'email', 'first_name', 'last_name', 'is_staff', 'get_preferred_fiat')
    list_select_related = ('profile',)

    def get_preferred_fiat(self, instance):
        if hasattr(instance, 'profile'):
            return instance.profile.preferred_fiat_currency
        return "N/A"
    get_preferred_fiat.short_description = 'Moeda Fiat Preferida'


admin.site.unregister(User)
admin.site.register(User, CustomUserAdmin)


@admin.register(Cryptocurrency)
class CryptocurrencyAdmin(admin.ModelAdmin):
    list_display = ('symbol', 'name', 'logo_url', 'current_price', 'price_currency', 'last_updated')
    search_fields = ('symbol', 'name')
    # Removido list_editable para segurança e consistência
    # list_editable = ('current_price', 'price_currency', 'last_updated')


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    # Exibimos a chave mascarada e se o segredo está definido
    list_display = ('user', 'preferred_fiat_currency', 'binance_api_key_masked', 'binance_api_secret_is_set')
    search_fields = ('user__username', 'user__email')
    list_select_related = ('user',)
    # Importante: Excluir os campos brutos do formulário do admin
    exclude = ('_binance_api_key', '_binance_api_secret')
    # Adicionar os campos de propriedade para que possam ser editados
    fields = ('user', 'binance_api_key', 'binance_api_secret', 'preferred_fiat_currency')
    readonly_fields = ('user',) # O usuário não deve ser alterado aqui

    def binance_api_key_masked(self, obj):
        # Acessa a propriedade que já descriptografa a chave
        key = obj.binance_api_key
        if key and key != "DECRYPTION_FAILED":
            return f"{key[:4]}...{key[-4:]}"
        elif key == "DECRYPTION_FAILED":
            return "Erro ao ler a chave"
        return "Não definida"
    binance_api_key_masked.short_description = 'Chave API Binance (Mascarada)'

    def binance_api_secret_is_set(self, obj):
        # Acessa a propriedade que descriptografa o segredo
        secret = obj.binance_api_secret
        if secret and secret != "DECRYPTION_FAILED":
            return True
        return False
    binance_api_secret_is_set.boolean = True # Exibe como um ícone de 'sim/não'
    binance_api_secret_is_set.short_description = 'Segredo API Definido?'


@admin.register(Holding)
class HoldingAdmin(admin.ModelAdmin):
    list_display = ('user_profile_username', 'cryptocurrency_symbol', 'quantity', 'average_buy_price')
    list_filter = ('cryptocurrency',)
    search_fields = ('user_profile__user__username', 'cryptocurrency__symbol', 'cryptocurrency__name')
    list_select_related = ('user_profile__user', 'cryptocurrency')
    raw_id_fields = ('user_profile', 'cryptocurrency')

    def user_profile_username(self, obj):
        return obj.user_profile.user.username
    user_profile_username.short_description = 'Usuário'
    user_profile_username.admin_order_field = 'user_profile__user__username'

    def cryptocurrency_symbol(self, obj):
        return obj.cryptocurrency.symbol
    cryptocurrency_symbol.short_description = 'Cripto Símbolo'
    cryptocurrency_symbol.admin_order_field = 'cryptocurrency__symbol'


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ('transaction_date', 'user_profile_username', 'transaction_type', 'cryptocurrency_symbol', 'quantity_crypto', 'price_per_unit', 'total_value', 'fees')
    list_filter = ('transaction_type', 'cryptocurrency', 'transaction_date', 'timestamp')
    search_fields = ('user_profile__user__username', 'cryptocurrency__symbol', 'cryptocurrency__name', 'binance_order_id')
    date_hierarchy = 'transaction_date'
    list_select_related = ('user_profile__user', 'cryptocurrency')
    raw_id_fields = ('user_profile', 'cryptocurrency')
    fieldsets = (
        (None, {'fields': ('user_profile', 'transaction_type', 'transaction_date', 'timestamp')}),
        ('Detalhes da Criptomoeda', {'fields': ('cryptocurrency', 'quantity_crypto')}),
        ('Valores (Moeda Base da Cripto)', {'fields': ('price_per_unit', 'total_value', 'fees')}),
        ('Informações Adicionais', {'fields': ('binance_order_id', 'notes'), 'classes': ('collapse',)}),
    )
    readonly_fields = ('timestamp', 'total_value')

    def user_profile_username(self, obj):
        return obj.user_profile.user.username
    user_profile_username.short_description = 'Usuário'
    user_profile_username.admin_order_field = 'user_profile__user__username'

    def cryptocurrency_symbol(self, obj):
        return obj.cryptocurrency.symbol
    cryptocurrency_symbol.short_description = 'Cripto Símbolo'
    cryptocurrency_symbol.admin_order_field = 'cryptocurrency__symbol'

