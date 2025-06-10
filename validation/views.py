from django.shortcuts import render, get_object_or_404
from django.views.generic import ListView, DetailView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse, Http404
from django.contrib import messages

from .models.exam import Exam
from .models.run import Run
from .models.polygon import Polygon
from .models.pred_severity import PredSeverity
from .models.pred_vertebra import PredVertebra
from .models.model_version import ModelVersion
from .models.run_assignment import RunAssignment

# Create your views here.
class RunAssignmentListView(LoginRequiredMixin, ListView):
    """View to display a list of all run assignments for the current user."""
    model = RunAssignment
    template_name = 'validation/run_assignment_list.html'
    context_object_name = 'assignments'
    login_url = '/users/login/'
    
    def get_queryset(self):
        if self.request.user.is_superuser:
            # Superusers can see all assignments
            return RunAssignment.objects.all().select_related(
                'run__exam_id', 'user', 'assigned_by'
            ).order_by('-assigned_at')
        else:
            # Regular users only see their own assignments
            return RunAssignment.objects.filter(
                user=self.request.user
            ).select_related(
                'run__exam_id', 'assigned_by'
            ).order_by('-assigned_at')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Add statistics for the current user (or all users if superuser)
        if self.request.user.is_superuser:
            total_assignments = RunAssignment.objects.count()
            completed_assignments = RunAssignment.objects.filter(is_completed=True).count()
            context['showing_all_users'] = True
        else:
            total_assignments = RunAssignment.objects.filter(user=self.request.user).count()
            completed_assignments = RunAssignment.objects.filter(
                user=self.request.user, 
                is_completed=True
            ).count()
            context['showing_all_users'] = False
        
        context['total_assignments'] = total_assignments
        context['completed_assignments'] = completed_assignments
        context['pending_assignments'] = total_assignments - completed_assignments
        
        if total_assignments > 0:
            context['completion_percentage'] = round((completed_assignments / total_assignments) * 100, 1)
        else:
            context['completion_percentage'] = 0
            
        return context

class ExamListView(LoginRequiredMixin, ListView):
    """View to display a list of exams for validation based on user permissions."""
    model = Exam
    template_name = 'validation/exam_list.html'
    context_object_name = 'exams'
    login_url = '/users/login/'
    
    def get_queryset(self):
        # Superusers can see all exams
        if self.request.user.is_superuser:
            return Exam.objects.all().order_by('-created_at')
        
        # Regular users only see exams that have runs assigned to them
        assigned_runs = RunAssignment.objects.filter(user=self.request.user).select_related('run__exam_id')
        exam_ids = [assignment.run.exam_id.id for assignment in assigned_runs]
        return Exam.objects.filter(id__in=exam_ids).order_by('-created_at')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Add assignment information for each exam
        exam_assignments = {}
        for exam in context['exams']:
            if self.request.user.is_superuser:
                # For superusers, show all assignments for this exam
                assignments = RunAssignment.objects.filter(
                    run__exam_id=exam
                ).select_related('run', 'user')
                
                exam_assignments[exam.id] = {
                    'assignments': assignments,
                    'total_assignments': assignments.count(),
                    'completed_assignments': assignments.filter(is_completed=True).count(),
                    'all_users': True,  # Flag to indicate this shows all users
                }
            else:
                # For regular users, show only their assignments
                assignments = RunAssignment.objects.filter(
                    user=self.request.user,
                    run__exam_id=exam
                ).select_related('run')
                
                exam_assignments[exam.id] = {
                    'assignments': assignments,
                    'total_assignments': assignments.count(),
                    'completed_assignments': assignments.filter(is_completed=True).count(),
                    'all_users': False,
                }
        
        context['exam_assignments'] = exam_assignments
        context['is_superuser'] = self.request.user.is_superuser
        return context

