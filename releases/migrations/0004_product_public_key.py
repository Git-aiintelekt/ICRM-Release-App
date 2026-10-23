from django.db import migrations, models

import releases.models

# Every product and client gets its own public link key. Plain SQL (MySQL 5.5): add the column, give each existing
# row a key, then make it required and unique. Each step checks first, so a run that stopped halfway finishes.


def forward(apps, schema_editor):
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("SHOW COLUMNS FROM `release_product`")
        if "public_key" not in {row[0] for row in cursor.fetchall()}:
            cursor.execute("ALTER TABLE `release_product` ADD COLUMN `public_key` varchar(24) NULL")
        cursor.execute("SELECT `id` FROM `release_product` WHERE `public_key` IS NULL OR `public_key` = ''")
        for (product_id,) in cursor.fetchall():
            cursor.execute("UPDATE `release_product` SET `public_key` = %s WHERE `id` = %s",
                           [releases.models.new_public_key(), product_id])
        cursor.execute("SHOW INDEX FROM `release_product`")
        if "release_product_public_key_unique" not in {row[2] for row in cursor.fetchall()}:
            cursor.execute("ALTER TABLE `release_product` MODIFY `public_key` varchar(24) NOT NULL, "
                           "ADD UNIQUE KEY `release_product_public_key_unique` (`public_key`)")


def backward(apps, schema_editor):
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("ALTER TABLE `release_product` DROP INDEX `release_product_public_key_unique`, "
                       "DROP COLUMN `public_key`")


class Migration(migrations.Migration):

    dependencies = [
        ('releases', '0003_product_clients'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[migrations.RunPython(forward, backward)],
            state_operations=[
                migrations.AddField(
                    model_name='product',
                    name='public_key',
                    field=models.CharField(default=releases.models.new_public_key, editable=False, max_length=24, unique=True),
                ),
            ],
        ),
    ]
