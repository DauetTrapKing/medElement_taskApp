# Generated by Django 3.2.25 on 2024-08-02 13:23

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('appointments', '0005_auto_20240802_1029'),
    ]

    operations = [
        migrations.DeleteModel(
            name='Comment',
        ),
        migrations.AlterField(
            model_name='analysisresult',
            name='will_return',
            field=models.TextField(blank=True, null=True),
        ),
    ]
