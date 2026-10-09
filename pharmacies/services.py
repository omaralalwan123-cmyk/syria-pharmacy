import math
from typing import List, Dict, Any
from django.db.models import Q
from .models import Region, ShiftSchedule


def calculate_haversine_distance(
    lat1: float, lon1: float, lat2: float, lon2: float
) -> float:
    """حساب المسافة الجغرافية بالكيلومتر بين نقطتين كرويتين."""
    earth_radius_km = 6371.0

    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)

    a = (
        math.sin(d_lat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(d_lon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return earth_radius_km * c


class PharmacySearchService:
    """خدمة مخصصة لإدارة استعلامات البحث والمطابقة."""

    @classmethod
    def search_by_text(cls, query_text: str) -> List[Dict[str, Any]]:
        clean_query = query_text.strip()
        if not clean_query:
            return []

        active_shifts = ShiftSchedule.objects.active_now()

        # 1. البحث عن مناطق مطابقة
        matched_regions = Region.objects.filter(
            Q(name__icontains=clean_query) |
            Q(city__icontains=clean_query) |
            Q(search_keywords__icontains=clean_query)
        )

        if matched_regions.exists():
            # فلترة المناوبات التابعة للمناطق المطابقة
            region_shifts = active_shifts.filter(pharmacy__region__in=matched_regions)
            
            # إذا وُجدت صيدليات مناوبة في هذه المنطقة، نعيدها مرتبة حسب المسافة من مركز المنطقة
            if region_shifts.exists():
                target_region = matched_regions.first()
                return cls._rank_pharmacies_by_coordinates(
                    shifts=region_shifts,
                    ref_lat=target_region.center_latitude,
                    ref_lng=target_region.center_longitude
                )

        # 2. في حال عدم وجود مناوبات بالمنطقة، أو عدم مطابقة منطقة، نبحث في أسماء وعناوين الصيدليات
        matched_shifts = active_shifts.filter(
            Q(pharmacy__name__icontains=clean_query) |
            Q(pharmacy__address_details__icontains=clean_query)
        )

        return [
            {"pharmacy": shift.pharmacy, "distance": None}
            for shift in matched_shifts
        ]

    @classmethod
    def search_by_coordinates(
        cls, latitude: float, longitude: float
    ) -> List[Dict[str, Any]]:
        active_shifts = ShiftSchedule.objects.active_now()
        return cls._rank_pharmacies_by_coordinates(
            shifts=active_shifts,
            ref_lat=latitude,
            ref_lng=longitude
        )

    @staticmethod
    def _rank_pharmacies_by_coordinates(
        shifts, ref_lat: float, ref_lng: float
    ) -> List[Dict[str, Any]]:
        results = []
        for shift in shifts:
            pharmacy = shift.pharmacy
            distance = calculate_haversine_distance(
                ref_lat, ref_lng, pharmacy.latitude, pharmacy.longitude
            )
            results.append({
                "pharmacy": pharmacy,
                "distance": round(distance, 2)
            })

        results.sort(key=lambda item: item["distance"])
        return results