from django.db import IntegrityError, models, transaction
from django.utils import timezone


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
