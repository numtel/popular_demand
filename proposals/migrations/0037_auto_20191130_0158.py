# Generated by Django 2.2.5 on 2019-11-30 01:58

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('proposals', '0036_auto_20191121_2231'),
    ]

    operations = [
        migrations.AddField(
            model_name='msg',
            name='collab_str',
            field=models.CharField(blank=True, max_length=1000, null=True),
        ),
        migrations.AddField(
            model_name='msg',
            name='has_pending_edit',
            field=models.BooleanField(default=False),
        ),
    ]
