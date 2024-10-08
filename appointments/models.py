from django.db import models
from django.utils import timezone


class Status(models.Model):
    number = models.CharField(
        max_length=255, default="Unknown"
    )  
    patient = models.CharField(
        max_length=255, default="Unknown"
    )  
    status = models.CharField(
        max_length=255, default="Unknown"
    )  
    RECEPTION_CODE = models.CharField(
        max_length=255, unique=True, default="Unknown",
        primary_key = True 
    )  
    call_date = models.DateTimeField(
        default=timezone.now
    )  
    order_key = models.CharField(
        max_length=255, default="Unknown"
    )
    audio_link = models.URLField(
        max_length=500, null=True, blank=True
    ) 

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
    will_attend = models.CharField(max_length=10, null=True, blank=True) 
    audio = models.FileField(upload_to="audios/", null=True, blank=True)
    address = models.TextField(null=True, blank=True)
    RECEPTION_CODE = models.CharField(max_length=255, unique=True, default="Unknown", primary_key = True)
    patient_code = models.CharField(max_length=255, default="Unknown")
