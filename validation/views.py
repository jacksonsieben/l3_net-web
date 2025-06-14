from django.shortcuts import render, get_object_or_404
from django.views.generic import ListView, DetailView, CreateView, FormView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse, Http404
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.utils.decorators import method_decorator
from django.urls import reverse_lazy
from django.contrib.auth import get_user_model
from django import forms

from .models.exam import Exam
from .models.run import Run
from .models.polygon import Polygon
from .models.pred_severity import PredSeverity
from .models.pred_vertebra import PredVertebra
from .models.model_version import ModelVersion
from .models.run_assignment import RunAssignment

User = get_user_model()

# Create your views here.
class RunAssignmentListView(LoginRequiredMixin, ListView):
    """View to display a list of all run assignments for the current user."""
    model = RunAssignment
    template_name = 'validation/run_assignment_list.html'
    context_object_name = 'assignments'
    login_url = '/users/login/'
    
    def get_queryset(self):
        # Superusers can see all assignments
        if self.request.user.is_superuser:
            return RunAssignment.objects.all().select_related(
                'run', 'user', 'assigned_by'
            ).order_by('-assigned_at')
        else:
            print("User is not a superuser, filtering assignments")
            print(self.request.user)
            # Regular users only see their own assignments
            return RunAssignment.objects.filter(
                user=self.request.user
            ).select_related(
                'run'
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
        # Check if filtering by run
        run_id = self.request.GET.get('run')
        
        # Superusers can see all exams
        if self.request.user.is_superuser:
            queryset = Exam.objects.prefetch_related('runs').order_by('-created_at')
            if run_id:
                # Filter by specific run
                queryset = queryset.filter(runs__id=run_id)
            return queryset
        
        # Regular users only see exams that have runs assigned to them
        assigned_runs = RunAssignment.objects.filter(user=self.request.user).select_related('run')
        exam_ids = []
        for assignment in assigned_runs:
            exam_ids.extend(list(assignment.run.exams.values_list('id', flat=True)))
        
        queryset = Exam.objects.filter(id__in=exam_ids).prefetch_related('runs').order_by('-created_at')
        
        if run_id:
            # Filter by specific run (only if user has access to that run)
            user_run_ids = [assignment.run.id for assignment in assigned_runs]
            if int(run_id) in user_run_ids:
                queryset = queryset.filter(runs__id=run_id)
            else:
                # User doesn't have access to this run, return empty queryset
                queryset = Exam.objects.none()
                
        return queryset
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Check if filtering by run
        run_id = self.request.GET.get('run')
        context['filtered_run'] = None
        
        if run_id:
            try:
                run = Run.objects.get(id=run_id)
                # Check if user has access to this run
                if self.request.user.is_superuser or RunAssignment.objects.filter(
                    user=self.request.user, run=run
                ).exists():
                    context['filtered_run'] = run
            except Run.DoesNotExist:
                pass
        
        # Add assignment information for each exam
        exam_assignments = {}
        for exam in context['exams']:
            if self.request.user.is_superuser:
                # For superusers, show all assignments for this exam
                assignments = RunAssignment.objects.filter(
                    run__exams=exam
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
                    run__exams=exam
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
            run__exams=exam
        ).exists()
        
        if not has_assignment:
            raise Http404("You don't have permission to validate this exam.")
        
        return exam
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Check if a specific run is requested via query parameter
        run_id = self.request.GET.get('run')
        selected_run = None
        
        if run_id:
            try:
                # Verify that the user has access to this specific run
                if self.request.user.is_superuser:
                    selected_run = Run.objects.get(id=run_id, exams=self.object)
                else:
                    # Check if user has assignment for this specific run
                    assignment = RunAssignment.objects.get(
                        user=self.request.user,
                        run__id=run_id,
                        run__exams=self.object
                    )
                    selected_run = assignment.run
            except (Run.DoesNotExist, RunAssignment.DoesNotExist):
                # If the specific run is not accessible, fall back to default behavior
                pass
        
        if selected_run:
            # Use the specifically requested run
            if self.request.user.is_superuser:
                # Create a mock assignment for superuser
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
                
                assignment = MockAssignment(selected_run)
                context['run'] = selected_run
                context['assignment'] = assignment
                context['validation_progress'] = assignment.get_validation_progress()
                context['is_superuser_view'] = True
            else:
                # Get the actual assignment for this user and run
                assignment = RunAssignment.objects.get(
                    user=self.request.user,
                    run=selected_run
                )
                context['run'] = selected_run
                context['assignment'] = assignment
                context['validation_progress'] = assignment.get_validation_progress()
                context['is_superuser_view'] = False
        else:
            # Fall back to default behavior (latest assigned run)
            # Get runs assigned to this user for this exam
            user_assignments = RunAssignment.objects.filter(
                user=self.request.user,
                run__exams=self.object
            ).select_related('run').order_by('-run__run_date')
            
            # For superusers, if they don't have assignments, get the latest run
            if self.request.user.is_superuser and not user_assignments.exists():
                latest_run = Run.objects.filter(exams=self.object).order_by('-run_date').first()
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
                            'id': severity.id,
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


# ============ ADMIN-ONLY VIEWS ============

class ExamCreationForm(forms.ModelForm):
    """Form for creating new exams."""
    class Meta:
        model = Exam
        fields = ['external_id', 'image_path']
        widgets = {
            'external_id': forms.TextInput(attrs={'placeholder': 'e.g., EXAM-2025-001'}),
            'image_path': forms.URLInput(attrs={'placeholder': 'https://example.com/image.png'}),
        }


@method_decorator(staff_member_required, name='dispatch')
class AdminExamCreateView(CreateView):
    """Admin-only view for creating new exams."""
    model = Exam
    form_class = ExamCreationForm
    template_name = 'validation/admin_exam_create.html'
    success_url = reverse_lazy('validation:admin_exam_create')
    
    def form_valid(self, form):
        messages.success(self.request, f'Exam "{form.instance.external_id}" created successfully!')
        return super().form_valid(form)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Add recent exams for reference
        context['recent_exams'] = Exam.objects.order_by('-created_at')[:5]
        return context


class RunAssignmentForm(forms.Form):
    """Form for assigning runs to users."""
    run = forms.ModelChoiceField(
        queryset=Run.objects.all(),
        empty_label="Select a run to assign...",
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    user = forms.ModelChoiceField(
        queryset=User.objects.filter(is_active=True),
        empty_label="Select a user...",
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'rows': 3,
            'placeholder': 'Optional notes about this assignment...'
        }),
        help_text="Optional notes about this assignment"
    )


