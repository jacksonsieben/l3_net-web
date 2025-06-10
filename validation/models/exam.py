from django.db import models

class Exam(models.Model):
    id = models.AutoField(primary_key=True)
    external_id = models.CharField(max_length=100, unique=True)
    image_path = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    