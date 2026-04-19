from django.urls import path
from . import views

app_name = "reports"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("sales/", views.sales_report, name="sales_report"),
    path("expenses/", views.expenses_report, name="expenses_report"),
    path("stock/", views.stock_report, name="stock_report"),
    path("payments/", views.payments_report, name="payments_report"),
    path("monthly-summary/", views.monthly_summary, name="monthly_summary"),

    path("closures/", views.period_closure_list, name="period_closure_list"),
    path("closures/create/", views.period_closure_create, name="period_closure_create"),
    path("closures/<int:pk>/", views.period_closure_detail, name="period_closure_detail"),
    path("closures/<int:pk>/reopen/", views.period_closure_reopen, name="period_closure_reopen"),
]