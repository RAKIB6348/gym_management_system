from django import forms
from django.core.validators import RegexValidator

from .models import Member


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
