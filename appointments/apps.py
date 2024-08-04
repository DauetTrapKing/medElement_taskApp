from django.apps import AppConfig


class AppointmentsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "appointments"

    def ready(self):  ### убрать после тестов
        from .tasks import test_request_task

        test_request_task.apply_async()
