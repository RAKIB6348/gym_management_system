import csv
from datetime import timedelta
from decimal import Decimal

from django.db.models import Count, DecimalField, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.http import HttpResponse
from django.utils import timezone

from .models import (
    Member, MemberSubscription, MembershipPayment, Trainer, TrainerAssignment,
    GymClass, ClassSession, ClassEnrollment,
)


def get_date_range(request):
    """Return (start_date, end_date, range_key, label). Dates are inclusive."""
    today = timezone.localdate()
    key = request.GET.get('range', 'this_month')
    start = request.GET.get('start', '').strip()
    end = request.GET.get('end', '').strip()
    if key == 'today':
        return today, today, key, 'Today'
    if key == 'this_week':
        start_date = today - timedelta(days=today.weekday())
        return start_date, today, key, 'This Week'
    if key == 'this_month':
        return today.replace(day=1), today, key, 'This Month'
    if key == 'this_year':
        return today.replace(month=1, day=1), today, key, 'This Year'
    if key == 'custom':
        try:
            start_date = timezone.datetime.fromisoformat(start).date() if start else today.replace(day=1)
            end_date = timezone.datetime.fromisoformat(end).date() if end else today
        except Exception:
            start_date, end_date = today.replace(day=1), today
        if start_date > end_date:
            start_date, end_date = end_date, start_date
        return start_date, end_date, key, 'Custom Range'
    return today.replace(day=1), today, 'this_month', 'This Month'


def completed_payments(start_date=None, end_date=None):
    qs = MembershipPayment.objects.filter(status=MembershipPayment.Status.COMPLETED)
    if start_date:
        qs = qs.filter(payment_date__gte=start_date)
    if end_date:
        qs = qs.filter(payment_date__lte=end_date)
    return qs


def sum_completed(start_date=None, end_date=None):
    return completed_payments(start_date, end_date).aggregate(
        total=Coalesce(Sum('amount'), Decimal('0.00'), output_field=DecimalField(max_digits=12, decimal_places=2))
    )['total'] or Decimal('0.00')


def subscription_due_rows():
    rows = []
    subs = MemberSubscription.objects.select_related('member', 'plan').prefetch_related('payments').all()
    for sub in subs:
        paid = sum((p.amount for p in sub.payments.all() if p.status == MembershipPayment.Status.COMPLETED), Decimal('0.00'))
        fee = sub.total_fee
        due = fee - paid
        if due < Decimal('0.00'):
            due = Decimal('0.00')
        rows.append({
            'subscription': sub,
            'member': sub.member,
            'plan': sub.plan,
            'total_fee': fee,
            'paid_amount': paid,
            'due_amount': due,
            'payment_status': sub.payment_status(total_paid=paid),
            'subscription_status': sub.current_status(),
        })
    return rows


def outstanding_due_rows():
    return [r for r in subscription_due_rows() if r['due_amount'] > Decimal('0.00')]


def csv_response(filename, headers, rows):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    writer = csv.writer(response)
    if headers:
        writer.writerow(headers)
    for row in rows:
        writer.writerow(row)
    return response
