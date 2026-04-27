# Generated for the Manager/Director MVP role.
#
# Adds:
#   - CustomUser.user_type choice "4" = Director
#   - Director profile model (one-to-one to CustomUser)

from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("main_app", "0023_enforce_session_on_student_and_enrollment"),
    ]

    operations = [
        migrations.AlterField(
            model_name="customuser",
            name="user_type",
            field=models.CharField(
                choices=[
                    (1, "HOD"),
                    (2, "Staff"),
                    (3, "Student"),
                    (4, "Director"),
                ],
                default=1,
                max_length=1,
            ),
        ),
        migrations.CreateModel(
            name="Director",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "admin",
                    models.OneToOneField(
                        on_delete=models.deletion.CASCADE,
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
        ),
    ]
