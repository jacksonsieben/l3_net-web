from django.test import TestCase
from django.db import transaction
from validation.models import Exam


class ExamShuffleTestCase(TestCase):
    def setUp(self):
        """Create test exams"""
        self.exam_data = [
            {'external_id': 'exam_001', 'image_path': '/path/to/image1.jpg', 'version': 'v1.0'},
            {'external_id': 'exam_002', 'image_path': '/path/to/image2.jpg', 'version': 'v1.0'},
            {'external_id': 'exam_003', 'image_path': '/path/to/image3.jpg', 'version': 'v1.1'},
            {'external_id': 'exam_004', 'image_path': '/path/to/image4.jpg', 'version': 'v1.1'},
            {'external_id': 'exam_005', 'image_path': '/path/to/image5.jpg', 'version': 'v2.0'},
        ]
        
        for data in self.exam_data:
            Exam.objects.create(**data)

    def test_shuffle_all_preserves_data(self):
        """Test that shuffle_all preserves all exam data"""
        # Get original data
        original_exams = list(Exam.objects.all().order_by('id'))
        original_external_ids = set(exam.external_id for exam in original_exams)
        original_image_paths = set(exam.image_path for exam in original_exams)
        original_versions = set(exam.version for exam in original_exams)
        original_count = len(original_exams)
        
        # Shuffle with a fixed seed for reproducibility
        shuffled_count = Exam.shuffle_all(seed=42)
        
        # Get data after shuffling
        shuffled_exams = list(Exam.objects.all().order_by('id'))
        shuffled_external_ids = set(exam.external_id for exam in shuffled_exams)
        shuffled_image_paths = set(exam.image_path for exam in shuffled_exams)
        shuffled_versions = set(exam.version for exam in shuffled_exams)
        
        # Verify data integrity
        self.assertEqual(shuffled_count, original_count)
        self.assertEqual(len(shuffled_exams), original_count)
        self.assertEqual(shuffled_external_ids, original_external_ids)
        self.assertEqual(shuffled_image_paths, original_image_paths)
        self.assertEqual(shuffled_versions, original_versions)
        
        # Verify that at least some order changed (very unlikely to be the same with 5 items)
        original_order = [exam.external_id for exam in original_exams]
        shuffled_order = [exam.external_id for exam in shuffled_exams]
        self.assertNotEqual(original_order, shuffled_order)

    def test_shuffle_by_version(self):
        """Test shuffling within versions"""
        # Get original data by version
        original_v1_0 = list(Exam.objects.filter(version='v1.0').values_list('external_id', flat=True))
        original_v1_1 = list(Exam.objects.filter(version='v1.1').values_list('external_id', flat=True))
        
        # Shuffle by version
        result = Exam.shuffle_by_version(seed=42)
        
        # Verify counts
        self.assertEqual(result['v1.0'], 2)
        self.assertEqual(result['v1.1'], 2)
        self.assertEqual(result['v2.0'], 0)  # Only 1 exam, can't shuffle
        
        # Verify that external_ids are preserved within each version
        shuffled_v1_0 = set(Exam.objects.filter(version='v1.0').values_list('external_id', flat=True))
        shuffled_v1_1 = set(Exam.objects.filter(version='v1.1').values_list('external_id', flat=True))
        
        self.assertEqual(set(original_v1_0), shuffled_v1_0)
        self.assertEqual(set(original_v1_1), shuffled_v1_1)

    def test_shuffle_image_paths(self):
        """Test shuffling image paths while keeping external_ids"""
        # Get original data
        original_external_ids = list(Exam.objects.all().order_by('id').values_list('external_id', flat=True))
        original_image_paths = set(Exam.objects.all().values_list('image_path', flat=True))
        
        # Shuffle image paths
        shuffled_count = Exam.shuffle_image_paths(seed=42)
        
        # Verify external_ids stayed the same
        shuffled_external_ids = list(Exam.objects.all().order_by('id').values_list('external_id', flat=True))
        shuffled_image_paths = set(Exam.objects.all().values_list('image_path', flat=True))
        
        self.assertEqual(shuffled_count, 5)
        self.assertEqual(original_external_ids, shuffled_external_ids)
        self.assertEqual(original_image_paths, shuffled_image_paths)
        
        # Verify that image paths were actually shuffled
        original_pairs = list(Exam.objects.all().order_by('id').values_list('external_id', 'image_path'))
        # Since we used a fixed seed, we can verify the shuffle happened
        # At least one pair should be different
        different_pairs = 0
        for i, (ext_id, img_path) in enumerate(original_pairs):
            original_path = self.exam_data[i]['image_path']
            if img_path != original_path:
                different_pairs += 1
        
        self.assertGreater(different_pairs, 0, "Image paths should have been shuffled")

    def test_shuffle_with_insufficient_data(self):
        """Test shuffling with insufficient data"""
        # Clear all but one exam
        Exam.objects.all().delete()
        Exam.objects.create(external_id='single_exam', image_path='/single.jpg', version='v1.0')
        
        # Try to shuffle - should return 0
        count = Exam.shuffle_all()
        self.assertEqual(count, 0)
        
        count = Exam.shuffle_image_paths()
        self.assertEqual(count, 0)

    def test_shuffle_reproducibility(self):
        """Test that shuffling with the same seed produces the same result"""
        # First shuffle
        Exam.shuffle_all(seed=123)
        first_order = list(Exam.objects.all().order_by('id').values_list('external_id', flat=True))
        
        # Reset data
        Exam.objects.all().delete()
        for data in self.exam_data:
            Exam.objects.create(**data)
        
        # Second shuffle with same seed
        Exam.shuffle_all(seed=123)
        second_order = list(Exam.objects.all().order_by('id').values_list('external_id', flat=True))
        
        # Should be the same
        self.assertEqual(first_order, second_order)