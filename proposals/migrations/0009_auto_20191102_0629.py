# Generated by Django 2.2.5 on 2019-11-02 06:29

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('proposals', '0008_stripeconfig_source_id'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='fund',
            name='stripe_charge_id',
        ),
        migrations.AddField(
            model_name='fund',
            name='status',
            field=models.PositiveSmallIntegerField(choices=[(0, 'PENDING'), (1, 'SUCCEEDED'), (2, 'FAILED')], default=0),
        ),
        migrations.AddField(
            model_name='fund',
            name='stripe_payment_intent_id',
            field=models.CharField(blank=True, max_length=255, null=True, unique=True),
        ),
    ]
