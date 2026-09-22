from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = []
    operations = [
        migrations.CreateModel(
            name="FuelStation",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("source_station_id", models.CharField(max_length=64, unique=True)),
                ("name", models.CharField(max_length=255)),
                ("address", models.CharField(max_length=255)),
                ("city", models.CharField(max_length=120)),
                ("state", models.CharField(db_index=True, max_length=2)),
                ("rack_id", models.CharField(blank=True, max_length=64)),
                ("retail_price", models.DecimalField(db_index=True, decimal_places=4, max_digits=8)),
                ("latitude", models.FloatField(blank=True, db_index=True, null=True)),
                ("longitude", models.FloatField(blank=True, db_index=True, null=True)),
                ("geocoding_status", models.CharField(db_index=True, default="pending", max_length=20)),
                ("geocoding_message", models.CharField(blank=True, max_length=255)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering": ("source_station_id",)},
        ),
        migrations.AddIndex(model_name="fuelstation", index=models.Index(fields=["latitude", "longitude"], name="trip_planne_latitud_1698fb_idx")),
    ]
