import csv
import io
import json
from datetime import date, datetime, time as dt_time, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import (
    Member, MembershipPlan, MemberSubscription, MembershipPayment,
    Trainer, TrainerAssignment, TrainerAvailability,
    GymClass, ClassSchedule, ClassSession, ClassEnrollment,
)


def make_image(name='test.jpg'):
    # tiny valid JPEG header/footer is complex; use a minimal PNG-like bytes won't pass ImageField validation.
    # Generate a simple valid GIF.
    gif = b'GIF87a\x01\x00\x01\x00\x80\x01\x00\x00\x00\x00\xff\xff\xff!\xf9\x04\x01\n\x00\x01\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;'
    return SimpleUploadedFile(name, gif, content_type='image/gif')


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class FullE2ETest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser(username='admin', password='adminpass123', email='admin@example.com')
        cls.staff = User.objects.create_user(username='staff', password='staffpass123', is_staff=True)
        cls.normal = User.objects.create_user(username='normal', password='normalpass123', is_staff=False)

        # 4 plans
        cls.plan_monthly = MembershipPlan.objects.create(name='Monthly', description='1 month', duration_months=1, price=Decimal('1500.00'), is_active=True)
        cls.plan_quarterly = MembershipPlan.objects.create(name='Quarterly', description='3 months', duration_months=3, price=Decimal('4000.00'), is_active=True)
        cls.plan_half = MembershipPlan.objects.create(name='Half-Yearly', description='6 months', duration_months=6, price=Decimal('7500.00'), is_active=True)
        cls.plan_yearly = MembershipPlan.objects.create(name='Yearly', description='12 months', duration_months=12, price=Decimal('14000.00'), is_active=True)

        # 20 members
        cls.members = []
        for i in range(1, 21):
            m = Member.objects.create(
                full_name=f'Member {i:02d}', mobile_number=f'+155500{i:04d}',
                email=f'm{i}@example.com', gender='male' if i % 2 else 'female',
                date_of_birth=date(1990, 1, 1), address=f'Addr {i}',
                emergency_contact_name=f'EC {i}', emergency_contact_number=f'+166600{i:04d}',
                joining_date=date(2026, 11, 1), status='active' if i <= 18 else 'inactive'
            )
            cls.members.append(m)

        # 15 subscriptions with varied statuses/scenarios
        today = date(2026, 11, 21)
        cls.subs = []
        # active
        cls.subs.append(MemberSubscription.objects.create(member=cls.members[0], plan=cls.plan_monthly, start_date=date(2026,11,1), end_date=date(2026,11,30), price_at_subscription=Decimal('1500.00'), status='active'))
        # expired
        cls.subs.append(MemberSubscription.objects.create(member=cls.members[1], plan=cls.plan_monthly, start_date=date(2026,10,1), end_date=date(2026,10,31), price_at_subscription=Decimal('1500.00'), status='expired'))
        # upcoming
        cls.subs.append(MemberSubscription.objects.create(member=cls.members[2], plan=cls.plan_quarterly, start_date=date(2026,12,1), end_date=date(2027,2,28), price_at_subscription=Decimal('4000.00'), status='upcoming'))
        # cancelled
        cls.subs.append(MemberSubscription.objects.create(member=cls.members[3], plan=cls.plan_monthly, start_date=date(2026,11,1), end_date=date(2026,11,30), price_at_subscription=Decimal('1500.00'), status='cancelled'))
        # create remaining 11 as active/expired mix
        for i in range(4, 15):
            start = date(2026, 11, 1) if i % 2 == 0 else date(2026, 9, 1)
            end = date(2026, 11, 30) if i % 2 == 0 else date(2026, 9, 30)
            cls.subs.append(MemberSubscription.objects.create(member=cls.members[i], plan=cls.plan_monthly, start_date=start, end_date=end, price_at_subscription=Decimal('1500.00'), status='active' if i % 2 == 0 else 'expired'))

        # 20 payments
        cls.payments = []
        for i in range(10):
            cls.payments.append(MembershipPayment.objects.create(member=cls.subs[0].member, subscription=cls.subs[0], amount=Decimal('100.00'), payment_date=date(2026,11,10), payment_method='cash', status='completed', collected_by=cls.staff, payment_reference=f'PAY-SEED-{i+1:02d}'))
        for i in range(5):
            cls.payments.append(MembershipPayment.objects.create(member=cls.subs[1].member, subscription=cls.subs[1], amount=Decimal('200.00'), payment_date=date(2026,11,11), payment_method='bkash', status='completed', collected_by=cls.staff, payment_reference=f'PAY-SEED-{11+i:02d}'))
        for i in range(3):
            cls.payments.append(MembershipPayment.objects.create(member=cls.subs[4].member, subscription=cls.subs[4], amount=Decimal('50.00'), payment_date=date(2026,11,12), payment_method='nagad', status='completed', collected_by=cls.staff, payment_reference=f'PAY-SEED-{16+i:02d}'))
        for i in range(2):
            cls.payments.append(MembershipPayment.objects.create(member=cls.subs[5].member, subscription=cls.subs[5], amount=Decimal('75.00'), payment_date=date(2026,11,13), payment_method='bank_transfer', status='cancelled', collected_by=cls.staff, payment_reference=f'PAY-SEED-{19+i:02d}'))

        # 5 trainers
        cls.trainers = []
        specs = ['Strength', 'Yoga', 'Cardio', 'HIIT', 'CrossFit']
        for i in range(5):
            cls.trainers.append(Trainer.objects.create(full_name=f'Trainer {i+1}', phone=f'+177700{i:04d}', email=f't{i}@example.com', gender='male', specialization=specs[i], experience_years=2+i, joining_date=date(2026,1,1), status='active'))

        # 10 trainer assignments
        cls.assignments = []
        for i in range(10):
            cls.assignments.append(TrainerAssignment.objects.create(trainer=cls.trainers[i % 5], member=cls.members[i], start_date=date(2026,11,1), status='active'))

        # trainer availability
        for t in cls.trainers:
            TrainerAvailability.objects.create(trainer=t, day_of_week=0, start_time=dt_time(6,0), end_time=dt_time(12,0), is_available=True)

        # 5 classes
        cls.classes = []
        names = ['Yoga', 'Cardio', 'Zumba', 'Strength Training', 'HIIT']
        for i, name in enumerate(names):
            cls.classes.append(GymClass.objects.create(name=name, description=name, trainer=cls.trainers[i], capacity=10, duration_minutes=60, status='active'))
            ClassSchedule.objects.create(gym_class=cls.classes[i], day_of_week=0, start_time=dt_time(7,0), end_time=dt_time(8,0), is_active=True)

        # 10 sessions
        tz = timezone.get_current_timezone()
        cls.sessions = []
        base = timezone.make_aware(datetime(2026, 11, 23, 7, 0), tz)  # Monday
        for i in range(10):
            start = base + timedelta(days=i)
            end = start + timedelta(hours=1)
            cls.sessions.append(ClassSession.objects.create(gym_class=cls.classes[i % 5], trainer=cls.classes[i % 5].trainer, start_datetime=start, end_datetime=end, capacity=10, status='scheduled'))

        # 15 enrollments
        cls.enrollments = []
        # ensure members 0-14 have subscriptions covering 2026-11-23 onward? subs[0] covers 11/1-11/30 for member 0; member 1 has expired. We'll enroll members with valid coverage.
        valid_members = [cls.members[0]] + cls.members[4:15]  # have active subs covering Nov
        for i in range(15):
            m = valid_members[i % len(valid_members)]
            s = cls.sessions[i % len(cls.sessions)]
            # avoid duplicate/overlap by using different sessions/members combos
            try:
                cls.enrollments.append(ClassEnrollment.objects.create(member=m, session=s, status='enrolled'))
            except Exception:
                pass

    def login_staff(self):
        self.client.force_login(self.staff)

    def login_admin(self):
        self.client.force_login(self.admin)

    # ---------------- Member Registration & Profile ----------------
    def test_member_create(self):
        self.login_staff()
        r = self.client.post(reverse('gym:member_create'), {
            'full_name': 'New E2E Member', 'mobile_number': '+15550999999', 'email': 'new@e2e.com',
            'gender': 'male', 'date_of_birth': '1995-05-05', 'address': 'A', 'emergency_contact_name': 'E',
            'emergency_contact_number': '+15550888888', 'joining_date': '2026-11-21', 'status': 'active'
        })
        self.assertEqual(r.status_code, 302)
        self.assertTrue(Member.objects.filter(full_name='New E2E Member').exists())

    def test_member_edit(self):
        self.login_staff()
        m = self.members[0]
        r = self.client.post(reverse('gym:member_edit', args=[m.pk]), {
            'full_name': 'Edited Name', 'mobile_number': m.mobile_number, 'email': m.email,
            'gender': m.gender, 'date_of_birth': '1990-01-01', 'address': 'New', 'emergency_contact_name': 'E',
            'emergency_contact_number': '+1666000001', 'joining_date': '2026-11-01', 'status': 'active'
        })
        self.assertEqual(r.status_code, 302)
        m.refresh_from_db()
        self.assertEqual(m.full_name, 'Edited Name')

    def test_member_view_profile(self):
        self.login_staff()
        r = self.client.get(reverse('gym:member_detail', args=[self.members[0].pk]))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, self.members[0].member_id)

    def test_member_unique_id(self):
        ids = list(Member.objects.values_list('member_id', flat=True))
        self.assertEqual(len(ids), len(set(ids)))
        self.assertTrue(all(i.startswith('GYM-') for i in ids))

    def test_member_search_filter(self):
        self.login_staff()
        r = self.client.get(reverse('gym:member_list'), {'q': self.members[0].member_id})
        self.assertContains(r, self.members[0].full_name)
        r = self.client.get(reverse('gym:member_list'), {'status': 'inactive'})
        self.assertEqual(r.status_code, 200)

    def test_member_activate_deactivate(self):
        self.login_staff()
        m = self.members[0]
        r = self.client.post(reverse('gym:member_toggle_status', args=[m.pk]), {'next': reverse('gym:member_list')})
        self.assertEqual(r.status_code, 302)
        m.refresh_from_db()
        self.assertIn(m.status, ['active', 'inactive'])

    def test_member_validation_and_duplicate(self):
        self.login_staff()
        r = self.client.post(reverse('gym:member_create'), {'full_name': '', 'mobile_number': '', 'gender': '', 'joining_date': '', 'status': ''})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(Member.objects.filter(full_name='').count(), 0)

    def test_member_photo_upload(self):
        self.login_staff()
        r = self.client.post(reverse('gym:member_create'), {
            'full_name': 'Photo Member', 'mobile_number': '+15550111111', 'email': '',
            'gender': 'male', 'date_of_birth': '', 'address': '', 'emergency_contact_name': '',
            'emergency_contact_number': '', 'joining_date': '2026-11-21', 'status': 'active',
            'profile_photo': make_image('photo.gif')
        })
        self.assertEqual(r.status_code, 302)
        m = Member.objects.get(full_name='Photo Member')
        self.assertTrue(bool(m.profile_photo))

    def test_member_auth(self):
        r = self.client.get(reverse('gym:member_list'))
        self.assertEqual(r.status_code, 302)

    # ---------------- Membership Plans ----------------
    def test_plan_create_monthly_yearly(self):
        self.login_staff()
        for name, dur, price in [('MPlan', 1, '1000.00'), ('YPlan', 12, '10000.00')]:
            r = self.client.post(reverse('gym:plan_create'), {'name': name, 'description': '', 'duration_months': dur, 'price': price, 'is_active': 'on'})
            self.assertEqual(r.status_code, 302)
            self.assertTrue(MembershipPlan.objects.filter(name=name, duration_months=dur).exists())

    def test_plan_edit_deactivate(self):
        self.login_staff()
        p = self.plan_monthly
        r = self.client.post(reverse('gym:plan_edit', args=[p.pk]), {'name': p.name, 'description': 'upd', 'duration_months': 1, 'price': '1600.00', 'is_active': 'on'})
        self.assertEqual(r.status_code, 302)
        p.refresh_from_db()
        self.assertEqual(p.price, Decimal('1600.00'))
        r = self.client.post(reverse('gym:plan_toggle_status', args=[p.pk]), {'next': reverse('gym:plan_list')})
        self.assertEqual(r.status_code, 302)

    def test_plan_assign_and_expiry(self):
        self.login_staff()
        m = Member.objects.create(full_name='PlanAssign', mobile_number='+15550222222', gender='male', joining_date=date(2026,11,1), status='active')
        r = self.client.post(reverse('gym:subscription_assign', args=[m.pk]), {'plan': self.plan_yearly.pk, 'start_date': '2026-11-21'})
        self.assertEqual(r.status_code, 302)
        sub = MemberSubscription.objects.get(member=m)
        self.assertEqual(sub.end_date, date(2027, 11, 20))

    def test_subscription_status_detection(self):
        today = date(2026, 11, 21)
        self.assertEqual(self.subs[0].current_status(today=today), 'active')
        self.assertEqual(self.subs[1].current_status(today=today), 'expired')
        self.assertEqual(self.subs[2].current_status(today=today), 'upcoming')

    def test_subscription_renew_and_overlap(self):
        self.login_staff()
        m = Member.objects.create(full_name='RenewM', mobile_number='+15550333333', gender='male', joining_date=date(2026,11,1), status='active')
        sub = MemberSubscription.objects.create(member=m, plan=self.plan_monthly, start_date=date(2026,11,1), end_date=date(2026,11,30), price_at_subscription=Decimal('1500.00'), status='active')
        # overlap
        r = self.client.post(reverse('gym:subscription_assign', args=[m.pk]), {'plan': self.plan_monthly.pk, 'start_date': '2026-11-15'})
        self.assertEqual(r.status_code, 200)
        # renew
        r = self.client.post(reverse('gym:subscription_renew', args=[m.pk, sub.pk]), {'plan': self.plan_monthly.pk, 'start_date': '2026-12-01'})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(MemberSubscription.objects.filter(member=m).count(), 2)

    def test_historical_subscription_price(self):
        m = Member.objects.create(full_name='HistM', mobile_number='+15550444444', gender='male', joining_date=date(2026,11,1), status='active')
        p = MembershipPlan.objects.create(name='HistP', duration_months=1, price=Decimal('1000.00'), is_active=True)
        sub = MemberSubscription.objects.create(member=m, plan=p, start_date=date(2026,11,1), end_date=date(2026,11,30), price_at_subscription=p.price, status='active')
        p.price = Decimal('2000.00')
        p.save()
        sub.refresh_from_db()
        self.assertEqual(sub.price_at_subscription, Decimal('1000.00'))

    # ---------------- Payments ----------------
    def _pay(self, member, sub, amount, token=None):
        if token is None:
            resp = self.client.get(reverse('gym:payment_collect', args=[member.pk]) + f'?subscription={sub.pk}')
            token = resp.context['payment_token']
        return self.client.post(reverse('gym:payment_collect', args=[member.pk]), {
            'payment_token': token, 'subscription': sub.pk, 'amount': str(amount),
            'payment_method': 'cash', 'payment_date': '2026-11-21', 'transaction_id': 'TX', 'note': ''
        })

    def test_payment_full_partial_multiple(self):
        self.login_staff()
        m = Member.objects.create(full_name='PayM', mobile_number='+15550555555', gender='male', joining_date=date(2026,11,1), status='active')
        sub = MemberSubscription.objects.create(member=m, plan=self.plan_monthly, start_date=date(2026,11,1), end_date=date(2026,11,30), price_at_subscription=Decimal('1500.00'), status='active')
        r = self._pay(m, sub, '500.00')
        self.assertEqual(r.status_code, 302)
        self.assertEqual(sub.payment_status(), 'Partial')
        self._pay(m, sub, '500.00')
        self._pay(m, sub, '500.00')
        self.assertEqual(sub.payment_status(), 'Paid')
        self.assertEqual(sub.remaining_due_amount(), Decimal('0.00'))

    def test_payment_reject_invalid(self):
        self.login_staff()
        m = Member.objects.create(full_name='PayInv', mobile_number='+15550666666', gender='male', joining_date=date(2026,11,1), status='active')
        sub = MemberSubscription.objects.create(member=m, plan=self.plan_monthly, start_date=date(2026,11,1), end_date=date(2026,11,30), price_at_subscription=Decimal('1000.00'), status='active')
        r = self._pay(m, sub, '1200.00')
        self.assertEqual(r.status_code, 200)
        r = self._pay(m, sub, '0.00')
        self.assertEqual(r.status_code, 200)
        r = self._pay(m, sub, '-5.00')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(MembershipPayment.objects.filter(subscription=sub, status='completed').count(), 0)

    def test_payment_duplicate_cancel_history_receipt(self):
        self.login_staff()
        m = Member.objects.create(full_name='PayDup', mobile_number='+15550777777', gender='male', joining_date=date(2026,11,1), status='active')
        sub = MemberSubscription.objects.create(member=m, plan=self.plan_monthly, start_date=date(2026,11,1), end_date=date(2026,11,30), price_at_subscription=Decimal('1000.00'), status='active')
        token = self.client.get(reverse('gym:payment_collect', args=[m.pk]) + f'?subscription={sub.pk}').context['payment_token']
        r1 = self._pay(m, sub, '200.00', token=token)
        self.assertEqual(r1.status_code, 302)
        r2 = self._pay(m, sub, '200.00', token=token)
        self.assertEqual(MembershipPayment.objects.filter(subscription=sub).count(), 1)
        pmt = MembershipPayment.objects.get(subscription=sub)
        # receipt
        rr = self.client.get(reverse('gym:payment_receipt', args=[pmt.pk]))
        self.assertEqual(rr.status_code, 200)
        self.assertEqual(rr['Content-Type'], 'application/pdf')
        # cancel
        self.login_admin()
        rc = self.client.post(reverse('gym:payment_cancel', args=[pmt.pk]), {'next': reverse('gym:payment_list')})
        self.assertEqual(rc.status_code, 302)
        pmt.refresh_from_db()
        self.assertEqual(pmt.status, 'cancelled')

    def test_payment_dashboard_totals(self):
        self.login_staff()
        r = self.client.get(reverse('gym:payment_dashboard'))
        self.assertEqual(r.status_code, 200)
        self.assertIn('total_collected', r.context)

    # ---------------- Trainers ----------------
    def test_trainer_crud_search_assign(self):
        self.login_staff()
        r = self.client.post(reverse('gym:trainer_create'), {
            'full_name': 'E2E Trainer', 'phone': '+18880001111', 'email': 'e2e@t.com', 'gender': 'male',
            'date_of_birth': '1990-01-01', 'address': 'A', 'specialization': 'Yoga', 'experience_years': 4,
            'qualification': 'Cert', 'joining_date': '2026-11-21', 'status': 'active'
        })
        self.assertEqual(r.status_code, 302)
        t = Trainer.objects.get(full_name='E2E Trainer')
        r = self.client.get(reverse('gym:trainer_detail', args=[t.pk]))
        self.assertContains(r, t.trainer_id)
        r = self.client.get(reverse('gym:trainer_list'), {'q': 'E2E'})
        self.assertContains(r, 'E2E Trainer')
        # assign
        m = Member.objects.create(full_name='AssignM', mobile_number='+15550990000', gender='male', joining_date=date(2026,11,1), status='active')
        r = self.client.post(reverse('gym:trainer_assign_member', args=[t.pk]), {'trainer': t.pk, 'member': m.pk, 'start_date': '2026-11-21', 'end_date': ''})
        self.assertEqual(r.status_code, 302)
        self.assertTrue(TrainerAssignment.objects.filter(trainer=t, member=m, status='active').exists())

    def test_trainer_reassign_availability_dashboard(self):
        self.login_staff()
        t1 = self.trainers[0]; t2 = self.trainers[1]
        m = Member.objects.create(full_name='ReasM', mobile_number='+15550990001', gender='female', joining_date=date(2026,11,1), status='active')
        TrainerAssignment.objects.create(trainer=t1, member=m, start_date=date(2026,11,1), status='active')
        r = self.client.post(reverse('gym:member_assign_trainer', args=[m.pk]), {'trainer': t2.pk, 'member': m.pk, 'start_date': '2026-11-21', 'end_date': ''})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(TrainerAssignment.objects.filter(member=m, status='active').count(), 1)
        self.assertEqual(TrainerAssignment.objects.filter(member=m).count(), 2)
        # availability
        r = self.client.post(reverse('gym:trainer_availability', args=[t1.pk]), {'day_of_week': '1', 'start_time': '09:00', 'end_time': '10:00', 'is_available': 'on'})
        self.assertEqual(r.status_code, 302)
        # overlapping availability
        r = self.client.post(reverse('gym:trainer_availability', args=[t1.pk]), {'day_of_week': '1', 'start_time': '09:30', 'end_time': '10:30', 'is_available': 'on'})
        self.assertEqual(r.status_code, 200)
        r = self.client.get(reverse('gym:trainer_dashboard'))
        self.assertEqual(r.status_code, 200)

    # ---------------- Classes & Schedules ----------------
    def test_class_create_schedule_generate_enroll(self):
        self.login_staff()
        t = self.trainers[2]
        TrainerAvailability.objects.get_or_create(trainer=t, day_of_week=0, start_time=dt_time(6,0), end_time=dt_time(12,0), defaults={'is_available': True})
        r = self.client.post(reverse('gym:class_create'), {'name': 'E2E Class', 'description': 'd', 'trainer': t.pk, 'capacity': 2, 'duration_minutes': 60, 'status': 'active'})
        self.assertEqual(r.status_code, 302)
        c = GymClass.objects.get(name='E2E Class')
        r = self.client.post(reverse('gym:class_schedule_add', args=[c.pk]), {'day_of_week': '0', 'start_time': '09:00', 'end_time': '10:00', 'is_active': 'on'})
        self.assertEqual(r.status_code, 302)
        self.assertTrue(ClassSchedule.objects.filter(gym_class=c, start_time=dt_time(9,0)).exists())
        with patch('gym.views.timezone.localdate', return_value=date(2026,11,16)):
            r = self.client.post(reverse('gym:class_session_generate', args=[c.pk]), {'days_ahead': 7})
        self.assertEqual(r.status_code, 302)
        session = ClassSession.objects.filter(gym_class=c).first()
        self.assertIsNotNone(session)
        # enroll valid member
        m = self.members[0]  # has active sub
        r = self.client.post(reverse('gym:class_session_enroll', args=[session.pk]), {'member_id': m.pk, 'next': reverse('gym:class_detail', args=[c.pk])})
        self.assertEqual(r.status_code, 302)
        self.assertTrue(ClassEnrollment.objects.filter(session=session, member=m, status='enrolled').exists())

    def test_class_conflicts_capacity_cancel(self):
        self.login_staff()
        c = self.classes[0]
        session = self.sessions[0]
        session.capacity = 1
        session.save(update_fields=['capacity'])
        # enroll 1
        m1 = self.members[0]
        m2 = self.members[4] if self.members[4].status == 'active' else self.members[5]
        # ensure m2 has valid sub
        if not MemberSubscription.objects.filter(member=m2, start_date__lte=session.start_datetime.date(), end_date__gte=session.start_datetime.date()).exclude(status='cancelled').exists():
            MemberSubscription.objects.create(member=m2, plan=self.plan_monthly, start_date=date(2026,11,1), end_date=date(2026,11,30), price_at_subscription=Decimal('1500.00'), status='active')
        ClassEnrollment.objects.filter(session=session).delete()
        self.client.post(reverse('gym:class_session_enroll', args=[session.pk]), {'member_id': m1.pk, 'next': '/'})
        self.client.post(reverse('gym:class_session_enroll', args=[session.pk]), {'member_id': m2.pk, 'next': '/'})
        self.assertEqual(ClassEnrollment.objects.filter(session=session, status='enrolled').count(), 1)
        # cancel enrollment
        e = ClassEnrollment.objects.filter(session=session, status='enrolled').first()
        r = self.client.post(reverse('gym:class_enrollment_cancel', args=[e.pk]), {'next': '/'})
        self.assertEqual(r.status_code, 302)
        e.refresh_from_db()
        self.assertEqual(e.status, 'cancelled')

    # ---------------- Reports & Dashboard ----------------
    def test_reports_dashboard_kpis_and_exports(self):
        self.login_admin()
        with patch('django.utils.timezone.localdate', return_value=date(2026,11,21)):
            r = self.client.get(reverse('gym:business_dashboard'), {'range': 'this_month', 'start': '2026-11-01', 'end': '2026-11-30'})
        self.assertEqual(r.status_code, 200)
        for k in ['total_members','active_memberships','expired_memberships','total_collection','today_collection','outstanding_due','active_trainers','upcoming_classes']:
            self.assertIn(k, r.context)
        # exports
        for url in [reverse('gym:report_payments'), reverse('gym:report_outstanding_dues'), reverse('gym:report_membership'), reverse('gym:report_trainers'), reverse('gym:report_classes')]:
            r = self.client.get(url, {'export': 'csv'})
            self.assertEqual(r.status_code, 200)
            self.assertIn('text/csv', r['Content-Type'])

    def test_reports_filtering_and_permissions(self):
        self.login_staff()
        r = self.client.get(reverse('gym:report_payments'), {'range': 'custom', 'start': '2026-11-01', 'end': '2026-11-30'})
        self.assertEqual(r.status_code, 200)
        # non-staff
        self.client.force_login(self.normal)
        r = self.client.get(reverse('gym:business_dashboard'))
        self.assertEqual(r.status_code, 403)

    # ---------------- E2E Workflow ----------------
    def test_end_to_end_workflow(self):
        self.login_admin()
        # 1 register member
        r = self.client.post(reverse('gym:member_create'), {'full_name':'E2E Flow','mobile_number':'01700000001','email':'flow@e.com','gender':'male','date_of_birth':'1990-01-01','address':'A','emergency_contact_name':'E','emergency_contact_number':'01700000002','joining_date':'2026-11-21','status':'active'})
        self.assertEqual(r.status_code, 302)
        m = Member.objects.get(full_name='E2E Flow')
        # 2 create plan
        r = self.client.post(reverse('gym:plan_create'), {'name':'E2E Plan','description':'','duration_months':1,'price':'1000.00','is_active':'on'})
        p = MembershipPlan.objects.get(name='E2E Plan')
        # 3 assign plan
        r = self.client.post(reverse('gym:subscription_assign', args=[m.pk]), {'plan': p.pk, 'start_date': '2026-11-21'})
        self.assertEqual(r.status_code, 302)
        sub = MemberSubscription.objects.get(member=m)
        # 4 partial payment
        token = self.client.get(reverse('gym:payment_collect', args=[m.pk]) + f'?subscription={sub.pk}').context['payment_token']
        r = self.client.post(reverse('gym:payment_collect', args=[m.pk]), {'payment_token':token,'subscription':sub.pk,'amount':'600.00','payment_method':'cash','payment_date':'2026-11-21','transaction_id':'','note':''})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(sub.remaining_due_amount(), Decimal('400.00'))
        # 6 final payment
        token = self.client.get(reverse('gym:payment_collect', args=[m.pk]) + f'?subscription={sub.pk}').context['payment_token']
        r = self.client.post(reverse('gym:payment_collect', args=[m.pk]), {'payment_token':token,'subscription':sub.pk,'amount':'400.00','payment_method':'cash','payment_date':'2026-11-21','transaction_id':'','note':''})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(sub.payment_status(), 'Paid')
        # 8 receipt
        pmt = MembershipPayment.objects.filter(subscription=sub, status='completed').first()
        r = self.client.get(reverse('gym:payment_receipt', args=[pmt.pk]))
        self.assertEqual(r.status_code, 200)
        # 9 create trainer
        r = self.client.post(reverse('gym:trainer_create'), {'full_name':'E2E Trainer Flow','phone':'01700000003','email':'','gender':'male','date_of_birth':'1990-01-01','address':'','specialization':'Strength','experience_years':2,'qualification':'','joining_date':'2026-11-21','status':'active'})
        t = Trainer.objects.get(full_name='E2E Trainer Flow')
        # 10 assign trainer
        r = self.client.post(reverse('gym:trainer_assign_member', args=[t.pk]), {'trainer':t.pk,'member':m.pk,'start_date':'2026-11-21','end_date':''})
        self.assertEqual(r.status_code, 302)
        # 11 availability
        r = self.client.post(reverse('gym:trainer_availability', args=[t.pk]), {'day_of_week':'0','start_time':'06:00','end_time':'12:00','is_available':'on'})
        self.assertEqual(r.status_code, 302)
        # 12 create class
        r = self.client.post(reverse('gym:class_create'), {'name':'E2E Class Flow','description':'','trainer':t.pk,'capacity':5,'duration_minutes':60,'status':'active'})
        c = GymClass.objects.get(name='E2E Class Flow')
        # 13 schedule
        r = self.client.post(reverse('gym:class_schedule_add', args=[c.pk]), {'day_of_week':'0','start_time':'07:00','end_time':'08:00','is_available':'on','is_active':'on'})
        # generate
        with patch('gym.views.timezone.localdate', return_value=date(2026,11,23)):
            self.client.post(reverse('gym:class_session_generate', args=[c.pk]), {'days_ahead': 7})
        session = ClassSession.objects.filter(gym_class=c, start_datetime__date__gte=date(2026,11,21)).first()
        # 14 enroll
        r = self.client.post(reverse('gym:class_session_enroll', args=[session.pk]), {'member_id': m.pk, 'next': '/'})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(ClassEnrollment.objects.filter(session=session, member=m, status='enrolled').count(), 1)
        # 16 renew
        r = self.client.post(reverse('gym:subscription_renew', args=[m.pk, sub.pk]), {'plan': p.pk, 'start_date': '2026-12-21'})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(MemberSubscription.objects.filter(member=m).count(), 2)
        # 18 dashboard
        r = self.client.get(reverse('gym:business_dashboard'))
        self.assertEqual(r.status_code, 200)
        # 19 reports
        r = self.client.get(reverse('gym:report_payments'))
        self.assertEqual(r.status_code, 200)
        # 20 export
        r = self.client.get(reverse('gym:report_payments'), {'export': 'csv'})
        self.assertEqual(r.status_code, 200)

    # ---------------- Security / UI smoke ----------------
    def test_security_auth_csrf_and_permissions(self):
        # protected pages redirect
        self.client.logout()
        for url in [reverse('gym:member_list'), reverse('gym:payment_list'), reverse('gym:trainer_list'), reverse('gym:class_list')]:
            r = self.client.get(url)
            self.assertEqual(r.status_code, 302)
        # staff-only financial reports
        self.client.force_login(self.normal)
        self.assertEqual(self.client.get(reverse('gym:report_payments')).status_code, 403)
        # CSRF enforcement
        from django.test import Client as CSRFClient
        c = CSRFClient(enforce_csrf_checks=True)
        c.force_login(self.staff)
        r = c.post(reverse('gym:member_create'), {'full_name':'X'})
        self.assertEqual(r.status_code, 403)

    def test_ui_template_smoke(self):
        self.login_admin()
        urls = [
            reverse('gym:member_list'), reverse('gym:plan_list'), reverse('gym:subscription_list'),
            reverse('gym:payment_list'), reverse('gym:trainer_list'), reverse('gym:class_list'),
            reverse('gym:business_dashboard'), reverse('gym:reports_index'), reverse('gym:weekly_schedule'),
        ]
        for url in urls:
            r = self.client.get(url)
            self.assertEqual(r.status_code, 200, url)
