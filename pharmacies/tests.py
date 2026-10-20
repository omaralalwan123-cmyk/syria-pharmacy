import json
from datetime import timedelta
from io import BytesIO, StringIO
from types import SimpleNamespace
from unittest.mock import patch
from zoneinfo import ZoneInfo

from asgiref.sync import async_to_sync
from django.core.exceptions import ValidationError
from django.core.management.base import CommandError
from django.test import TestCase
from django.utils import timezone

from .management.commands.listen_telegram import (
    Command,
    get_location_for_pharmacy,
    parse_roster_date,
    parse_shift_period,
)
from .management.commands.geocode_pharmacies import (
    Command as GeocodeCommand,
    matching_pharmacy_candidates,
)
from .models import Pharmacy, Region, ShiftSchedule, TelegramBotMessage


class PharmacyPageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.region = Region.objects.create(
            name="وسط دمشق",
            city="دمشق",
            center_latitude=33.5138,
            center_longitude=36.2765,
        )

        cls.current_pharmacy = Pharmacy.objects.create(
            name="صيدلية المناوبة",
            phone="+963111234567",
            region=cls.region,
            address_details="وسط دمشق",
            latitude=33.5138,
            longitude=36.2765,
        )
        cls.second_current_pharmacy = Pharmacy.objects.create(
            name="صيدلية مناوبة ثانية",
            phone="+963111234568",
            region=cls.region,
            address_details="شارع الثورة",
            latitude=33.515,
            longitude=36.28,
        )
        cls.expired_pharmacy = Pharmacy.objects.create(
            name="صيدلية انتهت مناوبتها",
            region=cls.region,
            address_details="وسط دمشق",
            latitude=33.52,
            longitude=36.28,
        )
        cls.upcoming_pharmacy = Pharmacy.objects.create(
            name="صيدلية مناوبتها قادمة",
            region=cls.region,
            address_details="وسط دمشق",
            latitude=33.50,
            longitude=36.27,
        )
        cls.inactive_pharmacy = Pharmacy.objects.create(
            name="صيدلية مناوبتها معطلة",
            region=cls.region,
            address_details="وسط دمشق",
            latitude=33.51,
            longitude=36.29,
        )

        now = timezone.now()
        ShiftSchedule.objects.create(
            pharmacy=cls.current_pharmacy,
            start_time=now - timedelta(hours=1),
            end_time=now + timedelta(hours=1),
        )
        ShiftSchedule.objects.create(
            pharmacy=cls.second_current_pharmacy,
            start_time=now - timedelta(hours=1),
            end_time=now + timedelta(hours=1),
        )
        ShiftSchedule.objects.create(
            pharmacy=cls.expired_pharmacy,
            start_time=now - timedelta(hours=2),
            end_time=now - timedelta(hours=1),
        )
        ShiftSchedule.objects.create(
            pharmacy=cls.upcoming_pharmacy,
            start_time=now + timedelta(hours=1),
            end_time=now + timedelta(hours=2),
        )
        ShiftSchedule.objects.create(
            pharmacy=cls.upcoming_pharmacy,
            start_time=now + timedelta(hours=3),
            end_time=now + timedelta(hours=4),
        )
        ShiftSchedule.objects.create(
            pharmacy=cls.inactive_pharmacy,
            start_time=now - timedelta(hours=1),
            end_time=now + timedelta(hours=1),
            is_active=False,
        )

    def test_index_shows_current_and_next_upcoming_shift_per_pharmacy(self):
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "flex-shrink: 0;")
        self.assertContains(response, "صيدلية المناوبة")
        self.assertContains(response, "صيدلية مناوبة ثانية")
        self.assertContains(response, "صيدلية مناوبتها قادمة")
        self.assertContains(response, "مناوبة جارية")
        self.assertContains(response, "مناوبة قادمة")
        self.assertNotContains(response, "صيدلية انتهت مناوبتها")
        self.assertNotContains(response, "صيدلية مناوبتها معطلة")
        self.assertEqual(response.content.count(b'class="card pharmacy-card'), 3)
        self.assertContains(response, 'href="tel:+963111234567"')
        self.assertContains(response, "+963111234567")
        self.assertContains(response, "وسط دمشق")
        self.assertNotContains(response, "دمشق - وسط دمشق")
        self.assertContains(response, "من ")
        self.assertContains(response, "إلى ")
        self.assertContains(response, 'data-pharmacy-latitude="33.5138"')

    def test_duplicate_current_shifts_render_only_one_card_per_pharmacy(self):
        now = timezone.now()
        ShiftSchedule.objects.create(
            pharmacy=self.current_pharmacy,
            start_time=now - timedelta(minutes=30),
            end_time=now + timedelta(hours=2),
        )

        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content.count(b'class="card pharmacy-card'), 3)

    def test_search_shows_current_and_upcoming_shifts(self):
        response = self.client.get("/search/", {"q": "صيدلية"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "صيدلية المناوبة")
        self.assertContains(response, "صيدلية مناوبة ثانية")
        self.assertContains(response, "صيدلية مناوبتها قادمة")
        self.assertNotContains(response, "صيدلية انتهت مناوبتها")
        self.assertNotContains(response, "صيدلية مناوبتها معطلة")
        self.assertContains(response, 'href="tel:+963111234567"')
        self.assertContains(response, "وسط دمشق")
        self.assertContains(response, "شارع الثورة")

    def test_missing_pharmacy_address_is_not_displayed(self):
        pharmacy = Pharmacy.objects.create(
            name="صيدلية بلا عنوان",
            region=self.region,
            address_details="دمشق - الموقع التفصيلي غير متوفر",
            latitude=33.5138,
            longitude=36.2765,
        )
        now = timezone.now()
        ShiftSchedule.objects.create(
            pharmacy=pharmacy,
            start_time=now - timedelta(minutes=30),
            end_time=now + timedelta(minutes=30),
        )

        response = self.client.get("/")

        self.assertContains(response, "صيدلية بلا عنوان")
        self.assertNotContains(response, "الموقع التفصيلي غير متوفر")

    def test_verified_location_is_added_to_map_even_without_text_address(self):
        pharmacy = Pharmacy.objects.create(
            name="صيدلية موقعها مؤكد",
            region=self.region,
            address_details="دمشق - الموقع التفصيلي غير متوفر",
            latitude=33.512345,
            longitude=36.278901,
            location_is_verified=True,
        )
        now = timezone.now()
        ShiftSchedule.objects.create(
            pharmacy=pharmacy,
            start_time=now - timedelta(minutes=30),
            end_time=now + timedelta(minutes=30),
        )

        response = self.client.get("/")

        self.assertContains(response, "صيدلية موقعها مؤكد")
        self.assertContains(response, 'data-pharmacy-latitude="33.512345"')
        self.assertContains(response, 'data-pharmacy-longitude="36.278901"')

    def test_pharmacy_coordinates_are_validated(self):
        pharmacy = Pharmacy(
            name="صيدلية بإحداثيات غير صالحة",
            region=self.region,
            address_details="وسط دمشق",
            latitude=91,
            longitude=36.2765,
        )

        with self.assertRaises(ValidationError):
            pharmacy.full_clean()

    def test_imported_location_is_never_randomly_guessed(self):
        address, latitude, longitude = get_location_for_pharmacy("صيدلية المزة")

        self.assertEqual(address, "دمشق - المزة (موقع تقريبي)")
        self.assertEqual((latitude, longitude), (33.5, 36.25))

        unknown_address, latitude, longitude = get_location_for_pharmacy("صيدلية غير معروفة")

        self.assertEqual(unknown_address, "دمشق - الموقع التفصيلي غير متوفر")
        self.assertEqual((latitude, longitude), (33.5138, 36.2765))


class TelegramBotMessageTests(TestCase):
    def test_geocoder_accepts_only_exact_pharmacy_matches_inside_damascus(self):
        candidates = [
            {
                "tags": {"amenity": "pharmacy", "name": "صيدلية الحفار"},
                "lat": "33.5205478",
                "lon": "36.2832006",
            },
            {
                "tags": {"amenity": "pharmacy", "name": "صيدلية الحفار فرع آخر"},
                "lat": "33.5205478",
                "lon": "36.2832006",
            },
            {
                "tags": {"amenity": "pharmacy", "name": "صيدلية الحفار"},
                "lat": "34.0",
                "lon": "36.2832006",
            },
            {
                "tags": {"shop": "chemist", "name": "صيدلية الحفار"},
                "lat": "33.5205478",
                "lon": "36.2832006",
            },
        ]

        matches = matching_pharmacy_candidates("الحفار", candidates)

        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["name"], "صيدلية الحفار")

    def test_geocoder_saves_exact_match_as_unverified_map_proposal(self):
        region = Region.objects.create(
            name="دمشق",
            city="دمشق",
            center_latitude=33.5138,
            center_longitude=36.2765,
        )
        pharmacy = Pharmacy.objects.create(
            name="الحفار",
            region=region,
            address_details="دمشق - الموقع التفصيلي غير متوفر",
            latitude=33.5138,
            longitude=36.2765,
        )
        candidate = {
            "tags": {
                "amenity": "pharmacy",
                "name": "صيدلية الحفار",
                "addr:street": "شارع الجلاء",
                "addr:city": "دمشق",
            },
            "lat": "33.5205478",
            "lon": "36.2832006",
        }
        output = StringIO()
        command = GeocodeCommand(stdout=output)

        with patch(
            "pharmacies.management.commands.geocode_pharmacies.urlopen",
            return_value=BytesIO(
                json.dumps({"elements": [candidate]}).encode("utf-8")
            ),
        ):
            command.handle(retry=False)

        pharmacy.refresh_from_db()
        self.assertEqual((pharmacy.latitude, pharmacy.longitude), (33.5205478, 36.2832006))
        self.assertIn("شارع الجلاء", pharmacy.address_details)
        self.assertIn("OpenStreetMap", pharmacy.address_details)
        self.assertFalse(pharmacy.location_is_verified)
        self.assertIsNotNone(pharmacy.location_lookup_attempted_at)

    def test_geocoder_skips_ambiguous_exact_matches(self):
        region = Region.objects.create(
            name="دمشق",
            city="دمشق",
            center_latitude=33.5138,
            center_longitude=36.2765,
        )
        pharmacy = Pharmacy.objects.create(
            name="الحفار",
            region=region,
            address_details="دمشق - الموقع التفصيلي غير متوفر",
            latitude=33.5138,
            longitude=36.2765,
        )
        candidates = [
            {
                "tags": {"amenity": "pharmacy", "name": "صيدلية الحفار"},
                "lat": "33.5205478",
                "lon": "36.2832006",
            },
            {
                "tags": {"amenity": "pharmacy", "name": "صيدلية الحفار"},
                "lat": "33.5215478",
                "lon": "36.2842006",
            },
        ]
        output = StringIO()

        with patch(
            "pharmacies.management.commands.geocode_pharmacies.urlopen",
            return_value=BytesIO(
                json.dumps({"elements": candidates}).encode("utf-8")
            ),
        ):
            GeocodeCommand(stdout=output).handle(retry=False)

        pharmacy.refresh_from_db()
        self.assertEqual((pharmacy.latitude, pharmacy.longitude), (33.5138, 36.2765))
        self.assertIn("نتائج متعددة", output.getvalue())
        self.assertIsNotNone(pharmacy.location_lookup_attempted_at)

    def test_geocoder_does_not_repeat_lookups_without_retry_option(self):
        region = Region.objects.create(
            name="دمشق",
            city="دمشق",
            center_latitude=33.5138,
            center_longitude=36.2765,
        )
        Pharmacy.objects.create(
            name="صيدلية غير موجودة على الخريطة",
            region=region,
            address_details="دمشق - الموقع التفصيلي غير متوفر",
            latitude=33.5138,
            longitude=36.2765,
            location_lookup_attempted_at=timezone.now(),
        )

        with patch(
            "pharmacies.management.commands.geocode_pharmacies.urlopen"
        ) as urlopen:
            GeocodeCommand(stdout=StringIO()).handle(retry=False)

        urlopen.assert_not_called()
    def test_import_does_not_overwrite_a_verified_pharmacy_location(self):
        region, _ = Region.objects.get_or_create(
            name="دمشق",
            defaults={
                "city": "دمشق",
                "center_latitude": 33.5138,
                "center_longitude": 36.2765,
            },
        )
        pharmacy = Pharmacy.objects.create(
            name="المزة",
            region=region,
            address_details="المزة، شارع رئيسي",
            latitude=33.501234,
            longitude=36.251234,
            location_is_verified=True,
        )
        command = Command(stdout=StringIO())

        command.process_message("1 - صيدلية المزة\n📍 1234567")

        pharmacy.refresh_from_db()
        self.assertEqual(pharmacy.address_details, "المزة، شارع رئيسي")
        self.assertEqual((pharmacy.latitude, pharmacy.longitude), (33.501234, 36.251234))
        self.assertTrue(pharmacy.location_is_verified)
        self.assertEqual(pharmacy.phone, "1234567")

    def test_import_preserves_existing_noncenter_coordinates_for_review(self):
        region, _ = Region.objects.get_or_create(
            name="دمشق",
            defaults={
                "city": "دمشق",
                "center_latitude": 33.5138,
                "center_longitude": 36.2765,
            },
        )
        pharmacy = Pharmacy.objects.create(
            name="المزة",
            region=region,
            address_details="دمشق - المزة (موقع تقريبي)",
            latitude=33.501234,
            longitude=36.251234,
        )
        command = Command(stdout=StringIO())

        command.process_message("1 - صيدلية المزة\n📍 1234567")

        pharmacy.refresh_from_db()
        self.assertEqual(
            pharmacy.address_details,
            "دمشق - المزة (موقع تقريبي)",
        )
        self.assertEqual((pharmacy.latitude, pharmacy.longitude), (33.501234, 36.251234))
        self.assertFalse(pharmacy.location_is_verified)

    def test_admin_pharmacy_form_includes_location_picker(self):
        from django.contrib.auth import get_user_model

        user = get_user_model().objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password="test-password",
        )
        self.client.force_login(user)

        response = self.client.get("/admin/pharmacies/pharmacy/add/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="pharmacy-location-map"')
        self.assertContains(response, "pharmacies/admin_pharmacy_map.")

    def test_damascus_roster_selection_clicks_required_buttons_in_order(self):
        command = Command(stdout=StringIO())
        clicks = []
        state = {"step": 0}

        class FakeButton:
            def __init__(self, text, state):
                self.text = text
                self.state = state

            async def click(self):
                clicks.append(self.text)
                self.state["step"] += 1

        class FakeClient:
            button_options = [
                ["مناوبات يوم الغد", "الصيدليات المناوبة"],
                ["حلب", "دمشق"],
                ["عرض: الخفارة", "عرض: مناوبات الغد"],
            ]

            async def get_messages(self, bot, limit):
                buttons = [
                    FakeButton(text, state)
                    for text in self.button_options[state["step"]]
                ]
                return [SimpleNamespace(buttons=[buttons])]

        client = FakeClient()

        with patch(
            "pharmacies.management.commands.listen_telegram.asyncio.sleep"
        ):
            async_to_sync(command.select_damascus_roster)(client, "bot")

        self.assertEqual(
            clicks,
            ["الصيدليات المناوبة", "دمشق", "عرض: الخفارة"],
        )

    def test_button_text_matching_accepts_spacing_around_colon(self):
        self.assertTrue(Command.button_text_contains("عرض :الخفارة", "عرض الخفارة"))
        self.assertTrue(Command.button_text_contains("عرض: الخفارة", "عرض الخفارة"))
        self.assertFalse(Command.button_text_contains("عرض: مناوبات الغد", "عرض الخفارة"))

    def test_bot_messages_are_saved_and_updated_without_duplicates(self):
        message = SimpleNamespace(
            out=False,
            chat_id=123456,
            id=42,
            date=timezone.now(),
            message="رسالة البوت",
            to_json=lambda: '{"message":"رسالة البوت","reply_markup":{}}',
        )

        self.assertEqual(
            Command.store_bot_messages([message], "pharmacy_bot"), [42]
        )
        self.assertEqual(
            Command.store_bot_messages([message], "pharmacy_bot"), []
        )

        self.assertEqual(TelegramBotMessage.objects.count(), 1)
        saved_message = TelegramBotMessage.objects.get()
        self.assertEqual(saved_message.text, "رسالة البوت")
        self.assertEqual(
            saved_message.raw_payload,
            '{"message":"رسالة البوت","reply_markup":{}}',
        )

        message.message = "رسالة بوت معدلة"
        message.to_json = lambda: '{"message":"رسالة بوت معدلة"}'
        self.assertEqual(
            Command.store_bot_messages([message], "pharmacy_bot"), [42]
        )

        saved_message.refresh_from_db()
        self.assertEqual(saved_message.text, "رسالة بوت معدلة")
        self.assertEqual(
            saved_message.raw_payload,
            '{"message":"رسالة بوت معدلة"}',
        )

    def test_importing_same_bot_roster_does_not_duplicate_active_shifts(self):
        command = Command(stdout=StringIO())
        roster = "1- صيدلية المزة\n📍1234567"

        command.process_message(roster)
        command.process_message(roster)

        pharmacy = Pharmacy.objects.get(name="المزة")
        self.assertEqual(pharmacy.shifts.count(), 1)
        self.assertTrue(pharmacy.shifts.get().is_active)

    def test_tomorrow_roster_uses_date_and_times_from_bot(self):
        command = Command(stdout=StringIO())
        roster = (
            "صيدليات محافظة دمشق (المسائية)\n"
            "التاريخ: 20-10-2026\n"
            "توقيت المناوبة: من 10:00 مساء حتى 12:00 ليلا\n"
            "1 - صيدلية المزة\n"
            "📍 1234567"
        )

        command.process_message(roster)

        shift = Pharmacy.objects.get(name="المزة").shifts.get()
        damascus = ZoneInfo("Asia/Damascus")
        self.assertEqual(
            shift.start_time.astimezone(damascus).isoformat(),
            "2026-10-20T22:00:00+03:00",
        )
        self.assertEqual(
            shift.end_time.astimezone(damascus).isoformat(),
            "2026-10-21T00:00:00+03:00",
        )

    def test_shift_period_parser_handles_midnight_crossing(self):
        roster_header = (
            "التاريخ: 20-10-2026\n"
            "توقيت المناوبة: من 12:00 ليلا حتى 09:00 صباحا"
        )
        start, end = parse_shift_period(roster_header)

        damascus = ZoneInfo("Asia/Damascus")
        self.assertEqual(parse_roster_date(roster_header).isoformat(), "2026-10-20")
        self.assertEqual(
            start.astimezone(damascus).isoformat(),
            "2026-10-20T00:00:00+03:00",
        )
        self.assertEqual(
            end.astimezone(damascus).isoformat(),
            "2026-10-20T09:00:00+03:00",
        )

    def test_dated_roster_with_unreadable_times_is_rejected(self):
        with self.assertRaises(CommandError):
            parse_shift_period("التاريخ: 20-10-2026")
