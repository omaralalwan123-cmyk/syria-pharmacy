import math
from django.shortcuts import render
from django.db.models import Q
from .models import ShiftSchedule

def calculate_distance(lat1, lon1, lat2, lon2):
    """حساب المسافة بالكيلموتر باستخدام صيغة Haversine"""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlon / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

def pharmacy_search_view(request):
    query = request.GET.get('q', '').strip()
    user_lat = request.GET.get('lat')
    user_lng = request.GET.get('lng')
    
    is_gps_search = False
    location_name = ''

    # 1. جلب المناوبات النشطة حالياً ومنع الـ N+1 Queries
    active_shifts = ShiftSchedule.objects.active_now()

    # 2. الفلترة النصية (حسب اسم الصيدلية، اسم المنطقة، المحافظة، أو الكلمات المفتاحية)
    if query:
        active_shifts = active_shifts.filter(
            Q(pharmacy__name__icontains=query) |
            Q(pharmacy__region__name__icontains=query) |
            Q(pharmacy__region__city__icontains=query) |
            Q(pharmacy__region__search_keywords__icontains=query) |
            Q(pharmacy__address_details__icontains=query)
        )

    results = []

    # 3. معالجة البحث عبر الـ GPS وحساب المسافات
    if user_lat and user_lng:
        try:
            u_lat = float(user_lat)
            u_lng = float(user_lng)
            is_gps_search = True

            for shift in active_shifts:
                p = shift.pharmacy
                if p.latitude and p.longitude:
                    dist = calculate_distance(u_lat, u_lng, p.latitude, p.longitude)
                    results.append({'pharmacy': p, 'distance': dist})

            # ترتيب النتائج من الأقرب إلى الأبعد
            results.sort(key=lambda x: x['distance'])
        except ValueError:
            user_lat, user_lng = None, None

    else:
        # بحث عادي بالاسم أو المنطقة
        for shift in active_shifts:
            results.append({'pharmacy': shift.pharmacy, 'distance': None})

    context = {
        'results': results,
        'query': query,
        'user_lat': user_lat,
        'user_lng': user_lng,
        'is_gps_search': is_gps_search,
        'location_name': location_name,
    }

    # إذا كان الطلب قادماً عبر HTMX نرجع الجزئية فقط، وإلا نرجع الصفحة كاملة
    if request.headers.get('HX-Request'):
        return render(request, 'pharmacies/partials/results_list.html', context)
    
    return render(request, 'pharmacies/search.html', context)