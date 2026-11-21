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

    path('trainers/', views.TrainerListView.as_view(), name='trainer_list'),
    path('trainers/dashboard/', views.TrainerDashboardView.as_view(), name='trainer_dashboard'),
    path('trainers/add/', views.TrainerCreateView.as_view(), name='trainer_create'),
    path('trainers/<int:pk>/', views.TrainerDetailView.as_view(), name='trainer_detail'),
    path('trainers/<int:pk>/edit/', views.TrainerUpdateView.as_view(), name='trainer_edit'),
    path('trainers/<int:pk>/toggle-status/', views.TrainerToggleStatusView.as_view(), name='trainer_toggle_status'),
    path('trainers/<int:trainer_pk>/assign-member/', views.TrainerAssignmentCreateView.as_view(), name='trainer_assign_member'),
    path('trainers/<int:trainer_pk>/availability/', views.TrainerAvailabilityManageView.as_view(), name='trainer_availability'),
    path('trainers/availability/<int:pk>/delete/', views.TrainerAvailabilityDeleteView.as_view(), name='trainer_availability_delete'),
    path('trainers/assignments/<int:pk>/end/', views.TrainerAssignmentEndView.as_view(), name='trainer_assignment_end'),
    path('members/<int:member_pk>/assign-trainer/', views.TrainerAssignmentCreateView.as_view(), name='member_assign_trainer'),

    path('classes/', views.GymClassListView.as_view(), name='class_list'),
    path('classes/dashboard/', views.ClassDashboardView.as_view(), name='class_dashboard'),
    path('classes/schedule/', views.WeeklyScheduleView.as_view(), name='weekly_schedule'),
    path('classes/add/', views.GymClassCreateView.as_view(), name='class_create'),
    path('classes/<int:pk>/', views.GymClassDetailView.as_view(), name='class_detail'),
    path('classes/<int:pk>/edit/', views.GymClassUpdateView.as_view(), name='class_edit'),
    path('classes/<int:pk>/toggle-status/', views.GymClassToggleStatusView.as_view(), name='class_toggle_status'),
    path('classes/<int:class_pk>/schedules/add/', views.ClassScheduleCreateView.as_view(), name='class_schedule_add'),
    path('classes/schedules/<int:pk>/toggle/', views.ClassScheduleToggleView.as_view(), name='class_schedule_toggle'),
    path('classes/<int:class_pk>/sessions/generate/', views.ClassSessionGenerateView.as_view(), name='class_session_generate'),
    path('classes/sessions/<int:pk>/cancel/', views.ClassSessionCancelView.as_view(), name='class_session_cancel'),
    path('classes/sessions/<int:pk>/enroll/', views.ClassSessionEnrollView.as_view(), name='class_session_enroll'),
    path('classes/enrollments/<int:pk>/cancel/', views.ClassEnrollmentCancelView.as_view(), name='class_enrollment_cancel'),
]
