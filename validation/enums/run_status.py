from django.db import models

class RunStatus(models.TextChoices):
    OPEN = 'Open',
    IN_PROGRESS = 'In Progress',
    COMPLETED = 'Completed',
    CANCELLED = 'Cancelled',