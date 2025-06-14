from django.db import models


class VertebraLevel(models.TextChoices):
    L1_L2 = 'L1/L2'
    L2_L3 = 'L2/L3'
    L3_L4 = 'L3/L4'
    L4_L5 = 'L4/L5'
    L5_S1 = 'L5/S1'
    UNKNOWN = 'Unknown'