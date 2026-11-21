import calendar
from datetime import datetime, timedelta
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import IntegrityError, models, transaction
from django.db.models import Q, Sum
from django.db.models.functions import Coalesce
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

    @property
    def total_fee(self):
        return self.price_at_subscription or Decimal('0.00')

    def total_paid_amount(self):
        total = self.payments.filter(status=MembershipPayment.Status.COMPLETED).aggregate(
            total=Coalesce(Sum('amount'), Decimal('0.00'), output_field=models.DecimalField(max_digits=10, decimal_places=2))
        )['total']
        return total or Decimal('0.00')

    def remaining_due_amount(self, total_paid=None):
        if total_paid is None:
            total_paid = self.total_paid_amount()
        remaining = self.total_fee - total_paid
        return remaining if remaining > Decimal('0.00') else Decimal('0.00')

    def payment_status(self, total_paid=None):
        if total_paid is None:
            total_paid = self.total_paid_amount()
        total_fee = self.total_fee
        if total_paid <= Decimal('0.00'):
            return 'Unpaid'
        if total_paid < total_fee:
            return 'Partial'
        return 'Paid'

    def payment_summary(self):
        total_paid = self.total_paid_amount()
        return {
            'total_fee': self.total_fee,
            'total_paid': total_paid,
            'remaining_due': self.remaining_due_amount(total_paid=total_paid),
            'payment_status': self.payment_status(total_paid=total_paid),
        }


class MembershipPayment(models.Model):
    class PaymentMethod(models.TextChoices):
        CASH = 'cash', 'Cash'
        BKASH = 'bkash', 'bKash'
        NAGAD = 'nagad', 'Nagad'
        BANK_TRANSFER = 'bank_transfer', 'Bank Transfer'

    class Status(models.TextChoices):
        COMPLETED = 'completed', 'Completed'
        CANCELLED = 'cancelled', 'Cancelled'

    payment_reference = models.CharField(max_length=20, unique=True, editable=False)
    member = models.ForeignKey(Member, on_delete=models.PROTECT, related_name='payments')
    subscription = models.ForeignKey(MemberSubscription, on_delete=models.PROTECT, related_name='payments')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_date = models.DateField(default=timezone.localdate)
    payment_method = models.CharField(max_length=20, choices=PaymentMethod.choices)
    transaction_id = models.CharField(max_length=100, blank=True)
    note = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.COMPLETED)
    collected_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='collected_payments')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-payment_date', '-created_at']
        indexes = [
            models.Index(fields=['payment_reference']),
            models.Index(fields=['payment_date']),
            models.Index(fields=['status']),
            models.Index(fields=['member', 'payment_date']),
        ]

    def __str__(self):
        return f'{self.payment_reference} - {self.member.member_id} - BDT {self.amount}'

    @classmethod
    def generate_payment_reference(cls):
        prefix = 'PAY-'
        last_payment = cls.objects.filter(payment_reference__startswith=prefix).order_by('-payment_reference').first()
        if last_payment:
            try:
                last_number = int(last_payment.payment_reference.replace(prefix, ''))
            except ValueError:
                last_number = 0
        else:
            last_number = 0
        return f'{prefix}{last_number + 1:04d}'

    def clean(self):
        errors = {}
        if self.amount is not None and self.amount <= Decimal('0.00'):
            errors['amount'] = 'Payment amount must be greater than zero.'
        if self.member_id and self.subscription_id and self.subscription.member_id != self.member_id:
            errors['subscription'] = 'Selected subscription does not belong to the selected member.'
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        if not self.payment_reference:
            last_error = None
            for _ in range(20):
                self.payment_reference = self.generate_payment_reference()
                try:
                    with transaction.atomic():
                        super().save(*args, **kwargs)
                    return
                except IntegrityError as exc:
                    last_error = exc
                    self.payment_reference = None
            raise last_error
        super().save(*args, **kwargs)


