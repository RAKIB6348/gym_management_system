import uuid
from datetime import timedelta
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.db import transaction
from django.db.models import Count, Q, Sum
from django.db.models.functions import Coalesce
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from .forms import (
    MemberForm, MembershipPlanForm, PaymentCollectForm, SubscriptionAssignForm,
    TrainerForm, TrainerAssignmentForm, TrainerAvailabilityForm,
)
from .models import (
    Member, MemberSubscription, MembershipPayment, MembershipPlan,
    Trainer, TrainerAssignment, TrainerAvailability,
)


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
            summary = subscription.payment_summary()
            subscription.total_paid_display = summary['total_paid']
            subscription.remaining_due_display = summary['remaining_due']
            subscription.payment_status_display = summary['payment_status']

        current_subscription = None
        for sub in subscriptions:
            if sub.display_status == MemberSubscription.Status.ACTIVE:
                current_subscription = sub
                break
        if current_subscription is None:
            upcoming = [s for s in subscriptions if s.display_status == MemberSubscription.Status.UPCOMING]
            if upcoming:
                current_subscription = sorted(upcoming, key=lambda s: s.start_date)[0]

        payment_history = list(
            self.object.payments.select_related('subscription', 'subscription__plan', 'collected_by').order_by('-payment_date', '-created_at')
        )
        current_payment_summary = current_subscription.payment_summary() if current_subscription else None

        trainer_assignments = list(
            self.object.trainer_assignments.select_related('trainer').order_by('-start_date', '-created_at')
        )
        current_trainer_assignment = next((a for a in trainer_assignments if a.status == TrainerAssignment.Status.ACTIVE), None)

        context['subscriptions'] = subscriptions
        context['current_subscription'] = current_subscription
        context['today'] = today
        context['payment_history'] = payment_history
        context['current_payment_summary'] = current_payment_summary
        context['trainer_assignments'] = trainer_assignments
        context['current_trainer_assignment'] = current_trainer_assignment
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


