# -*- coding: utf-8 -*-
                                             
from django.db import migrations, models

class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='FuelStation',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('opis_id', models.CharField(max_length=20, unique=True)),
                ('name', models.CharField(max_length=255)),
                ('address', models.CharField(blank=True, max_length=255)),
                ('city', models.CharField(max_length=100)),
                ('state', models.CharField(max_length=2)),
                ('rack_id', models.CharField(blank=True, max_length=20)),
                ('price', models.FloatField()),
                ('lat', models.FloatField(blank=True, null=True)),
                ('lon', models.FloatField(blank=True, null=True)),
                ('geocode_failed', models.BooleanField(default=False)),
            ],
            options={
                'indexes': [models.Index(fields=['state'], name='trip_fuelst_state_2c37dc_idx'), models.Index(fields=['lat', 'lon'], name='trip_fuelst_lat_ec94e8_idx'), models.Index(fields=['geocode_failed'], name='trip_fuelst_geocode_2b08b0_idx')],
            },
        ),
    ]
