from django.shortcuts import render
from django.db.models import (
    BooleanField,
    Case,
    DateTimeField,
    F,
    IntegerField,
    OuterRef,
    Q,
    Subquery,
    Value,
    When,
)
from django.http import HttpResponseBadRequest
from django.utils import timezone
from .models import ShiftSchedule
from .services import calculate_haversine_distance


def _current_or_upcoming_pharmacy_shifts():
    now = timezone.now()
    available_shifts = ShiftSchedule.objects.filter(
        is_active=True,
        end_time__gte=now,
    )
    preferred_shift = available_shifts.filter(
        pharmacy_id=OuterRef('pharmacy_id')
    ).order_by(
        Case(
            When(start_time__lte=now, then=Value(0)),
            default=Value(1),
            output_field=IntegerField(),
        ),
        Case(
            When(start_time__lte=now, then=F('start_time')),
            output_field=DateTimeField(),
        ).desc(nulls_last=True),
        Case(
            When(start_time__gt=now, then=F('start_time')),
            output_field=DateTimeField(),
        ).asc(nulls_last=True),
        '-pk',
    )
    return available_shifts.filter(
        pk=Subquery(preferred_shift.values('pk')[:1])
    ).select_related('pharmacy', 'pharmacy__region').annotate(
        is_upcoming=Case(
            When(start_time__gt=now, then=Value(True)),
            default=Value(False),
            output_field=BooleanField(),
        )
    )

def index(request):
    shifts = _current_or_upcoming_pharmacy_shifts()
    return render(request, 'pharmacies/index.html', {'shifts': shifts})


def pharmacy_search(request):
    query = request.GET.get('q', '').strip()
    latitude = request.GET.get('lat')
    longitude = request.GET.get('lng')
    
    shifts = _current_or_upcoming_pharmacy_shifts()
    
    if query:
        shifts = shifts.filter(
            Q(pharmacy__name__icontains=query) |
            Q(pharmacy__phone__icontains=query) |
            Q(pharmacy__address_details__icontains=query)
        )
    elif latitude and longitude:
        try:
            user_latitude = float(latitude)
            user_longitude = float(longitude)
        except ValueError:
            return HttpResponseBadRequest("Invalid latitude or longitude.")
        if not -90 <= user_latitude <= 90 or not -180 <= user_longitude <= 180:
            return HttpResponseBadRequest("Latitude or longitude is out of range.")
        shifts = sorted(
            shifts,
            key=lambda shift: calculate_haversine_distance(
                user_latitude,
                user_longitude,
                shift.pharmacy.latitude,
                shift.pharmacy.longitude,
            ),
        )

    return render(
        request,
        'pharmacies/partials/pharmacy_list.html',
        {'shifts': shifts, 'query': query},
    )