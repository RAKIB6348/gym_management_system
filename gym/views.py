from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from .forms import MemberForm, MembershipPlanForm, SubscriptionAssignForm
from .models import Member, MemberSubscription, MembershipPlan


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

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = timezone.localdate()
        subscriptions = list(
            self.object.subscriptions.select_related('plan').order_by('-start_date', '-created_at')
        )
        for subscription in subscriptions:
            subscription.display_status = subscription.current_status(today=today)
            if subscription.display_status == MemberSubscription.Status.ACTIVE:
                subscription.days_remaining_value = (subscription.end_date - today).days
            elif subscription.display_status == MemberSubscription.Status.UPCOMING:
                subscription.days_remaining_value = (subscription.start_date - today).days
            else:
                subscription.days_remaining_value = 0

        current_subscription = None
        for sub in subscriptions:
            if sub.display_status == MemberSubscription.Status.ACTIVE:
                current_subscription = sub
                break
        if current_subscription is None:
            upcoming = [s for s in subscriptions if s.display_status == MemberSubscription.Status.UPCOMING]
            if upcoming:
                current_subscription = sorted(upcoming, key=lambda s: s.start_date)[0]

        context['subscriptions'] = subscriptions
        context['current_subscription'] = current_subscription
        context['today'] = today
        return context


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


class MembershipPlanListView(LoginRequiredMixin, ListView):
    model = MembershipPlan
    template_name = 'gym/plan_list.html'
    context_object_name = 'plans'
    paginate_by = 10

    def get_queryset(self):
        queryset = MembershipPlan.objects.all()
        query = self.request.GET.get('q', '').strip()
        status = self.request.GET.get('status', '').strip()
        if query:
            queryset = queryset.filter(Q(name__icontains=query) | Q(description__icontains=query))
        if status == 'active':
            queryset = queryset.filter(is_active=True)
        elif status == 'inactive':
            queryset = queryset.filter(is_active=False)
        return queryset.order_by('duration_months', 'name')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['search_query'] = self.request.GET.get('q', '').strip()
        context['status_filter'] = self.request.GET.get('status', '').strip()
        query_params = self.request.GET.copy()
        query_params.pop('page', None)
        context['query_string'] = query_params.urlencode()
        return context


class MembershipPlanCreateView(LoginRequiredMixin, CreateView):
    model = MembershipPlan
    form_class = MembershipPlanForm
    template_name = 'gym/plan_form.html'

    def get_success_url(self):
        return reverse('gym:plan_detail', kwargs={'pk': self.object.pk})

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, f'Plan "{self.object.name}" was created successfully.')
        return response

    def form_invalid(self, form):
        messages.error(self.request, 'Please correct the errors below.')
        return super().form_invalid(form)


class MembershipPlanDetailView(LoginRequiredMixin, DetailView):
    model = MembershipPlan
    template_name = 'gym/plan_detail.html'
    context_object_name = 'plan'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        recent_subscriptions = self.object.subscriptions.select_related('member').order_by('-created_at')[:10]
        today = timezone.localdate()
        for sub in recent_subscriptions:
            sub.display_status = sub.current_status(today=today)
        context['recent_subscriptions'] = recent_subscriptions
        return context


class MembershipPlanUpdateView(LoginRequiredMixin, UpdateView):
    model = MembershipPlan
    form_class = MembershipPlanForm
    template_name = 'gym/plan_form.html'

    def get_success_url(self):
        return reverse('gym:plan_detail', kwargs={'pk': self.object.pk})

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, f'Plan "{self.object.name}" was updated successfully.')
        return response

    def form_invalid(self, form):
        messages.error(self.request, 'Please correct the errors below.')
        return super().form_invalid(form)


class MembershipPlanToggleStatusView(LoginRequiredMixin, View):
    def post(self, request, pk):
        plan = get_object_or_404(MembershipPlan, pk=pk)
        plan.is_active = not plan.is_active
        plan.save(update_fields=['is_active', 'updated_at'])
        state = 'activated' if plan.is_active else 'deactivated'
        messages.success(request, f'Plan "{plan.name}" was {state}.')
        next_url = request.POST.get('next') or reverse('gym:plan_detail', kwargs={'pk': plan.pk})
        return redirect(next_url)