class ExamDetailView(LoginRequiredMixin, DetailView):
    """View to display an individual exam with its predictions for validation."""
    model = Exam
    template_name = 'validation/exam_detail.html'
    context_object_name = 'exam'
    login_url = '/users/login/'
    
    def get_object(self, queryset=None):
        """Override to check if user has access to this exam through run assignments."""
        exam = super().get_object(queryset)
        
        # Superusers can access any exam
        if self.request.user.is_superuser:
            return exam
        
        # Check if user has any run assignments for this exam
        has_assignment = RunAssignment.objects.filter(
            user=self.request.user,
            run__exam_id=exam
        ).exists()
        
        if not has_assignment:
            raise Http404("You don't have permission to validate this exam.")
        
        return exam
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Get runs assigned to this user for this exam
        user_assignments = RunAssignment.objects.filter(
            user=self.request.user,
            run__exam_id=self.object
        ).select_related('run').order_by('-run__run_date')
        
        # For superusers, if they don't have assignments, get the latest run
        if self.request.user.is_superuser and not user_assignments.exists():
            latest_run = Run.objects.filter(exam_id=self.object).order_by('-run_date').first()
            if latest_run:
                # Create a mock assignment context for display
                class MockAssignment:
                    def __init__(self, run):
                        self.run = run
                        self.is_completed = False
                    
                    def get_validation_progress(self):
                        return {
                            'total_predictions': 0,
                            'validated_predictions': 0,
                            'remaining_predictions': 0,
                            'percentage_complete': 0,
                            'is_complete': False
                        }
                
                assignment = MockAssignment(latest_run)
                run = latest_run
                context['run'] = run
                context['assignment'] = assignment
                context['validation_progress'] = assignment.get_validation_progress()
                context['is_superuser_view'] = True
        elif user_assignments.exists():
            # Use the latest assigned run
            assignment = user_assignments.first()
            run = assignment.run
            context['run'] = run
            context['assignment'] = assignment
            context['validation_progress'] = assignment.get_validation_progress()
            context['is_superuser_view'] = False
        else:
            return context
        
        # Get severity and vertebrae predictions for the run
        if 'run' in context:
            run = context['run']
            severity_predictions = []
            vertebrae_predictions = []
            
            # Get all severities for this run
            severities = PredSeverity.objects.filter(run_id=run)
            vertebrae = PredVertebra.objects.filter(run_id=run)
            
            for severity in severities:
                # Check if severity has a bounding box
                if hasattr(severity, 'bounding_box') and severity.bounding_box:
                    # Find the closest vertebra for this severity
                    for vertebra in vertebrae:
                        severity_predictions.append({
                            # 'vertebra_name': vertebra.name,
                            'severity_name': severity.severity_name,
                            'confidence': severity.confidence * 100,  # Convert to percentage
                            'bounding_box': {
                                'x1': severity.bounding_box.x1,
                                'y1': severity.bounding_box.y1,
                                'x2': severity.bounding_box.x2,
                                'y2': severity.bounding_box.y2,
                            }
                        })
                        # Just add one association for demo purposes
                        break
            
            for vertebra in vertebrae:
                vertebrae_predictions.append({
                    'vertebra_name': vertebra.name,
                    'confidence': vertebra.confidence * 100,  # Convert to percentage
                    'polygon': {
                        'x1': vertebra.polygon.x1,
                        'y1': vertebra.polygon.y1,
                        'x2': vertebra.polygon.x2,
                        'y2': vertebra.polygon.y2,
                    }
                })
            
            context['vertebrae'] = vertebrae
            context['severity_predictions'] = severity_predictions
            context['vertebrae_predictions'] = vertebrae_predictions
            
        return context

def get_exam_data(request, pk):
    """API endpoint to get exam data in JSON format."""
    exam = get_object_or_404(Exam, pk=pk)
    run = Run.objects.filter(exam_id=exam).order_by('-run_date').first()
    
    if not run:
        return JsonResponse({'error': 'No runs found for this exam'}, status=404)
    
    # Get vertebra predictions
    vertebrae = PredVertebra.objects.filter(run_id=run)
    
    # Format data for response
    data = {
        'exam_id': exam.id,
        'external_id': exam.external_id,
        'image_path': exam.image_path,
        'predictions': []
    }
    
    # Get all severities for this run
    severities = PredSeverity.objects.filter(run_id=run)
    
    for severity in severities:
        # Check if severity has a bounding box
        if hasattr(severity, 'bounding_box') and severity.bounding_box:
            # Find a vertebra to pair with this severity
            for vertebra in vertebrae:
                data['predictions'].append({
                    'vertebra_name': vertebra.name,
                    'severity_name': severity.severity_name,
                    'confidence': severity.confidence * 100,  # Convert to percentage
                    'bounding_box': {
                        'x1': severity.bounding_box.x1,
                        'y1': severity.bounding_box.y1,
                        'x2': severity.bounding_box.x2,
                        'y2': severity.bounding_box.y2,
                    }
                })
                # Just pair with one vertebra for demonstration
                break
    
    return JsonResponse(data)