class Trainer(models.Model):
    class Gender(models.TextChoices):
        MALE = 'male', 'Male'
        FEMALE = 'female', 'Female'
        OTHER = 'other', 'Other'

    class Status(models.TextChoices):
        ACTIVE = 'active', 'Active'
        INACTIVE = 'inactive', 'Inactive'

    trainer_id = models.CharField(max_length=20, unique=True, editable=False)
    full_name = models.CharField(max_length=150)
    photo = models.ImageField(upload_to='trainers/photos/', blank=True, null=True)
    phone = models.CharField(max_length=20)
    email = models.EmailField(blank=True)
    gender = models.CharField(max_length=10, choices=Gender.choices)
    date_of_birth = models.DateField(blank=True, null=True)
    address = models.TextField(blank=True)
    specialization = models.CharField(max_length=120)
    experience_years = models.PositiveIntegerField(default=0)
    qualification = models.TextField(blank=True)
    joining_date = models.DateField(default=timezone.localdate)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.trainer_id} - {self.full_name}'

    @classmethod
    def generate_trainer_id(cls):
        prefix = 'TR-'
        last = cls.objects.filter(trainer_id__startswith=prefix).order_by('-trainer_id').first()
        if last:
            try:
                last_number = int(last.trainer_id.replace(prefix, ''))
            except ValueError:
                last_number = 0
        else:
            last_number = 0
        return f'{prefix}{last_number + 1:04d}'

    def save(self, *args, **kwargs):
        if not self.trainer_id:
            last_error = None
            for _ in range(20):
                self.trainer_id = self.generate_trainer_id()
                try:
                    with transaction.atomic():
                        super().save(*args, **kwargs)
                    return
                except IntegrityError as exc:
                    last_error = exc
                    self.trainer_id = None
            raise last_error
        super().save(*args, **kwargs)


class TrainerAssignment(models.Model):
    class Status(models.TextChoices):
        ACTIVE = 'active', 'Active'
        COMPLETED = 'completed', 'Completed'
        CANCELLED = 'cancelled', 'Cancelled'

    trainer = models.ForeignKey(Trainer, on_delete=models.PROTECT, related_name='assignments')
    member = models.ForeignKey(Member, on_delete=models.PROTECT, related_name='trainer_assignments')
    start_date = models.DateField(default=timezone.localdate)
    end_date = models.DateField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-start_date', '-created_at']
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['member', 'status']),
            models.Index(fields=['trainer', 'status']),
        ]

    def __str__(self):
        return f'{self.member.member_id} -> {self.trainer.trainer_id} ({self.status})'

    def clean(self):
        errors = {}
        if self.start_date and self.end_date and self.end_date < self.start_date:
            errors['end_date'] = 'End date cannot be before start date.'
        if self.trainer_id and self.trainer.status != Trainer.Status.ACTIVE and self.status == self.Status.ACTIVE and not self.pk:
            errors['trainer'] = 'Inactive trainers cannot receive new assignments.'
        if errors:
            raise ValidationError(errors)

        if self.status == self.Status.ACTIVE and self.member_id and not getattr(self, '_allow_reassign', False):
            qs = TrainerAssignment.objects.filter(member_id=self.member_id, status=self.Status.ACTIVE)
            if self.pk:
                qs = qs.exclude(pk=self.pk)
            if qs.exists():
                raise ValidationError('This member already has an active trainer assignment.')

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class TrainerAvailability(models.Model):
    class DayOfWeek(models.IntegerChoices):
        MONDAY = 0, 'Monday'
        TUESDAY = 1, 'Tuesday'
        WEDNESDAY = 2, 'Wednesday'
        THURSDAY = 3, 'Thursday'
        FRIDAY = 4, 'Friday'
        SATURDAY = 5, 'Saturday'
        SUNDAY = 6, 'Sunday'

    trainer = models.ForeignKey(Trainer, on_delete=models.CASCADE, related_name='availabilities')
    day_of_week = models.IntegerField(choices=DayOfWeek.choices)
    start_time = models.TimeField()
    end_time = models.TimeField()
    is_available = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['day_of_week', 'start_time']
        indexes = [models.Index(fields=['trainer', 'day_of_week'])]

    def __str__(self):
        return f'{self.trainer.trainer_id} {self.get_day_of_week_display()} {self.start_time}-{self.end_time}'

    def clean(self):
        errors = {}
        if self.start_time and self.end_time and self.end_time <= self.start_time:
            errors['end_time'] = 'End time must be after start time.'
        if errors:
            raise ValidationError(errors)

        if self.trainer_id and self.start_time and self.end_time:
            qs = TrainerAvailability.objects.filter(trainer_id=self.trainer_id, day_of_week=self.day_of_week)
            if self.pk:
                qs = qs.exclude(pk=self.pk)
            # overlap: start < other_end and end > other_start
            qs = qs.filter(start_time__lt=self.end_time, end_time__gt=self.start_time)
            if qs.exists():
                raise ValidationError('This availability slot overlaps an existing slot for the same trainer.')

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class GymClass(models.Model):
    class Status(models.TextChoices):
        ACTIVE = 'active', 'Active'
        INACTIVE = 'inactive', 'Inactive'

    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    trainer = models.ForeignKey(Trainer, on_delete=models.PROTECT, related_name='gym_classes')
    capacity = models.PositiveIntegerField()
    duration_minutes = models.PositiveIntegerField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name

    def clean(self):
        errors = {}
        if self.capacity is not None and self.capacity < 1:
            errors['capacity'] = 'Capacity must be at least 1.'
        if self.duration_minutes is not None and self.duration_minutes < 1:
            errors['duration_minutes'] = 'Duration must be at least 1 minute.'
        if self.trainer_id and self.trainer.status != Trainer.Status.ACTIVE and self.status == self.Status.ACTIVE:
            # Allow keeping existing inactive assignment? New/active classes should have active trainer.
            if not self.pk:
                errors['trainer'] = 'Trainer must be active.'
        if errors:
            raise ValidationError(errors)