@method_decorator(staff_member_required, name='dispatch')
class AdminRunAssignmentView(FormView):
    """Admin-only view for assigning runs to users."""
    form_class = RunAssignmentForm
    template_name = 'validation/admin_run_assignment.html'
    success_url = reverse_lazy('validation:admin_run_assignment')
    
    def form_valid(self, form):
        run = form.cleaned_data['run']
        user = form.cleaned_data['user']
        notes = form.cleaned_data['notes']
        
        # Check if assignment already exists
        assignment, created = RunAssignment.objects.get_or_create(
            run=run,
            user=user,
            defaults={
                'assigned_by': self.request.user,
                'notes': notes
            }
        )
        
        if created:
            messages.success(self.request, f'Run "{run.name}" assigned to {user.email} successfully!')
        else:
            messages.warning(self.request, f'Run "{run.name}" is already assigned to {user.email}.')
        
        return super().form_valid(form)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Get recent assignments
        context['recent_assignments'] = RunAssignment.objects.select_related(
            'run', 'user', 'assigned_by'
        ).order_by('-assigned_at')[:10]
        
        # Get run statistics
        context['total_runs'] = Run.objects.count()
        context['assigned_runs'] = Run.objects.filter(assignments__isnull=False).distinct().count()
        context['unassigned_runs'] = Run.objects.filter(assignments__isnull=True).count()
        
        # Get user statistics
        context['total_users'] = User.objects.filter(is_active=True).count()
        context['users_with_assignments'] = User.objects.filter(run_assignments__isnull=False).distinct().count()
        
        return context
