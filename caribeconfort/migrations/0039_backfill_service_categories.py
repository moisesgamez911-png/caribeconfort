from django.db import migrations


DEFAULT_CATEGORIES = (
    'Habitación',
    'Alimentación',
    'Minibar',
    'Recreación',
    'Eventos',
    'Lavandería',
    'Transporte',
    'Otros',
)


def backfill_service_categories(apps, schema_editor):
    CategoriaServicio = apps.get_model('caribeconfort', 'CategoriaServicio')
    Servicios = apps.get_model('caribeconfort', 'Servicios')
    db_alias = schema_editor.connection.alias
    categories_by_name = {}

    for name in DEFAULT_CATEGORIES:
        categories_by_name.setdefault(name.casefold(), name)

    for service in Servicios.objects.using(db_alias).all().iterator():
        name = (service.categoria or 'Otros').strip()[:50] or 'Otros'
        categories_by_name.setdefault(name.casefold(), name)

    categories = {}
    for key, name in categories_by_name.items():
        category = CategoriaServicio.objects.using(db_alias).filter(
            nombre__iexact=name,
        ).first()
        if category is None:
            category = CategoriaServicio.objects.using(db_alias).create(nombre=name)
        categories[key] = category

    batch = []
    for service in Servicios.objects.using(db_alias).all().iterator():
        name = (service.categoria or 'Otros').strip()[:50] or 'Otros'
        category = categories[name.casefold()]
        service.categoria = category.nombre
        service.categoria_catalogo_id = category.pk
        batch.append(service)

    if batch:
        Servicios.objects.using(db_alias).bulk_update(
            batch,
            ['categoria', 'categoria_catalogo'],
        )


class Migration(migrations.Migration):

    dependencies = [
        ('caribeconfort', '0038_categoriaservicio_alter_servicios_categoria_and_more'),
    ]

    operations = [
        migrations.RunPython(
            backfill_service_categories,
            migrations.RunPython.noop,
        ),
    ]
