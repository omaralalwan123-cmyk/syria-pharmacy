from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("pharmacies", "0005_alter_pharmacy_latitude_alter_pharmacy_longitude"),
    ]

    operations = [
        migrations.AddField(
            model_name="pharmacy",
            name="location_lookup_attempted_at",
            field=models.DateTimeField(
                blank=True, db_index=True, null=True, verbose_name="آخر بحث عن الموقع"
            ),
        ),
    ]
