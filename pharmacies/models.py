from django.db import models
from django.utils import timezone


class ActiveShiftQuerySet(models.QuerySet):
    """QuerySet مخصص لفلترة المناوبات النشطة حالياً ومنع تكرار الاستعلامات (N+1 Queries)."""

    def active_now(self):
        now = timezone.now()
        return self.filter(
            is_active=True,
            start_time__lte=now,
            end_time__gte=now
        ).select_related('pharmacy', 'pharmacy__region')


class Region(models.Model):
    name = models.CharField(max_length=100, db_index=True, verbose_name="اسم المنطقة")
    city = models.CharField(max_length=100, db_index=True, verbose_name="المحافظة/المدينة")
    search_keywords = models.TextField(
        blank=True, 
        help_text="كلمات مفتاحية مفصولة بفواصل (مثال: شيخ سعد، أوتستراد، جبل)"
    )
    center_latitude = models.FloatField(verbose_name="خط العرض لمركز المنطقة")
    center_longitude = models.FloatField(verbose_name="خط الطول لمركز المنطقة")

    class Meta:
        app_label = 'pharmacies'
        verbose_name = "منطقة"
        verbose_name_plural = "المناطق"
        ordering = ['city', 'name']

    def __str__(self) -> str:
        return f"{self.city} - {self.name}"


class Pharmacy(models.Model):
    name = models.CharField(max_length=255, db_index=True, verbose_name="اسم الصيدلية")
    phone = models.CharField(max_length=50, blank=True, verbose_name="رقم الهاتف")
    region = models.ForeignKey(
        Region, 
        on_delete=models.PROTECT, 
        related_name='pharmacies', 
        verbose_name="المنطقة"
    )
    address_details = models.TextField(verbose_name="تفاصيل العنوان النصي")
    latitude = models.FloatField(verbose_name="خط العرض")
    longitude = models.FloatField(verbose_name="خط الطول")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = 'pharmacies'
        verbose_name = "صيدلية"
        verbose_name_plural = "الصيدليات"

    def __str__(self) -> str:
        return self.name


class ShiftSchedule(models.Model):
    pharmacy = models.ForeignKey(
        Pharmacy, 
        on_delete=models.CASCADE, 
        related_name='shifts', 
        verbose_name="الصيدلية"
    )
    start_time = models.DateTimeField(db_index=True, verbose_name="بداية المناوبة")
    end_time = models.DateTimeField(db_index=True, verbose_name="نهاية المناوبة")
    is_active = models.BooleanField(default=True, db_index=True, verbose_name="مناوبة نشطة")

    objects = ActiveShiftQuerySet.as_manager()

    class Meta:
        app_label = 'pharmacies'
        verbose_name = "جدول مناوبة"
        verbose_name_plural = "جداول المناوبات"
        ordering = ['start_time']

    def __str__(self) -> str:
        return f"مناوبة {self.pharmacy.name}"