from django.db import models

from validation.enums.run_status import RunStatus

class Run(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(
        max_length=200, 
        help_text="Name or description of this run",
        default="Unnamed Run"
    )
    exams = models.ManyToManyField(
        'validation.Exam',
        related_name='runs',
        help_text="Exams included in this run"
    )
    run_date = models.DateTimeField(auto_now_add=True)
    description = models.TextField(
        blank=True, 
        null=True, 
        help_text="Optional description of this run"
    )
    status = models.CharField(
        choices=RunStatus.choices,
        max_length=20,
        default=RunStatus.OPEN,
        help_text="Current status of this run"
    )
    
    class Meta:
        ordering = ['-run_date']
    
    def __str__(self):
        return f"{self.name} ({self.run_date.strftime('%Y-%m-%d')})"
    
    def get_exam_count(self):
        """Return the number of exams in this run"""
        return self.exams.count()
    
    def get_total_predictions(self):
        """Return the total number of predictions across all exams in this run"""
        return self.predicted_severities.count() + self.predicted_vertebrae.count()
