import calendar
from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, models, transaction
from django.db.models import Q
from django.utils import timezone


def add_calendar_months(value, months):
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    last_day = calendar.monthrange(year, month)[1]
    day = min(value.day, last_day)
    return value.replace(year=year, month=month, day=day)


def calculate_subscription_end_date(start_date, duration_months):
    if duration_months < 1:
        raise ValueError('duration_months must be at least 1')
    month_index = start_date.month - 1 + duration_months
    year = start_date.year + month_index // 12
    month = month_index % 12 + 1
    last_day = calendar.monthrange(year, month)[1]
    if start_date.day > last_day:
        # End-of-month start dates clamp to the last valid day of the target month.
        return start_date.replace(year=year, month=month, day=last_day)
    target = start_date.replace(year=year, month=month, day=start_date.day)
    return target - timedelta(days=1)


class Member(models.Model):
    class Gender(models.TextChoices):
        MALE = 'male', 'Male'
        FEMALE = 'female', 'Female'
        OTHER = 'other', 'Other'

    class Status(models.TextChoices):
        ACTIVE = 'active', 'Active'
        INACTIVE = 'inactive', 'Inactive'

    member_id = models.CharField(max_length=20, unique=True, editable=False)
    full_name = models.CharField(max_length=150)
    profile_photo = models.ImageField(upload_to='members/photos/', blank=True, null=True)
    mobile_number = models.CharField(max_length=20)
    email = models.EmailField(blank=True)
    gender = models.CharField(max_length=10, choices=Gender.choices)
    date_of_birth = models.DateField(blank=True, null=True)
    address = models.TextField(blank=True)
    emergency_contact_name = models.CharField(max_length=150, blank=True)
    emergency_contact_number = models.CharField(max_length=20, blank=True)
    joining_date = models.DateField(default=timezone.localdate)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.member_id} - {self.full_name}'

    @classmethod
    def generate_member_id(cls):
        prefix = 'GYM-'
        last_member = cls.objects.filter(member_id__startswith=prefix).order_by('-member_id').first()
        if last_member:
            try:
                last_number = int(last_member.member_id.replace(prefix, ''))
            except ValueError:
                last_number = 0
        else:
            last_number = 0
        return f'{prefix}{last_number + 1:04d}'

    def save(self, *args, **kwargs):
        if not self.member_id:
            last_error = None
            for _ in range(20):
                self.member_id = self.generate_member_id()
                try:
                    with transaction.atomic():
                        super().save(*args, **kwargs)
                    return
                except IntegrityError as exc:
                    last_error = exc
                    self.member_id = None
            raise last_error
        super().save(*args, **kwargs)

    def current_subscription(self, today=None):
        today = today or timezone.localdate()
        subscriptions = self.subscriptions.select_related('plan').all()
        active = []
        upcoming = []
        for subscription in subscriptions:
            current_status = subscription.current_status(today=today)
            if current_status == MemberSubscription.Status.ACTIVE:
                active.append(subscription)
            elif current_status == MemberSubscription.Status.UPCOMING:
                upcoming.append(subscription)
        if active:
            return sorted(active, key=lambda s: (s.end_date, s.start_date))[-1]
        if upcoming:
            return sorted(upcoming, key=lambda s: (s.start_date, s.end_date))[0]
        return None


class MembershipPlan(models.Model):
    class Duration(models.IntegerChoices):
        MONTHLY = 1, 'Monthly (1 month)'
        QUARTERLY = 3, 'Quarterly (3 months)'
        HALF_YEARLY = 6, 'Half-Yearly (6 months)'
        YEARLY = 12, 'Yearly (12 months)'

    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    duration_months = models.PositiveIntegerField()
    price = models.DecimalField(max_digits=10, decimal_places=2)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['duration_months', 'name']

    def __str__(self):
        return f'{self.name} ({self.duration_months} month{"s" if self.duration_months != 1 else ""})'

    def clean(self):
        errors = {}
        if self.duration_months is not None and self.duration_months < 1:
            errors['duration_months'] = 'Duration must be at least 1 month.'
        if self.price is not None and self.price < Decimal('0.00'):
            errors['price'] = 'Price cannot be negative.'
        if errors:
            raise ValidationError(errors)

    @property
    def duration_label(self):
        return f'{self.duration_months} month{"s" if self.duration_months != 1 else ""}'


class MemberSubscription(models.Model):
    class Status(models.TextChoices):
        UPCOMING = 'upcoming', 'Upcoming'
        ACTIVE = 'active', 'Active'
        EXPIRED = 'expired', 'Expired'
        CANCELLED = 'cancelled', 'Cancelled'

    member = models.ForeignKey(Member, on_delete=models.PROTECT, related_name='subscriptions')
    plan = models.ForeignKey(MembershipPlan, on_delete=models.PROTECT, related_name='subscriptions')
    start_date = models.DateField()
    end_date = models.DateField()
    price_at_subscription = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-start_date', '-created_at']

    def __str__(self):
        return f'{self.member.member_id} - {self.plan.name} ({self.start_date} to {self.end_date})'

    def clean(self):
        errors = {}
        if self.start_date and self.end_date and self.end_date < self.start_date:
            errors['end_date'] = 'End date cannot be before start date.'
        if self.plan_id and not self.plan.is_active and not self.pk:
            errors['plan'] = 'Deactivated plans cannot be assigned to new subscriptions.'
        if self.price_at_subscription is not None and self.price_at_subscription < Decimal('0.00'):
            errors['price_at_subscription'] = 'Price cannot be negative.'
        if errors:
            raise ValidationError(errors)

        if self.member_id and self.start_date and self.end_date and self.status in self.blocking_statuses():
            overlap = MemberSubscription.objects.filter(member_id=self.member_id)
            if self.pk:
                overlap = overlap.exclude(pk=self.pk)
            overlap = overlap.filter(status__in=self.blocking_statuses())
            overlap = overlap.filter(start_date__lte=self.end_date, end_date__gte=self.start_date)
            if overlap.exists():
                raise ValidationError('This subscription overlaps an existing active or upcoming membership.')

    @staticmethod
    def blocking_statuses():
        return [MemberSubscription.Status.UPCOMING, MemberSubscription.Status.ACTIVE]

    @staticmethod
    def compute_status(start_date, end_date, today=None, status=None):
        today = today or timezone.localdate()
        if status == MemberSubscription.Status.CANCELLED:
            return MemberSubscription.Status.CANCELLED
        if today < start_date:
            return MemberSubscription.Status.UPCOMING
        if today > end_date:
            return MemberSubscription.Status.EXPIRED
        return MemberSubscription.Status.ACTIVE

    def current_status(self, today=None):
        return self.compute_status(self.start_date, self.end_date, today=today, status=self.status)

    @property
    def days_remaining(self):
        today = timezone.localdate()
        status = self.current_status(today=today)
        if status == self.Status.ACTIVE:
            return (self.end_date - today).days
        if status == self.Status.UPCOMING:
            return (self.start_date - today).days
        return 0

    def sync_status(self, today=None):
        computed = self.current_status(today=today)
        if self.status != self.Status.CANCELLED and self.status != computed:
            self.status = computed
        return self.status

    def save(self, *args, **kwargs):
        if self.plan_id and self.price_at_subscription is None:
            self.price_at_subscription = self.plan.price
        if self.start_date and self.plan_id and not self.end_date:
            self.end_date = calculate_subscription_end_date(self.start_date, self.plan.duration_months)
        self.status = self.compute_status(self.start_date, self.end_date, status=self.status)
        self.full_clean()
        super().save(*args, **kwargs)