class MemberSubscriptionListView(LoginRequiredMixin, ListView):
    model = MemberSubscription
    template_name = 'gym/subscription_list.html'
    context_object_name = 'subscriptions'
    paginate_by = 10

    def get_queryset(self):
        queryset = MemberSubscription.objects.select_related('member', 'plan').all()
        query = self.request.GET.get('q', '').strip()
        status = self.request.GET.get('status', '').strip()

        if query:
            queryset = queryset.filter(
                Q(member__full_name__icontains=query)
                | Q(member__member_id__icontains=query)
                | Q(member__mobile_number__icontains=query)
                | Q(plan__name__icontains=query)
            )
        if status in {choice for choice, _ in MemberSubscription.Status.choices}:
            today = timezone.localdate()
            if status == MemberSubscription.Status.CANCELLED:
                queryset = queryset.filter(status=MemberSubscription.Status.CANCELLED)
            elif status == MemberSubscription.Status.UPCOMING:
                queryset = queryset.exclude(status=MemberSubscription.Status.CANCELLED).filter(start_date__gt=today)
            elif status == MemberSubscription.Status.EXPIRED:
                queryset = queryset.exclude(status=MemberSubscription.Status.CANCELLED).filter(end_date__lt=today)
            elif status == MemberSubscription.Status.ACTIVE:
                queryset = queryset.exclude(status=MemberSubscription.Status.CANCELLED).filter(
                    start_date__lte=today, end_date__gte=today
                )
        return queryset.order_by('-start_date', '-created_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = timezone.localdate()
        for subscription in context['subscriptions']:
            subscription.display_status = subscription.current_status(today=today)
        context['search_query'] = self.request.GET.get('q', '').strip()
        context['status_filter'] = self.request.GET.get('status', '').strip()
        context['status_choices'] = MemberSubscription.Status.choices
        query_params = self.request.GET.copy()
        query_params.pop('page', None)
        context['query_string'] = query_params.urlencode()
        return context


class SubscriptionAssignView(LoginRequiredMixin, CreateView):
    model = MemberSubscription
    form_class = SubscriptionAssignForm
    template_name = 'gym/subscription_form.html'

    def dispatch(self, request, *args, **kwargs):
        self.member = get_object_or_404(Member, pk=kwargs['member_pk'])
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['member'] = self.member
        return kwargs

    def get_initial(self):
        initial = super().get_initial()
        initial['start_date'] = timezone.localdate()
        return initial

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['member'] = self.member
        context['is_renewal'] = False
        context['plans'] = MembershipPlan.objects.filter(is_active=True).order_by('duration_months', 'name')
        return context

    def form_valid(self, form):
        try:
            with transaction.atomic():
                self.object = form.save()
        except Exception as exc:
            form.add_error(None, str(exc))
            return self.form_invalid(form)
        messages.success(
            self.request,
            f'Membership plan "{self.object.plan.name}" assigned to {self.member.full_name}.'
        )
        return redirect('gym:member_detail', pk=self.member.pk)

    def form_invalid(self, form):
        messages.error(self.request, 'Please correct the errors below.')
        return super().form_invalid(form)


class SubscriptionRenewView(LoginRequiredMixin, CreateView):
    model = MemberSubscription
    form_class = SubscriptionAssignForm
    template_name = 'gym/subscription_form.html'

    def dispatch(self, request, *args, **kwargs):
        self.member = get_object_or_404(Member, pk=kwargs['member_pk'])
        self.subscription = get_object_or_404(
            MemberSubscription.objects.select_related('plan'), pk=kwargs['subscription_pk'], member=self.member
        )
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['member'] = self.member
        return kwargs

    def get_initial(self):
        initial = super().get_initial()
        today = timezone.localdate()
        latest_blocking = (
            MemberSubscription.objects.filter(member=self.member, status__in=MemberSubscription.blocking_statuses())
            .order_by('-end_date')
            .first()
        )
        if latest_blocking and latest_blocking.end_date >= today:
            initial['start_date'] = latest_blocking.end_date + timedelta(days=1)
        else:
            # Expired/no active membership - allow selected start date, default today.
            initial['start_date'] = today
        initial['plan'] = self.subscription.plan_id
        return initial

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['member'] = self.member
        context['is_renewal'] = True
        context['renewed_subscription'] = self.subscription
        context['plans'] = MembershipPlan.objects.filter(is_active=True).order_by('duration_months', 'name')
        return context

    def form_valid(self, form):
        try:
            with transaction.atomic():
                self.object = form.save()
        except Exception as exc:
            form.add_error(None, str(exc))
            return self.form_invalid(form)
        messages.success(self.request, f'Membership renewed for {self.member.full_name}.')
        return redirect('gym:member_detail', pk=self.member.pk)

    def form_invalid(self, form):
        messages.error(self.request, 'Please correct the errors below.')
        return super().form_invalid(form)