class PaymentCollectView(LoginRequiredMixin, View):
    template_name = 'gym/payment_form.html'

    def get_member_and_subscription(self, request, member_pk):
        member = get_object_or_404(Member, pk=member_pk)
        subscription_id = request.GET.get('subscription') or request.POST.get('subscription')
        subscriptions = list(member.subscriptions.select_related('plan').order_by('-start_date', '-created_at'))
        selected = None
        if subscription_id:
            selected = next((s for s in subscriptions if str(s.pk) == str(subscription_id)), None)
        if selected is None:
            today = timezone.localdate()
            for s in subscriptions:
                ds = s.current_status(today=today)
                if ds == MemberSubscription.Status.ACTIVE:
                    selected = s
                    break
            if selected is None:
                upcoming = [s for s in subscriptions if s.current_status(today=today) == MemberSubscription.Status.UPCOMING]
                if upcoming:
                    selected = sorted(upcoming, key=lambda s: s.start_date)[0]
            if selected is None and subscriptions:
                selected = subscriptions[0]
        return member, selected, subscriptions

    def get(self, request, member_pk):
        member, subscription, subscriptions = self.get_member_and_subscription(request, member_pk)
        if not subscription:
            messages.error(request, 'Assign a membership plan before collecting payment.')
            return redirect('gym:member_detail', pk=member.pk)
        summary = subscription.payment_summary()
        form = PaymentCollectForm(subscription=subscription, initial={'payment_date': timezone.localdate()})
        token = uuid.uuid4().hex
        request.session[f'payment_token_{member.pk}'] = token
        context = {
            'member': member,
            'subscription': subscription,
            'subscriptions': subscriptions,
            'summary': summary,
            'form': form,
            'payment_token': token,
        }
        return self._render(request, context)

    def post(self, request, member_pk):
        member, subscription, subscriptions = self.get_member_and_subscription(request, member_pk)
        if not subscription:
            messages.error(request, 'Assign a membership plan before collecting payment.')
            return redirect('gym:member_detail', pk=member.pk)

        token = request.POST.get('payment_token', '')
        session_key = f'payment_token_{member.pk}'
        expected = request.session.get(session_key)
        if not expected or token != expected:
            messages.error(request, 'Duplicate or invalid payment submission. Please try again.')
            return redirect('gym:payment_collect', member_pk=member.pk)

        form = PaymentCollectForm(request.POST, subscription=subscription)
        summary = subscription.payment_summary()
        context = {
            'member': member,
            'subscription': subscription,
            'subscriptions': subscriptions,
            'summary': summary,
            'form': form,
            'payment_token': token,
        }
        if not form.is_valid():
            messages.error(request, 'Please correct the errors below.')
            return self._render(request, context)

        amount = form.cleaned_data['amount']
        try:
            with transaction.atomic():
                locked_subscription = MemberSubscription.objects.select_for_update().select_related('member', 'plan').get(pk=subscription.pk)
                if locked_subscription.member_id != member.pk:
                    raise ValueError('Selected subscription does not belong to this member.')
                paid = locked_subscription.payments.filter(status=MembershipPayment.Status.COMPLETED).aggregate(
                    total=Coalesce(Sum('amount'), Decimal('0.00'))
                )['total'] or Decimal('0.00')
                remaining = locked_subscription.total_fee - paid
                if amount > remaining:
                    form.add_error('amount', f'Payment exceeds remaining due amount (BDT {remaining:.2f}).')
                    raise ValueError('overpayment')
                payment = form.save(commit=False)
                payment.member = member
                payment.subscription = locked_subscription
                payment.collected_by = request.user
                payment.status = MembershipPayment.Status.COMPLETED
                payment.save()
        except ValueError as exc:
            if str(exc) == 'overpayment':
                summary = subscription.payment_summary()
                context['summary'] = summary
                messages.error(request, 'Payment exceeds remaining due amount.')
                return self._render(request, context)
            form.add_error(None, str(exc))
            messages.error(request, 'Could not record payment.')
            return self._render(request, context)

        request.session.pop(session_key, None)
        messages.success(request, f'Payment {payment.payment_reference} recorded successfully. Receipt is available.')
        return redirect('gym:member_detail', pk=member.pk)

    def _render(self, request, context):
        from django.shortcuts import render
        return render(request, self.template_name, context)


