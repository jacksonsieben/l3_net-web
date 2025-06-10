from django.db import models
from django.utils import timezone


class RunAssignment(models.Model):
    """
    Model to assign runs to users for validation.
    Tracks which user is responsible for validating which run.
    """
    id = models.AutoField(primary_key=True)
    
    # Foreign keys
    run = models.ForeignKey(
        'validation.Run',
        on_delete=models.CASCADE,
        related_name='assignments'
    )
    user = models.ForeignKey(
        'users.CustomUser',
        on_delete=models.CASCADE,
        related_name='run_assignments'
    )
    
    # Assignment metadata
    assigned_at = models.DateTimeField(default=timezone.now)
    assigned_by = models.ForeignKey(
        'users.CustomUser',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_runs',
        help_text="User who made this assignment (usually admin/superuser)"
    )
    
    # Status tracking
    is_completed = models.BooleanField(
        default=False,
        help_text="True when all predictions in this run have been validated"
    )
    completed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp when validation was completed"
    )
    
    # Optional fields
    notes = models.TextField(
        blank=True,
        null=True,
        help_text="Optional notes about this assignment"
    )
    
    class Meta:
        unique_together = ['run', 'user']  # One assignment per run per user
        indexes = [
            models.Index(fields=['user', 'is_completed']),
            models.Index(fields=['run']),
            models.Index(fields=['assigned_at']),
        ]
    
    def __str__(self):
        status = "✓ Completed" if self.is_completed else "⏳ Pending"
        return f"Run {self.run.id} → {self.user.email} ({status})"
    
    def save(self, *args, **kwargs):
        """Override save to automatically set completed_at when is_completed changes to True"""
        if self.is_completed and not self.completed_at:
            self.completed_at = timezone.now()
        elif not self.is_completed:
            self.completed_at = None
        super().save(*args, **kwargs)
    
    def get_validation_progress(self):
        """
        Calculate validation progress for this assignment.
        Returns a dictionary with progress information.
        """
        # Get all severity predictions for this run
        total_predictions = self.run.predicted_severities.count()
        
        # Count how many have been validated
        validated_predictions = self.run.predicted_severities.filter(
            validations__user_id=self.user
        ).distinct().count()
        
        if total_predictions == 0:
            percentage = 0
        else:
            percentage = (validated_predictions / total_predictions) * 100
        
        return {
            'total_predictions': total_predictions,
            'validated_predictions': validated_predictions,
            'remaining_predictions': total_predictions - validated_predictions,
            'percentage_complete': round(percentage, 1),
            'is_complete': validated_predictions >= total_predictions and total_predictions > 0
        }
    
    def update_completion_status(self):
        """
        Update the is_completed status based on validation progress.
        Call this method after a validation is added or removed.
        """
        progress = self.get_validation_progress()
        old_status = self.is_completed
        self.is_completed = progress['is_complete']
        
        if old_status != self.is_completed:
            self.save()
        
        return self.is_completed
