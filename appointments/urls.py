from django.urls import path
from .views import upload_excel_view

urlpatterns = [
    path("upload_excel/",upload_excel_view , name='upload_excel'),
]