class PaymentHistoryListView(LoginRequiredMixin, ListView):
    model = MembershipPayment
    template_name = 'gym/payment_list.html'
    context_object_name = 'payments'
    paginate_by = 10

    def get_queryset(self):
        queryset = MembershipPayment.objects.select_related('member', 'subscription', 'subscription__plan', 'collected_by').all()
        query = self.request.GET.get('q', '').strip()
        method = self.request.GET.get('method', '').strip()
        status = self.request.GET.get('status', '').strip()
        date_from = self.request.GET.get('date_from', '').strip()
        date_to = self.request.GET.get('date_to', '').strip()

        if query:
            queryset = queryset.filter(
                Q(member__full_name__icontains=query)
                | Q(member__member_id__icontains=query)
                | Q(payment_reference__icontains=query)
            )
        if method in {c for c, _ in MembershipPayment.PaymentMethod.choices}:
            queryset = queryset.filter(payment_method=method)
        if status in {c for c, _ in MembershipPayment.Status.choices}:
            queryset = queryset.filter(status=status)
        if date_from:
            queryset = queryset.filter(payment_date__gte=date_from)
        if date_to:
            queryset = queryset.filter(payment_date__lte=date_to)
        return queryset.order_by('-payment_date', '-created_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['search_query'] = self.request.GET.get('q', '').strip()
        context['method_filter'] = self.request.GET.get('method', '').strip()
        context['status_filter'] = self.request.GET.get('status', '').strip()
        context['date_from'] = self.request.GET.get('date_from', '').strip()
        context['date_to'] = self.request.GET.get('date_to', '').strip()
        context['method_choices'] = MembershipPayment.PaymentMethod.choices
        context['status_choices'] = MembershipPayment.Status.choices
        query_params = self.request.GET.copy()
        query_params.pop('page', None)
        context['query_string'] = query_params.urlencode()
        return context


class PaymentCancelView(LoginRequiredMixin, UserPassesTestMixin, View):
    raise_exception = True

    def test_func(self):
        return self.request.user.is_staff or self.request.user.is_superuser

    def post(self, request, pk):
        payment = get_object_or_404(MembershipPayment.objects.select_related('member'), pk=pk)
        if payment.status == MembershipPayment.Status.CANCELLED:
            messages.info(request, f'Payment {payment.payment_reference} is already cancelled.')
        else:
            payment.status = MembershipPayment.Status.CANCELLED
            payment.save(update_fields=['status', 'updated_at'])
            messages.success(request, f'Payment {payment.payment_reference} was cancelled. Totals have been recalculated.')
        next_url = request.POST.get('next') or reverse('gym:payment_list')
        return redirect(next_url)


class PaymentReceiptView(LoginRequiredMixin, View):
    def get(self, request, pk):
        payment = get_object_or_404(
            MembershipPayment.objects.select_related('member', 'subscription', 'subscription__plan', 'collected_by'),
            pk=pk,
        )
        subscription = payment.subscription
        completed_payments = list(
            subscription.payments.filter(status=MembershipPayment.Status.COMPLETED).order_by('payment_date', 'created_at')
        )
        total_paid = sum((p.amount for p in completed_payments), Decimal('0.00'))
        previous_paid = total_paid - payment.amount if payment.status == MembershipPayment.Status.COMPLETED else total_paid
        if previous_paid < Decimal('0.00'):
            previous_paid = Decimal('0.00')
        remaining_due = subscription.total_fee - total_paid
        if remaining_due < Decimal('0.00'):
            remaining_due = Decimal('0.00')

        from io import BytesIO
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable

        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=18*mm, leftMargin=18*mm, topMargin=16*mm, bottomMargin=16*mm)
        styles = getSampleStyleSheet()
        styles.add(ParagraphStyle(name='GymTitle', parent=styles['Title'], fontSize=20, leading=24, textColor=colors.HexColor('#1d6fff'), spaceAfter=2))
        styles.add(ParagraphStyle(name='Muted', parent=styles['Normal'], fontSize=9, textColor=colors.HexColor('#667085'), leading=12))
        styles.add(ParagraphStyle(name='Label', parent=styles['Normal'], fontSize=9, textColor=colors.HexColor('#667085'), leading=11))
        styles.add(ParagraphStyle(name='Value', parent=styles['Normal'], fontSize=10, leading=13, spaceAfter=2))
        styles.add(ParagraphStyle(name='Section', parent=styles['Heading3'], fontSize=11, leading=14, textColor=colors.HexColor('#182230'), spaceBefore=8, spaceAfter=6))

        story = []
        story.append(Paragraph('GymFlow Management System', styles['GymTitle']))
        story.append(Paragraph('123 Fitness Avenue, Dhaka, Bangladesh | +880 1700-000000 | info@gymflow.example', styles['Muted']))
        story.append(Spacer(1, 4*mm))
        story.append(HRFlowable(width='100%', thickness=1, color=colors.HexColor('#e5eaf2'), spaceBefore=0, spaceAfter=8))

        story.append(Paragraph('Payment Receipt', styles['Section']))
        meta = [
            ['Receipt Number', payment.payment_reference, 'Payment Date', payment.payment_date.strftime('%B %d, %Y')],
            ['Collected By', payment.collected_by.get_full_name() or payment.collected_by.username, 'Status', payment.get_status_display()],
        ]
        meta_table = Table(meta, colWidths=[35*mm, 52*mm, 30*mm, 52*mm])
        meta_table.setStyle(TableStyle([
            ('FONTNAME', (0,0), (-1,-1), 'Helvetica'),
            ('FONTSIZE', (0,0), (-1,-1), 9),
            ('TEXTCOLOR', (0,0), (0,-1), colors.HexColor('#667085')),
            ('TEXTCOLOR', (2,0), (2,-1), colors.HexColor('#667085')),
            ('FONTNAME', (1,0), (1,-1), 'Helvetica-Bold'),
            ('FONTNAME', (3,0), (3,-1), 'Helvetica-Bold'),
            ('BOTTOMPADDING', (0,0), (-1,-1), 6),
            ('TOPPADDING', (0,0), (-1,-1), 6),
        ]))
        story.append(meta_table)

        story.append(Paragraph('Member & Subscription', styles['Section']))
        details = [
            ['Member Name', payment.member.full_name, 'Member ID', payment.member.member_id],
            ['Membership Plan', subscription.plan.name, 'Payment Method', payment.get_payment_method_display()],
            ['Subscription Period', f"{subscription.start_date.strftime('%b %d, %Y')} - {subscription.end_date.strftime('%b %d, %Y')}", 'Transaction Ref', payment.transaction_id or 'N/A'],
        ]
        detail_table = Table(details, colWidths=[35*mm, 52*mm, 30*mm, 52*mm])
        detail_table.setStyle(TableStyle([
            ('FONTNAME', (0,0), (-1,-1), 'Helvetica'),
            ('FONTSIZE', (0,0), (-1,-1), 9),
            ('TEXTCOLOR', (0,0), (0,-1), colors.HexColor('#667085')),
            ('TEXTCOLOR', (2,0), (2,-1), colors.HexColor('#667085')),
            ('FONTNAME', (1,0), (1,-1), 'Helvetica-Bold'),
            ('FONTNAME', (3,0), (3,-1), 'Helvetica-Bold'),
            ('BOTTOMPADDING', (0,0), (-1,-1), 6),
            ('TOPPADDING', (0,0), (-1,-1), 6),
        ]))
        story.append(detail_table)

        story.append(Paragraph('Payment Summary', styles['Section']))
        summary_rows = [
            ['Total Membership Fee', f'BDT {subscription.total_fee:.2f}'],
            ['Previous Paid Amount', f'BDT {previous_paid:.2f}'],
            ['Current Payment Amount', f'BDT {payment.amount:.2f}'],
            ['Total Paid Amount', f'BDT {total_paid:.2f}'],
            ['Remaining Due', f'BDT {remaining_due:.2f}'],
        ]
        summary_table = Table(summary_rows, colWidths=[110*mm, 59*mm])
        summary_table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-2), colors.HexColor('#f8fafc')),
            ('BACKGROUND', (0,-1), (-1,-1), colors.HexColor('#eff6ff')),
            ('FONTNAME', (0,0), (-1,-1), 'Helvetica'),
            ('FONTNAME', (0,-1), (-1,-1), 'Helvetica-Bold'),
            ('FONTSIZE', (0,0), (-1,-1), 10),
            ('TEXTCOLOR', (1,0), (1,-1), colors.HexColor('#182230')),
            ('ALIGN', (1,0), (1,-1), 'RIGHT'),
            ('ROWBACKGROUNDS', (0,0), (-1,-2), [colors.HexColor('#f8fafc'), colors.white]),
            ('BOX', (0,0), (-1,-1), 0.5, colors.HexColor('#e5eaf2')),
            ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor('#e5eaf2')),
            ('PADDING', (0,0), (-1,-1), 8),
        ]))
        story.append(summary_table)

        if payment.note:
            story.append(Paragraph('Notes', styles['Section']))
            story.append(Paragraph(payment.note.replace('\n', '<br/>'), styles['Normal']))

        story.append(Spacer(1, 10*mm))
        story.append(HRFlowable(width='100%', thickness=0.7, color=colors.HexColor('#e5eaf2'), spaceBefore=0, spaceAfter=6))
        story.append(Paragraph('This is a system-generated receipt for gym membership payment records.', styles['Muted']))

        doc.build(story)
        buffer.seek(0)
        response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
        response['Content-Disposition'] = f'inline; filename="{payment.payment_reference}.pdf"'
        return response


