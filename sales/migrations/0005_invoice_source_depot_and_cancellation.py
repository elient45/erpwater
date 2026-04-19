from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def backfill_source_depot(apps, schema_editor):
    Invoice = apps.get_model("sales", "Invoice")
    InvoiceStockLink = apps.get_model("sales", "InvoiceStockLink")

    for link in InvoiceStockLink.objects.select_related("stock_movement").all():
        stock_movement = link.stock_movement
        if stock_movement and stock_movement.depot_from_id:
            Invoice.objects.filter(
                pk=link.invoice_id,
                source_depot_id__isnull=True,
            ).update(source_depot_id=stock_movement.depot_from_id)


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("inventory", "0007_stockbalance_version_number"),
        ("sales", "0004_invoice_version_number"),
    ]

    operations = [

        migrations.AddField(
            model_name="invoice",
            name="source_depot",
            field=models.ForeignKey(
                blank=True,
                db_column="source_depot_id",
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="source_invoices",
                to="inventory.depot",
            ),
        ),
        migrations.RunPython(backfill_source_depot, migrations.RunPython.noop),
    ]
