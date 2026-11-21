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

from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.utils import timezone

from .models import MembershipPlan, MemberSubscription, calculate_subscription_end_date


class MembershipPlanSubscriptionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='staff2', password='pass12345')
        self.client.force_login(self.user)
        self.member = Member.objects.create(
            full_name='Test Member',
            mobile_number='+15550001111',
            gender=Member.Gender.MALE,
            joining_date=date(2026, 1, 1),
            status=Member.Status.ACTIVE,
        )

    def create_plan(self, **overrides):
        data = {
            'name': 'Monthly Plan',
            'description': 'Basic plan',
            'duration_months': 1,
            'price': Decimal('1500.00'),
            'is_active': True,
        }
        data.update(overrides)
        return MembershipPlan.objects.create(**data)

    def test_create_monthly_plan(self):
        response = self.client.post(reverse('gym:plan_create'), {
            'name': 'Monthly',
            'description': 'Monthly plan',
            'duration_months': 1,
            'price': '1500.00',
            'is_active': 'on',
        })
        self.assertEqual(response.status_code, 302)
        plan = MembershipPlan.objects.get(name='Monthly')
        self.assertEqual(plan.duration_months, 1)
        self.assertEqual(plan.price, Decimal('1500.00'))

    def test_create_yearly_plan(self):
        response = self.client.post(reverse('gym:plan_create'), {
            'name': 'Yearly',
            'description': 'Yearly plan',
            'duration_months': 12,
            'price': '12000.00',
            'is_active': 'on',
        })
        self.assertEqual(response.status_code, 302)
        plan = MembershipPlan.objects.get(name='Yearly')
        self.assertEqual(plan.duration_months, 12)
        self.assertEqual(plan.price, Decimal('12000.00'))

    def test_edit_plan_price(self):
        plan = self.create_plan(name='Editable', price=Decimal('1000.00'))
        response = self.client.post(reverse('gym:plan_edit', args=[plan.pk]), {
            'name': 'Editable',
            'description': 'Updated',
            'duration_months': 1,
            'price': '1800.00',
            'is_active': 'on',
        })
        self.assertEqual(response.status_code, 302)
        plan.refresh_from_db()
        self.assertEqual(plan.price, Decimal('1800.00'))

    def test_assign_plan_to_member(self):
        plan = self.create_plan()
        with patch('django.utils.timezone.localdate', return_value=date(2026, 11, 21)):
            response = self.client.post(reverse('gym:subscription_assign', args=[self.member.pk]), {
                'plan': plan.pk,
                'start_date': '2026-11-21',
            })
        self.assertEqual(response.status_code, 302)
        sub = MemberSubscription.objects.get(member=self.member)
        self.assertEqual(sub.plan, plan)
        self.assertEqual(sub.price_at_subscription, Decimal('1500.00'))

    def test_verify_automatic_expiry_date(self):
        plan = self.create_plan(duration_months=1)
        # End-of-month handling: Jan 31 + 1 month => Feb 28 (last valid day)
        end = calculate_subscription_end_date(date(2026, 1, 31), 1)
        self.assertEqual(end, date(2026, 2, 28))
        # Regular case
        self.assertEqual(calculate_subscription_end_date(date(2026, 11, 1), 1), date(2026, 11, 30))
        # Yearly
        self.assertEqual(calculate_subscription_end_date(date(2026, 1, 1), 12), date(2026, 12, 31))

    def test_verify_active_membership(self):
        plan = self.create_plan()
        sub = MemberSubscription.objects.create(
            member=self.member, plan=plan, start_date=date(2026, 11, 1),
            end_date=date(2026, 11, 30), price_at_subscription=plan.price,
            status=MemberSubscription.Status.ACTIVE,
        )
        with patch('django.utils.timezone.localdate', return_value=date(2026, 11, 21)):
            self.assertEqual(sub.current_status(), MemberSubscription.Status.ACTIVE)

    def test_verify_expired_membership(self):
        plan = self.create_plan()
        sub = MemberSubscription.objects.create(
            member=self.member, plan=plan, start_date=date(2026, 10, 1),
            end_date=date(2026, 10, 31), price_at_subscription=plan.price,
            status=MemberSubscription.Status.ACTIVE,
        )
        with patch('django.utils.timezone.localdate', return_value=date(2026, 11, 21)):
            self.assertEqual(sub.current_status(), MemberSubscription.Status.EXPIRED)

    def test_renew_existing_membership(self):
        plan = self.create_plan(duration_months=1)
        existing = MemberSubscription.objects.create(
            member=self.member, plan=plan, start_date=date(2026, 11, 1),
            end_date=date(2026, 11, 30), price_at_subscription=plan.price,
            status=MemberSubscription.Status.ACTIVE,
        )
        with patch('django.utils.timezone.localdate', return_value=date(2026, 11, 21)):
            response = self.client.post(
                reverse('gym:subscription_renew', args=[self.member.pk, existing.pk]),
                {'plan': plan.pk, 'start_date': '2026-12-01'},
            )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(MemberSubscription.objects.filter(member=self.member).count(), 2)
        renewed = MemberSubscription.objects.exclude(pk=existing.pk).get()
        self.assertEqual(renewed.start_date, date(2026, 12, 1))
        self.assertEqual(renewed.end_date, date(2026, 12, 31))
        existing.refresh_from_db()
        self.assertEqual(existing.start_date, date(2026, 11, 1))  # history preserved

    def test_prevent_overlapping_subscriptions(self):
        plan = self.create_plan(duration_months=1)
        MemberSubscription.objects.create(
            member=self.member, plan=plan, start_date=date(2026, 11, 1),
            end_date=date(2026, 11, 30), price_at_subscription=plan.price,
            status=MemberSubscription.Status.ACTIVE,
        )
        with patch('django.utils.timezone.localdate', return_value=date(2026, 11, 15)):
            response = self.client.post(reverse('gym:subscription_assign', args=[self.member.pk]), {
                'plan': plan.pk,
                'start_date': '2026-11-15',
            })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(MemberSubscription.objects.filter(member=self.member).count(), 1)
        self.assertContains(response, 'overlaps')

    def test_verify_member_subscription_history(self):
        plan = self.create_plan(duration_months=1)
        MemberSubscription.objects.create(
            member=self.member, plan=plan, start_date=date(2026, 9, 1),
            end_date=date(2026, 9, 30), price_at_subscription=Decimal('1200.00'),
            status=MemberSubscription.Status.EXPIRED,
        )
        MemberSubscription.objects.create(
            member=self.member, plan=plan, start_date=date(2026, 10, 1),
            end_date=date(2026, 10, 31), price_at_subscription=Decimal('1300.00'),
            status=MemberSubscription.Status.EXPIRED,
        )
        response = self.client.get(reverse('gym:member_detail', args=[self.member.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Subscription History')
        self.assertContains(response, 'BDT 1200.00')
        self.assertContains(response, 'BDT 1300.00')

    def test_verify_deactivated_plan_restrictions(self):
        plan = self.create_plan(is_active=False)
        with patch('django.utils.timezone.localdate', return_value=date(2026, 11, 21)):
            response = self.client.post(reverse('gym:subscription_assign', args=[self.member.pk]), {
                'plan': plan.pk,
                'start_date': '2026-11-21',
            })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(MemberSubscription.objects.filter(member=self.member).count(), 0)

    def test_verify_authentication_and_permissions(self):
        self.client.logout()
        plan = self.create_plan()
        urls = [
            reverse('gym:plan_list'),
            reverse('gym:plan_create'),
            reverse('gym:subscription_list'),
            reverse('gym:subscription_assign', args=[self.member.pk]),
        ]
        for url in urls:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 302)
            self.assertIn('/accounts/login/', response.url)
