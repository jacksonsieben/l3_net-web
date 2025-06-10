from django.db import models

class Polygon(models.Model):
    id = models.AutoField(primary_key=True)
    # vertebra_id = models.ForeignKey('validation.PredVertebra', on_delete=models.CASCADE, related_name='vertebrea')
    x1 = models.FloatField()
    y1 = models.FloatField()
    x2 = models.FloatField()
    y2 = models.FloatField()