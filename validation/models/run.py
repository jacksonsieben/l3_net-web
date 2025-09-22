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
    
    # Intra-operator reliability fields (safe additions)
    original_run = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='duplicate_runs',
        help_text="Original run this is duplicated from (for intra-operator studies)"
    )
    study_type = models.CharField(
        max_length=50,
        default='original',
        help_text="Type of study: 'original', 'intra_operator_round_2', etc."
    )
    intra_operator_study_name = models.CharField(
        max_length=200,
        null=True,
        blank=True,
        help_text="Name to group related runs for intra-operator reliability studies"
    )
    
    # Assignment protection for intra-operator studies
    assignments_locked = models.BooleanField(
        default=False,
        help_text="If True, prevents new assignments to maintain expert consistency for reliability studies"
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
    
    def is_intra_operator_study(self):
        """Check if this run is part of an intra-operator reliability study"""
        return self.original_run is not None or self.duplicate_runs.exists()
    
    def get_related_runs(self):
        """Get all runs related to this one for intra-operator studies"""
        if self.original_run:
            # This is a duplicate, get the original and all its duplicates
            return [self.original_run] + list(self.original_run.duplicate_runs.all())
        elif self.duplicate_runs.exists():
            # This is an original with duplicates
            return [self] + list(self.duplicate_runs.all())
        else:
            # This is a standalone run
            return [self]
