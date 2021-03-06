# Generated by Django 2.2.5 on 2019-11-06 22:45

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('proposals', '0013_auto_20191106_0140'),
    ]

    operations = [
        migrations.CreateModel(
            name='Tx',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('amount_cents', models.IntegerField()),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('stripe_payment_intent_id', models.CharField(blank=True, max_length=255, null=True, unique=True)),
                ('stripe_refund_id', models.CharField(blank=True, max_length=255, null=True, unique=True)),
                ('bid', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='tx', to='proposals.Bid')),
                ('creator', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='tx', to=settings.AUTH_USER_MODEL)),
                ('next_tx', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='prev_tx', to='proposals.Tx')),
                ('proposal', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='tx', to='proposals.Proposal')),
            ],
        ),
    ]
