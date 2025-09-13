from django.db import models
from huggingface_hub import HfApi, HfFolder
from django.conf import settings
import logging
import random
from django.db import transaction

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
    
    @classmethod
    def shuffle_all(cls, seed=None):
        """
        Shuffle all exams by updating their IDs randomly.
        This preserves all relationships while changing the order.
        
        Args:
            seed (int, optional): Random seed for reproducible shuffling
            
        Returns:
            int: Number of exams shuffled
        """
        if seed is not None:
            random.seed(seed)
        
        with transaction.atomic():
            # Get all exam IDs
            exam_ids = list(cls.objects.values_list('id', flat=True))
            
            if len(exam_ids) < 2:
                logger.info("Less than 2 exams found, no shuffling needed")
                return 0
            
            # Create a shuffled copy of IDs
            shuffled_ids = exam_ids.copy()
            random.shuffle(shuffled_ids)
            
            # Create a mapping of old_id -> new_id
            id_mapping = dict(zip(exam_ids, shuffled_ids))
            
            # Temporarily set all IDs to negative values to avoid conflicts
            for old_id in exam_ids:
                cls.objects.filter(id=old_id).update(id=-old_id)
            
            # Now update to the new shuffled IDs
            for old_id, new_id in id_mapping.items():
                cls.objects.filter(id=-old_id).update(id=new_id)
            
            logger.info(f"Successfully shuffled {len(exam_ids)} exams")
            return len(exam_ids)
    
    @classmethod
    def shuffle_by_version(cls, version=None, seed=None):
        """
        Shuffle exams within a specific version.
        
        Args:
            version (str, optional): Version to shuffle. If None, shuffles all versions separately
            seed (int, optional): Random seed for reproducible shuffling
            
        Returns:
            dict: Number of exams shuffled per version
        """
        if seed is not None:
            random.seed(seed)
        
        result = {}
        
        if version:
            # Shuffle only the specified version
            versions_to_shuffle = [version]
        else:
            # Get all distinct versions
            versions_to_shuffle = cls.objects.values_list('version', flat=True).distinct()
        
        with transaction.atomic():
            for ver in versions_to_shuffle:
                exam_ids = list(cls.objects.filter(version=ver).values_list('id', flat=True))
                
                if len(exam_ids) < 2:
                    result[ver] = 0
                    continue
                
                # Get external_ids for this version
                external_ids = list(cls.objects.filter(version=ver).values_list('external_id', flat=True))
                shuffled_external_ids = external_ids.copy()
                random.shuffle(shuffled_external_ids)
                
                # Update external_ids in shuffled order
                for exam_id, new_external_id in zip(exam_ids, shuffled_external_ids):
                    cls.objects.filter(id=exam_id).update(external_id=new_external_id)
                
                result[ver] = len(exam_ids)
                logger.info(f"Shuffled {len(exam_ids)} exams in version '{ver}'")
        
        return result
    
    @classmethod
    def shuffle_image_paths(cls, seed=None):
        """
        Shuffle image paths while keeping external_ids the same.
        Useful for creating randomized datasets for training/testing.
        
        Args:
            seed (int, optional): Random seed for reproducible shuffling
            
        Returns:
            int: Number of exams shuffled
        """
        if seed is not None:
            random.seed(seed)
        
        with transaction.atomic():
            # Get all image paths
            image_paths = list(cls.objects.values_list('image_path', flat=True))
            
            if len(image_paths) < 2:
                logger.info("Less than 2 exams found, no shuffling needed")
                return 0
            
            # Shuffle the paths
            shuffled_paths = image_paths.copy()
            random.shuffle(shuffled_paths)
            
            # Get all exams ordered by ID
            exams = cls.objects.all().order_by('id')
            
            # Update each exam with a shuffled image path
            for exam, new_path in zip(exams, shuffled_paths):
                exam.image_path = new_path
                exam.save(update_fields=['image_path'])
            
            logger.info(f"Successfully shuffled image paths for {len(image_paths)} exams")
            return len(image_paths)
    
    def __str__(self):
        return f"Exam {self.external_id} (v{self.version})"
    
    class Meta:
        ordering = ['-created_at']
