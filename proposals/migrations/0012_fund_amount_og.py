# Generated by Django 2.2.5 on 2019-11-05 21:46

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('proposals', '0011_auto_20191105_1716'),
    ]

    operations = [
        migrations.AddField(
            model_name='fund',
            name='amount_og',
            field=models.PositiveIntegerField(default=0),
            preserve_default=False,
        ),
    ]
