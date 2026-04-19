from django.contrib import admin
from django.urls import include, path

from reports.views import dashboard

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", dashboard, name="dashboard"),
    path("accounts/", include("accounts.urls")),
    path("inventory/", include("inventory.urls")),
    path("sales/", include("sales.urls")),
    path("expenses/", include("expenses.urls")),
    path("reports/", include("reports.urls")),
]