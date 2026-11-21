from decimal import Decimal

from django import forms
from django.core.validators import RegexValidator
from django.utils import timezone

from .models import (
    Member, MemberSubscription, MembershipPayment, MembershipPlan,
    Trainer, TrainerAssignment, TrainerAvailability,
    calculate_subscription_end_date,
)


phone_validator = RegexValidator(
    regex=r'^\+?[0-9\-\s]{7,20}$',
    message='Enter a valid phone number (digits, spaces, hyphens, optional leading +).',
)


class MemberForm(forms.ModelForm):
    mobile_number = forms.CharField(
        max_length=20,
        required=True,
        validators=[phone_validator],
        widget=forms.TextInput(attrs={'placeholder': 'e.g. +1 555 123 4567'}),
    )
    emergency_contact_number = forms.CharField(
        max_length=20,
        required=False,
        validators=[phone_validator],
        widget=forms.TextInput(attrs={'placeholder': 'e.g. +1 555 987 6543'}),
    )

    class Meta:
        model = Member
        fields = [
            'full_name',
            'profile_photo',
            'mobile_number',
            'email',
            'gender',
            'date_of_birth',
            'address',
            'emergency_contact_name',
            'emergency_contact_number',
            'joining_date',
            'status',
        ]
        widgets = {
            'full_name': forms.TextInput(attrs={'placeholder': 'Full name'}),
            'email': forms.EmailInput(attrs={'placeholder': 'name@example.com'}),
            'gender': forms.RadioSelect,
            'date_of_birth': forms.DateInput(attrs={'type': 'date'}),
            'address': forms.Textarea(attrs={'rows': 3, 'placeholder': 'Street, city, state'}),
            'emergency_contact_name': forms.TextInput(attrs={'placeholder': 'Emergency contact name'}),
            'joining_date': forms.DateInput(attrs={'type': 'date'}),
        }

    def clean_full_name(self):
        name = self.cleaned_data.get('full_name', '').strip()
        if not name:
            raise forms.ValidationError('Full name is required.')
        return name

    def clean(self):
        cleaned_data = super().clean()
        emergency_name = cleaned_data.get('emergency_contact_name', '').strip()
        emergency_number = cleaned_data.get('emergency_contact_number', '').strip()
        cleaned_data['emergency_contact_name'] = emergency_name
        cleaned_data['emergency_contact_number'] = emergency_number

        if emergency_number and not emergency_name:
            self.add_error('emergency_contact_name', 'Emergency contact name is required when a number is provided.')
        return cleaned_data


class MembershipPlanForm(forms.ModelForm):
    class Meta:
        model = MembershipPlan
        fields = ['name', 'description', 'duration_months', 'price', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={'placeholder': 'e.g. Monthly Premium'}),
            'description': forms.Textarea(attrs={'rows': 3, 'placeholder': 'Optional plan details'}),
            'duration_months': forms.NumberInput(attrs={'min': 1, 'step': 1}),
            'price': forms.NumberInput(attrs={'min': 0, 'step': '0.01'}),
        }

    def clean_duration_months(self):
        duration = self.cleaned_data.get('duration_months')
        if duration is None or duration < 1:
            raise forms.ValidationError('Duration must be at least 1 month.')
        return duration

    def clean_price(self):
        price = self.cleaned_data.get('price')
        if price is None or price < Decimal('0.00'):
            raise forms.ValidationError('Price cannot be negative.')
        return price


