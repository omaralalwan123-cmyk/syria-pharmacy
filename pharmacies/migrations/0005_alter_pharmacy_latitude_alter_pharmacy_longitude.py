import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("pharmacies", "0004_pharmacy_location_is_verified"),
    ]

    operations = [
        migrations.AlterField(
            model_name="pharmacy",
            name="latitude",
            field=models.FloatField(
                validators=[
                    django.core.validators.MinValueValidator(-90),
                    django.core.validators.MaxValueValidator(90),
                ],
                verbose_name="خط العرض",
            ),
        ),
        migrations.AlterField(
            model_name="pharmacy",
            name="longitude",
            field=models.FloatField(
                validators=[
                    django.core.validators.MinValueValidator(-180),
                    django.core.validators.MaxValueValidator(180),
                ],
                verbose_name="خط الطول",
            ),
        ),
    ]
