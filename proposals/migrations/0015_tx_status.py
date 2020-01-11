# Generated by Django 2.2.5 on 2019-11-06 22:54

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('proposals', '0014_tx'),
    ]

    operations = [
        migrations.AddField(
            model_name='tx',
            name='status',
            field=models.PositiveSmallIntegerField(choices=[(0, 'PENDING'), (1, 'SUCCEEDED'), (2, 'FAILED')], default=0),
        ),
    ]
