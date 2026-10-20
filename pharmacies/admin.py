from django.contrib import admin

from .models import Pharmacy, TelegramBotMessage


@admin.register(Pharmacy)
class PharmacyAdmin(admin.ModelAdmin):
    change_form_template = "admin/pharmacies/pharmacy/change_form.html"
    list_display = ("name", "region", "phone", "location_status")
    list_filter = ("location_is_verified", "region__city", "region")
    search_fields = ("name", "phone", "address_details", "region__name")
    fieldsets = (
        (None, {"fields": ("name", "region", "phone", "address_details")}),
        (
            "موقع الصيدلية",
            {
                "fields": (
                    ("latitude", "longitude"),
                    "location_is_verified",
                    "location_lookup_attempted_at",
                ),
                "description": "انقر على الخريطة لتحديد الموقع، ثم احفظ الصيدلية.",
            },
        ),
    )
    readonly_fields = ("location_lookup_attempted_at",)

    class Media:
        css = {"all": ("https://unpkg.com/leaflet@1.9.4/dist/leaflet.css",)}
        js = (
            "https://unpkg.com/leaflet@1.9.4/dist/leaflet.js",
            "pharmacies/admin_pharmacy_map.js",
        )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("region")

    @admin.display(description="حالة الموقع", ordering="location_is_verified")
    def location_status(self, obj):
        return "مؤكد" if obj.location_is_verified else "بحاجة إلى تحديد"


@admin.register(TelegramBotMessage)
class TelegramBotMessageAdmin(admin.ModelAdmin):
    list_display = ("bot_username", "telegram_message_id", "message_date")
    list_filter = ("bot_username",)
    search_fields = ("text",)
    readonly_fields = (
        "bot_username",
        "chat_id",
        "telegram_message_id",
        "message_date",
        "text",
        "raw_payload",
        "received_at",
    )
