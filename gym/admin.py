from django.contrib import admin

from .models import Member, MembershipPlan, MemberSubscription, MembershipPayment


@admin.register(Member)
class MemberAdmin(admin.ModelAdmin):
    list_display = ('member_id', 'full_name', 'mobile_number', 'joining_date', 'status')
    list_filter = ('status', 'joining_date')
    search_fields = ('member_id', 'full_name', 'mobile_number', 'email')
    readonly_fields = ('member_id', 'created_at', 'updated_at')


@admin.register(MembershipPlan)
class MembershipPlanAdmin(admin.ModelAdmin):
    list_display = ('name', 'duration_months', 'price', 'is_active', 'updated_at')
    list_filter = ('is_active', 'duration_months')
    search_fields = ('name', 'description')


@admin.register(MemberSubscription)
class MemberSubscriptionAdmin(admin.ModelAdmin):
    list_display = ('member', 'plan', 'start_date', 'end_date', 'price_at_subscription', 'status')
    list_filter = ('status', 'plan')
    search_fields = ('member__member_id', 'member__full_name', 'plan__name')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(MembershipPayment)
class MembershipPaymentAdmin(admin.ModelAdmin):
    list_display = ('payment_reference', 'member', 'subscription', 'amount', 'payment_date', 'payment_method', 'status', 'collected_by')
    list_filter = ('status', 'payment_method', 'payment_date')
    search_fields = ('payment_reference', 'member__member_id', 'member__full_name', 'transaction_id')
    readonly_fields = ('payment_reference', 'created_at', 'updated_at')
