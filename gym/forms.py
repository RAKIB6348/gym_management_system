from decimal import Decimal

from django import forms
from django.core.validators import RegexValidator
from django.utils import timezone

from .models import Member, MemberSubscription, MembershipPlan, calculate_subscription_end_date


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
