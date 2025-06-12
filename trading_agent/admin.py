from django.contrib import admin
from .models import StrategyLog # (NOVO) Importa o novo modelo

@admin.register(StrategyLog)
class StrategyLogAdmin(admin.ModelAdmin):
    """
    (NOVO) Configuração do Admin para o modelo StrategyLog.
    """
    list_display = ('user_profile', 'period_start_date', 'period_end_date', 'created_at')
    list_filter = ('user_profile',)
    search_fields = ('user_profile__user__username', 'ai_reflection', 'suggested_modifications')
    readonly_fields = ('user_profile', 'period_start_date', 'period_end_date', 'performance_summary', 'ai_reflection', 'suggested_modifications', 'created_at')

    def has_add_permission(self, request):
        # Impede a criação manual de logs, pois eles devem ser gerados apenas pela tarefa Celery.
        return False
