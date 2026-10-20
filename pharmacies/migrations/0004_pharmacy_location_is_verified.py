from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("pharmacies", "0003_alter_telegrambotmessage_received_at"),
    ]

    operations = [
        migrations.AddField(
            model_name="pharmacy",
            name="location_is_verified",
            field=models.BooleanField(
                default=False,
                help_text="فعّل هذا الخيار للمواقع التي تم تحديدها بدقة من الخريطة.",
                verbose_name="موقع الصيدلية مؤكد",
            ),
        ),
    ]
