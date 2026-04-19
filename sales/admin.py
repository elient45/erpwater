from django.contrib import admin

from .models import Client, FinancialAccount, Invoice, InvoiceItem, InvoiceStockLink, Payment,Delivery


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ("name", "client_type", "phone", "is_active")
    list_filter = ("client_type", "is_active")
    search_fields = ("name", "phone", "nif_rccm")


class InvoiceItemInline(admin.TabularInline):
    model = InvoiceItem
    extra = 0


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ("number", "customer", "status", "issue_date", "total", "paid_amount")
    list_filter = ("status", "sale_mode")
    search_fields = ("number", "customer__name")
    inlines = [InvoiceItemInline]


@admin.register(FinancialAccount)
class FinancialAccountAdmin(admin.ModelAdmin):
    list_display = ("name", "account_type", "is_active")


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("invoice", "amount", "method", "paid_at", "account", "received_by")


@admin.register(InvoiceStockLink)
class InvoiceStockLinkAdmin(admin.ModelAdmin):
    list_display = ("invoice", "stock_movement")

@admin.register(Delivery)
class DeliveryAdmin(admin.ModelAdmin):
    list_display = ("invoice", "delivered_by", "delivery_date", "status", "recipient_name")
    list_filter = ("status",)
    search_fields = ("invoice__number", "invoice__customer__name", "recipient_name", "recipient_phone")