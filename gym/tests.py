from datetime import date

from django.contrib.auth.models import User
from django.db import IntegrityError
from django.test import TestCase
from django.urls import reverse

from .models import Member


class MemberFeatureTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='staff', password='pass12345')
        self.client.force_login(self.user)

    def create_member(self, **overrides):
        data = {
            'full_name': 'Jane Doe',
            'mobile_number': '+15551234567',
            'email': 'jane@example.com',
            'gender': Member.Gender.FEMALE,
            'date_of_birth': '1990-05-10',
            'address': '123 Main St',
            'emergency_contact_name': 'John Doe',
            'emergency_contact_number': '+15557654321',
            'joining_date': '2026-11-01',
            'status': Member.Status.ACTIVE,
        }
        data.update(overrides)
        return Member.objects.create(**data)

    def test_create_member_successfully(self):
        response = self.client.post(reverse('gym:member_create'), {
            'full_name': 'Alice Smith',
            'mobile_number': '+15550001111',
            'email': 'alice@example.com',
            'gender': Member.Gender.FEMALE,
            'date_of_birth': '1992-03-15',
            'address': '456 Oak Ave',
            'emergency_contact_name': 'Bob Smith',
            'emergency_contact_number': '+15550002222',
            'joining_date': '2026-11-21',
            'status': Member.Status.ACTIVE,
        })
        self.assertEqual(response.status_code, 302)
        member = Member.objects.get(full_name='Alice Smith')
        self.assertTrue(member.member_id.startswith('GYM-'))
        self.assertEqual(member.status, Member.Status.ACTIVE)
        self.assertEqual(member.mobile_number, '+15550001111')

    def test_edit_member_details(self):
        member = self.create_member(full_name='Old Name')
        response = self.client.post(reverse('gym:member_edit', args=[member.pk]), {
            'full_name': 'New Name',
            'mobile_number': '+15559998888',
            'email': 'new@example.com',
            'gender': Member.Gender.FEMALE,
            'date_of_birth': '1990-05-10',
            'address': 'Updated Address',
            'emergency_contact_name': 'John Doe',
            'emergency_contact_number': '+15557654321',
            'joining_date': '2026-11-01',
            'status': Member.Status.ACTIVE,
        })
        self.assertEqual(response.status_code, 302)
        member.refresh_from_db()
        self.assertEqual(member.full_name, 'New Name')
        self.assertEqual(member.mobile_number, '+15559998888')
        self.assertEqual(member.address, 'Updated Address')

    def test_view_member_profile(self):
        member = self.create_member()
        response = self.client.get(reverse('gym:member_detail', args=[member.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, member.full_name)
        self.assertContains(response, member.member_id)
        self.assertContains(response, member.mobile_number)
        self.assertContains(response, 'Emergency Contact')

    def test_search_and_filter_members(self):
        active = self.create_member(full_name='Alice Active', mobile_number='+15550000001', email='a@example.com')
        Member.objects.create(
            full_name='Bob Inactive',
            mobile_number='+15550000002',
            email='i@example.com',
            gender=Member.Gender.MALE,
            joining_date=date(2026, 11, 1),
            status=Member.Status.INACTIVE,
        )

        search_response = self.client.get(reverse('gym:member_list'), {'q': 'Alice'})
        self.assertContains(search_response, 'Alice Active')
        self.assertNotContains(search_response, 'Bob Inactive')

        phone_response = self.client.get(reverse('gym:member_list'), {'q': '+15550000002'})
        self.assertContains(phone_response, 'Bob Inactive')
        self.assertNotContains(phone_response, 'Alice Active')

        id_response = self.client.get(reverse('gym:member_list'), {'q': active.member_id})
        self.assertContains(id_response, 'Alice Active')
        self.assertNotContains(id_response, 'Bob Inactive')

        status_response = self.client.get(reverse('gym:member_list'), {'status': Member.Status.INACTIVE})
        self.assertContains(status_response, 'Bob Inactive')
        self.assertNotContains(status_response, 'Alice Active')

    def test_activate_deactivate_member(self):
        member = self.create_member(status=Member.Status.ACTIVE)
        response = self.client.post(reverse('gym:member_toggle_status', args=[member.pk]), {'next': reverse('gym:member_list')})
        self.assertEqual(response.status_code, 302)
        member.refresh_from_db()
        self.assertEqual(member.status, Member.Status.INACTIVE)

        response = self.client.post(reverse('gym:member_toggle_status', args=[member.pk]), {'next': reverse('gym:member_list')})
        self.assertEqual(response.status_code, 302)
        member.refresh_from_db()
        self.assertEqual(member.status, Member.Status.ACTIVE)

    def test_required_field_validation(self):
        response = self.client.post(reverse('gym:member_create'), {
            'full_name': '',
            'mobile_number': '',
            'email': '',
            'gender': '',
            'date_of_birth': '',
            'address': '',
            'emergency_contact_name': '',
            'emergency_contact_number': '',
            'joining_date': '',
            'status': '',
        })
        self.assertEqual(response.status_code, 200)
        form = response.context['form']
        self.assertIn('full_name', form.errors)
        self.assertIn('mobile_number', form.errors)
        self.assertIn('gender', form.errors)
        self.assertIn('joining_date', form.errors)
        self.assertIn('status', form.errors)
        self.assertEqual(Member.objects.count(), 0)

    def test_duplicate_member_id_prevented(self):
        first = self.create_member(full_name='First')
        with self.assertRaises(IntegrityError):
            Member.objects.create(
                member_id=first.member_id,
                full_name='Duplicate',
                mobile_number='+15550009999',
                gender=Member.Gender.MALE,
                joining_date=date(2026, 11, 21),
                status=Member.Status.ACTIVE,
            )

    def test_database_persistence(self):
        self.client.post(reverse('gym:member_create'), {
            'full_name': 'Persistent Member',
            'mobile_number': '+15551112222',
            'email': 'persist@example.com',
            'gender': Member.Gender.MALE,
            'date_of_birth': '1988-01-01',
            'address': '789 Pine Rd',
            'emergency_contact_name': 'Emergency Person',
            'emergency_contact_number': '+15553334444',
            'joining_date': '2026-11-21',
            'status': Member.Status.ACTIVE,
        })
        member = Member.objects.get(full_name='Persistent Member')
        self.assertEqual(Member.objects.filter(pk=member.pk).count(), 1)
        fetched = Member.objects.get(pk=member.pk)
        self.assertEqual(fetched.email, 'persist@example.com')
        self.assertEqual(fetched.address, '789 Pine Rd')
