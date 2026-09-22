from django.db import migrations, models


def migrate_statuses(apps, schema_editor):
    station = apps.get_model("trip_planner", "FuelStation")
    station.objects.filter(geocoding_status="success").update(geocoding_status="census_matched", geocoding_provider="census")
    station.objects.filter(geocoding_status="failed").update(geocoding_status="census_failed", geocoding_provider="census")


def reverse_statuses(apps, schema_editor):
    station = apps.get_model("trip_planner", "FuelStation")
    station.objects.filter(geocoding_status__in=("census_matched", "ors_matched", "imported_coordinates")).update(geocoding_status="success")
    station.objects.filter(geocoding_status__in=("census_failed", "unresolved")).update(geocoding_status="failed")


class Migration(migrations.Migration):
    dependencies = [("trip_planner", "0001_initial")]
    operations = [
        migrations.AddField(model_name="fuelstation", name="geocoding_provider", field=models.CharField(blank=True, max_length=20)),
        migrations.AlterField(model_name="fuelstation", name="geocoding_status", field=models.CharField(choices=[("pending", "Pending Census"), ("census_matched", "Census matched"), ("census_failed", "Census failed"), ("ors_matched", "ORS matched"), ("imported_coordinates", "Imported coordinates"), ("unresolved", "Unresolved")], db_index=True, default="pending", max_length=20)),
        migrations.RunPython(migrate_statuses, reverse_statuses),
    ]
