from django.urls import path
from django.views.generic import RedirectView

from . import views

app_name = 'gym'

urlpatterns = [
    path('', RedirectView.as_view(pattern_name='gym:member_list', permanent=False)),
    path('members/', views.MemberListView.as_view(), name='member_list'),
    path('members/add/', views.MemberCreateView.as_view(), name='member_create'),
    path('members/<int:pk>/', views.MemberDetailView.as_view(), name='member_detail'),
    path('members/<int:pk>/edit/', views.MemberUpdateView.as_view(), name='member_edit'),
    path('members/<int:pk>/toggle-status/', views.MemberToggleStatusView.as_view(), name='member_toggle_status'),
    path('members/<int:member_pk>/assign-plan/', views.SubscriptionAssignView.as_view(), name='subscription_assign'),
    path('members/<int:member_pk>/subscriptions/<int:subscription_pk>/renew/', views.SubscriptionRenewView.as_view(), name='subscription_renew'),

    path('plans/', views.MembershipPlanListView.as_view(), name='plan_list'),
    path('plans/add/', views.MembershipPlanCreateView.as_view(), name='plan_create'),
    path('plans/<int:pk>/', views.MembershipPlanDetailView.as_view(), name='plan_detail'),
    path('plans/<int:pk>/edit/', views.MembershipPlanUpdateView.as_view(), name='plan_edit'),
    path('plans/<int:pk>/toggle-status/', views.MembershipPlanToggleStatusView.as_view(), name='plan_toggle_status'),

    path('subscriptions/', views.MemberSubscriptionListView.as_view(), name='subscription_list'),

    path('payments/', views.PaymentHistoryListView.as_view(), name='payment_list'),
    path('payments/dashboard/', views.PaymentDashboardView.as_view(), name='payment_dashboard'),
    path('payments/<int:pk>/receipt/', views.PaymentReceiptView.as_view(), name='payment_receipt'),
    path('payments/<int:pk>/cancel/', views.PaymentCancelView.as_view(), name='payment_cancel'),
    path('members/<int:member_pk>/payments/collect/', views.PaymentCollectView.as_view(), name='payment_collect'),
]
