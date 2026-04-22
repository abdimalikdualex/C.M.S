from django.apps import AppConfig


class MainAppConfig(AppConfig):
    name = "main_app"
    default_auto_field = "django.db.models.AutoField"

    def ready(self):
        import main_app.signals  # noqa: F401
