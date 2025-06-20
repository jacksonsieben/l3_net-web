# Generated by Django 5.2.1 on 2025-06-10 09:10

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('validation', '0004_alter_validation_unique_together_runassignment'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='run',
            options={'ordering': ['-run_date']},
        ),
        migrations.RemoveField(
            model_name='run',
            name='exam_id',
        ),
        migrations.AddField(
            model_name='run',
            name='description',
            field=models.TextField(blank=True, help_text='Optional description of this run', null=True),
        ),
        migrations.AddField(
            model_name='run',
            name='exams',
            field=models.ManyToManyField(help_text='Exams included in this run', related_name='runs', to='validation.exam'),
        ),
        migrations.AddField(
            model_name='run',
            name='name',
            field=models.CharField(default='Unnamed Run', help_text='Name or description of this run', max_length=200),
        ),
    ]
