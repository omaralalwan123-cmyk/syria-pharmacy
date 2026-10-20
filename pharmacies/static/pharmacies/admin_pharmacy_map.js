(function () {
    function initializePharmacyMap() {
        var container = document.getElementById("pharmacy-location-map");
        var latitudeInput = document.getElementById("id_latitude");
        var longitudeInput = document.getElementById("id_longitude");
        var verifiedInput = document.getElementById("id_location_is_verified");
        var addressInput = document.getElementById("id_address_details");

        if (!container || !latitudeInput || !longitudeInput || !verifiedInput || !addressInput || !window.L) {
            return;
        }

        var damascus = [33.5138, 36.2765];
        var latitude = Number.parseFloat(latitudeInput.value);
        var longitude = Number.parseFloat(longitudeInput.value);
        var hasCoordinates = Number.isFinite(latitude)
            && Number.isFinite(longitude)
            && latitude >= -90
            && latitude <= 90
            && longitude >= -180
            && longitude <= 180
            && (verifiedInput.checked
                || addressInput.value.trim() !== "دمشق - الموقع التفصيلي غير متوفر");
        var initialPosition = hasCoordinates ? [latitude, longitude] : damascus;
        var map = window.L.map(container).setView(initialPosition, hasCoordinates ? 15 : 12);

        window.L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
            maxZoom: 19,
            attribution: "© OpenStreetMap contributors"
        }).addTo(map);

        var marker = null;

        function updateCoordinates(position, confirmLocation) {
            latitudeInput.value = position.lat.toFixed(6);
            longitudeInput.value = position.lng.toFixed(6);
            if (confirmLocation) {
                verifiedInput.checked = true;
            }
        }

        function placeMarker(position, confirmLocation) {
            if (!marker) {
                marker = window.L.marker(position, { draggable: true }).addTo(map);
                marker.on("dragend", function () {
                    updateCoordinates(marker.getLatLng(), true);
                });
            } else {
                marker.setLatLng(position);
            }
            updateCoordinates(window.L.latLng(position), confirmLocation);
        }

        if (hasCoordinates) {
            placeMarker(initialPosition, false);
        }

        map.on("click", function (event) {
            placeMarker(event.latlng, true);
        });

        function updateMarkerFromInputs() {
            var nextLatitude = Number.parseFloat(latitudeInput.value);
            var nextLongitude = Number.parseFloat(longitudeInput.value);
            if (
                !Number.isFinite(nextLatitude)
                || !Number.isFinite(nextLongitude)
                || nextLatitude < -90
                || nextLatitude > 90
                || nextLongitude < -180
                || nextLongitude > 180
            ) {
                return;
            }
            var position = [nextLatitude, nextLongitude];
            placeMarker(position, false);
            map.panTo(position);
        }

        latitudeInput.addEventListener("change", updateMarkerFromInputs);
        longitudeInput.addEventListener("change", updateMarkerFromInputs);
        window.setTimeout(function () {
            map.invalidateSize();
        }, 0);
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", initializePharmacyMap);
    } else {
        initializePharmacyMap();
    }
})();
