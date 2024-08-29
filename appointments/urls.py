from django.urls import path
from .views import process_conversation

urlpatterns = [
    path("proccess_conversation/",process_conversation , name='receive_comment'),
]