class ClassSchedule(models.Model):
    class DayOfWeek(models.IntegerChoices):
        MONDAY = 0, 'Monday'
        TUESDAY = 1, 'Tuesday'
        WEDNESDAY = 2, 'Wednesday'
        THURSDAY = 3, 'Thursday'
        FRIDAY = 4, 'Friday'
        SATURDAY = 5, 'Saturday'
        SUNDAY = 6, 'Sunday'

    gym_class = models.ForeignKey(GymClass, on_delete=models.PROTECT, related_name='schedules')
    day_of_week = models.IntegerField(choices=DayOfWeek.choices)
    start_time = models.TimeField()
    end_time = models.TimeField()
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['day_of_week', 'start_time']

    def __str__(self):
        return f'{self.gym_class.name} - {self.get_day_of_week_display()} {self.start_time}-{self.end_time}'

    def clean(self):
        errors = {}
        if self.start_time and self.end_time and self.end_time <= self.start_time:
            errors['end_time'] = 'End time must be after start time.'
        if errors:
            raise ValidationError(errors)

        if not self.gym_class_id or not self.start_time or not self.end_time:
            return

        trainer = self.gym_class.trainer
        if trainer.status != Trainer.Status.ACTIVE and self.is_active:
            raise ValidationError('Trainer must be active for an active schedule.')

        # Validate against trainer availability - there must be an available slot covering this schedule
        availability_qs = TrainerAvailability.objects.filter(
            trainer=trainer, day_of_week=self.day_of_week, is_available=True,
            start_time__lte=self.start_time, end_time__gte=self.end_time,
        )
        if not availability_qs.exists():
            raise ValidationError('Schedule must be within the trainer\'s available time slots.')

        # Prevent overlapping active schedules for same trainer
        overlapping = ClassSchedule.objects.filter(
            gym_class__trainer=trainer,
            day_of_week=self.day_of_week,
            is_active=True,
        ).exclude(pk=self.pk)
        if self.pk:
            overlapping = overlapping.exclude(pk=self.pk)
        overlapping = overlapping.filter(start_time__lt=self.end_time, end_time__gt=self.start_time)
        if overlapping.exists():
            raise ValidationError('This schedule overlaps another active session for the same trainer.')

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class ClassSession(models.Model):
    class Status(models.TextChoices):
        SCHEDULED = 'scheduled', 'Scheduled'
        COMPLETED = 'completed', 'Completed'
        CANCELLED = 'cancelled', 'Cancelled'

    gym_class = models.ForeignKey(GymClass, on_delete=models.PROTECT, related_name='sessions')
    schedule = models.ForeignKey(ClassSchedule, on_delete=models.SET_NULL, null=True, blank=True, related_name='sessions')
    trainer = models.ForeignKey(Trainer, on_delete=models.PROTECT, related_name='class_sessions')
    start_datetime = models.DateTimeField()
    end_datetime = models.DateTimeField()
    capacity = models.PositiveIntegerField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.SCHEDULED)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['start_datetime']
        indexes = [
            models.Index(fields=['start_datetime']),
            models.Index(fields=['status']),
            models.Index(fields=['trainer', 'start_datetime']),
        ]
        constraints = [
            models.UniqueConstraint(fields=['schedule', 'start_datetime'], name='unique_schedule_session_start')
        ]

    def __str__(self):
        return f'{self.gym_class.name} @ {self.start_datetime}'

    def clean(self):
        errors = {}
        if self.start_datetime and self.end_datetime and self.end_datetime <= self.start_datetime:
            errors['end_datetime'] = 'End datetime must be after start datetime.'
        if self.capacity is not None and self.capacity < 1:
            errors['capacity'] = 'Capacity must be at least 1.'
        if errors:
            raise ValidationError(errors)

        if self.trainer_id and self.start_datetime and self.end_datetime and self.status == self.Status.SCHEDULED:
            qs = ClassSession.objects.filter(
                trainer_id=self.trainer_id,
                status=self.Status.SCHEDULED,
                start_datetime__lt=self.end_datetime,
                end_datetime__gt=self.start_datetime,
            )
            if self.pk:
                qs = qs.exclude(pk=self.pk)
            if qs.exists():
                raise ValidationError('This session overlaps another scheduled session for the same trainer.')

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    @property
    def enrolled_count(self):
        return self.enrollments.filter(status=ClassEnrollment.Status.ENROLLED).count()

    @property
    def available_seats(self):
        remaining = self.capacity - self.enrolled_count
        return remaining if remaining > 0 else 0