class PaymentDashboardView(LoginRequiredMixin, View):
    template_name = 'gym/payment_dashboard.html'

    def get(self, request):
        today = timezone.localdate()
        completed = MembershipPayment.objects.filter(status=MembershipPayment.Status.COMPLETED)

        total_collected = completed.aggregate(total=Coalesce(Sum('amount'), Decimal('0.00')))['total'] or Decimal('0.00')
        today_collected = completed.filter(payment_date=today).aggregate(total=Coalesce(Sum('amount'), Decimal('0.00')))['total'] or Decimal('0.00')

        subscriptions = MemberSubscription.objects.all().prefetch_related('payments')
        total_fees = Decimal('0.00')
        total_outstanding = Decimal('0.00')
        outstanding_rows = []
        for sub in subscriptions.select_related('member', 'plan'):
            paid = sum((p.amount for p in sub.payments.all() if p.status == MembershipPayment.Status.COMPLETED), Decimal('0.00'))
            fee = sub.total_fee
            due = fee - paid
            if due < Decimal('0.00'):
                due = Decimal('0.00')
            total_fees += fee
            total_outstanding += due
            if due > Decimal('0.00'):
                sub.paid_display = paid
                sub.due_display = due
                sub.payment_status_display = sub.payment_status(total_paid=paid)
                outstanding_rows.append(sub)
        outstanding_rows.sort(key=lambda s: (s.due_display, s.member.full_name), reverse=True)

        recent_payments = MembershipPayment.objects.select_related('member', 'subscription__plan', 'collected_by').order_by('-payment_date', '-created_at')[:10]
        method_breakdown = []
        for value, label in MembershipPayment.PaymentMethod.choices:
            method_qs = completed.filter(payment_method=value)
            agg = method_qs.aggregate(total=Coalesce(Sum('amount'), Decimal('0.00')), count=Count('id'))
            method_breakdown.append({'label': label, 'total': agg['total'] or Decimal('0.00'), 'count': agg['count']})

        context = {
            'total_fees': total_fees,
            'total_collected': total_collected,
            'total_outstanding': total_outstanding,
            'today_collected': today_collected,
            'recent_payments': recent_payments,
            'outstanding_rows': outstanding_rows[:10],
            'method_breakdown': method_breakdown,
        }
        return self._render(request, context)

    def _render(self, request, context):
        from django.shortcuts import render
        return render(request, self.template_name, context)


