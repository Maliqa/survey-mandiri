from django.db import migrations

DEFAULT_RATES = [
    # category, unit_label, unit_price (IDR), min_units, max_units
    ("leasing", "kunjungan", 150_000, 1, 500),
    ("caleg", "responden", 50_000, 50, 20_000),
    ("product", "responden", 40_000, 20, 10_000),
]


def seed(apps, schema_editor):
    PricingRate = apps.get_model("surveys", "PricingRate")
    for category, label, price, min_u, max_u in DEFAULT_RATES:
        PricingRate.objects.get_or_create(
            category=category,
            defaults={"unit_label": label, "unit_price": price, "min_units": min_u, "max_units": max_u},
        )


class Migration(migrations.Migration):
    dependencies = [("surveys", "0001_initial")]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
