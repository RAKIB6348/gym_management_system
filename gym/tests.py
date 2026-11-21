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

from decimal import Decimal
from django.test import TransactionTestCase
from .models import MembershipPayment


class PaymentFeatureTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(username='paystaff', password='pass12345', is_staff=True)
        self.client.force_login(self.staff)
        self.member = Member.objects.create(
            full_name='Pay Member',
            mobile_number='+15550009999',
            gender=Member.Gender.MALE,
            joining_date=date(2026, 1, 1),
            status=Member.Status.ACTIVE,
        )
        self.plan = MembershipPlan.objects.create(name='Monthly', duration_months=1, price=Decimal('1500.00'), is_active=True)
        self.subscription = MemberSubscription.objects.create(
            member=self.member, plan=self.plan, start_date=date(2026, 11, 1),
            end_date=date(2026, 11, 30), price_at_subscription=Decimal('1500.00'),
            status=MemberSubscription.Status.ACTIVE,
        )

    def get_token(self, member_pk):
        response = self.client.get(reverse('gym:payment_collect', args=[member_pk]))
        return response.context['payment_token']

    def post_payment(self, amount, method='cash', date_str='2026-11-21', token=None, subscription=None):
        sub = subscription or self.subscription
        if token is None:
            token = self.get_token(self.member.pk)
        return self.client.post(reverse('gym:payment_collect', args=[self.member.pk]), {
            'payment_token': token,
            'subscription': sub.pk,
            'amount': str(amount),
            'payment_method': method,
            'payment_date': date_str,
            'transaction_id': 'TXN1',
            'note': '',
        })

    def test_full_membership_payment(self):
        response = self.post_payment('1500.00')
        self.assertEqual(response.status_code, 302)
        self.subscription.refresh_from_db()
        self.assertEqual(self.subscription.payment_status(), 'Paid')
        self.assertEqual(self.subscription.remaining_due_amount(), Decimal('0.00'))

    def test_partial_membership_payment(self):
        self.post_payment('1000.00')
        self.assertEqual(self.subscription.total_paid_amount(), Decimal('1000.00'))
        self.assertEqual(self.subscription.remaining_due_amount(), Decimal('500.00'))
        self.assertEqual(self.subscription.payment_status(), 'Partial')

    def test_multiple_partial_payments(self):
        self.post_payment('1000.00')
        self.post_payment('300.00')
        self.post_payment('200.00')
        self.assertEqual(self.subscription.total_paid_amount(), Decimal('1500.00'))
        self.assertEqual(self.subscription.remaining_due_amount(), Decimal('0.00'))
        self.assertEqual(self.subscription.payment_status(), 'Paid')
        self.assertEqual(MembershipPayment.objects.filter(subscription=self.subscription, status='completed').count(), 3)

    def test_remaining_due_calculation(self):
        self.post_payment('400.00')
        self.assertEqual(self.subscription.remaining_due_amount(), Decimal('1100.00'))

    def test_payment_status_calculation(self):
        self.assertEqual(self.subscription.payment_status(), 'Unpaid')
        self.post_payment('500.00')
        self.assertEqual(self.subscription.payment_status(), 'Partial')
        self.post_payment('1000.00')
        self.assertEqual(self.subscription.payment_status(), 'Paid')

    def test_overpayment_prevention(self):
        response = self.post_payment('1600.00')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(MembershipPayment.objects.count(), 0)
        self.assertContains(response, 'exceeds remaining due')

    def test_zero_negative_payment_rejection(self):
        response = self.post_payment('0.00')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(MembershipPayment.objects.count(), 0)
        response = self.post_payment('-10.00')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(MembershipPayment.objects.count(), 0)

    def test_duplicate_submission_prevention(self):
        token = self.get_token(self.member.pk)
        r1 = self.post_payment('500.00', token=token)
        self.assertEqual(r1.status_code, 302)
        r2 = self.post_payment('500.00', token=token)
        self.assertEqual(r2.status_code, 302)  # redirected with error
        self.assertEqual(MembershipPayment.objects.filter(subscription=self.subscription).count(), 1)

    def test_payment_cancellation_and_recalculation(self):
        self.post_payment('1000.00')
        payment = MembershipPayment.objects.first()
        response = self.client.post(reverse('gym:payment_cancel', args=[payment.pk]), {'next': reverse('gym:payment_list')})
        self.assertEqual(response.status_code, 302)
        payment.refresh_from_db()
        self.assertEqual(payment.status, MembershipPayment.Status.CANCELLED)
        self.assertEqual(self.subscription.total_paid_amount(), Decimal('0.00'))
        self.assertEqual(self.subscription.payment_status(), 'Unpaid')

    def test_payment_history(self):
        self.post_payment('500.00')
        response = self.client.get(reverse('gym:payment_list'), {'q': self.member.member_id})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'PAY-')
        self.assertContains(response, self.member.full_name)

    def test_pdf_receipt_generation(self):
        self.post_payment('500.00')
        payment = MembershipPayment.objects.first()
        response = self.client.get(reverse('gym:payment_receipt', args=[payment.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertTrue(response.content.startswith(b'%PDF'))

    def test_dashboard_totals(self):
        self.post_payment('500.00')
        # another subscription/member
        m2 = Member.objects.create(full_name='M2', mobile_number='222', gender='male', joining_date=date(2026,1,1), status='active')
        sub2 = MemberSubscription.objects.create(member=m2, plan=self.plan, start_date=date(2026,11,1), end_date=date(2026,11,30), price_at_subscription=Decimal('1500.00'), status='active')
        # pay sub2 fully
        token = self.get_token(m2.pk)
        self.client.post(reverse('gym:payment_collect', args=[m2.pk]), {
            'payment_token': token, 'subscription': sub2.pk, 'amount': '1500.00', 'payment_method': 'cash', 'payment_date': '2026-11-21', 'transaction_id': '', 'note': ''
        })
        response = self.client.get(reverse('gym:payment_dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['total_fees'], Decimal('3000.00'))
        self.assertEqual(response.context['total_collected'], Decimal('2000.00'))
        self.assertEqual(response.context['total_outstanding'], Decimal('1000.00'))

    def test_authentication_and_permissions(self):
        self.client.logout()
        urls = [
            reverse('gym:payment_list'),
            reverse('gym:payment_dashboard'),
            reverse('gym:payment_collect', args=[self.member.pk]),
        ]
        for url in urls:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 302)
            self.assertIn('/accounts/login/', response.url)

        # cancel requires admin/staff
        payment = MembershipPayment.objects.create(
            member=self.member, subscription=self.subscription, amount=Decimal('100.00'),
            payment_date=date(2026,11,21), payment_method='cash', status='completed', collected_by=self.staff
        )
        nonstaff = User.objects.create_user(username='normal', password='pass12345', is_staff=False)
        self.client.force_login(nonstaff)
        response = self.client.post(reverse('gym:payment_cancel', args=[payment.pk]))
        self.assertEqual(response.status_code, 403)


class PaymentConcurrencyTests(TransactionTestCase):
    def setUp(self):
        self.staff = User.objects.create_user(username='concurrent', password='pass12345', is_staff=True)
        self.member = Member.objects.create(
            full_name='Concurrent Member', mobile_number='999', gender='male', joining_date=date(2026,1,1), status='active'
        )
        self.plan = MembershipPlan.objects.create(name='Plan', duration_months=1, price=Decimal('1000.00'), is_active=True)
        self.subscription = MemberSubscription.objects.create(
            member=self.member, plan=self.plan, start_date=date(2026,11,1), end_date=date(2026,11,30),
            price_at_subscription=Decimal('1000.00'), status='active'
        )

    def test_concurrent_payment_protection(self):
        import threading
        from django.db.models import Sum
        from django.db.models.functions import Coalesce
        from django.test import Client

        results = []

        def pay():
            try:
                c = Client()
                c.force_login(self.staff)
                resp_get = c.get(reverse('gym:payment_collect', args=[self.member.pk]))
                token = resp_get.context['payment_token']
                resp = c.post(reverse('gym:payment_collect', args=[self.member.pk]), {
                    'payment_token': token,
                    'subscription': self.subscription.pk,
                    'amount': '800.00',
                    'payment_method': 'cash',
                    'payment_date': '2026-11-21',
                    'transaction_id': '',
                    'note': '',
                })
                results.append(resp.status_code)
            except Exception:
                results.append('error')

        t1 = threading.Thread(target=pay)
        t2 = threading.Thread(target=pay)
        t1.start(); t2.start()
        t1.join(); t2.join()

        total_paid = MembershipPayment.objects.filter(
            subscription=self.subscription, status=MembershipPayment.Status.COMPLETED
        ).aggregate(total=Coalesce(Sum('amount'), Decimal('0.00')))['total']
        self.assertLessEqual(total_paid, Decimal('1000.00'))
        self.assertTrue(MembershipPayment.objects.filter(subscription=self.subscription, status='completed').count() >= 1)

from .models import Trainer, TrainerAssignment, TrainerAvailability


class TrainerFeatureTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(username='trainerstaff', password='pass12345', is_staff=True)
        self.client.force_login(self.staff)
        self.member = Member.objects.create(
            full_name='Member One', mobile_number='+15550001001', gender='male',
            joining_date=date(2026, 1, 1), status='active'
        )
        self.member2 = Member.objects.create(
            full_name='Member Two', mobile_number='+15550001002', gender='female',
            joining_date=date(2026, 1, 1), status='active'
        )

    def create_trainer(self, **overrides):
        data = {
            'full_name': 'Trainer One', 'phone': '+15559990001', 'email': 't1@example.com',
            'gender': 'male', 'date_of_birth': '1990-01-01', 'address': 'Gym St',
            'specialization': 'Strength', 'experience_years': 5, 'qualification': 'Cert',
            'joining_date': '2026-01-01', 'status': 'active',
        }
        data.update(overrides)
        return Trainer.objects.create(**data)

    def test_create_trainer(self):
        response = self.client.post(reverse('gym:trainer_create'), {
            'full_name': 'New Trainer', 'phone': '+15551112222', 'email': 'new@t.com',
            'gender': 'female', 'date_of_birth': '1992-02-02', 'address': 'Addr',
            'specialization': 'Yoga', 'experience_years': 3, 'qualification': 'RYT',
            'joining_date': '2026-11-21', 'status': 'active',
        })
        self.assertEqual(response.status_code, 302)
        trainer = Trainer.objects.get(full_name='New Trainer')
        self.assertTrue(trainer.trainer_id.startswith('TR-'))
        self.assertEqual(trainer.specialization, 'Yoga')

    def test_edit_trainer(self):
        trainer = self.create_trainer(full_name='Old')
        response = self.client.post(reverse('gym:trainer_edit', args=[trainer.pk]), {
            'full_name': 'Updated Trainer', 'phone': '+15551112222', 'email': 'u@t.com',
            'gender': 'male', 'date_of_birth': '1990-01-01', 'address': 'New Addr',
            'specialization': 'Cardio', 'experience_years': 7, 'qualification': 'New Cert',
            'joining_date': '2026-01-01', 'status': 'active',
        })
        self.assertEqual(response.status_code, 302)
        trainer.refresh_from_db()
        self.assertEqual(trainer.full_name, 'Updated Trainer')
        self.assertEqual(trainer.specialization, 'Cardio')

    def test_activate_deactivate_trainer(self):
        trainer = self.create_trainer(status='active')
        r = self.client.post(reverse('gym:trainer_toggle_status', args=[trainer.pk]), {'next': reverse('gym:trainer_list')})
        self.assertEqual(r.status_code, 302)
        trainer.refresh_from_db()
        self.assertEqual(trainer.status, 'inactive')
        self.client.post(reverse('gym:trainer_toggle_status', args=[trainer.pk]), {'next': reverse('gym:trainer_list')})
        trainer.refresh_from_db()
        self.assertEqual(trainer.status, 'active')

    def test_search_and_filter_trainers(self):
        self.create_trainer(full_name='Alice Strength', phone='+111', specialization='Strength')
        self.create_trainer(full_name='Bob Yoga', phone='+222', specialization='Yoga', status='inactive')
        r = self.client.get(reverse('gym:trainer_list'), {'q': 'Alice'})
        self.assertContains(r, 'Alice Strength')
        self.assertNotContains(r, 'Bob Yoga')
        r = self.client.get(reverse('gym:trainer_list'), {'specialization': 'Yoga'})
        self.assertContains(r, 'Bob Yoga')
        self.assertNotContains(r, 'Alice Strength')
        r = self.client.get(reverse('gym:trainer_list'), {'status': 'inactive'})
        self.assertContains(r, 'Bob Yoga')
        self.assertNotContains(r, 'Alice Strength')

    def test_assign_trainer_to_member(self):
        trainer = self.create_trainer()
        response = self.client.post(reverse('gym:trainer_assign_member', args=[trainer.pk]), {
            'trainer': trainer.pk, 'member': self.member.pk, 'start_date': '2026-11-21', 'end_date': ''
        })
        self.assertEqual(response.status_code, 302)
        a = TrainerAssignment.objects.get(member=self.member)
        self.assertEqual(a.trainer, trainer)
        self.assertEqual(a.status, TrainerAssignment.Status.ACTIVE)

    def test_prevent_duplicate_active_assignments(self):
        trainer = self.create_trainer()
        trainer2 = self.create_trainer(full_name='T2', phone='+15550002')
        TrainerAssignment.objects.create(trainer=trainer, member=self.member, start_date=date(2026,11,1), status='active')
        # direct model create should fail
        with self.assertRaises(Exception):
            TrainerAssignment.objects.create(trainer=trainer2, member=self.member, start_date=date(2026,11,2), status='active')

    def test_reassign_trainer(self):
        trainer1 = self.create_trainer(full_name='T1', phone='+1')
        trainer2 = self.create_trainer(full_name='T2', phone='+2')
        TrainerAssignment.objects.create(trainer=trainer1, member=self.member, start_date=date(2026,11,1), status='active')
        response = self.client.post(reverse('gym:member_assign_trainer', args=[self.member.pk]), {
            'trainer': trainer2.pk, 'member': self.member.pk, 'start_date': '2026-11-21', 'end_date': ''
        })
        self.assertEqual(response.status_code, 302)
        assignments = TrainerAssignment.objects.filter(member=self.member).order_by('start_date')
        self.assertEqual(assignments.count(), 2)
        self.assertEqual(assignments[0].status, TrainerAssignment.Status.COMPLETED)
        self.assertEqual(assignments[1].status, TrainerAssignment.Status.ACTIVE)
        self.assertEqual(assignments[1].trainer, trainer2)

    def test_verify_assignment_history(self):
        trainer1 = self.create_trainer(full_name='T1', phone='+1')
        trainer2 = self.create_trainer(full_name='T2', phone='+2')
        TrainerAssignment.objects.create(trainer=trainer1, member=self.member, start_date=date(2026,10,1), end_date=date(2026,10,31), status='completed')
        TrainerAssignment.objects.create(trainer=trainer2, member=self.member, start_date=date(2026,11,1), status='active')
        r = self.client.get(reverse('gym:member_detail', args=[self.member.pk]))
        self.assertContains(r, 'Previous Trainer History')
        self.assertContains(r, 'T1')
        self.assertContains(r, 'T2')

    def test_configure_trainer_availability(self):
        trainer = self.create_trainer()
        response = self.client.post(reverse('gym:trainer_availability', args=[trainer.pk]), {
            'day_of_week': '0', 'start_time': '09:00', 'end_time': '11:00', 'is_available': 'on'
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(TrainerAvailability.objects.filter(trainer=trainer).count(), 1)
        slot = TrainerAvailability.objects.first()
        self.assertEqual(slot.day_of_week, 0)

    def test_prevent_overlapping_availability(self):
        trainer = self.create_trainer()
        TrainerAvailability.objects.create(trainer=trainer, day_of_week=0, start_time='09:00', end_time='11:00', is_available=True)
        response = self.client.post(reverse('gym:trainer_availability', args=[trainer.pk]), {
            'day_of_week': '0', 'start_time': '10:00', 'end_time': '12:00', 'is_available': 'on'
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(TrainerAvailability.objects.filter(trainer=trainer).count(), 1)

    def test_verify_trainer_dashboard(self):
        t1 = self.create_trainer(full_name='T1', phone='+1')
        self.create_trainer(full_name='T2', phone='+2', status='inactive')
        TrainerAssignment.objects.create(trainer=t1, member=self.member, start_date=date(2026,11,1), status='active')
        r = self.client.get(reverse('gym:trainer_dashboard'))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.context['total_trainers'], 2)
        self.assertEqual(r.context['active_trainers'], 1)
        self.assertEqual(r.context['inactive_trainers'], 1)
        self.assertEqual(r.context['members_with_trainers'], 1)

    def test_verify_member_profile_integration(self):
        trainer = self.create_trainer(full_name='Coach', specialization='Cardio')
        TrainerAssignment.objects.create(trainer=trainer, member=self.member, start_date=date(2026,11,21), status='active')
        r = self.client.get(reverse('gym:member_detail', args=[self.member.pk]))
        self.assertContains(r, 'Current Trainer')
        self.assertContains(r, 'Coach')
        self.assertContains(r, 'Cardio')
        self.assertContains(r, 'Change Trainer')

    def test_verify_authentication_and_permissions(self):
        self.client.logout()
        trainer = self.create_trainer()
        urls = [
            reverse('gym:trainer_list'),
            reverse('gym:trainer_create'),
            reverse('gym:trainer_dashboard'),
            reverse('gym:trainer_detail', args=[trainer.pk]),
        ]
        for url in urls:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 302)
            self.assertIn('/accounts/login/', response.url)

from datetime import datetime, time as dt_time
from django.utils import timezone as dj_timezone
from .models import GymClass, ClassSchedule, ClassSession, ClassEnrollment, TrainerAvailability


class ClassScheduleFeatureTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(username='classstaff', password='pass12345', is_staff=True)
        self.client.force_login(self.staff)
        self.trainer = Trainer.objects.create(full_name='Class Trainer', phone='900', gender='male', specialization='Yoga', experience_years=3, joining_date=date(2026,1,1), status='active')
        self.member = Member.objects.create(full_name='Class Member', mobile_number='901', gender='male', joining_date=date(2026,1,1), status='active')
        # active subscription covering 2026-11
        self.plan = MembershipPlan.objects.create(name='Month', duration_months=1, price=Decimal('1000.00'), is_active=True)
        self.sub = MemberSubscription.objects.create(member=self.member, plan=self.plan, start_date=date(2026,11,1), end_date=date(2026,11,30), price_at_subscription=Decimal('1000.00'), status='active')
        # trainer availability Monday 09:00-11:00
        TrainerAvailability.objects.create(trainer=self.trainer, day_of_week=0, start_time=dt_time(9,0), end_time=dt_time(11,0), is_available=True)

    def create_class(self, **overrides):
        data = {'name': 'Yoga', 'description': 'Relax', 'trainer': self.trainer, 'capacity': 10, 'duration_minutes': 60, 'status': 'active'}
        data.update(overrides)
        return GymClass.objects.create(**data)

    def test_create_gym_class(self):
        r = self.client.post(reverse('gym:class_create'), {
            'name': 'HIIT', 'description': 'Hard', 'trainer': self.trainer.pk,
            'capacity': 15, 'duration_minutes': 45, 'status': 'active'
        })
        self.assertEqual(r.status_code, 302)
        self.assertTrue(GymClass.objects.filter(name='HIIT').exists())

    def test_edit_gym_class(self):
        c = self.create_class(name='Old')
        r = self.client.post(reverse('gym:class_edit', args=[c.pk]), {
            'name': 'New Name', 'description': 'D', 'trainer': self.trainer.pk,
            'capacity': 20, 'duration_minutes': 30, 'status': 'active'
        })
        self.assertEqual(r.status_code, 302)
        c.refresh_from_db()
        self.assertEqual(c.name, 'New Name')
        self.assertEqual(c.capacity, 20)

    def test_assign_trainer(self):
        t2 = Trainer.objects.create(full_name='T2', phone='902', gender='female', specialization='Cardio', experience_years=2, joining_date=date(2026,1,1), status='active')
        c = self.create_class()
        r = self.client.post(reverse('gym:class_edit', args=[c.pk]), {
            'name': c.name, 'description': '', 'trainer': t2.pk,
            'capacity': 10, 'duration_minutes': 60, 'status': 'active'
        })
        self.assertEqual(r.status_code, 302)
        c.refresh_from_db()
        self.assertEqual(c.trainer, t2)

    def test_configure_weekly_schedule(self):
        c = self.create_class()
        r = self.client.post(reverse('gym:class_schedule_add', args=[c.pk]), {
            'day_of_week': '0', 'start_time': '09:00', 'end_time': '10:00', 'is_active': 'on'
        })
        self.assertEqual(r.status_code, 302)
        self.assertEqual(ClassSchedule.objects.filter(gym_class=c).count(), 1)

    def test_prevent_trainer_schedule_conflict(self):
        c1 = self.create_class(name='C1')
        c2 = self.create_class(name='C2')
        ClassSchedule.objects.create(gym_class=c1, day_of_week=0, start_time=dt_time(9,0), end_time=dt_time(10,0), is_active=True)
        r = self.client.post(reverse('gym:class_schedule_add', args=[c2.pk]), {
            'day_of_week': '0', 'start_time': '09:30', 'end_time': '10:30', 'is_active': 'on'
        })
        self.assertEqual(r.status_code, 302)
        self.assertEqual(ClassSchedule.objects.filter(gym_class=c2).count(), 0)

    def test_validate_trainer_availability(self):
        c = self.create_class()
        # outside availability
        r = self.client.post(reverse('gym:class_schedule_add', args=[c.pk]), {
            'day_of_week': '0', 'start_time': '11:00', 'end_time': '12:00', 'is_active': 'on'
        })
        self.assertEqual(r.status_code, 302)
        self.assertEqual(ClassSchedule.objects.filter(gym_class=c).count(), 0)

    def test_generate_class_sessions(self):
        c = self.create_class()
        ClassSchedule.objects.create(gym_class=c, day_of_week=0, start_time=dt_time(9,0), end_time=dt_time(10,0), is_active=True) # Monday
        # generate for 14 days from "today" in test; we'll patch localdate
        with patch('gym.views.timezone.localdate', return_value=date(2026, 11, 16)):  # a Monday
            r = self.client.post(reverse('gym:class_session_generate', args=[c.pk]), {'days_ahead': 7})
        self.assertEqual(r.status_code, 302)
        self.assertTrue(ClassSession.objects.filter(gym_class=c).exists())

    def test_prevent_duplicate_sessions(self):
        c = self.create_class()
        ClassSchedule.objects.create(gym_class=c, day_of_week=0, start_time=dt_time(9,0), end_time=dt_time(10,0), is_active=True)
        with patch('gym.views.timezone.localdate', return_value=date(2026, 11, 16)):
            self.client.post(reverse('gym:class_session_generate', args=[c.pk]), {'days_ahead': 7})
            count1 = ClassSession.objects.filter(gym_class=c).count()
            self.client.post(reverse('gym:class_session_generate', args=[c.pk]), {'days_ahead': 7})
            count2 = ClassSession.objects.filter(gym_class=c).count()
        self.assertEqual(count1, count2)

    def make_session(self, gym_class=None, start=None, end=None, capacity=5):
        gym_class = gym_class or self.create_class()
        tz = dj_timezone.get_current_timezone()
        start = start or dj_timezone.make_aware(datetime(2026, 11, 23, 9, 0), tz)
        end = end or dj_timezone.make_aware(datetime(2026, 11, 23, 10, 0), tz)
        return ClassSession.objects.create(gym_class=gym_class, schedule=None, trainer=gym_class.trainer, start_datetime=start, end_datetime=end, capacity=capacity, status='scheduled')

    def test_enroll_member(self):
        c = self.create_class()
        s = self.make_session(gym_class=c)
        r = self.client.post(reverse('gym:class_session_enroll', args=[s.pk]), {'member_id': self.member.pk, 'next': reverse('gym:class_detail', args=[c.pk])})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(ClassEnrollment.objects.filter(session=s, member=self.member, status='enrolled').count(), 1)

    def test_prevent_duplicate_enrollment(self):
        c = self.create_class()
        s = self.make_session(gym_class=c)
        self.client.post(reverse('gym:class_session_enroll', args=[s.pk]), {'member_id': self.member.pk, 'next': '/'})
        r = self.client.post(reverse('gym:class_session_enroll', args=[s.pk]), {'member_id': self.member.pk, 'next': '/'})
        self.assertEqual(ClassEnrollment.objects.filter(session=s, member=self.member, status='enrolled').count(), 1)

    def test_prevent_capacity_overflow(self):
        c = self.create_class(capacity=1)
        s = self.make_session(gym_class=c, capacity=1)
        m2 = Member.objects.create(full_name='M2', mobile_number='902', gender='female', joining_date=date(2026,1,1), status='active')
        MemberSubscription.objects.create(member=m2, plan=self.plan, start_date=date(2026,11,1), end_date=date(2026,11,30), price_at_subscription=Decimal('1000.00'), status='active')
        self.client.post(reverse('gym:class_session_enroll', args=[s.pk]), {'member_id': self.member.pk, 'next': '/'})
        r = self.client.post(reverse('gym:class_session_enroll', args=[s.pk]), {'member_id': m2.pk, 'next': '/'})
        self.assertEqual(ClassEnrollment.objects.filter(session=s, status='enrolled').count(), 1)

    def test_reject_expired_membership(self):
        c = self.create_class()
        tz = dj_timezone.get_current_timezone()
        s = self.make_session(gym_class=c, start=dj_timezone.make_aware(datetime(2026, 12, 15, 9, 0), tz), end=dj_timezone.make_aware(datetime(2026, 12, 15, 10, 0), tz))
        r = self.client.post(reverse('gym:class_session_enroll', args=[s.pk]), {'member_id': self.member.pk, 'next': '/'})
        self.assertEqual(ClassEnrollment.objects.filter(session=s, status='enrolled').count(), 0)

    def test_cancel_enrollment(self):
        c = self.create_class()
        s = self.make_session(gym_class=c)
        self.client.post(reverse('gym:class_session_enroll', args=[s.pk]), {'member_id': self.member.pk, 'next': '/'})
        e = ClassEnrollment.objects.get(session=s, member=self.member)
        r = self.client.post(reverse('gym:class_enrollment_cancel', args=[e.pk]), {'next': reverse('gym:member_detail', args=[self.member.pk])})
        self.assertEqual(r.status_code, 302)
        e.refresh_from_db()
        self.assertEqual(e.status, 'cancelled')

    def test_verify_member_profile_integration(self):
        c = self.create_class(name='Yoga Class')
        s = self.make_session(gym_class=c)
        ClassEnrollment.objects.create(member=self.member, session=s, status='enrolled')
        r = self.client.get(reverse('gym:member_detail', args=[self.member.pk]))
        self.assertContains(r, 'My Classes')
        self.assertContains(r, 'Yoga Class')

    def test_verify_dashboard_kpi_calculations(self):
        c = self.create_class()
        tz = dj_timezone.get_current_timezone()
        s = ClassSession.objects.create(gym_class=c, schedule=None, trainer=self.trainer, start_datetime=timezone.now() + timedelta(days=1), end_datetime=timezone.now() + timedelta(days=1, hours=1), capacity=10, status='scheduled')
        ClassEnrollment.objects.create(member=self.member, session=s, status='enrolled')
        r = self.client.get(reverse('gym:class_dashboard'))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.context['total_active_classes'], 1)
        self.assertGreaterEqual(r.context['upcoming_sessions_count'], 1)
        self.assertEqual(r.context['total_enrolled_members'], 1)

    def test_verify_authentication_and_permissions(self):
        self.client.logout()
        c = self.create_class()
        urls = [reverse('gym:class_list'), reverse('gym:class_create'), reverse('gym:class_dashboard'), reverse('gym:weekly_schedule')]
        for url in urls:
            r = self.client.get(url)
            self.assertEqual(r.status_code, 302)
            self.assertIn('/accounts/login/', r.url)


class ClassEnrollmentConcurrencyTests(TransactionTestCase):
    def setUp(self):
        self.staff = User.objects.create_user(username='classcon', password='pass12345', is_staff=True)
        self.trainer = Trainer.objects.create(full_name='CT', phone='999', gender='male', specialization='S', experience_years=1, joining_date=date(2026,1,1), status='active')
        self.plan = MembershipPlan.objects.create(name='M', duration_months=1, price=Decimal('1000.00'), is_active=True)
        self.cls = GymClass.objects.create(name='C', trainer=self.trainer, capacity=1, duration_minutes=60, status='active')
        tz = dj_timezone.get_current_timezone()
        self.session_obj = ClassSession.objects.create(gym_class=self.cls, trainer=self.trainer, start_datetime=dj_timezone.make_aware(datetime(2026,11,23,9,0), tz), end_datetime=dj_timezone.make_aware(datetime(2026,11,23,10,0), tz), capacity=1, status='scheduled')
        self.m1 = Member.objects.create(full_name='M1', mobile_number='1', gender='male', joining_date=date(2026,1,1), status='active')
        self.m2 = Member.objects.create(full_name='M2', mobile_number='2', gender='female', joining_date=date(2026,1,1), status='active')
        MemberSubscription.objects.create(member=self.m1, plan=self.plan, start_date=date(2026,11,1), end_date=date(2026,11,30), price_at_subscription=Decimal('1000.00'), status='active')
        MemberSubscription.objects.create(member=self.m2, plan=self.plan, start_date=date(2026,11,1), end_date=date(2026,11,30), price_at_subscription=Decimal('1000.00'), status='active')

    def test_prevent_concurrent_overbooking(self):
        import threading
        from django.test import Client
        results = []

        def enroll(member):
            try:
                c = Client()
                c.force_login(self.staff)
                r = c.post(reverse('gym:class_session_enroll', args=[self.session_obj.pk]), {'member_id': member.pk, 'next': '/'})
                results.append(r.status_code)
            except Exception:
                results.append('err')

        t1 = threading.Thread(target=enroll, args=(self.m1,))
        t2 = threading.Thread(target=enroll, args=(self.m2,))
        t1.start(); t2.start(); t1.join(); t2.join()
        enrolled = ClassEnrollment.objects.filter(session=self.session_obj, status='enrolled').count()
        self.assertLessEqual(enrolled, 1)
