from django.db import models


class FuelStation(models.Model):
    class GeocodingStatus(models.TextChoices):
        PENDING = "pending", "Pending Census"
        CENSUS_MATCHED = "census_matched", "Census matched"
        CENSUS_FAILED = "census_failed", "Census failed"
        ORS_MATCHED = "ors_matched", "ORS matched"
        IMPORTED_COORDINATES = "imported_coordinates", "Imported coordinates"
        UNRESOLVED = "unresolved", "Unresolved"

    source_station_id = models.CharField(max_length=64, unique=True)
    name = models.CharField(max_length=255)
    address = models.CharField(max_length=255)
    city = models.CharField(max_length=120)
    state = models.CharField(max_length=2, db_index=True)
    rack_id = models.CharField(max_length=64, blank=True)
    retail_price = models.DecimalField(max_digits=8, decimal_places=4, db_index=True)
    latitude = models.FloatField(null=True, blank=True, db_index=True)
    longitude = models.FloatField(null=True, blank=True, db_index=True)
    geocoding_status = models.CharField(max_length=20, choices=GeocodingStatus.choices, default=GeocodingStatus.PENDING, db_index=True)
    geocoding_provider = models.CharField(max_length=20, blank=True)
    geocoding_message = models.CharField(max_length=255, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("source_station_id",)
        indexes = [models.Index(fields=("latitude", "longitude"), name="trip_planne_latitud_1698fb_idx")]

    def __str__(self):
        return f"{self.name} ({self.city}, {self.state})"
