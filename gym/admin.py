from django.contrib import admin

from .models import Member


@admin.register(Member)
class MemberAdmin(admin.ModelAdmin):
    list_display = ('member_id', 'full_name', 'mobile_number', 'joining_date', 'status')
    list_filter = ('status', 'joining_date')
    search_fields = ('member_id', 'full_name', 'mobile_number', 'email')
    readonly_fields = ('member_id', 'created_at', 'updated_at')
