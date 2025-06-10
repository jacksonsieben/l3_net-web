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
    
    class Meta:
        unique_together = ['pred_severity_id', 'user_id']  # One validation per prediction per user
        
    def __str__(self):
        return f"Validation by {self.user_id.email} for {self.pred_severity_id}"
    
    def save(self, *args, **kwargs):
        """Override save to update assignment completion status"""
        super().save(*args, **kwargs)
        self._update_assignment_status()
    
    def delete(self, *args, **kwargs):
        """Override delete to update assignment completion status"""
        super().delete(*args, **kwargs)
        self._update_assignment_status()
    
    def _update_assignment_status(self):
        """Update the completion status of related run assignments"""
        try:
            # Get the run from the prediction
            run = self.pred_severity_id.run_id
            
            # Find any assignments for this run and user
            from validation.models.run_assignment import RunAssignment
            assignments = RunAssignment.objects.filter(
                run=run,
                user=self.user_id
            )
            
            # Update completion status for each assignment
            for assignment in assignments:
                assignment.update_completion_status()
                
        except Exception:
            # Don't fail the save/delete if assignment update fails
            pass