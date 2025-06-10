from django.db import models

class VertebraName(models.TextChoices):
    T8 = 'T8'
    T9 = 'T9'
    T10 = 'T10'
    T11 = 'T11'
    T12 = 'T12'
    L1 = 'L1'
    L2 = 'L2'
    L3 = 'L3'
    L4 = 'L4'
    L5 = 'L5'
    S1 = 'S1'
    UNKNOWN = 'UNKNOWN'