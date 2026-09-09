from django.urls import path

from . import views

app_name = "dashboard"

urlpatterns = [
    path("", views.home, name="home"),
    path("estas-sin-conexion/", views.offline, name="offline"),
    path("sw.js", views.service_worker, name="service-worker"),
]
