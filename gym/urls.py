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
]