class ClassEnrollment(models.Model):
    class Status(models.TextChoices):
        ENROLLED = 'enrolled', 'Enrolled'
        CANCELLED = 'cancelled', 'Cancelled'

    member = models.ForeignKey(Member, on_delete=models.PROTECT, related_name='class_enrollments')
    session = models.ForeignKey(ClassSession, on_delete=models.PROTECT, related_name='enrollments')
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ENROLLED)
    enrolled_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-enrolled_at']
        indexes = [
            models.Index(fields=['member', 'status']),
            models.Index(fields=['session', 'status']),
        ]

    def __str__(self):
        return f'{self.member.member_id} - {self.session} ({self.status})'

    def clean(self):
        errors = {}
        if self.member_id and self.member.status != Member.Status.ACTIVE:
            errors['member'] = 'Inactive members cannot be enrolled.'
        if self.session_id and self.session.status != ClassSession.Status.SCHEDULED:
            errors['session'] = 'Only scheduled sessions can be enrolled.'
        if errors:
            raise ValidationError(errors)

        if self.status == self.Status.ENROLLED and self.member_id and self.session_id:
            dup = ClassEnrollment.objects.filter(member_id=self.member_id, session_id=self.session_id, status=self.Status.ENROLLED)
            if self.pk:
                dup = dup.exclude(pk=self.pk)
            if dup.exists():
                raise ValidationError('Member is already enrolled in this session.')

            # valid membership covering session date
            session_date = timezone.localdate(self.session.start_datetime) if timezone.is_aware(self.session.start_datetime) else self.session.start_datetime.date()
            has_membership = MemberSubscription.objects.filter(
                member_id=self.member_id,
                start_date__lte=session_date,
                end_date__gte=session_date,
            ).exclude(status=MemberSubscription.Status.CANCELLED).exists()
            # also ensure computed status is active/upcoming? covering date means active on that date
            if not has_membership:
                # check by date coverage independent of stored status except cancelled
                raise ValidationError('Member must have a valid membership covering the session date.')

            # overlapping booking for same member
            overlapping = ClassEnrollment.objects.filter(
                member_id=self.member_id,
                status=self.Status.ENROLLED,
                session__status=ClassSession.Status.SCHEDULED,
                session__start_datetime__lt=self.session.end_datetime,
                session__end_datetime__gt=self.session.start_datetime,
            )
            if self.pk:
                overlapping = overlapping.exclude(pk=self.pk)
            if overlapping.exists():
                raise ValidationError('Member already has an overlapping class booking.')

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
