

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("pharmacies", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="TelegramBotMessage",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("bot_username", models.CharField(max_length=255)),
                ("chat_id", models.BigIntegerField()),
                ("telegram_message_id", models.BigIntegerField()),
                ("message_date", models.DateTimeField(blank=True, null=True)),
                ("text", models.TextField(blank=True)),
                ("raw_payload", models.TextField()),
                ("received_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "رسالة بوت تلغرام",
                "verbose_name_plural": "رسائل بوت تلغرام",
                "ordering": ["-message_date", "-telegram_message_id"],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("chat_id", "telegram_message_id"),
                        name="unique_telegram_bot_message",
                    )
                ],
            },
        ),
    ]
