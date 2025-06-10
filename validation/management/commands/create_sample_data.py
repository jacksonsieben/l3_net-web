import os
import random
from django.core.management.base import BaseCommand
from django.conf import settings
from django.utils import timezone
from validation.models import (
    Exam, ModelVersion, Run, Polygon, 
    PredVertebra, PredSeverity, Validation
)
from validation.enums.vertebra_name import VertebraName
from validation.enums.severity import Severity
from users.models import CustomUser


class Command(BaseCommand):
    help = 'Creates sample data for the validation app'
    
    def handle(self, *args, **kwargs):
        self.stdout.write('Creating sample data for validation app...')
        
        # Create a test user if not exists
        try:
            user, created = CustomUser.objects.get_or_create(
                email='test@example.com',
                defaults={
                    'full_name': 'Test User',
                    'is_active': True,
                    'is_staff': False,
                }
            )
            if created:
                user.set_password('password123')
                user.save()
                self.stdout.write(self.style.SUCCESS(f'Created test user: {user.email}'))
            else:
                self.stdout.write(f'Using existing user: {user.email}')
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Error creating user: {str(e)}'))
            return
        
        # Create sample model versions
        model_versions = []
        for i in range(1, 3):
            model_version, created = ModelVersion.objects.get_or_create(
                version_number=f'v1.{i}',
                defaults={
                    'model_name': f'SpineStenosis-{i}',
                    'model_type': 'classification',
                    'description': f'Sample model version {i} for spine stenosis detection',
                    'model_path': f'/path/to/model/v1.{i}/model.h5'
                }
            )
            model_versions.append(model_version)
            if created:
                self.stdout.write(self.style.SUCCESS(f'Created model version: {model_version.version_number}'))
            else:
                self.stdout.write(f'Using existing model version: {model_version.version_number}')
        
        # Create sample exams (5 exams)
        exams = []
        for i in range(1, 6):
            exam_id = f'EXAM-{i:04d}'
            image_path = f'https://huggingface.co/datasets/sieben-ips/l3net/resolve/v1.0.0/scan_1.png'
            
            exam, created = Exam.objects.get_or_create(
                external_id=exam_id,
                defaults={
                    'image_path': image_path
                }
            )
            exams.append(exam)
            if created:
                self.stdout.write(self.style.SUCCESS(f'Created exam: {exam.external_id}'))
            else:
                self.stdout.write(f'Using existing exam: {exam.external_id}')
        
        # Create runs for each exam
        runs = []
        for exam in exams:
            run, created = Run.objects.get_or_create(
                exam_id=exam,
                defaults={
                    'run_date': timezone.now()
                }
            )
            runs.append(run)
            if created:
                self.stdout.write(self.style.SUCCESS(f'Created run for exam: {exam.external_id}'))
            else:
                self.stdout.write(f'Using existing run for exam: {exam.external_id}')
        
        # For each run, create vertebrae predictions with polygons
        vertebra_choices = list(VertebraName.choices)
        severity_choices = list(Severity.choices)
        
        for run in runs:
            # Create 3-7 vertebrae predictions per run
            num_vertebrae = random.randint(3, 7)
            
            for _ in range(num_vertebrae):
                # Create polygon first
                x1 = random.uniform(0.1, 0.4)
                y1 = random.uniform(0.1, 0.4)
                x2 = x1 + random.uniform(0.1, 0.3)
                y2 = y1 + random.uniform(0.1, 0.3)
                
                polygon = Polygon.objects.create(
                    x1=x1, y1=y1, x2=x2, y2=y2
                )
                self.stdout.write(self.style.SUCCESS(f'Created polygon at ({x1:.2f}, {y1:.2f}, {x2:.2f}, {y2:.2f})'))
                
                # Choose random vertebra name
                vertebra_name = random.choice(vertebra_choices)[0]
                
                # Create vertebra prediction
                vertebra = PredVertebra.objects.create(
                    name=vertebra_name,
                    confidence=random.uniform(0.75, 0.99),
                    run_id=run,
                    model_version=random.choice(model_versions),
                    polygon=polygon
                )
                self.stdout.write(self.style.SUCCESS(f'Created vertebra prediction: {vertebra.name}'))
                
                # Create a new bounding box for severity (separate from vertebra polygon)
                x1_sev = random.uniform(0.1, 0.4)
                y1_sev = random.uniform(0.1, 0.4)
                x2_sev = x1_sev + random.uniform(0.1, 0.3)
                y2_sev = y1_sev + random.uniform(0.1, 0.3)
                
                severity_polygon = Polygon.objects.create(
                    x1=x1_sev, y1=y1_sev, x2=x2_sev, y2=y2_sev
                )
                self.stdout.write(self.style.SUCCESS(f'Created severity polygon at ({x1_sev:.2f}, {y1_sev:.2f}, {x2_sev:.2f}, {y2_sev:.2f})'))
                
                # Choose random severity
                severity_name = random.choice(severity_choices)[0]
                
                # Create severity prediction
                severity = PredSeverity.objects.create(
                    severity_name=severity_name,
                    confidence=random.uniform(0.7, 0.98),
                    run_id=run,
                    model_version=random.choice(model_versions),
                    bounding_box=severity_polygon
                )
                self.stdout.write(self.style.SUCCESS(f'Created severity prediction: {severity.severity_name}'))
                
                # Randomly add validations (50% chance)
                if random.random() > 0.5:
                    validation = Validation.objects.create(
                        pred_severity_id=severity,
                        user_id=user,
                        is_correct=random.choice([True, False]),
                        comment=random.choice(["Looks good", "Not quite right", "Perfect match", None]),
                        bounding_box=polygon if random.random() > 0.5 else None,
                        severity_name=random.choice([severity_name, None])
                    )
                    self.stdout.write(self.style.SUCCESS(f'Created validation for severity: {severity.severity_name}'))
        
        self.stdout.write(self.style.SUCCESS('Successfully created sample validation data!'))