class SubscriptionAssignForm(forms.ModelForm):
    class Meta:
        model = MemberSubscription
        fields = ['plan', 'start_date']
        widgets = {
            'start_date': forms.DateInput(attrs={'type': 'date'}),
        }

    def __init__(self, *args, member=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.member = member
        self.fields['plan'].queryset = MembershipPlan.objects.filter(is_active=True).order_by('duration_months', 'name')
        self.fields['plan'].empty_label = 'Select a plan'
        self.fields['start_date'].initial = self.fields['start_date'].initial or timezone.localdate()

    def clean(self):
        cleaned_data = super().clean()
        plan = cleaned_data.get('plan')
        start_date = cleaned_data.get('start_date')
        if plan and start_date and self.member:
            end_date = calculate_subscription_end_date(start_date, plan.duration_months)
            cleaned_data['end_date'] = end_date
            cleaned_data['price_at_subscription'] = plan.price
            overlap = MemberSubscription.objects.filter(
                member=self.member,
                status__in=MemberSubscription.blocking_statuses(),
                start_date__lte=end_date,
                end_date__gte=start_date,
            )
            if self.instance.pk:
                overlap = overlap.exclude(pk=self.instance.pk)
            if overlap.exists():
                raise forms.ValidationError(
                    'This member already has an active or upcoming subscription that overlaps the selected dates.'
                )
        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.member = self.member
        instance.plan = self.cleaned_data['plan']
        instance.start_date = self.cleaned_data['start_date']
        instance.end_date = self.cleaned_data['end_date']
        instance.price_at_subscription = self.cleaned_data['price_at_subscription']
        instance.status = MemberSubscription.compute_status(instance.start_date, instance.end_date)
        if commit:
            instance.save()
        return instance


class PaymentCollectForm(forms.ModelForm):
    class Meta:
        model = MembershipPayment
        fields = ['amount', 'payment_method', 'transaction_id', 'payment_date', 'note']
        widgets = {
            'amount': forms.NumberInput(attrs={'min': '0.01', 'step': '0.01', 'placeholder': '0.00'}),
            'payment_date': forms.DateInput(attrs={'type': 'date'}),
            'transaction_id': forms.TextInput(attrs={'placeholder': 'Optional transaction reference'}),
            'note': forms.Textarea(attrs={'rows': 3, 'placeholder': 'Optional note'}),
        }

    def __init__(self, *args, subscription=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.subscription = subscription
        self.fields['payment_date'].initial = self.fields['payment_date'].initial or timezone.localdate()

    def clean_amount(self):
        amount = self.cleaned_data.get('amount')
        if amount is None or amount <= Decimal('0.00'):
            raise forms.ValidationError('Payment amount must be greater than zero.')
        if self.subscription:
            remaining = self.subscription.remaining_due_amount()
            if amount > remaining:
                raise forms.ValidationError(
                    f'Payment exceeds remaining due amount (BDT {remaining:.2f}).'
                )
        return amount


class TrainerForm(forms.ModelForm):
    phone = forms.CharField(
        max_length=20,
        required=True,
        validators=[phone_validator],
        widget=forms.TextInput(attrs={'placeholder': 'e.g. +1 555 123 4567'}),
    )

    class Meta:
        model = Trainer
        fields = [
            'full_name', 'photo', 'phone', 'email', 'gender', 'date_of_birth',
            'address', 'specialization', 'experience_years', 'qualification',
            'joining_date', 'status',
        ]
        widgets = {
            'full_name': forms.TextInput(attrs={'placeholder': 'Full name'}),
            'email': forms.EmailInput(attrs={'placeholder': 'name@example.com'}),
            'gender': forms.RadioSelect,
            'date_of_birth': forms.DateInput(attrs={'type': 'date'}),
            'address': forms.Textarea(attrs={'rows': 3, 'placeholder': 'Address'}),
            'specialization': forms.TextInput(attrs={'placeholder': 'e.g. Strength Training, Yoga'}),
            'experience_years': forms.NumberInput(attrs={'min': 0, 'step': 1}),
            'qualification': forms.Textarea(attrs={'rows': 3, 'placeholder': 'Certifications, qualifications'}),
            'joining_date': forms.DateInput(attrs={'type': 'date'}),
        }

    def clean_full_name(self):
        name = self.cleaned_data.get('full_name', '').strip()
        if not name:
            raise forms.ValidationError('Full name is required.')
        return name

    def clean_experience_years(self):
        years = self.cleaned_data.get('experience_years')
        if years is None or years < 0:
            raise forms.ValidationError('Experience years cannot be negative.')
        return years


class TrainerAssignmentForm(forms.ModelForm):
    class Meta:
        model = TrainerAssignment
        fields = ['trainer', 'member', 'start_date', 'end_date']
        widgets = {
            'start_date': forms.DateInput(attrs={'type': 'date'}),
            'end_date': forms.DateInput(attrs={'type': 'date'}),
        }

    def __init__(self, *args, trainer=None, member=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fixed_trainer = trainer
        self.fixed_member = member
        if trainer is not None:
            self.fields['trainer'].initial = trainer
            self.fields['trainer'].queryset = Trainer.objects.filter(pk=trainer.pk)
            self.fields['trainer'].widget = forms.HiddenInput()
        else:
            self.fields['trainer'].queryset = Trainer.objects.filter(status=Trainer.Status.ACTIVE).order_by('full_name')
            self.fields['trainer'].empty_label = 'Select a trainer'
        if member is not None:
            self.fields['member'].initial = member
            self.fields['member'].queryset = Member.objects.filter(pk=member.pk)
            self.fields['member'].widget = forms.HiddenInput()
        else:
            self.fields['member'].queryset = Member.objects.order_by('full_name')
            self.fields['member'].empty_label = 'Select a member'
        if not self.initial.get('start_date'):
            self.fields['start_date'].initial = timezone.localdate()

    def clean(self):
        cleaned = super().clean()
        trainer = cleaned.get('trainer')
        member = cleaned.get('member')
        start_date = cleaned.get('start_date')
        end_date = cleaned.get('end_date')
        if start_date and end_date and end_date < start_date:
            self.add_error('end_date', 'End date cannot be before start date.')
        if trainer and trainer.status != Trainer.Status.ACTIVE:
            self.add_error('trainer', 'Inactive trainers cannot receive new assignments.')
        # Reassignment is handled in the view by ending the current active assignment in a transaction.
        return cleaned


class TrainerAvailabilityForm(forms.ModelForm):
    class Meta:
        model = TrainerAvailability
        fields = ['day_of_week', 'start_time', 'end_time', 'is_available']
        widgets = {
            'start_time': forms.TimeInput(attrs={'type': 'time'}),
            'end_time': forms.TimeInput(attrs={'type': 'time'}),
        }