class TrainerListView(LoginRequiredMixin, ListView):
    model = Trainer
    template_name = 'gym/trainer_list.html'
    context_object_name = 'trainers'
    paginate_by = 10

    def get_queryset(self):
        qs = Trainer.objects.all().annotate(
            assigned_members_count=Count('assignments__member', filter=Q(assignments__status=TrainerAssignment.Status.ACTIVE), distinct=True)
        )
        q = self.request.GET.get('q', '').strip()
        status = self.request.GET.get('status', '').strip()
        specialization = self.request.GET.get('specialization', '').strip()
        if q:
            qs = qs.filter(Q(full_name__icontains=q) | Q(phone__icontains=q) | Q(trainer_id__icontains=q))
        if status in {Trainer.Status.ACTIVE, Trainer.Status.INACTIVE}:
            qs = qs.filter(status=status)
        if specialization:
            qs = qs.filter(specialization__icontains=specialization)
        return qs.order_by('-created_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['search_query'] = self.request.GET.get('q', '').strip()
        context['status_filter'] = self.request.GET.get('status', '').strip()
        context['specialization_filter'] = self.request.GET.get('specialization', '').strip()
        context['status_choices'] = Trainer.Status.choices
        params = self.request.GET.copy()
        params.pop('page', None)
        context['query_string'] = params.urlencode()
        return context


class TrainerCreateView(LoginRequiredMixin, CreateView):
    model = Trainer
    form_class = TrainerForm
    template_name = 'gym/trainer_form.html'

    def get_success_url(self):
        return reverse('gym:trainer_detail', kwargs={'pk': self.object.pk})

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, f'Trainer {self.object.trainer_id} was created successfully.')
        return response

    def form_invalid(self, form):
        messages.error(self.request, 'Please correct the errors below.')
        return super().form_invalid(form)


