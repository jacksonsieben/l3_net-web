from django.db import models

class Run(models.Model):
    id = models.AutoField(primary_key=True)
    exam_id = models.ForeignKey(
        'validation.Exam',
        on_delete=models.CASCADE,
        related_name='runs'
    )
    run_date = models.DateTimeField(auto_now_add=True)
