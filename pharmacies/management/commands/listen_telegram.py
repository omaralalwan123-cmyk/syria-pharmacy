import asyncio
import random
import re
from datetime import timedelta
from asgiref.sync import sync_to_async
from django.core.management.base import BaseCommand
from django.conf import settings
from django.utils import timezone
from telethon import TelegramClient
from pharmacies.models import Pharmacy, Region, ShiftSchedule

DAMASCUS_NEIGHBORHOODS = {
    'المزة': (33.5000, 36.2500),
    'أبو رمانة': (33.5190, 36.2850),
    'المالكي': (33.5200, 36.2800),
    'الشعلان': (33.5186, 36.2913),
    'الروضة': (33.5167, 36.2833),
    'المهاجرين': (33.5278, 36.2750),
    'ركن الدين': (33.5389, 36.3028),
    'القصاع': (33.5222, 36.3167),
    'باب توما': (33.5114, 36.3153),
    'الميدان': (33.4833, 36.3000),
    'كفرسوسة': (33.4889, 36.2694),
    'التجارة': (33.5280, 36.3100),
    'القصور': (33.5300, 36.3050),
    'البرامكة': (33.5083, 36.2917),
    'الصالحية': (33.5220, 36.2890),
    'العباسيين': (33.5333, 36.3167),
    'الزاهرة': (33.4750, 36.3000),
}

def extract_neighborhood_and_coords(text_chunk: str):
    """
    يبحث عن أي حي حقيقي من أحياء دمشق داخل نص سطر الصيدلية أو تفاصيلها،
    ويعيد اسم الحي وإحداثياته المضبوطة.
    """
    for neighborhood, coords in DAMASCUS_NEIGHBORHOODS.items():
        if neighborhood in text_chunk:
            return neighborhood, coords[0], coords[1]
    
    # افتراضي في حال لم يُذكر الحي صراحةً ضمن النص
    base_lat, base_lng = 33.5138, 36.2765
    lat_offset = random.uniform(-0.012, 0.012)
    lng_offset = random.uniform(-0.012, 0.012)
    return "دمشق - وسط المدينة", round(base_lat + lat_offset, 6), round(base_lng + lng_offset, 6)

class Command(BaseCommand):
    help = 'إرسال طلب لبوت التلغرام وجلب المناوبات وتحديث قاعدة البيانات'

    def handle(self, *args, **options):
        api_id = settings.TELEGRAM_API_ID
        api_hash = settings.TELEGRAM_API_HASH
        bot_username = settings.TELEGRAM_CHANNEL

        if not api_id or not api_hash or not bot_username:
            self.stdout.write(self.style.ERROR("تأكد من ضبط متغيرات TELEGRAM في ملف .env"))
            return

        asyncio.run(self.fetch_from_bot(api_id, api_hash, bot_username))

    async def fetch_from_bot(self, api_id, api_hash, bot_username):
        async with TelegramClient('pharmacy_session', int(api_id), api_hash) as client:
            self.stdout.write(self.style.WARNING(f"جاري التفاعل مع البوت @{bot_username}..."))
            
            await client.send_message(bot_username, "/start")
            await asyncio.sleep(2)

            messages = await client.get_messages(bot_username, limit=3)
            for msg in messages:
                if msg.buttons:
                    for row in msg.buttons:
                        for button in row:
                            if "الصيدليات" in button.text or "مناوبة" in button.text:
                                await button.click()
                                await asyncio.sleep(2)
                                break

            messages = await client.get_messages(bot_username, limit=3)
            for msg in messages:
                if msg.buttons:
                    for row in msg.buttons:
                        for button in row:
                            if button.text == "دمشق":
                                await button.click()
                                await asyncio.sleep(2)
                                break

            messages = await client.get_messages(bot_username, limit=3)
            for msg in messages:
                if msg.buttons:
                    for row in msg.buttons:
                        for button in row:
                            if "الخفارة" in button.text or "المسائية" in button.text:
                                await button.click()
                                await asyncio.sleep(3)
                                break

            messages = await client.get_messages(bot_username, limit=5)
            response_text = None
            for msg in messages:
                if msg.text and ("صيدلية" in msg.text or "📍" in msg.text):
                    response_text = msg.text
                    break

            if response_text:
                self.stdout.write(self.style.SUCCESS(f"\n[تم استلام الرد النهائي من البوت]:\n{response_text}\n"))
                await sync_to_async(self.process_message)(response_text)
            else:
                last_msg = messages[0].text if messages else "لا توجد رسائل"
                self.stdout.write(self.style.ERROR(f"لم يتم العثور على القائمة. نص آخر رسالة:\n{last_msg}"))

    def process_message(self, text: str):
        try:
            # نمط مطابقة يلتقط النص الكامل لكل صيدلية مع رقم الهاتف والسطر للبحث عن الحي داخله
            pattern = r'\d+[\*-]*\s*([^\n\*]+)\s*\n📍(\d+)'
            matches = re.findall(pattern, text)

            if not matches:
                pattern = r'([^\n]+)\n📍\s*(\d+)'
                matches = re.findall(pattern, text)

            if not matches:
                self.stdout.write(self.style.NOTICE("لم يتم العثور على صيدليات مطابقة في نص الرد."))
                return

            region, _ = Region.objects.get_or_create(
                name="دمشق",
                defaults={'city': 'دمشق', 'center_latitude': 33.5138, 'center_longitude': 36.2765}
            )

            start_now = timezone.now()
            end_shift = start_now + timedelta(hours=12)

            for raw_name, phone_number in matches:
                # 1. تنظيف اسم الصيدلية من الأرقام والرموز وكلمة "صيدلية"
                clean_name = re.sub(r'[\*\d\-\.]', '', raw_name).strip()
                clean_name = re.sub(r'صيدلية', '', clean_name).strip()

                if not clean_name:
                    continue

                phone_number = phone_number.strip()
                
                # استخراج الحي الحقيقي والإحداثيات بناءً على النص الكامل لرسالة البوت أو اسم الصيدلية
                neighborhood, lat, lng = extract_neighborhood_and_coords(raw_name)
                address_full = f"دمشق - {neighborhood}" if neighborhood != "دمشق - وسط المدينة" else "دمشق"

                # حفظ الصيدلية مع العنوان التفصيلي الحيوي
                pharmacy, _ = Pharmacy.objects.get_or_create(
                    name=clean_name,
                    region=region,
                    defaults={
                        'address_details': address_full,
                        'phone': phone_number,
                        'latitude': lat,
                        'longitude': lng
                    }
                )

                pharmacy.name = clean_name
                pharmacy.address_details = address_full
                pharmacy.latitude = lat
                pharmacy.longitude = lng
                pharmacy.phone = phone_number
                pharmacy.save()

                ShiftSchedule.objects.get_or_create(
                    pharmacy=pharmacy,
                    start_time=start_now,
                    defaults={'end_time': end_shift, 'is_active': True}
                )
                self.stdout.write(
                    self.style.SUCCESS(f"✓ تم تحديث: صيدلية {clean_name} | العنوان: {address_full} ({phone_number})")
                )

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"خطأ أثناء المعالجة: {e}"))