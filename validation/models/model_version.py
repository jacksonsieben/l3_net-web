from django.db import models

class ModelVersion(models.Model):
    id = models.AutoField(primary_key=True)
    version_number = models.CharField(max_length=50, help_text="Version number of the model")
    model_name = models.CharField(max_length=100, help_text="Name of the model")
    model_type = models.CharField(max_length=100, help_text="Type of the model (e.g., classification, regression)")
    created_at = models.DateTimeField(auto_now_add=True, help_text="Timestamp when the model version was created")
    updated_at = models.DateTimeField(auto_now=True, help_text="Timestamp when the model version was last updated")
    description = models.TextField(blank=True, null=True, help_text="Description of the model version")
    model_path = models.CharField(max_length=255, help_text="Path to the model file")