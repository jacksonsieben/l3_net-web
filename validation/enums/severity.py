from django.db import models

class Severity(models.TextChoices):
    NORMAL_MILD = 'Normal/Mild'
    MODERATE = 'Moderate'
    SEVERE = 'Severe'
    NOTHING = 'Nothing'
    UNKNOWN = 'Unkown'