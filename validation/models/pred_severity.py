from django.db import models

from validation.enums.severity import Severity
from validation.enums.vertebra_level import VertebraLevel

class PredSeverity(models.Model):
    """
    Model to store predicted severity data.
    """
    id = models.AutoField(primary_key=True)
    severity_name = models.CharField(choices=Severity.choices, max_length=20, default=Severity.UNKNOWN)
    predicted_at = models.DateTimeField(auto_now_add=True)
    confidence = models.FloatField(default=0.0)
    vertebrae_level = models.CharField(
        choices=VertebraLevel.choices,
        max_length=20,
        null=False,
        blank=False,
    )
    run_id = models.ForeignKey(
        'validation.Run',
        on_delete=models.CASCADE,
        related_name='predicted_severities'
    )
    exam_id = models.ForeignKey(
        'validation.Exam',
        on_delete=models.CASCADE,
        related_name='predicted_severities',
        null=True,  # Temporary for migration
        blank=True
    )
    model_version = models.ForeignKey(
        'validation.ModelVersion',
        on_delete=models.CASCADE,
        related_name='predicted_severities'
    )
    bounding_box = models.ForeignKey(
        'validation.Polygon',
        on_delete=models.CASCADE,
        related_name='predicted_severities'
    )

    class Meta:
        # Ensure one prediction per severity level per exam per run
        unique_together = ['run_id', 'exam_id', 'vertebrae_level']
