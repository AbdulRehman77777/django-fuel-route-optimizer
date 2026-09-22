from django.urls import include, path
from django.views.generic import TemplateView

urlpatterns = [
    path("api/v1/", include("trip_planner.api.urls")),
    path("", TemplateView.as_view(template_name="map.html"), name="map"),
]
