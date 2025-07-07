from django.db import models
from huggingface_hub import HfApi, HfFolder
from django.conf import settings
import logging

logger = logging.getLogger(__name__)

class Exam(models.Model):
    id = models.AutoField(primary_key=True)
    external_id = models.CharField(max_length=100, unique=True)
    image_path = models.CharField(max_length=255)
    version = models.CharField(
        max_length=100,
        default="main",
        help_text="Dataset version/tag from Hugging Face repository"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    @classmethod
    def get_available_versions(cls):
        """Get available versions/tags from Hugging Face repository"""
        try:
            hf_api = HfApi()
            token = settings.HF_TOKEN
            HfFolder.save_token(token)
            # You'll need to set your actual dataset repository ID in settings
            repo_id = getattr(settings, 'HF_REPO_ID', 'sieben-ips/l3net')
            
            # Get repository references
            refs = hf_api.list_repo_refs(repo_id, repo_type="dataset", token=token)

            # Start with 'main' as default
            versions = ['main']
            
            # Add tags if available
            if hasattr(refs, 'tags') and refs.tags:
                versions.extend([tag.name for tag in refs.tags])
            
            # Remove duplicates while preserving order
            seen = set()
            unique_versions = []
            for version in versions:
                if version not in seen:
                    seen.add(version)
                    unique_versions.append(version)
            
            return unique_versions
            
        except Exception as e:
            logger.error(f"Error fetching HF versions: {e}")
            return ['main']  # Fallback to main only
    
    def __str__(self):
        return f"Exam {self.external_id} (v{self.version})"
    
    class Meta:
        ordering = ['-created_at']
