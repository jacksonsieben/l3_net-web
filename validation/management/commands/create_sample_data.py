import os
import random
from django.core.management.base import BaseCommand
from django.conf import settings
from django.utils import timezone
from validation.models import (
    Exam, ModelVersion, Run, Polygon, 
    PredVertebra, PredSeverity, Validation, RunAssignment
)
from validation.enums.vertebra_name import VertebraName
from validation.enums.severity import Severity
from users.models import CustomUser


class Command(BaseCommand):
    help = 'Creates sample data for the validation app'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Clear existing data before creating new sample data',
        )
    
    def handle(self, *args, **kwargs):
        self.stdout.write('Creating sample data for validation app...')
        
        # Clear existing data if --force flag is used
        if kwargs['force']:
            self.stdout.write('Clearing existing validation data...')
            Validation.objects.all().delete()
            PredSeverity.objects.all().delete()
            PredVertebra.objects.all().delete()
            Polygon.objects.all().delete()
            RunAssignment.objects.all().delete()
            Run.objects.all().delete()
            Exam.objects.all().delete()
            ModelVersion.objects.all().delete()
            self.stdout.write(self.style.SUCCESS('Cleared existing data!'))
        
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
        
        try:
            user, created = CustomUser.objects.get_or_create(
                email='admin@email.com',
                defaults={
                    'full_name': 'Test User',
                    'is_active': True,
                    'is_staff': True,
                    'is_superuser': True,
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
        
        # Create sample runs with names and descriptions
        runs = []
        run_names = [
            "Initial Model Validation - Batch 1",
            "Quality Control Review - Week 12",
            "Expert Radiologist Review",
            "Cross-validation Study",
            "Final Model Assessment"
        ]
        
        for i, run_name in enumerate(run_names, 1):
            run, created = Run.objects.get_or_create(
                name=run_name,
                defaults={
                    'run_date': timezone.now(),
                    'description': f'Sample run {i} for validation and testing purposes'
                }
            )
            
            # Add exams to this run (each run gets 2-3 exams)
            run_exams = exams[i-1:i+1] if i < len(exams) else exams[-2:]
            for exam in run_exams:
                run.exams.add(exam)
            
            runs.append(run)
            if created:
                self.stdout.write(self.style.SUCCESS(f'Created run: {run.name} with {len(run_exams)} exams'))
            else:
                self.stdout.write(f'Using existing run: {run.name}')
        
        # Create run assignments for the user
        for run in runs:
            assignment, created = RunAssignment.objects.get_or_create(
                run=run,
                user=user,
                defaults={
                    'assigned_by': user,  # For demo, user assigns to themselves
                    'notes': f'Sample assignment for {run.name}'
                }
            )
            if created:
                self.stdout.write(self.style.SUCCESS(f'Created assignment: {run.name} → {user.email}'))
            else:
                self.stdout.write(f'Using existing assignment: {run.name} → {user.email}')
        
        # For each run, create vertebrae predictions with polygons
        vertebra_choices = list(VertebraName.choices)
        severity_choices = list(Severity.choices)
        
        # Create a consistent set of predictions for each exam
        # This ensures that the same exam has the same predictions across different runs
        exam_predictions = {}  # Will store predictions per exam
        
        for exam in exams:
            # Create 3-7 vertebrae predictions per exam (consistent across runs)
            num_vertebrae = random.randint(3, 7)
            predictions_for_exam = []
            
            for i in range(num_vertebrae):
                # Create polygon first
                x1 = random.uniform(0.1, 0.8)
                y1 = random.uniform(0.1, 0.8)
                x2 = x1 + random.uniform(0.05, 0.15)
                y2 = y1 + random.uniform(0.05, 0.15)
                
                # Ensure coordinates don't exceed 1.0
                x2 = min(x2, 1.0)
                y2 = min(y2, 1.0)
                
                polygon = Polygon.objects.create(
                    x1=x1, y1=y1, x2=x2, y2=y2
                )
                
                # Choose vertebra name (avoid duplicates within same exam)
                available_vertebrae = [v[0] for v in vertebra_choices if v[0] not in [p['vertebra_name'] for p in predictions_for_exam]]
                if not available_vertebrae:
                    available_vertebrae = [v[0] for v in vertebra_choices]
                vertebra_name = random.choice(available_vertebrae)
                
                # Create a severity polygon (separate from vertebra polygon)
                x1_sev = random.uniform(0.1, 0.8)
                y1_sev = random.uniform(0.1, 0.8)
                x2_sev = x1_sev + random.uniform(0.05, 0.15)
                y2_sev = y1_sev + random.uniform(0.05, 0.15)
                
                # Ensure coordinates don't exceed 1.0
                x2_sev = min(x2_sev, 1.0)
                y2_sev = min(y2_sev, 1.0)
                
                severity_polygon = Polygon.objects.create(
                    x1=x1_sev, y1=y1_sev, x2=x2_sev, y2=y2_sev
                )
                
                # Choose random severity
                severity_name = random.choice(severity_choices)[0]
                
                predictions_for_exam.append({
                    'vertebra_name': vertebra_name,
                    'vertebra_confidence': random.uniform(0.75, 0.99),
                    'vertebra_polygon': polygon,
                    'severity_name': severity_name,
                    'severity_confidence': random.uniform(0.7, 0.98),
                    'severity_polygon': severity_polygon,
                    'model_version': random.choice(model_versions)
                })
            
            exam_predictions[exam.id] = predictions_for_exam
            self.stdout.write(self.style.SUCCESS(f'Created {len(predictions_for_exam)} predictions for exam {exam.external_id}'))
        
        # Now create the actual prediction records for each run that contains each exam
        for run in runs:
            for exam in run.exams.all():
                predictions = exam_predictions[exam.id]
                
                for pred_data in predictions:
                    # Create vertebra prediction
                    vertebra = PredVertebra.objects.create(
                        name=pred_data['vertebra_name'],
                        confidence=pred_data['vertebra_confidence'],
                        run_id=run,
                        model_version=pred_data['model_version'],
                        polygon=pred_data['vertebra_polygon']
                    )
                    
                    # Create severity prediction
                    severity = PredSeverity.objects.create(
                        severity_name=pred_data['severity_name'],
                        confidence=pred_data['severity_confidence'],
                        run_id=run,
                        model_version=pred_data['model_version'],
                        bounding_box=pred_data['severity_polygon']
                    )
                    
                    self.stdout.write(self.style.SUCCESS(f'Created predictions for {exam.external_id} in run {run.name}: {vertebra.name} + {severity.severity_name}'))
                    
                    # Randomly add validations (30% chance)
                    if random.random() > 0.7:
                        validation = Validation.objects.create(
                            pred_severity_id=severity,
                            user_id=user,
                            is_correct=random.choice([True, False]),
                            comment=random.choice(["Looks accurate", "Needs adjustment", "Perfect detection", "Uncertain", None]),
                            bounding_box=pred_data['severity_polygon'] if random.random() > 0.5 else None,
                            severity_name=random.choice([pred_data['severity_name'], None])
                        )
                        self.stdout.write(self.style.SUCCESS(f'Created validation for {exam.external_id} - {severity.severity_name}'))
        
        self.stdout.write(self.style.SUCCESS('Successfully created sample validation data!'))
