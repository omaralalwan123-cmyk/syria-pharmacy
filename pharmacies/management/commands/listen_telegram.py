import asyncio
import re
import time
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from asgiref.sync import sync_to_async
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from django.utils import timezone
from telethon import TelegramClient
from pharmacies.models import Pharmacy, Region, ShiftSchedule, TelegramBotMessage

DAMASCUS_NEIGHBORHOODS = {
    'الشعلان': (33.5186, 36.2913),
    'المزة': (33.5000, 36.2500),
    'الميدان': (33.4833, 36.3000),
    'القصاع': (33.5222, 36.3167),
    'المالكي': (33.5200, 36.2800),
    'أبو رمانة': (33.5190, 36.2850),
    'الروضة': (33.5167, 36.2833),
    'البرامكة': (33.5083, 36.2917),
    'كفرسوسة': (33.4889, 36.2694),
    'ركن الدين': (33.5389, 36.3028),
    'المهاجرين': (33.5278, 36.2750),
    'باب توما': (33.5114, 36.3153),
    'المشروع': (33.5050, 36.2450),
    'الفيلات': (33.4950, 36.2550),
    'الشهبندر': (33.5250, 36.2950),
    'الفرات': (33.5120, 36.2880),
    'بدر': (33.4900, 36.2800),
    'الحفار': (33.5150, 36.2920),
}


def get_location_for_pharmacy(pharmacy_name: str):
    for neighborhood, coords in DAMASCUS_NEIGHBORHOODS.items():
        if neighborhood in pharmacy_name:
            return f"دمشق - {neighborhood} (موقع تقريبي)", coords[0], coords[1]
    return "دمشق - الموقع التفصيلي غير متوفر", 33.5138, 36.2765


def parse_roster_date(text: str):
    date_match = re.search(r'التاريخ:\s*(\d{1,2}-\d{1,2}-\d{4})', text)
    return (
        datetime.strptime(date_match.group(1), "%d-%m-%Y").date()
        if date_match
        else None
    )


def parse_shift_period(text: str, now=None):
    period_match = re.search(
        r'من\s*(\d{1,2}):(\d{2})\s*([^\s]+).*?(?:حتى|إلى)\s*'
        r'(\d{1,2}):(\d{2})\s*([^\s]+)',
        text,
    )
    shift_date = parse_roster_date(text)
    if not shift_date:
        start = now or timezone.now()
        return start, start + timedelta(hours=12)
    if not period_match:
        raise CommandError("رسالة المناوبة تحتوي على تاريخ دون وقت مناوبة قابل للقراءة.")

    start_hour, start_minute = int(period_match.group(1)), int(period_match.group(2))
    start_period = period_match.group(3)
    end_hour, end_minute = int(period_match.group(4)), int(period_match.group(5))
    end_period = period_match.group(6)

    def to_24_hour(hour, period):
        if not 1 <= hour <= 12:
            raise ValueError(f"Invalid 12-hour time: {hour}")
        if "صباح" in period or "ليلا" in period or "ليلاً" in period:
            return hour % 12
        if "مساء" in period or "ظهرا" in period or "ظهرًا" in period:
            return hour % 12 + 12
        raise ValueError(f"Unsupported Arabic time period: {period}")

    damascus = ZoneInfo("Asia/Damascus")
    start = datetime(
        shift_date.year,
        shift_date.month,
        shift_date.day,
        to_24_hour(start_hour, start_period),
        start_minute,
        tzinfo=damascus,
    )
    end = datetime(
        shift_date.year,
        shift_date.month,
        shift_date.day,
        to_24_hour(end_hour, end_period),
        end_minute,
        tzinfo=damascus,
    )
    if end <= start:
        end += timedelta(days=1)
    return start, end


