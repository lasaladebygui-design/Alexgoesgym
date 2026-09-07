from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("entrar/", auth_views.LoginView.as_view(template_name="accounts/login.html"), name="login"),
    path("salir/", auth_views.LogoutView.as_view(), name="logout"),
    path("registro/", views.signup, name="signup"),
    path("perfil/", views.profile, name="profile"),
    path("perfil/exportar/", views.export_excel, name="export-excel"),
    path("amigos/", views.friends_list, name="friends"),
    path("amigos/<str:username>/solicitar/", views.friend_request_send, name="friend-request-send"),
    path("amigos/solicitudes/<int:pk>/aceptar/", views.friend_request_accept, name="friend-request-accept"),
    path("amigos/solicitudes/<int:pk>/rechazar/", views.friend_request_decline, name="friend-request-decline"),
    path("amigos/solicitudes/<int:pk>/retirar/", views.friend_request_withdraw, name="friend-request-withdraw"),
]