class TrainerDetailView(LoginRequiredMixin, DetailView):
    model = Trainer
    template_name = 'gym/trainer_detail.html'
    context_object_name = 'trainer'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        assignments = list(self.object.assignments.select_related('member').order_by('-start_date', '-created_at'))
        context['active_assignments'] = [a for a in assignments if a.status == TrainerAssignment.Status.ACTIVE]
        context['assignment_history'] = assignments
        context['availabilities'] = self.object.availabilities.all().order_by('day_of_week', 'start_time')
        return context


class TrainerUpdateView(LoginRequiredMixin, UpdateView):
    model = Trainer
    form_class = TrainerForm
    template_name = 'gym/trainer_form.html'

    def get_success_url(self):
        return reverse('gym:trainer_detail', kwargs={'pk': self.object.pk})

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, f'Trainer {self.object.trainer_id} was updated successfully.')
        return response

    def form_invalid(self, form):
        messages.error(self.request, 'Please correct the errors below.')
        return super().form_invalid(form)


class TrainerToggleStatusView(LoginRequiredMixin, View):
    def post(self, request, pk):
        trainer = get_object_or_404(Trainer, pk=pk)
        trainer.status = Trainer.Status.INACTIVE if trainer.status == Trainer.Status.ACTIVE else Trainer.Status.ACTIVE
        trainer.save(update_fields=['status', 'updated_at'])
        messages.success(request, f'Trainer {trainer.trainer_id} was {"activated" if trainer.status == Trainer.Status.ACTIVE else "deactivated"}.')
        return redirect(request.POST.get('next') or reverse('gym:trainer_detail', kwargs={'pk': trainer.pk}))


class TrainerAssignmentCreateView(LoginRequiredMixin, CreateView):
    model = TrainerAssignment
    form_class = TrainerAssignmentForm
    template_name = 'gym/trainer_assignment_form.html'

    def dispatch(self, request, *args, **kwargs):
        self.trainer = None
        self.member = None
        if 'trainer_pk' in kwargs:
            self.trainer = get_object_or_404(Trainer, pk=kwargs['trainer_pk'])
        if 'member_pk' in kwargs:
            self.member = get_object_or_404(Member, pk=kwargs['member_pk'])
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['trainer'] = self.trainer
        kwargs['member'] = self.member
        return kwargs

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.instance._allow_reassign = True
        return form

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['trainer'] = self.trainer
        context['member'] = self.member
        context['current_assignment'] = None
        member = self.member or (self.object.member if self.object and self.object.pk else None)
        if member:
            context['current_assignment'] = TrainerAssignment.objects.filter(member=member, status=TrainerAssignment.Status.ACTIVE).select_related('trainer').first()
        return context

    def form_valid(self, form):
        try:
            with transaction.atomic():
                member = form.cleaned_data['member']
                trainer = form.cleaned_data['trainer']
                if trainer.status != Trainer.Status.ACTIVE:
                    form.add_error('trainer', 'Inactive trainers cannot receive new assignments.')
                    return self.form_invalid(form)
                existing = TrainerAssignment.objects.select_for_update().filter(member=member, status=TrainerAssignment.Status.ACTIVE).first()
                if existing:
                    # Reassign: end existing assignment, preserve history
                    existing.status = TrainerAssignment.Status.COMPLETED
                    existing.end_date = form.cleaned_data['start_date'] - timedelta(days=1) if form.cleaned_data.get('start_date') else timezone.localdate()
                    if existing.end_date and existing.start_date and existing.end_date < existing.start_date:
                        existing.end_date = existing.start_date
                    existing.save(update_fields=['status', 'end_date', 'updated_at'])
                self.object = form.save(commit=False)
                self.object.status = TrainerAssignment.Status.ACTIVE
                self.object.save()
        except Exception as exc:
            form.add_error(None, str(exc))
            return self.form_invalid(form)
        messages.success(self.request, f'Trainer {self.object.trainer.full_name} assigned to {self.object.member.full_name}.')
        if self.trainer:
            return redirect('gym:trainer_detail', pk=self.trainer.pk)
        return redirect('gym:member_detail', pk=self.object.member.pk)

    def form_invalid(self, form):
        messages.error(self.request, 'Please correct the errors below.')
        return super().form_invalid(form)


