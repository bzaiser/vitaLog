from django.urls import path

from . import views

app_name = "tracker"

urlpatterns = [
    path("", views.dashboard_view, name="dashboard"),
    path("bewegung/", views.set_daily_activity_view, name="set_daily_activity"),
    path("mahlzeiten/", views.meals_list_view, name="meals_list"),
    path("vorlagen/", views.meal_templates_view, name="meal_templates_list"),
    path("wasser/", views.water_list_view, name="water_list"),
    path("gewicht/", views.weights_list_view, name="weights_list"),
    path("auswertungen/", views.analytics_view, name="analytics"),
    path("profil/", views.profile_view, name="profile"),
    path("accounts/login/", views.TrackerLoginView.as_view(), name="login"),
    path("accounts/logout/", views.logout_view, name="logout"),
    path("accounts/register/", views.register_view, name="register"),
]
