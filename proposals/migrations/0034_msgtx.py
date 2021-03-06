# Generated by Django 2.2.5 on 2019-11-18 21:43

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('proposals', '0033_msg_update_creator'),
    ]

    operations = [
        migrations.CreateModel(
            name='MsgTx',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('amount_cents', models.IntegerField()),
                ('status', models.PositiveSmallIntegerField(choices=[(0, 'PENDING'), (1, 'SUCCEEDED'), (2, 'FAILED'), (3, 'CANCELLED'), (4, 'PAID_OUT')], default=0)),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('stripe_payment_intent_id', models.CharField(blank=True, max_length=255, null=True, unique=True)),
                ('stripe_refund_id', models.CharField(blank=True, max_length=255, null=True, unique=True)),
                ('creator', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='msg_tx', to=settings.AUTH_USER_MODEL)),
                ('msg', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='tx', to='proposals.Msg')),
                ('next_tx', models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='prev_tx', to='proposals.MsgTx')),
            ],
        ),
    ]
