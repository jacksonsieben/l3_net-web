from django.db import models

from validation.enums.severity import Severity

class PredSeverity(models.Model):
    """
    Model to store predicted severity data.
    """
    id = models.AutoField(primary_key=True)
    severity_name = models.CharField(choices=Severity.choices, max_length=20, default=Severity.UNKNOWN)
    predicted_at = models.DateTimeField(auto_now_add=True)
    confidence = models.FloatField(default=0.0)
    run_id = models.ForeignKey(
        'validation.Run',
        on_delete=models.CASCADE,
        related_name='predicted_severities'
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