class TrainerAssignmentEndView(LoginRequiredMixin, View):
    def post(self, request, pk):
        assignment = get_object_or_404(TrainerAssignment, pk=pk)
        if assignment.status == TrainerAssignment.Status.ACTIVE:
            assignment.status = TrainerAssignment.Status.COMPLETED
            assignment.end_date = timezone.localdate()
            assignment.save(update_fields=['status', 'end_date', 'updated_at'])
            messages.success(request, 'Trainer assignment ended.')
        else:
            messages.info(request, 'Assignment is already not active.')
        return redirect(request.POST.get('next') or reverse('gym:trainer_detail', kwargs={'pk': assignment.trainer_id}))


class TrainerAvailabilityManageView(LoginRequiredMixin, View):
    template_name = 'gym/trainer_availability.html'

    def get(self, request, trainer_pk):
        trainer = get_object_or_404(Trainer, pk=trainer_pk)
        form = TrainerAvailabilityForm()
        availabilities = trainer.availabilities.all().order_by('day_of_week', 'start_time')
        return self._render(request, trainer, form, availabilities)

    def post(self, request, trainer_pk):
        trainer = get_object_or_404(Trainer, pk=trainer_pk)
        form = TrainerAvailabilityForm(request.POST)
        if form.is_valid():
            slot = form.save(commit=False)
            slot.trainer = trainer
            try:
                slot.save()
                messages.success(request, 'Availability slot added.')
                return redirect('gym:trainer_availability', trainer_pk=trainer.pk)
            except Exception as exc:
                form.add_error(None, str(exc))
        messages.error(request, 'Please correct the errors below.')
        availabilities = trainer.availabilities.all().order_by('day_of_week', 'start_time')
        return self._render(request, trainer, form, availabilities)

    def _render(self, request, trainer, form, availabilities):
        from django.shortcuts import render
        return render(request, self.template_name, {'trainer': trainer, 'form': form, 'availabilities': availabilities})


class TrainerAvailabilityDeleteView(LoginRequiredMixin, View):
    def post(self, request, pk):
        slot = get_object_or_404(TrainerAvailability, pk=pk)
        trainer_pk = slot.trainer_id
        slot.delete()
        messages.success(request, 'Availability slot removed.')
        return redirect(request.POST.get('next') or reverse('gym:trainer_availability', kwargs={'trainer_pk': trainer_pk}))


class TrainerDashboardView(LoginRequiredMixin, View):
    template_name = 'gym/trainer_dashboard.html'

    def get(self, request):
        total = Trainer.objects.count()
        active = Trainer.objects.filter(status=Trainer.Status.ACTIVE).count()
        inactive = Trainer.objects.filter(status=Trainer.Status.INACTIVE).count()
        members_with_trainers = TrainerAssignment.objects.filter(status=TrainerAssignment.Status.ACTIVE).values('member').distinct().count()
        recent_assignments = TrainerAssignment.objects.select_related('trainer', 'member').order_by('-created_at')[:10]
        top_trainers = Trainer.objects.annotate(
            active_count=Count('assignments__member', filter=Q(assignments__status=TrainerAssignment.Status.ACTIVE), distinct=True)
        ).order_by('-active_count', 'full_name')[:10]
        return render(request, self.template_name, {
            'total_trainers': total,
            'active_trainers': active,
            'inactive_trainers': inactive,
            'members_with_trainers': members_with_trainers,
            'recent_assignments': recent_assignments,
            'top_trainers': top_trainers,
        })