class Command(BaseCommand):
    help = 'استقبال رسائل بوت التلغرام وتحديث قاعدة البيانات بشكل دوري'

    def handle(self, *args, **options):
        for output in (self.stdout, self.stderr):
            stream = getattr(output, '_out', None)
            reconfigure = getattr(stream, 'reconfigure', None)
            if reconfigure:
                reconfigure(encoding='utf-8', errors='backslashreplace')

        api_id = settings.TELEGRAM_API_ID
        api_hash = settings.TELEGRAM_API_HASH
        bot_username = settings.TELEGRAM_CHANNEL

        if not api_id or not api_hash or not bot_username:
            self.stdout.write(self.style.ERROR("تأكد من ضبط متغيرات TELEGRAM في ملف .env"))
            return

        interval = options["interval"]
        if interval <= 0:
            raise CommandError("--interval يجب أن يكون أكبر من صفر.")

        while True:
            asyncio.run(self.fetch_from_bot(api_id, api_hash, bot_username))
            if options["once"]:
                return
            self.stdout.write(
                self.style.WARNING(f"اكتمل التحديث؛ سيُعاد بعد {interval:g} ثانية.")
            )
            time.sleep(interval)

    def add_arguments(self, parser):
        parser.add_argument(
            "--interval",
            type=float,
            default=900,
            help="الفاصل بين عمليات جلب البيانات بالثواني (الافتراضي: 900).",
        )
        parser.add_argument(
            "--once",
            action="store_true",
            help="جلب البيانات مرة واحدة ثم إنهاء الأمر.",
        )

    async def fetch_from_bot(self, api_id, api_hash, bot_username):
        async with TelegramClient('pharmacy_session', int(api_id), api_hash) as client:
            self.stdout.write(self.style.WARNING(f"جاري التفاعل مع البوت @{bot_username}..."))
            bot = await client.get_entity(bot_username)
            latest_message = await client.get_messages(bot, limit=1)
            last_message_id = latest_message[0].id if latest_message else 0

            await client.send_message(bot, "/start")
            await asyncio.sleep(2)

            await self.select_damascus_roster(client, bot)
            await self.click_button(
                client,
                bot,
                lambda text: "مناوبات يوم الغد" in text,
                "مناوبات يوم الغد",
            )
            await asyncio.sleep(3)

            all_messages = await client.get_messages(
                bot, limit=None, min_id=last_message_id
            )
            await sync_to_async(self.store_bot_messages)(all_messages, bot_username)
            stored_messages = await sync_to_async(self.get_new_bot_messages)(
                bot.id, last_message_id
            )
            tomorrow = datetime.now(ZoneInfo("Asia/Damascus")).date() + timedelta(days=1)
            roster_messages = [
                message
                for message in stored_messages
                if message.text
                and re.search(r'(?m)^\s*\d+\s*[-.*]', message.text)
                and chr(0x1F4CD) in message.text
            ]
            response_messages = [
                message for message in roster_messages
                if parse_roster_date(message.text) == tomorrow
            ]

            if not response_messages:
                raise CommandError(
                    "لم يرسل البوت قائمة الغد بتاريخ "
                    f"{tomorrow:%d-%m-%Y} بعد الضغط على الزر "
                    f"(وصلت {len(roster_messages)} صفحة من التواريخ: "
                    f"{sorted({str(parse_roster_date(message.text)) for message in roster_messages})})."
                )

            for message in sorted(
                response_messages, key=lambda item: item.telegram_message_id
            ):
                await sync_to_async(self.process_message)(message.text)

    async def select_damascus_roster(self, client, bot):
        await self.click_button(
            client,
            bot,
            lambda text: self.button_text_contains(text, "الصيدليات المناوبة"),
            "الصيدليات المناوبة",
        )
        await self.click_button(client, bot, lambda text: text == "دمشق", "دمشق")
        await self.click_button(
            client,
            bot,
            lambda text: self.button_text_contains(text, "عرض الخفارة"),
            "عرض: الخفارة",
        )

    @staticmethod
    def button_text_contains(text, phrase):
        normalized_text = re.sub(r"\s*[:：]\s*", " ", text)
        normalized_text = re.sub(r"\s+", " ", normalized_text).strip()
        return phrase in normalized_text

    @staticmethod
    def get_new_bot_messages(chat_id, last_message_id):
        return list(
            TelegramBotMessage.objects.filter(
                chat_id=chat_id,
                telegram_message_id__gt=last_message_id,
            ).order_by("telegram_message_id")
        )

    @staticmethod
    async def click_button(client, bot, matches_text, button_description):
        messages = await client.get_messages(bot, limit=3)
        for message in messages:
            for row in message.buttons or []:
                for button in row:
                    if button.text and matches_text(button.text):
                        await button.click()
                        await asyncio.sleep(2)
                        return True
        raise CommandError(f"لم يعثر البوت على زر «{button_description}».")

    @staticmethod
    def store_bot_messages(messages, bot_username):
        changed_message_ids = []
        for message in messages:
            if message.out:
                continue

            payload = {
                "bot_username": bot_username,
                "message_date": message.date,
                "text": message.message or "",
                "raw_payload": message.to_json(),
            }
            stored_message, created = TelegramBotMessage.objects.get_or_create(
                chat_id=message.chat_id,
                telegram_message_id=message.id,
                defaults=payload,
            )
            if created:
                changed_message_ids.append(message.id)
            elif any(
                getattr(stored_message, field) != value
                for field, value in payload.items()
            ):
                for field, value in payload.items():
                    setattr(stored_message, field, value)
                stored_message.save(update_fields=list(payload))
                changed_message_ids.append(message.id)
        return changed_message_ids

    def process_message(self, text: str):
        pattern = r'(?m)^\s*\d+\s*[-.*]*\s*([^\n]+?)\s*\r?\n\s*📍\s*(\d+)'
        matches = re.findall(pattern, text)

        if not matches:
            raise CommandError("وصل رد من البوت لكن لم أتمكن من استخراج الصيدليات منه.")

        region, _ = Region.objects.get_or_create(
            name="دمشق",
            defaults={'city': 'دمشق', 'center_latitude': 33.5138, 'center_longitude': 36.2765}
        )

        start_time, end_time = parse_shift_period(text)

        for raw_name, phone_number in matches:
            clean_name = re.sub(r'[\*\d\-\.]', '', raw_name).strip()
            clean_name = re.sub(r'صيدلية', '', clean_name).strip()

            if not clean_name:
                continue

            phone_number = phone_number.strip()
            address, lat, lng = get_location_for_pharmacy(clean_name)

            pharmacy, _ = Pharmacy.objects.get_or_create(
                name=clean_name,
                region=region,
                defaults={
                    'address_details': address,
                    'phone': phone_number,
                    'latitude': lat,
                    'longitude': lng
                }
            )

            pharmacy.name = clean_name
            has_existing_location = (
                pharmacy.latitude,
                pharmacy.longitude,
            ) != (33.5138, 36.2765)
            if not pharmacy.location_is_verified and not has_existing_location:
                pharmacy.address_details = address
                pharmacy.latitude = lat
                pharmacy.longitude = lng
            pharmacy.phone = phone_number
            pharmacy.save()

            shift = ShiftSchedule.objects.filter(
                pharmacy=pharmacy,
                is_active=True,
                start_time__lte=start_time,
                end_time__gte=start_time,
            ).order_by("-start_time").first()
            if shift:
                shift.end_time = max(shift.end_time, end_time)
                shift.save(update_fields=["end_time"])
            else:
                ShiftSchedule.objects.create(
                    pharmacy=pharmacy,
                    start_time=start_time,
                    end_time=end_time,
                    is_active=True,
                )

            self.stdout.write(
                self.style.SUCCESS(f"✓ تم إضافة/تحديث مناوبة: صيدلية {clean_name} ({phone_number}) -> ({lat}, {lng})")
            )
