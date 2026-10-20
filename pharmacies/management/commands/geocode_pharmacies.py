import json
import re
import unicodedata
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from pharmacies.models import Pharmacy


DAMASCUS_BOUNDS = (33.39, 33.66, 36.08, 36.52)
OVERPASS_URLS = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
)
OVERPASS_QUERY = (
    '[out:json][timeout:30];('
    'node["amenity"="pharmacy"](33.39,36.08,33.66,36.52);'
    'way["amenity"="pharmacy"](33.39,36.08,33.66,36.52);'
    'relation["amenity"="pharmacy"](33.39,36.08,33.66,36.52);'
    'node["healthcare"="pharmacy"](33.39,36.08,33.66,36.52);'
    'way["healthcare"="pharmacy"](33.39,36.08,33.66,36.52);'
    ');out center tags;'
)
USER_AGENT = "SyriaPharmacyDirectory/1.0"


def normalize_pharmacy_name(value):
    value = unicodedata.normalize("NFKC", value)
    value = value.replace("ـ", "")
    value = re.sub(r"[\u064b-\u065f\u0670]", "", value)
    value = value.translate(str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ى": "ي"}))
    value = re.sub(r"^\s*صيدلية\s+", "", value)
    return re.sub(r"[^\w]+", "", value).casefold()


def matching_pharmacy_candidates(pharmacy_name, candidates):
    expected_name = normalize_pharmacy_name(pharmacy_name)
    south, north, west, east = DAMASCUS_BOUNDS
    matches = {}

    for candidate in candidates:
        tags = candidate.get("tags", {})
        if not (
            tags.get("amenity") == "pharmacy"
            or tags.get("healthcare") == "pharmacy"
            or tags.get("shop") == "chemist"
        ):
            continue
        candidate_names = {
            normalize_pharmacy_name(tags[name_field])
            for name_field in ("name", "name:ar")
            if tags.get(name_field)
        }
        if expected_name not in candidate_names:
            continue

        center = candidate.get("center", {})
        try:
            latitude = float(candidate.get("lat", center.get("lat")))
            longitude = float(candidate.get("lon", center.get("lon")))
        except (KeyError, TypeError, ValueError):
            continue

        if not south <= latitude <= north or not west <= longitude <= east:
            continue
        matches[(latitude, longitude)] = {
            "lat": latitude,
            "lon": longitude,
            "display_name": tags.get("name:ar") or tags.get("name") or pharmacy_name,
            "name": tags.get("name:ar") or tags.get("name") or pharmacy_name,
            "address": {
                "road": tags.get("addr:street"),
                "neighbourhood": tags.get("addr:neighbourhood"),
                "suburb": tags.get("addr:suburb"),
                "city_district": tags.get("addr:district"),
                "city": tags.get("addr:city"),
            },
        }

    return list(matches.values())


def suggested_address(candidate):
    address = candidate.get("address", {})
    parts = []
    for key in ("road", "neighbourhood", "suburb", "city_district", "city"):
        value = address.get(key)
        if value and value not in parts:
            parts.append(value)
    location = "، ".join(parts) if parts else candidate["display_name"]
    return f"موقع مقترح من OpenStreetMap، يحتاج إلى تأكيد: {location}"


class Command(BaseCommand):
    help = "اقتراح مواقع الصيدليات من بيانات OpenStreetMap دون اعتماد النتائج تلقائياً."

    def add_arguments(self, parser):
        parser.add_argument(
            "--retry",
            action="store_true",
            help="إعادة البحث عن كل المواقع غير المؤكدة، حتى التي سبق البحث عنها.",
        )

    def handle(self, *args, **options):
        pharmacies = Pharmacy.objects.filter(location_is_verified=False).order_by("pk")
        if not options["retry"]:
            pharmacies = pharmacies.filter(location_lookup_attempted_at__isnull=True)
        pharmacies = list(pharmacies)
        if not pharmacies:
            self.stdout.write("لا توجد صيدليات بحاجة إلى بحث عن الموقع.")
            return

        osm_pharmacies = self.fetch_osm_pharmacies()

        matched = 0
        not_found = 0
        ambiguous = 0

        for pharmacy in pharmacies:
            matches = matching_pharmacy_candidates(pharmacy.name, osm_pharmacies)
            if len(matches) != 1:
                pharmacy.location_lookup_attempted_at = timezone.now()
                pharmacy.save(update_fields=("location_lookup_attempted_at",))
                if matches:
                    ambiguous += 1
                    self.stdout.write(
                        self.style.WARNING(f"نتائج متعددة؛ تُرك الموقع للمراجعة: {pharmacy.name}")
                    )
                else:
                    not_found += 1
                continue

            candidate = matches[0]
            pharmacy.latitude = float(candidate["lat"])
            pharmacy.longitude = float(candidate["lon"])
            pharmacy.address_details = suggested_address(candidate)
            pharmacy.location_lookup_attempted_at = timezone.now()
            pharmacy.save(
                update_fields=(
                    "latitude",
                    "longitude",
                    "address_details",
                    "location_lookup_attempted_at",
                )
            )
            matched += 1
            self.stdout.write(self.style.SUCCESS(f"اقتُرح موقع للصيدلية: {pharmacy.name}"))

        self.stdout.write(
            self.style.SUCCESS(
                f"انتهى البحث باستخدام بيانات OpenStreetMap: {matched} موقعًا مقترحًا، "
                f"{not_found} دون نتيجة مطابقة، {ambiguous} نتيجة ملتبسة. "
                "المواقع المقترحة تحتاج إلى تأكيد من لوحة الإدارة."
            )
        )

    @staticmethod
    def fetch_osm_pharmacies():
        last_error = None
        for url in OVERPASS_URLS:
            request = Request(
                url,
                data=OVERPASS_QUERY.encode("utf-8"),
                headers={
                    "User-Agent": USER_AGENT,
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Accept": "application/json",
                },
            )
            try:
                with urlopen(request, timeout=60) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                if not isinstance(payload, dict):
                    raise ValueError("The Overpass response is not a JSON object.")
                elements = payload["elements"]
                if not isinstance(elements, list):
                    raise ValueError("The Overpass response does not contain an element list.")
                return elements
            except (
                HTTPError,
                URLError,
                TimeoutError,
                UnicodeDecodeError,
                json.JSONDecodeError,
                KeyError,
                TypeError,
                ValueError,
            ) as error:
                last_error = error

        raise CommandError(
            f"تعذر تنزيل مواقع الصيدليات من OpenStreetMap عبر جميع الخوادم: {last_error}"
        ) from last_error
