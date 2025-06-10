from django.db import models

from validation.enums.severity import Severity

class Validation(models.Model):
    id = models.AutoField(primary_key=True)
    created_at = models.DateTimeField(auto_now_add=True)
    pred_severity_id = models.ForeignKey(
        'validation.PredSeverity',
        on_delete=models.CASCADE,
        related_name='validations'
    )
    user_id = models.ForeignKey(
        'users.CustomUser',
        on_delete=models.CASCADE,
        related_name='validations'
    )
    is_correct = models.BooleanField(default=False)
    comment = models.TextField(blank=True, null=True)
    bounding_box = models.ForeignKey(
        'validation.Polygon',
        on_delete=models.SET_NULL,
        related_name='validations',
        null=True,
        blank=True
    )
    severity_name = models.CharField(choices=Severity.choices, max_length=20, null=True, blank=True)