"""
URL configuration for api project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.contrib import admin
from django.urls import path, include
from appointments import views as appointments_view

urlpatterns = [
    path("admin/", admin.site.urls),
    path("appointments/", include("appointments.urls")),
    path("receive_comment/", appointments_view.receive_comment, name='receive_comment'),
    path("end_of_speech/", appointments_view.end_of_speech, name='end_of_speech'),
]
