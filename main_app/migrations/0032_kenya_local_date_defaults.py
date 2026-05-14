import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("main_app", "0031_course_units_exam_results"),
    ]

    operations = [
        migrations.AlterField(
            model_name="student",
            name="enrollment_date",
            field=models.DateField(default=django.utils.timezone.localdate),
        ),
        migrations.AlterField(
            model_name="enrollment",
            name="start_date",
            field=models.DateField(default=django.utils.timezone.localdate),
        ),
    ]
