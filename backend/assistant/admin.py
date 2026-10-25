from django.contrib import admin

from .models import Conversation, Turn


class TurnInline(admin.StackedInline):
    model = Turn
    extra = 0
    can_delete = False
    fields = ('status', 'prompt', 'reply', 'error', 'activity', 'cost_usd', 'created_at', 'finished_at')
    readonly_fields = fields


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    """Read-only: the record of what the agent was asked and what it did is the point of keeping it."""
    list_display = ('title', 'created_by', 'created_at', 'updated_at')
    search_fields = ('title', 'turns__prompt', 'turns__reply')
    readonly_fields = ('title', 'session_id', 'created_by', 'created_at', 'updated_at')
    inlines = [TurnInline]

    def has_add_permission(self, request):
        return False
