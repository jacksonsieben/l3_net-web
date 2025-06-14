from django.db import models

from validation.enums.vertebra_name import VertebraName

class PredVertebra(models.Model):
    """
    Model to store predicted vertebra data.
    """
    id = models.AutoField(primary_key=True)
    name = models.CharField(
        max_length=20,
        choices=VertebraName.choices,
        default=VertebraName.UNKNOWN
    )
    predicted_at = models.DateTimeField(auto_now_add=True)
    confidence = models.FloatField(default=0.0)
    run_id = models.ForeignKey(
        'validation.Run',
        on_delete=models.CASCADE,
        related_name='predicted_vertebrae'
    )
    exam_id = models.ForeignKey(
        'validation.Exam',
        on_delete=models.CASCADE,
        related_name='predicted_vertebrae',
        null=True,  # Temporary for migration
        blank=True
    )
    model_version = models.ForeignKey(
        'validation.ModelVersion',
        on_delete=models.CASCADE,
        related_name='predicted_vertebrae'
    )
    polygon = models.ForeignKey(
        'validation.Polygon',
        on_delete=models.CASCADE,
        related_name='predicted_vertebrae'
    )

    class Meta:
        # Ensure one prediction per vertebra per exam per run
        unique_together = ['run_id', 'exam_id', 'name']