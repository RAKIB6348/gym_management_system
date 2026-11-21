from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from .forms import MemberForm
from .models import Member


class MemberListView(LoginRequiredMixin, ListView):
    model = Member
    template_name = 'gym/member_list.html'
    context_object_name = 'members'
    paginate_by = 10

    def get_queryset(self):
        queryset = Member.objects.all()
        query = self.request.GET.get('q', '').strip()
        status = self.request.GET.get('status', '').strip()

        if query:
            queryset = queryset.filter(
                Q(full_name__icontains=query)
                | Q(mobile_number__icontains=query)
                | Q(member_id__icontains=query)
            )
        if status in {Member.Status.ACTIVE, Member.Status.INACTIVE}:
            queryset = queryset.filter(status=status)

        return queryset.order_by('-created_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['search_query'] = self.request.GET.get('q', '').strip()
        context['status_filter'] = self.request.GET.get('status', '').strip()
        context['status_choices'] = Member.Status.choices
        context['total_members'] = Member.objects.count()
        context['active_members'] = Member.objects.filter(status=Member.Status.ACTIVE).count()
        context['inactive_members'] = Member.objects.filter(status=Member.Status.INACTIVE).count()
        query_params = self.request.GET.copy()
        query_params.pop('page', None)
        context['query_string'] = query_params.urlencode()
        return context


class MemberCreateView(LoginRequiredMixin, CreateView):
    model = Member
    form_class = MemberForm
    template_name = 'gym/member_form.html'

    def get_success_url(self):
        return reverse_lazy('gym:member_detail', kwargs={'pk': self.object.pk})

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, f'Member {self.object.member_id} was created successfully.')
        return response

    def form_invalid(self, form):
        messages.error(self.request, 'Please correct the errors below.')
        return super().form_invalid(form)


class MemberDetailView(LoginRequiredMixin, DetailView):
    model = Member
    template_name = 'gym/member_detail.html'
    context_object_name = 'member'


class MemberUpdateView(LoginRequiredMixin, UpdateView):
    model = Member
    form_class = MemberForm
    template_name = 'gym/member_form.html'

    def get_success_url(self):
        return reverse_lazy('gym:member_detail', kwargs={'pk': self.object.pk})

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, f'Member {self.object.member_id} was updated successfully.')
        return response

    def form_invalid(self, form):
        messages.error(self.request, 'Please correct the errors below.')
        return super().form_invalid(form)


class MemberToggleStatusView(LoginRequiredMixin, View):
    def post(self, request, pk):
        member = get_object_or_404(Member, pk=pk)
        if member.status == Member.Status.ACTIVE:
            member.status = Member.Status.INACTIVE
            verb = 'deactivated'
        else:
            member.status = Member.Status.ACTIVE
            verb = 'activated'
        member.save(update_fields=['status', 'updated_at'])
        messages.success(request, f'Member {member.member_id} was {verb}.')
        next_url = request.POST.get('next') or reverse_lazy('gym:member_detail', kwargs={'pk': member.pk})
        return redirect(next_url)
