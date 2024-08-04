from django.db import models
from django.utils import timezone


class Status(models.Model):
    number = models.CharField(
        max_length=255, default="Unknown"
    )  # Добавляем значение по умолчанию
    patient = models.CharField(
        max_length=255, default="Unknown"
    )  # Добавляем значение по умолчанию
    status = models.CharField(
        max_length=255, default="Unknown"
    )  # Добавляем значение по умолчанию
    RECEPTION_CODE = models.CharField(
        max_length=255, unique=True, default="Unknown"
    )  # Добавляем значение по умолчанию
    call_date = models.DateTimeField(
        default=timezone.now
    )  # Добавляем значение по умолчанию


class Review(models.Model):
    number = models.CharField(max_length=255, default="Unknown")
    patient = models.CharField(max_length=255, default="Unknown")
    reception_date = models.DateField(default=timezone.now)
    reception_time = models.TimeField(default=timezone.now)
    doctor = models.CharField(max_length=255, default="Unknown")
    doctor_rating = models.IntegerField(null=True, blank=True)
    doctor_feedback = models.TextField(null=True, blank=True)
    clinic_rating = models.IntegerField(null=True, blank=True)
    clinic_feedback = models.TextField(null=True, blank=True)
    will_attend = models.BooleanField(default=False)
    audio = models.FileField(upload_to="audios/", null=True, blank=True)
    address = models.TextField(null=True, blank=True)
    RECEPTION_CODE = models.CharField(max_length=255, unique=True, default="Unknown")
    patient_code = models.CharField(max_length=255, default="Unknown")


class AnalysisResult(models.Model):
    reception_code = models.CharField(max_length=255, unique=True)
    doctor_rating = models.IntegerField(null=True, blank=True)
    doctor_feedback = models.TextField(null=True, blank=True)
    clinic_rating = models.IntegerField(null=True, blank=True)
    clinic_feedback = models.TextField(null=True, blank=True)
    will_return = models.TextField(null=True, blank=True)
    analyzed_at = models.DateTimeField(auto_now_add=True)
