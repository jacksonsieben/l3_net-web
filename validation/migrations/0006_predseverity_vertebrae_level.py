# Generated by Django 5.2.1 on 2025-06-11 08:47

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('validation', '0005_alter_run_options_remove_run_exam_id_run_description_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='predseverity',
            name='vertebrae_level',
            field=models.CharField(choices=[('L1/L2', 'L1 L2'), ('L2/L3', 'L2 L3'), ('L3/L4', 'L3 L4'), ('L4/L5', 'L4 L5'), ('L5/S1', 'L5 S1'), ('Unknown', 'Unknown')], default='Unknown', max_length=20),
        ),
    ]
