from django.urls import path

from . import views

app_name = "inventory"

urlpatterns = [
    path("products/", views.product_list, name="product_list"),
    path("products/create/", views.product_create, name="product_create"),
    path("products/<int:pk>/edit/", views.product_update, name="product_update"),

    path("depots/", views.depot_list, name="depot_list"),
    path("depots/create/", views.depot_create, name="depot_create"),
    path("depots/<int:pk>/edit/", views.depot_update, name="depot_update"),

    path("movements/", views.movement_list, name="movement_list"),
    path("movements/create/", views.movement_create, name="movement_create"),
    path("movements/<int:pk>/", views.movement_detail, name="movement_detail"),

    path("balances/", views.stock_balance_list, name="stock_balance_list"),

    path("productions/", views.production_list, name="production_list"),
    path("productions/create/", views.production_create, name="production_create"),
    path("productions/<int:pk>/", views.production_detail, name="production_detail"),
    path("productions/<int:pk>/start/", views.production_start, name="production_start"),
    path("productions/<int:pk>/close/", views.production_close, name="production_close"),

    path("suppliers/", views.supplier_list, name="supplier_list"),
    path("suppliers/create/", views.supplier_create, name="supplier_create"),

    path("purchases/", views.purchase_list, name="purchase_list"),
    path("purchases/create/", views.purchase_create, name="purchase_create"),
    path("purchases/<int:pk>/", views.purchase_detail, name="purchase_detail"),
    path("purchases/<int:pk>/receive/", views.purchase_receive, name="purchase_receive"),
    path("purchases/<int:pk>/register-expense/", views.purchase_register_expense, name="purchase_register_expense"),

    path("payables/", views.supplier_payable_list, name="supplier_payable_list"),
    path("payables/<int:pk>/", views.supplier_payable_detail, name="supplier_payable_detail"),
    path("payables/<int:payable_pk>/pay/", views.supplier_payment_create, name="supplier_payment_create"),

    path("supplies/", views.supply_item_list, name="supply_item_list"),
    path("supplies/create/", views.supply_item_create, name="supply_item_create"),
    path("supplies/<int:pk>/edit/", views.supply_item_update, name="supply_item_update"),
]