from django.urls import path
from .views import receive_comment, end_of_speech

urlpatterns = [
    path("receive_comment/", receive_comment, name='receive_comment'),
    path("end_of_speech/", end_of_speech, name='end_of_speech'),
]