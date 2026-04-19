from django.urls import path
from . import views

app_name = "expenses"

urlpatterns = [
    path("accounts/", views.account_list, name="account_list"),
    path("accounts/create/", views.account_create, name="account_create"),
    path("categories/", views.category_list, name="category_list"),
    path("categories/create/", views.category_create, name="category_create"),
    path("transactions/", views.financial_transaction_list, name="financial_transaction_list"),
    path("", views.expense_list, name="expense_list"),
    path("create/", views.expense_create, name="expense_create"),
    path("transactions/deposit/", views.deposit_create, name="deposit_create"),
path("transactions/withdrawal/", views.withdrawal_create, name="withdrawal_create"),
path("transactions/transfer/", views.transfer_create, name="transfer_create"),
]