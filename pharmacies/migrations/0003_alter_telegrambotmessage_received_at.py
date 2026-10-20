from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("pharmacies", "0002_telegrambotmessage"),
    ]

    operations = [
        migrations.AlterField(
            model_name="telegrambotmessage",
            name="received_at",
            field=models.DateTimeField(auto_now_add=True),
        ),
    ]
