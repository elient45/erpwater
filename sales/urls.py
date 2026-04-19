from django.urls import path

from . import views

app_name = "sales"

urlpatterns = [
    path("clients/", views.client_list, name="client_list"),
    path("clients/create/", views.client_create, name="client_create"),

    path("invoices/", views.invoice_list, name="invoice_list"),
    path("invoices/create/", views.invoice_create, name="invoice_create"),
    path("invoices/<int:pk>/", views.invoice_detail, name="invoice_detail"),
    path("invoices/<int:pk>/validate/", views.invoice_validate, name="invoice_validate"),
    path("invoices/<int:pk>/cancel/", views.invoice_cancel, name="invoice_cancel"),

    path("invoices/<int:invoice_pk>/payments/create/", views.payment_create, name="payment_create"),

    path("invoices/<int:pk>/print/", views.invoice_print, name="invoice_print"),
    path("invoices/<int:pk>/pdf/", views.invoice_pdf_download, name="invoice_pdf_download"),

    path("deliveries/", views.delivery_list, name="delivery_list"),
    path("invoices/<int:invoice_pk>/delivery/create/", views.delivery_create, name="delivery_create"),
    path("deliveries/<int:pk>/", views.delivery_detail, name="delivery_detail"),
    path("deliveries/<int:pk>/edit/", views.delivery_update, name="delivery_update"),
]
