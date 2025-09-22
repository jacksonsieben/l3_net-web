from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.views.generic import ListView, DetailView, FormView
from django.views.generic.edit import CreateView, UpdateView, DeleteView
from django.urls import reverse_lazy
from django.http import JsonResponse, Http404, HttpResponse, HttpResponseRedirect
from django.db.models import Count, F, Case, When, Q
from django.db.models.functions import Coalesce
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.views.decorators.http import require_http_methods
from django.contrib.admin.views.decorators import staff_member_required
from django import forms
from collections import defaultdict, Counter
import json
import os

from huggingface_hub import hf_hub_download

from .models import Exam, Run, RunAssignment, PredSeverity, Validation, PredVertebra
from .enums.run_status import RunStatus
from .enums.severity import Severity

from users.models import CustomUser

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
            # Regular users only see their own assignments, excluding cancelled runs
            return RunAssignment.objects.filter(
                user=self.request.user
            ).exclude(
                run__status='Cancelled'
            ).select_related(
                'run', 'assigned_by'
            ).order_by('-assigned_at')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Update completion status for all assignments before displaying
        assignments = self.get_queryset()
        for assignment in assignments:
            assignment.update_completion_status()
        
        # Add statistics for the current user (or all users if superuser)
        if self.request.user.is_superuser:
            total_assignments = RunAssignment.objects.count()
            completed_assignments = RunAssignment.objects.filter(is_completed=True).count()
            context['showing_all_users'] = True
        else:
            # For regular users, only count assignments for non-cancelled runs
            total_assignments = RunAssignment.objects.filter(
                user=self.request.user
            ).exclude(
                run__status='Cancelled'
            ).count()
            completed_assignments = RunAssignment.objects.filter(
                user=self.request.user, 
                is_completed=True
            ).exclude(
                run__status='Cancelled'
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
    
    def dispatch(self, request, *args, **kwargs):
        """Check run status and redirect if necessary."""
        run_id = request.GET.get('run')
        
        if run_id:
            try:
                run = Run.objects.get(id=run_id)
                
                # Check if user has access to this run (unless they're a superuser)
                if not request.user.is_superuser:
                    if not RunAssignment.objects.filter(user=request.user, run=run).exists():
                        messages.error(request, "You don't have permission to access this run.")
                        return redirect('validation:run_assignment_list')
                
                # Check run status and redirect if needed
                if run.status == RunStatus.OPEN:
                    messages.warning(request, f"Run '{run.name}' is still open and not ready for validation.")
                    return redirect('validation:run_assignment_list')
                elif run.status == RunStatus.CANCELLED:
                    messages.error(request, f"Run '{run.name}' has been cancelled and is no longer available.")
                    return redirect('validation:run_assignment_list')
                
            except Run.DoesNotExist:
                messages.error(request, "The requested run does not exist.")
                return redirect('validation:run_assignment_list')
        
        return super().dispatch(request, *args, **kwargs)
    
    def get_queryset(self):
        # Check if filtering by run
        run_id = self.request.GET.get('run')
        
        # Superusers can see all exams
        if self.request.user.is_superuser:
            queryset = Exam.objects.prefetch_related('runs').order_by('id')
            if run_id:
                # Filter by specific run
                queryset = queryset.filter(runs__id=run_id)
            return queryset
        
        # Regular users only see exams that have runs assigned to them
        assigned_runs = RunAssignment.objects.filter(user=self.request.user).select_related('run')
        exam_ids = []
        for assignment in assigned_runs:
            exam_ids.extend(list(assignment.run.exams.values_list('id', flat=True)))
        
        queryset = Exam.objects.filter(id__in=exam_ids).prefetch_related('runs').order_by('id')
        
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
        
        # Add validation progress information for each exam
        exam_progress = {}
        total_percentage = 0
        exams_with_predictions = 0
        
        for exam in context['exams']:
            if context['filtered_run']:
                # Calculate validation progress for this specific exam in the filtered run
                progress = self._get_exam_validation_progress(exam, context['filtered_run'], self.request.user)
                exam_progress[exam.id] = progress
                
                # Only count exams that actually have predictions
                if progress['total_predictions'] > 0:
                    total_percentage += progress.get('percentage_complete', 0)
                    exams_with_predictions += 1
            else:
                # If no specific run is filtered, we can't show validation progress
                exam_progress[exam.id] = {
                    'total_predictions': 0,
                    'validated_predictions': 0,
                    'status': 'no_run_filter'
                }
        
        # Calculate average percentage only for exams with predictions
        if exams_with_predictions > 0:
            exam_progress['total_percentage'] = round(total_percentage / exams_with_predictions, 1)
        else:
            exam_progress['total_percentage'] = 0
            
        print("Exam progress data:", exam_progress)
        
        context['exam_progress'] = exam_progress
        return context
    
    def _get_exam_validation_progress(self, exam, run, user):
        """Calculate validation progress for a specific exam, run, and user."""
        # Get all severity predictions for this specific exam and run
        predictions = PredSeverity.objects.filter(
            exam_id=exam,
            run_id=run
        )

        if predictions.count() == 0:
            return {
                'total_predictions': 0,
                'validated_predictions': 0,
                'remaining_predictions': 0,
                'percentage_complete': 0,
                'status': 'no_predictions'
            }
        
        validated_predictions = 0
        for prediction in predictions:
            # Count how many have been validated AND submitted by this user
            validations = Validation.objects.filter(
                pred_severity_id=prediction.id,
                user_id=user.id
            ).count()
            
            if validations != 0:
                validated_predictions += validations

        print("Validated predictions for exam {}, run {}: {}".format(exam.id, run.id, validated_predictions))

        # Determine status based on validation progress
        if validated_predictions == 0:
            status = 'pending'
            percentage = 0
        elif validated_predictions >= predictions.count():
            status = 'all_validated'
            percentage = 100
        else:
            status = 'partially_validated'
            percentage = (validated_predictions / predictions.count()) * 100
        
        return {
            'total_predictions': predictions.count(),
            'validated_predictions': validated_predictions,
            'remaining_predictions': predictions.count() - validated_predictions,
            'percentage_complete': round(percentage, 1),
            'status': status
        }

class ExamDetailView(LoginRequiredMixin, DetailView):
    """View to display an individual exam with its predictions for validation."""
    model = Exam
    template_name = 'validation/exam_detail.html'
    context_object_name = 'exam'
    login_url = '/users/login/'
    
    def dispatch(self, request, *args, **kwargs):
        """Check run status and control access based on it."""
        run_id = request.GET.get('run')
        
        if run_id:
            try:
                run = Run.objects.get(id=run_id)
                
                # Check if user has access to this run (unless they're a superuser)
                if not request.user.is_superuser:
                    if not RunAssignment.objects.filter(user=request.user, run=run).exists():
                        messages.error(request, "You don't have permission to access this run.")
                        return redirect('validation:run_assignment_list')
                
                # Check run status and redirect if needed
                if run.status == RunStatus.OPEN:
                    messages.warning(request, f"Run '{run.name}' is still open and not ready for validation.")
                    return redirect('validation:run_assignment_list')
                elif run.status == RunStatus.CANCELLED:
                    messages.error(request, f"Run '{run.name}' has been cancelled and is no longer available.")
                    return redirect('validation:run_assignment_list')
                
                # Store run status for context
                self.run_status = run.status
                
            except Run.DoesNotExist:
                messages.error(request, "The requested run does not exist.")
                return redirect('validation:run_assignment_list')
        else:
            self.run_status = None
        
        return super().dispatch(request, *args, **kwargs)
    
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
        
        # Get severity and vertebrae predictions for this specific exam and run
        if 'run' in context:
            run = context['run']
            current_exam = self.object
            severity_predictions = []
            vertebrae_predictions = []
            
            # Get severities for this specific exam and run
            severities = PredSeverity.objects.filter(run_id=run, exam_id=current_exam)
            vertebrae = PredVertebra.objects.filter(run_id=run, exam_id=current_exam)
            
            # Check if there are any predictions for this exam
            if not severities.exists() and not vertebrae.exists():
                context['no_predictions'] = True
                context['severity_predictions'] = []
                context['vertebrae_predictions'] = []
            else:
                # Get existing validations for the current user and this exam's predictions
                existing_validations = Validation.objects.filter(
                    pred_severity_id__run_id=run,
                    pred_severity_id__exam_id=current_exam,
                    user_id=self.request.user
                ).select_related('pred_severity_id')
                
                # Create a mapping of prediction_id -> validation
                validations = {}
                for validation in existing_validations:
                    validations[validation.pred_severity_id.id] = validation
                
                for severity in severities:
                    # Check if severity has a bounding box
                    if hasattr(severity, 'bounding_box') and severity.bounding_box:
                        validation = validations.get(severity.id)
                        # Find the closest vertebra for this severity
                        for vertebra in vertebrae:
                            severity_predictions.append({
                                'vertebrae_level': severity.vertebrae_level,
                                'id': severity.id,
                                'severity_name': severity.severity_name,
                                'confidence': severity.confidence * 100,  # Convert to percentage
                                'bounding_box': {
                                    'x1': severity.bounding_box.x1,
                                    'y1': severity.bounding_box.y1,
                                    'x2': severity.bounding_box.x2,
                                    'y2': severity.bounding_box.y2,
                                },
                                'validation': {
                                    'id': validation.id if validation else None,
                                    'severity_name': validation.severity_name if validation else severity.severity_name,
                                    'is_correct': validation.is_correct if validation else True,
                                    'is_modified': validation.severity_name != severity.severity_name if validation else False,
                                    'validated_at': validation.validated_at if validation else None,
                                    'exists': validation is not None,  # Track if validation exists
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
        else:
            # No predictions for this exam
            context['no_predictions'] = True
            context['severity_predictions'] = []
            context['vertebrae_predictions'] = []
        
        # Add navigation to next/previous exams (always, regardless of predictions)
        self._add_navigation_context(context)
        
        # Add run status to context for template access control
        if hasattr(self, 'run_status') and self.run_status:
            context['run_status'] = self.run_status
        elif 'run' in context:
            context['run_status'] = context['run'].status
        
        return context
    
    def _add_navigation_context(self, context):
        """Add next/previous exam navigation to context - only within current run."""
        current_exam = self.object
        
        # Only add navigation if we have a run context
        if 'run' not in context:
            return
            
        current_run = context['run']
        
        # Get all exams for the current run, ordered by ID
        run_exams = current_run.exams.all().order_by('id')
        
        # Convert to list to enable indexing
        exam_list = list(run_exams)
        
        # Find current exam index in this run
        current_index = None
        for i, exam in enumerate(exam_list):
            if exam.id == current_exam.id:
                current_index = i
                break
        
        if current_index is not None:
            # Get previous exam in the run
            if current_index > 0:
                context['previous_exam'] = exam_list[current_index - 1]
            else:
                context['previous_exam'] = None
            
            # Get next exam in the run
            if current_index < len(exam_list) - 1:
                context['next_exam'] = exam_list[current_index + 1]
            else:
                context['next_exam'] = None
            
            # Add position information within the run
            context['exam_position'] = {
                'current': current_index + 1,
                'total': len(exam_list)
            }
            
            # Add position information
            context['exam_position'] = {
                'current': current_index + 1,
                'total': len(exam_list)
            }
        else:
            context['previous_exam'] = None
            context['next_exam'] = None
            context['exam_position'] = {'current': 1, 'total': 1}

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
    version = forms.ChoiceField(
        choices=[],
        initial='main',
        help_text='Select the dataset version from Hugging Face repository'
    )
    
    class Meta:
        model = Exam
        fields = ['external_id', 'image_path', 'version']
        widgets = {
            'external_id': forms.TextInput(attrs={'placeholder': 'e.g., EXAM-2025-001'}),
            'image_path': forms.TextInput(attrs={'placeholder': 'e.g., /path/to/image.png or https://example.com/image.png'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        try:
            # Get available versions from Hugging Face
            versions = Exam.get_available_versions()
            self.fields['version'].choices = [(v, v) for v in versions]
        except Exception:
            # Fallback to main if HF API fails
            self.fields['version'].choices = [('main', 'main')]


class ExamEditForm(forms.ModelForm):
    """Form for editing existing exams."""
    version = forms.ChoiceField(
        choices=[],
        help_text='Select the dataset version from Hugging Face repository'
    )
    
    class Meta:
        model = Exam
        fields = ['external_id', 'image_path', 'version']
        widgets = {
            'external_id': forms.TextInput(attrs={'placeholder': 'e.g., EXAM-2025-001'}),
            'image_path': forms.TextInput(attrs={'placeholder': 'e.g., /path/to/image.png or https://example.com/image.png'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        try:
            # Get available versions from Hugging Face
            versions = Exam.get_available_versions()
            self.fields['version'].choices = [(v, v) for v in versions]
        except Exception:
            # Fallback to main if HF API fails
            self.fields['version'].choices = [('main', 'main')]
        
        # Handle null version values - set to "main" if empty
        if self.instance and self.instance.pk:
            if not self.instance.version or self.instance.version.strip() == '':
                self.instance.version = 'main'
                self.initial['version'] = 'main'
    
    def clean_external_id(self):
        """Validate that external_id is unique, excluding current instance."""
        external_id = self.cleaned_data.get('external_id')
        if external_id:
            # Exclude current instance from uniqueness check
            qs = Exam.objects.filter(external_id=external_id)
            if self.instance and self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise forms.ValidationError("An exam with this External ID already exists.")
        return external_id
        
        if queryset.exists():
            raise forms.ValidationError("An exam with this external ID already exists.")
        
        return external_id


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


@method_decorator(staff_member_required, name='dispatch')
class AdminExamEditView(UpdateView):
    """Admin-only view for editing existing exams."""
    model = Exam
    form_class = ExamEditForm
    template_name = 'validation/admin_exam_edit.html'
    
    def form_valid(self, form):
        messages.success(self.request, f'Exam "{form.instance.external_id}" updated successfully!')
        return super().form_valid(form)
    
    def get_success_url(self):
        return reverse_lazy('validation:admin_exam_edit', kwargs={'pk': self.object.pk})
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['exam'] = self.object
        context['editing'] = True
        # Add runs associated with this exam for reference
        context['associated_runs'] = self.object.runs.all()
        return context

class RunAssignmentForm(forms.Form):
    """Form for assigning runs to users."""
    run = forms.ModelChoiceField(
        queryset=Run.objects.all(),
        empty_label="Select a run to assign...",
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    user = forms.ModelChoiceField(
        queryset=CustomUser.objects.filter(is_active=True),
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
        
        # Check if assignments are locked for this run
        if run.assignments_locked:
            messages.error(
                self.request, 
                f'Cannot assign "{run.name}" - assignments are locked to maintain '
                f'expert consistency for intra-operator reliability study. '
                f'This run is part of: {run.intra_operator_study_name or "a reliability study"}'
            )
            return super().form_invalid(form)
        
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
        context['total_users'] = CustomUser.objects.filter(is_active=True).count()
        context['users_with_assignments'] = CustomUser.objects.filter(run_assignments__isnull=False).distinct().count()

        return context

@method_decorator(staff_member_required, name='dispatch')
class AdminExamDeleteView(DeleteView):
    """Admin-only view for deleting exams."""
    model = Exam
    template_name = 'validation/admin_exam_delete.html'
    success_url = reverse_lazy('validation:exam_list')
    
    def delete(self, request, *args, **kwargs):
        """Override delete to add success message."""
        self.object = self.get_object()
        external_id = self.object.external_id
        success_url = self.get_success_url()
        
        # Check if exam has associated runs or predictions
        has_runs = self.object.runs.exists()
        
        if has_runs:
            messages.warning(
                request, 
                f'Warning: Exam "{external_id}" had associated runs and predictions that were also deleted.'
            )
        
        self.object.delete()
        messages.success(request, f'Exam "{external_id}" has been successfully deleted.')
        return HttpResponseRedirect(success_url)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Add information about what will be deleted
        context['associated_runs'] = self.object.runs.all()
        context['has_associations'] = self.object.runs.exists()
        return context


@method_decorator(staff_member_required, name='dispatch')
class AdminRunListView(ListView):
    """Admin-only view for managing all runs with lazy loading."""
    model = Run
    template_name = 'validation/admin_run_list.html'
    context_object_name = 'runs'
    paginate_by = 20
    
    def get_queryset(self):
        # Use minimal query - only get basic run data
        queryset = Run.objects.select_related().order_by('-run_date')
        
        # Filter by search query if provided
        search = self.request.GET.get('search')
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) |
                Q(description__icontains=search)
            )
        
        return queryset
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['search_query'] = self.request.GET.get('search', '')
        
        # Don't calculate statistics upfront - use lazy loading via AJAX
        context['lazy_loading'] = True
        
        return context


@method_decorator(staff_member_required, name='dispatch')
class AdminRunEditView(UpdateView):
    """Admin-only view for editing run details."""
    model = Run
    fields = ['name', 'description']
    template_name = 'validation/admin_run_edit.html'
    success_url = reverse_lazy('validation:admin_run_list')
    
    def form_valid(self, form):
        messages.success(self.request, f'Run "{form.instance.name}" updated successfully!')
        return super().form_valid(form)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Get run statistics
        run = self.object
        context['exam_count'] = run.exams.count()
        context['assignment_count'] = run.assignments.count()
        context['prediction_count'] = run.get_total_predictions()
        
        # Get assignments for this run
        context['assignments'] = run.assignments.select_related('user', 'assigned_by').all()
        
        return context


@method_decorator(staff_member_required, name='dispatch')
class AdminRunDeleteView(DeleteView):
    """Admin-only view for deleting runs."""
    model = Run
    template_name = 'validation/admin_run_delete.html'
    success_url = reverse_lazy('validation:admin_run_list')
    
    def delete(self, request, *args, **kwargs):
        """Override delete to add success message."""
        self.object = self.get_object()
        run_name = self.object.name
        success_url = self.get_success_url()
        
        # Check if run has assignments or predictions
        has_assignments = self.object.assignments.exists()
        has_predictions = self.object.get_total_predictions() > 0
        
        if has_assignments or has_predictions:
            messages.warning(
                request,
                f'Run "{run_name}" has been deleted, including {self.object.assignments.count()} assignment(s) '
                f'and {self.object.get_total_predictions()} prediction(s).'
            )
        else:
            messages.success(request, f'Run "{run_name}" deleted successfully!')
        
        self.object.delete()
        return HttpResponseRedirect(success_url)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Get run details for confirmation
        run = self.object
        context['exam_count'] = run.exams.count()
        context['assignment_count'] = run.assignments.count()
        context['prediction_count'] = run.get_total_predictions()
        context['assignments'] = run.assignments.select_related('user').all()
        
        return context


@method_decorator(staff_member_required, name='dispatch')
class AdminRunAssignView(FormView):
    """Admin-only view for assigning a specific run to users."""
    form_class = RunAssignmentForm
    template_name = 'validation/admin_run_assign.html'
    
    def get_success_url(self):
        return reverse_lazy('validation:admin_run_list')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Get the run from URL parameter
        run_id = self.kwargs.get('pk')
        if run_id:
            try:
                context['run'] = Run.objects.get(pk=run_id)
                context['existing_assignments'] = context['run'].assignments.select_related('user', 'assigned_by').all()
            except Run.DoesNotExist:
                context['run'] = None
        
        return context
    
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        
        # Pre-populate run field if provided in URL
        run_id = self.kwargs.get('pk')
        if run_id:
            try:
                run = Run.objects.get(pk=run_id)
                if 'initial' not in kwargs:
                    kwargs['initial'] = {}
                kwargs['initial']['run'] = run
            except Run.DoesNotExist:
                pass
        
        return kwargs
    
    def form_valid(self, form):
        run = form.cleaned_data['run']
        user = form.cleaned_data['user']
        notes = form.cleaned_data['notes']
        
        # Check if assignments are locked for this run
        if run.assignments_locked:
            messages.error(
                self.request, 
                f'Cannot assign "{run.name}" - assignments are locked to maintain '
                f'expert consistency for intra-operator reliability study. '
                f'This run is part of: {run.intra_operator_study_name or "a reliability study"}'
            )
            return super().form_invalid(form)
        
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

def stream_exam_image(request, exam_id):
    """Stream exam image from Hugging Face dataset."""
    # Get the exam to verify access
    exam = get_object_or_404(Exam, id=exam_id)
    
    # Check if user has access to this exam
    if not request.user.is_superuser:
        has_assignment = RunAssignment.objects.filter(
            user=request.user,
            run__exams=exam
        ).exists()
        
        if not has_assignment:
            raise Http404("You don't have permission to view this exam image.")
    
    try:
        # Get Hugging Face token from environment
        hf_token = os.environ.get('HF_TOKEN')
        if not hf_token:
            return HttpResponse("Hugging Face token not configured", status=500)
        
        # Construct the file path in the dataset
        file_path = exam.image_path
        print("Attempting to download file:", file_path)
        # Download the image from Hugging Face
        repo_id = "sieben-ips/l3net"
        
        # Use hf_hub_download to get the file
        downloaded_file = hf_hub_download(
            repo_id=repo_id,
            filename=file_path,
            token=hf_token,
            repo_type="dataset",
            revision=exam.version or 'main' 
        )
        print("File downloaded successfully:", downloaded_file)
        # Read and stream the original image without modifications
        with open(downloaded_file, 'rb') as f:
            image_data = f.read()
        print("Image data read successfully, size:", len(image_data))
        
        response = HttpResponse(image_data, content_type='image/jpeg')
        response['Cache-Control'] = 'max-age=3600'  # Cache for 1 hour
        return response
        
    except Exception as e:
        # Log the error (you might want to use proper logging)
        print(f"Error streaming image for exam {exam_id}: {str(e)}")
        return HttpResponse("Image not found", status=404)

@csrf_exempt
@require_http_methods(["POST"])
def update_validation_severity(request):
    """API endpoint to update the severity of a validation."""
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Authentication required'}, status=401)
    
    try:
        data = json.loads(request.body)
        prediction_id = data.get('prediction_id')
        new_severity = data.get('severity')
        
        if not prediction_id or new_severity is None:
            return JsonResponse({'error': 'Invalid data'}, status=400)
        
        # Validate the new severity value
        if new_severity not in [severity.value for severity in Severity]:
            return JsonResponse({'error': 'Invalid severity value'}, status=400)
        
        # Get the prediction
        prediction = PredSeverity.objects.get(id=prediction_id)
        
        # Get or create validation for this prediction and user
        validation, created = Validation.objects.get_or_create(
            pred_severity_id=prediction,
            user_id=request.user,
            defaults={
                'severity_name': new_severity,  # Use the new severity as default
                'is_correct': (new_severity == prediction.severity_name),
            }
        )
        
        # If validation already existed, update it
        if not created:
            validation.severity_name = new_severity
            validation.is_correct = (new_severity == prediction.severity_name)
            validation.save()

        return JsonResponse({
            'message': 'Validation updated successfully',
            'is_modified': not validation.is_correct
        })
    except PredSeverity.DoesNotExist:
        return JsonResponse({'error': 'Prediction not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@csrf_exempt
@require_http_methods(["POST"])
def submit_all_validations(request):
    """API endpoint to submit all pending validations for a specific exam."""
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Authentication required'}, status=401)
    
    try:
        data = json.loads(request.body)
        run_id = data.get('run_id')
        exam_id = data.get('exam_id')
        
        if not run_id or not exam_id:
            return JsonResponse({'error': 'Run ID and Exam ID required'}, status=400)
        
        # Get all predictions for this specific exam and run
        predictions = PredSeverity.objects.filter(run_id_id=run_id, exam_id_id=exam_id)
        
        # Get existing validations for this user, exam, and run
        existing_validations = Validation.objects.filter(
            pred_severity_id__run_id_id=run_id,
            pred_severity_id__exam_id_id=exam_id,
            user_id=request.user
        )
        
        # Update validated_at timestamp for existing validations
        from django.utils import timezone
        validated_at = timezone.now()
        updated_count = existing_validations.update(validated_at=validated_at)
        
        # For predictions without validations, create them as "correct" (unchanged)
        existing_prediction_ids = set(existing_validations.values_list('pred_severity_id', flat=True))
        new_validations = []
        
        for prediction in predictions:
            if prediction.id not in existing_prediction_ids:
                new_validations.append(Validation(
                    pred_severity_id=prediction,
                    user_id=request.user,
                    severity_name=prediction.severity_name,
                    is_correct=True,
                    validated_at=validated_at
                ))
        
        if new_validations:
            Validation.objects.bulk_create(new_validations)
            updated_count += len(new_validations)

        return JsonResponse({
            'message': f'Successfully submitted {updated_count} validations for this exam',
            'count': updated_count
        })
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@csrf_exempt
@require_http_methods(["POST"])
@staff_member_required
def update_run_status(request):
    """API endpoint to update the status of a run."""
    try:
        data = json.loads(request.body)
        run_id = data.get('run_id')
        new_status = data.get('status')
        
        if not run_id or new_status is None:
            return JsonResponse({'error': 'Invalid data'}, status=400)
        
        # Validate the new status value
        from .enums.run_status import RunStatus
        if new_status not in [status.value for status in RunStatus]:
            return JsonResponse({'error': 'Invalid status value'}, status=400)
        
        # Update the run status
        run = Run.objects.get(id=run_id)
        run.status = new_status
        run.save()
        
        return JsonResponse({'message': 'Run status updated successfully'})
    except Run.DoesNotExist:
        return JsonResponse({'error': 'Run not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
def get_hf_versions(request):
    """API endpoint to get available Hugging Face dataset versions"""
    try:
        versions = Exam.get_available_versions()
        return JsonResponse({'versions': versions})
    except Exception as e:
        return JsonResponse({'error': 'Failed to fetch versions'}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
@staff_member_required
def create_exam_api(request):
    """API endpoint to create a new exam"""
    try:
        data = json.loads(request.body)
        
        # Use the serializer for validation
        from .serializers import ExamCreateSerializer
        serializer = ExamCreateSerializer(data=data)
        
        if serializer.is_valid():
            exam = serializer.save()
            
            return JsonResponse({
                'id': exam.id,
                'external_id': exam.external_id,
                'image_path': exam.image_path,
                'version': exam.version,
                'created_at': exam.created_at.isoformat(),
                'updated_at': exam.updated_at.isoformat()
            })
        else:
            return JsonResponse({'error': serializer.errors}, status=400)
            
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
def list_exams_api(request):
    """API endpoint to list exams"""
    try:
        exams = Exam.objects.all().order_by('-created_at')
        
        exam_list = []
        for exam in exams:
            exam_list.append({
                'id': exam.id,
                'external_id': exam.external_id,
                'image_path': exam.image_path,
                'version': exam.version,
                'created_at': exam.created_at.isoformat(),
                'updated_at': exam.updated_at.isoformat()
            })
        
        return JsonResponse({'exams': exam_list})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@method_decorator(staff_member_required, name='dispatch')
class AdminExamListView(ListView):
    """Admin-only view for managing all exams."""
    model = Exam
    template_name = 'validation/admin_exam_list.html'
    context_object_name = 'exams'
    paginate_by = 20
    
    def get_queryset(self):
        queryset = Exam.objects.prefetch_related(
            'runs'
        ).annotate(
            run_count=Count('runs', distinct=True)
        ).order_by('-created_at')
        
        # Filter by search query if provided
        search = self.request.GET.get('search')
        if search:
            queryset = queryset.filter(
                Q(external_id__icontains=search) |
                Q(image_path__icontains=search) |
                Q(version__icontains=search)
            )
        
        return queryset
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['search_query'] = self.request.GET.get('search', '')
        
        # Get statistics
        context['total_exams'] = Exam.objects.count()
        context['exams_with_runs'] = Exam.objects.filter(runs__isnull=False).distinct().count()
        context['exams_without_runs'] = Exam.objects.filter(runs__isnull=True).count()
        
        return context

# ============ AJAX ENDPOINTS FOR LAZY LOADING ============

@login_required
@require_http_methods(["GET"])
def get_run_statistics(request):
    """AJAX endpoint to get run statistics for the admin dashboard."""
    if not request.user.is_staff:
        return JsonResponse({'error': 'Admin access required'}, status=403)
    
    try:
        from django.core.cache import cache
        
        # Try to get from cache first (cache for 5 minutes)
        cache_key = 'run_statistics'
        stats = cache.get(cache_key)
        
        if stats is None:
            # Calculate statistics
            total_runs = Run.objects.count()
            assigned_runs = Run.objects.filter(assignments__isnull=False).distinct().count()
            unassigned_runs = Run.objects.filter(assignments__isnull=True).count()
            
            stats = {
                'total_runs': total_runs,
                'assigned_runs': assigned_runs,
                'unassigned_runs': unassigned_runs
            }
            
            # Cache for 5 minutes
            cache.set(cache_key, stats, 300)
        else:
            print("Cache hit for run statistics")
        
        return JsonResponse(stats)
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
@require_http_methods(["GET"])
def get_run_details(request, run_id):
    """AJAX endpoint to get detailed information for a specific run."""
    if not request.user.is_staff:
        return JsonResponse({'error': 'Admin access required'}, status=403)
    
    try:
        from django.core.cache import cache
        
        # Try to get from cache first (cache for 2 minutes)
        cache_key = f'run_details_{run_id}'
        details = cache.get(cache_key)
        
        if details is None:
            run = get_object_or_404(Run, id=run_id)
            
            # Get counts efficiently
            exam_count = run.exams.count()
            assignment_count = run.assignments.count()
            severity_count = PredSeverity.objects.filter(run_id=run).count()
            vertebra_count = PredVertebra.objects.filter(run_id=run).count()
            prediction_count = severity_count + vertebra_count
            
            details = {
                'exam_count': exam_count,
                'assignment_count': assignment_count,
                'prediction_count': prediction_count,
                'status': run.status
            }
            
            # Cache for 2 minutes
            cache.set(cache_key, details, 120)
        else:
            print(f"Cache hit for run details {run_id}")
        
        return JsonResponse(details)
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
@staff_member_required
def bulk_get_run_details(request):
    """AJAX endpoint to get details for multiple runs at once."""
    try:
        data = json.loads(request.body)
        run_ids = data.get('run_ids', [])
        
        if not run_ids:
            return JsonResponse({'error': 'No run IDs provided'}, status=400)
        
        # Limit to 50 runs at once to prevent performance issues
        if len(run_ids) > 50:
            return JsonResponse({'error': 'Too many run IDs (max 50)'}, status=400)
        
        from django.core.cache import cache
        
        results = {}
        uncached_runs = []
        
        # Check cache first
        for run_id in run_ids:
            cache_key = f'run_details_{run_id}'
            cached_details = cache.get(cache_key)
            if cached_details:
                results[str(run_id)] = cached_details
            else:
                uncached_runs.append(run_id)
        
        # Get uncached runs efficiently
        if uncached_runs:
            runs = Run.objects.filter(id__in=uncached_runs).prefetch_related(
                'exams', 'assignments'
            )
            
            # Get prediction counts efficiently
            severity_counts = PredSeverity.objects.filter(
                run_id__in=uncached_runs
            ).values('run_id').annotate(count=Count('id'))
            
            vertebra_counts = PredVertebra.objects.filter(
                run_id__in=uncached_runs
            ).values('run_id').annotate(count=Count('id'))
            
            # Create lookup dictionaries
            severity_lookup = {item['run_id']: item['count'] for item in severity_counts}
            vertebra_lookup = {item['run_id']: item['count'] for item in vertebra_counts}
            
            for run in runs:
                severity_count = severity_lookup.get(run.id, 0)
                vertebra_count = vertebra_lookup.get(run.id, 0)
                
                details = {
                    'exam_count': run.exams.count(),
                    'assignment_count': run.assignments.count(),
                    'prediction_count': severity_count + vertebra_count,
                    'status': run.status
                }
                
                # Cache for 2 minutes
                cache_key = f'run_details_{run.id}'
                cache.set(cache_key, details, 120)
                
                results[str(run.id)] = details
        
        return JsonResponse({'results': results})
        
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


# Analytics Views for Admin Dashboard
@staff_member_required
def analytics_dashboard(request):
    """Analytics dashboard for admins to view validation results and metrics."""
    from sklearn.metrics import cohen_kappa_score
    import csv
    from collections import defaultdict
    
    # Get all completed runs
    runs = Run.objects.filter(status='Completed').prefetch_related(
        'predicted_severities__validations__user_id',
        'assignments__user'
    )
    
    analytics_data = []
    
    for run in runs:
        run_data = {
            'run': run,
            'overall_accuracy': 0,
            'total_validations': 0,
            'expert_kappas': {},
            'overall_kappa': 0,
            'experts': set()
        }
        
        # Get all validations for this run
        validations = Validation.objects.filter(
            pred_severity_id__run_id=run,
            validated_at__isnull=False
        ).select_related('user_id', 'pred_severity_id')
        
        if validations.exists():
            # Calculate overall accuracy
            correct_validations = validations.filter(is_correct=True).count()
            total_validations = validations.count()
            run_data['overall_accuracy'] = (correct_validations / total_validations * 100) if total_validations > 0 else 0
            run_data['total_validations'] = total_validations
            
            # Group validations by expert
            expert_validations = defaultdict(list)
            for validation in validations:
                expert_validations[validation.user_id].append(validation)
                run_data['experts'].add(validation.user_id)
            
            # Calculate Cohen's Kappa for each expert pair
            print(f"Number of experts for run {run.name}: {len(expert_validations)}")
            print(f"Expert emails: {[expert.email for expert in expert_validations.keys()]}")
            
            if len(expert_validations) >= 2:
                experts = list(expert_validations.keys())
                
                # Calculate pairwise kappa for each expert against others
                for expert in experts:
                    expert_kappa_scores = []
                    
                    for other_expert in experts:
                        if other_expert != expert:
                            # Get common predictions between this pair of experts
                            expert_pred_ids = {v.pred_severity_id.id for v in expert_validations[expert]}
                            other_pred_ids = {v.pred_severity_id.id for v in expert_validations[other_expert]}
                            common_pred_ids = expert_pred_ids.intersection(other_pred_ids)
                            
                            if len(common_pred_ids) >= 2:  # Need at least 2 common predictions
                                # Get predictions for common prediction IDs
                                expert_vals = {v.pred_severity_id.id: v.severity_name or v.pred_severity_id.severity_name 
                                             for v in expert_validations[expert] if v.pred_severity_id.id in common_pred_ids}
                                other_vals = {v.pred_severity_id.id: v.severity_name or v.pred_severity_id.severity_name 
                                            for v in expert_validations[other_expert] if v.pred_severity_id.id in common_pred_ids}
                                
                                # Create aligned lists for the same predictions
                                expert_predictions = []
                                other_predictions = []
                                for pred_id in common_pred_ids:
                                    if pred_id in expert_vals and pred_id in other_vals:
                                        expert_predictions.append(expert_vals[pred_id])
                                        other_predictions.append(other_vals[pred_id])
                                
                                # Calculate Cohen's Kappa for this pair
                                if len(expert_predictions) >= 2:
                                    try:
                                        kappa = cohen_kappa_score(expert_predictions, other_predictions)
                                        expert_kappa_scores.append(kappa)
                                        print(f"Kappa between {expert.email} and {other_expert.email}: {kappa}")
                                        print(f"Expert 1 predictions: {expert_predictions}")
                                        print(f"Expert 2 predictions: {other_predictions}")
                                    except Exception as e:
                                        print(f"Error calculating kappa: {e}")
                    
                    # Average kappa scores for this expert
                    if expert_kappa_scores:
                        avg_kappa = sum(expert_kappa_scores) / len(expert_kappa_scores)
                        run_data['expert_kappas'][expert.email] = round(avg_kappa, 3)
                    else:
                        run_data['expert_kappas'][expert.email] = 'Insufficient data'
                
                # Calculate overall kappa (average of all pairwise kappas)
                if len(expert_validations) >= 2:
                    all_kappa_scores = []
                    
                    experts_list = list(expert_validations.keys())
                    for i in range(len(experts_list)):
                        for j in range(i + 1, len(experts_list)):
                            expert1, expert2 = experts_list[i], experts_list[j]
                            
                            expert1_pred_ids = {v.pred_severity_id.id for v in expert_validations[expert1]}
                            expert2_pred_ids = {v.pred_severity_id.id for v in expert_validations[expert2]}
                            common_pred_ids = expert1_pred_ids.intersection(expert2_pred_ids)
                            
                            if len(common_pred_ids) >= 2:
                                expert1_vals = {v.pred_severity_id.id: v.severity_name or v.pred_severity_id.severity_name 
                                              for v in expert_validations[expert1] if v.pred_severity_id.id in common_pred_ids}
                                expert2_vals = {v.pred_severity_id.id: v.severity_name or v.pred_severity_id.severity_name 
                                              for v in expert_validations[expert2] if v.pred_severity_id.id in common_pred_ids}
                                
                                # Create aligned prediction lists
                                pred1_list = []
                                pred2_list = []
                                for pred_id in common_pred_ids:
                                    if pred_id in expert1_vals and pred_id in expert2_vals:
                                        pred1_list.append(expert1_vals[pred_id])
                                        pred2_list.append(expert2_vals[pred_id])
                                
                                if len(pred1_list) >= 2:
                                    try:
                                        kappa = cohen_kappa_score(pred1_list, pred2_list)
                                        all_kappa_scores.append(kappa)
                                    except:
                                        pass
                    
                    if all_kappa_scores:
                        overall_kappa = sum(all_kappa_scores) / len(all_kappa_scores)
                        run_data['overall_kappa'] = round(overall_kappa, 3)
                    else:
                        run_data['overall_kappa'] = 'N/A'
            else:
                # Single expert - Cohen's Kappa requires at least 2 experts
                for expert in expert_validations.keys():
                    run_data['expert_kappas'][expert.email] = 'Single expert'
                run_data['overall_kappa'] = 'Single expert'
                print(f"Single expert detected: {list(expert_validations.keys())[0].email}")
        
        analytics_data.append(run_data)
    
    context = {
        'analytics_data': analytics_data,
        'total_runs': len(analytics_data)
    }
    
    return render(request, 'validation/analytics_dashboard.html', context)


@staff_member_required
def export_validation_results_csv(request, run_id=None):
    """Export validation results as CSV."""
    import csv
    from django.http import HttpResponse
    
    # Create the HttpResponse object with CSV header
    response = HttpResponse(content_type='text/csv')
    
    if run_id:
        run = get_object_or_404(Run, id=run_id)
        filename = f'validation_results_run_{run.id}_{run.name.replace(" ", "_")}.csv'
        
        # Filter validations for specific run
        validations = Validation.objects.filter(
            pred_severity_id__run_id=run,
            validated_at__isnull=False
        ).select_related(
            'user_id', 'pred_severity_id', 'pred_severity_id__exam_id'
        ).order_by('pred_severity_id__exam_id__external_id', 'pred_severity_id__vertebrae_level')
    else:
        filename = 'all_validation_results.csv'
        
        # Get all validations
        validations = Validation.objects.filter(
            validated_at__isnull=False
        ).select_related(
            'user_id', 'pred_severity_id', 'pred_severity_id__exam_id', 'pred_severity_id__run_id'
        ).order_by('pred_severity_id__run_id', 'pred_severity_id__exam_id__external_id', 'pred_severity_id__vertebrae_level')
    
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    writer = csv.writer(response)
    
    # Write CSV header
    headers = [
        'Run ID', 'Run Name', 'Exam ID', 'Exam External ID', 
        'Vertebrae Level', 'Original Prediction', 'Original Confidence',
        'Expert Email', 'Expert Validation', 'Is Correct', 
        'Validated At', 'Comment'
    ]
    writer.writerow(headers)
    
    # Write data rows
    for validation in validations:
        row = [
            validation.pred_severity_id.run_id.id,
            validation.pred_severity_id.run_id.name,
            validation.pred_severity_id.exam_id.id,
            validation.pred_severity_id.exam_id.external_id,
            validation.pred_severity_id.vertebrae_level,
            validation.pred_severity_id.severity_name,
            validation.pred_severity_id.confidence,
            validation.user_id.email,
            validation.severity_name or validation.pred_severity_id.severity_name,
            'Yes' if validation.is_correct else 'No',
            validation.validated_at.strftime('%Y-%m-%d %H:%M:%S') if validation.validated_at else '',
            validation.comment or ''
        ]
        writer.writerow(row)
    
    return response


@staff_member_required
def run_analytics_detail(request, run_id):
    """Detailed analytics view for a specific run."""
    from sklearn.metrics import cohen_kappa_score, confusion_matrix
    from collections import defaultdict, Counter
    import json
    
    run = get_object_or_404(Run, id=run_id)
    
    # Get all validations for this run
    validations = Validation.objects.filter(
        pred_severity_id__run_id=run,
        validated_at__isnull=False
    ).select_related('user_id', 'pred_severity_id', 'pred_severity_id__exam_id')
    
    if not validations.exists():
        messages.warning(request, f'No validation data found for run "{run.name}".')
        return redirect('validation:analytics_dashboard')
    
    # Calculate detailed metrics
    analytics = {
        'run': run,
        'total_validations': validations.count(),
        'experts': {},
        'overall_metrics': {},
        'confusion_matrix': {},
        'severity_breakdown': {}
    }
    
    # Group by expert
    expert_validations = defaultdict(list)
    for validation in validations:
        expert_validations[validation.user_id].append(validation)
    
    # Calculate metrics for each expert
    for expert, expert_vals in expert_validations.items():
        expert_stats = {
            'total_validations': len(expert_vals),
            'correct_validations': sum(1 for v in expert_vals if v.is_correct),
            'accuracy': 0,
            'severity_counts': Counter(),
            'agreement_with_others': {}
        }
        
        # Calculate accuracy
        if expert_stats['total_validations'] > 0:
            expert_stats['accuracy'] = (expert_stats['correct_validations'] / expert_stats['total_validations']) * 100
        
        # Count severity classifications
        for val in expert_vals:
            severity = val.severity_name or val.pred_severity_id.severity_name
            expert_stats['severity_counts'][severity] += 1
        
        # Convert Counter to dict for template compatibility
        expert_stats['severity_counts'] = dict(expert_stats['severity_counts'])
        
        analytics['experts'][expert.email] = expert_stats
    
    # Calculate inter-rater agreement (Cohen's Kappa)
    if len(expert_validations) >= 2:
        experts = list(expert_validations.keys())
        kappa_matrix = {}
        
        for i, expert1 in enumerate(experts):
            kappa_matrix[expert1.email] = {}
            for j, expert2 in enumerate(experts):
                if i != j:
                    # Find common predictions
                    expert1_pred_ids = {v.pred_severity_id.id for v in expert_validations[expert1]}
                    expert2_pred_ids = {v.pred_severity_id.id for v in expert_validations[expert2]}
                    common_pred_ids = expert1_pred_ids.intersection(expert2_pred_ids)
                    
                    if len(common_pred_ids) >= 5:
                        expert1_vals = {v.pred_severity_id.id: v.severity_name or v.pred_severity_id.severity_name 
                                      for v in expert_validations[expert1] if v.pred_severity_id.id in common_pred_ids}
                        expert2_vals = {v.pred_severity_id.id: v.severity_name or v.pred_severity_id.severity_name 
                                      for v in expert_validations[expert2] if v.pred_severity_id.id in common_pred_ids}
                        
                        pred1_list = [expert1_vals[pid] for pid in common_pred_ids if pid in expert1_vals]
                        pred2_list = [expert2_vals[pid] for pid in common_pred_ids if pid in expert2_vals]
                        
                        if len(pred1_list) >= 5 and len(pred1_list) == len(pred2_list):
                            try:
                                kappa = cohen_kappa_score(pred1_list, pred2_list)
                                kappa_matrix[expert1.email][expert2.email] = round(kappa, 3)
                            except:
                                kappa_matrix[expert1.email][expert2.email] = 'N/A'
                        else:
                            kappa_matrix[expert1.email][expert2.email] = 'Insufficient data'
                    else:
                        kappa_matrix[expert1.email][expert2.email] = 'Insufficient data'
                else:
                    kappa_matrix[expert1.email][expert2.email] = 1.0  # Perfect agreement with self
        
        analytics['kappa_matrix'] = kappa_matrix
    
    # Overall severity breakdown
    all_severities = Counter()
    original_severities = Counter()
    
    for validation in validations:
        validated_severity = validation.severity_name or validation.pred_severity_id.severity_name
        all_severities[validated_severity] += 1
        original_severities[validation.pred_severity_id.severity_name] += 1
    
    analytics['severity_breakdown'] = {
        'validated': dict(all_severities),
        'original': dict(original_severities)
    }
    
    # Overall accuracy
    correct_count = validations.filter(is_correct=True).count()
    analytics['overall_accuracy'] = (correct_count / analytics['total_validations']) * 100 if analytics['total_validations'] > 0 else 0
    
    context = {
        'analytics': analytics,
        'severity_choices': [choice[0] for choice in Severity.choices],
        'severity_breakdown_json': json.dumps(analytics['severity_breakdown'])
    }
    
    return render(request, 'validation/run_analytics_detail.html', context)


@staff_member_required
def duplicate_run_for_intra_operator(request, run_id):
    """
    Safely duplicate a run for intra-operator reliability studies.
    Creates a complete copy with new prediction IDs but same data.
    """
    original_run = get_object_or_404(Run, id=run_id)
    
    if request.method == 'POST':
        try:
            # Get study name from form
            study_name = request.POST.get('study_name', f"Intra-operator study for {original_run.name}")
            round_number = request.POST.get('round_number', '2')
            
            # Create the duplicate run
            duplicate_run = Run.objects.create(
                name=f"{original_run.name} - Round {round_number}",
                description=f"Intra-operator reliability round {round_number} for: {original_run.description or original_run.name}",
                status=RunStatus.OPEN,
                original_run=original_run,
                study_type=f'intra_operator_round_{round_number}',
                intra_operator_study_name=study_name,
                assignments_locked=True  # Lock assignments to prevent changes
            )
            
            # Update original run to mark it as part of a study if not already
            if not original_run.intra_operator_study_name:
                original_run.study_type = 'original'
                original_run.intra_operator_study_name = study_name
                original_run.save()
            
            # Copy all exam relationships
            duplicate_run.exams.set(original_run.exams.all())
            
            # Copy all assignments to maintain expert consistency for intra-operator analysis
            from validation.models import RunAssignment
            original_assignments = RunAssignment.objects.filter(run=original_run)
            
            for assignment in original_assignments:
                RunAssignment.objects.create(
                    run=duplicate_run,
                    user=assignment.user,
                    assigned_by=request.user,  # Current admin who created the duplicate
                    notes=f"Auto-assigned from original run {original_run.id} for intra-operator reliability study. "
                          f"Original assignment: {assignment.notes or 'No notes'}"
                )
            
            # Duplicate all predicted severities with new IDs
            for pred_severity in original_run.predicted_severities.all():
                # Create new prediction with same data but new ID
                new_pred = PredSeverity.objects.create(
                    severity_name=pred_severity.severity_name,
                    confidence=pred_severity.confidence,
                    vertebrae_level=pred_severity.vertebrae_level,
                    run_id=duplicate_run,
                    exam_id=pred_severity.exam_id,
                    model_version=pred_severity.model_version,
                    bounding_box=pred_severity.bounding_box
                )
            
            # Copy predicted vertebrae if they exist
            for pred_vertebra in original_run.predicted_vertebrae.all():
                PredVertebra.objects.create(
                    name=pred_vertebra.name,  # Fixed: was vertebra_name
                    confidence=pred_vertebra.confidence,
                    run_id=duplicate_run,
                    exam_id=pred_vertebra.exam_id,
                    model_version=pred_vertebra.model_version,
                    polygon=pred_vertebra.polygon  # Fixed: was bounding_box
                )
            
            messages.success(
                request, 
                f'Successfully created duplicate run "{duplicate_run.name}" for intra-operator reliability study. '
                f'Original data remains completely untouched. New run has {duplicate_run.get_total_predictions()} predictions ready for validation.'
            )
            
            return redirect('validation:admin_run_list')
            
        except Exception as e:
            messages.error(request, f'Error creating duplicate run: {str(e)}')
            return redirect('validation:admin_run_list')
    
    # GET request - show confirmation form
    context = {
        'original_run': original_run,
        'prediction_count': original_run.get_total_predictions(),
        'exam_count': original_run.get_exam_count(),
    }
    
    return render(request, 'validation/duplicate_run_form.html', context)


@staff_member_required 
def intra_operator_analytics(request, run_id):
    """
    Show intra-operator analytics comparing validation rounds by the same expert.
    """
    original_run = get_object_or_404(Run, id=run_id)
    
    # Get all related runs for this intra-operator study
    related_runs = original_run.get_related_runs()
    
    if len(related_runs) < 2:
        messages.info(request, 'This run has no duplicates for intra-operator analysis.')
        return redirect('validation:run_analytics_detail', run_id=run_id)
    
    # Calculate intra-operator agreement for each expert
    intra_operator_data = []
    
    for expert in CustomUser.objects.filter(validations__pred_severity_id__run_id__in=related_runs).distinct():
        expert_data = {
            'expert': expert,
            'rounds': [],
            'kappa_scores': []
        }
        
        # Get validations for each round
        for run in related_runs:
            validations = Validation.objects.filter(
                pred_severity_id__run_id=run,
                user_id=expert
            ).select_related('pred_severity_id')
            
            if validations.exists():
                expert_data['rounds'].append({
                    'run': run,
                    'validation_count': validations.count(),
                    'validations': validations
                })
        
        # Calculate Cohen's Kappa between rounds for this expert
        if len(expert_data['rounds']) >= 2:
            from sklearn.metrics import cohen_kappa_score
            
            # Compare each pair of rounds
            for i in range(len(expert_data['rounds'])):
                for j in range(i + 1, len(expert_data['rounds'])):
                    round1 = expert_data['rounds'][i]
                    round2 = expert_data['rounds'][j]
                    
                    # Get common predictions (same vertebrae level and exam)
                    round1_vals = {}
                    round2_vals = {}
                    
                    for val in round1['validations']:
                        key = (val.pred_severity_id.exam_id.id, val.pred_severity_id.vertebrae_level)
                        round1_vals[key] = val.severity_name or val.pred_severity_id.severity_name
                    
                    for val in round2['validations']:
                        key = (val.pred_severity_id.exam_id.id, val.pred_severity_id.vertebrae_level)
                        round2_vals[key] = val.severity_name or val.pred_severity_id.severity_name
                    
                    # Find common predictions
                    common_keys = set(round1_vals.keys()).intersection(set(round2_vals.keys()))
                    
                    if len(common_keys) >= 2:
                        pred1_list = [round1_vals[key] for key in common_keys]
                        pred2_list = [round2_vals[key] for key in common_keys]
                        
                        try:
                            kappa = cohen_kappa_score(pred1_list, pred2_list)
                            expert_data['kappa_scores'].append({
                                'round1': round1['run'].name,
                                'round2': round2['run'].name,
                                'kappa': round(kappa, 3),
                                'common_predictions': len(common_keys)
                            })
                        except:
                            pass
        
        if expert_data['rounds']:
            intra_operator_data.append(expert_data)
    
    context = {
        'original_run': original_run,
        'related_runs': related_runs,
        'intra_operator_data': intra_operator_data,
        'study_name': original_run.intra_operator_study_name,
    }
    
    return render(request, 'validation/intra_operator_analytics.html', context)


@staff_member_required
def comprehensive_run_analytics(request, run_id):
    """
    Comprehensive analytics showing both inter-operator and intra-operator metrics for a run.
    """
    original_run = get_object_or_404(Run, id=run_id)
    
    # Get all related runs for this study (original + duplicates)
    related_runs = original_run.get_related_runs()
    
    # Get all experts who validated any run in this study
    all_experts = CustomUser.objects.filter(
        validations__pred_severity_id__run_id__in=related_runs
    ).distinct()
    
    # Inter-operator analysis (between different experts on same run)
    inter_operator_data = {}
    for run in related_runs:
        run_validations = Validation.objects.filter(
            pred_severity_id__run_id=run
        ).select_related('user_id', 'pred_severity_id')
        
        # Group by expert
        expert_validations = defaultdict(list)
        for validation in run_validations:
            expert_validations[validation.user_id].append(validation)
        
        # Calculate inter-operator kappa for this run
        if len(expert_validations) >= 2:
            from sklearn.metrics import cohen_kappa_score
            experts_list = list(expert_validations.keys())
            run_kappa_scores = []
            
            for i in range(len(experts_list)):
                for j in range(i + 1, len(experts_list)):
                    expert1, expert2 = experts_list[i], experts_list[j]
                    
                    # Get common predictions
                    expert1_pred_ids = {v.pred_severity_id.id for v in expert_validations[expert1]}
                    expert2_pred_ids = {v.pred_severity_id.id for v in expert_validations[expert2]}
                    common_pred_ids = expert1_pred_ids.intersection(expert2_pred_ids)
                    
                    if len(common_pred_ids) >= 2:
                        expert1_vals = {v.pred_severity_id.id: v.severity_name or v.pred_severity_id.severity_name 
                                      for v in expert_validations[expert1] if v.pred_severity_id.id in common_pred_ids}
                        expert2_vals = {v.pred_severity_id.id: v.severity_name or v.pred_severity_id.severity_name 
                                      for v in expert_validations[expert2] if v.pred_severity_id.id in common_pred_ids}
                        
                        pred1_list = []
                        pred2_list = []
                        for pred_id in common_pred_ids:
                            if pred_id in expert1_vals and pred_id in expert2_vals:
                                pred1_list.append(expert1_vals[pred_id])
                                pred2_list.append(expert2_vals[pred_id])
                        
                        if len(pred1_list) >= 2:
                            try:
                                kappa = cohen_kappa_score(pred1_list, pred2_list)
                                run_kappa_scores.append({
                                    'expert1': expert1.email,
                                    'expert2': expert2.email,
                                    'kappa': round(kappa, 3),
                                    'common_predictions': len(pred1_list)
                                })
                            except:
                                pass
            
            inter_operator_data[run.id] = {
                'run': run,
                'expert_count': len(expert_validations),
                'kappa_scores': run_kappa_scores,
                'average_kappa': round(sum(score['kappa'] for score in run_kappa_scores) / len(run_kappa_scores), 3) if run_kappa_scores else None
            }
        else:
            inter_operator_data[run.id] = {
                'run': run,
                'expert_count': len(expert_validations),
                'kappa_scores': [],
                'average_kappa': 'Single expert' if len(expert_validations) == 1 else 'No data'
            }
    
    # Intra-operator analysis (same expert across different runs)
    intra_operator_data = []
    if len(related_runs) >= 2:
        from sklearn.metrics import cohen_kappa_score
        
        for expert in all_experts:
            expert_data = {
                'expert': expert,
                'rounds': [],
                'kappa_scores': []
            }
            
            # Get validations for each round for this expert
            for run in related_runs:
                validations = Validation.objects.filter(
                    pred_severity_id__run_id=run,
                    user_id=expert
                ).select_related('pred_severity_id')
                
                if validations.exists():
                    expert_data['rounds'].append({
                        'run': run,
                        'validation_count': validations.count(),
                        'validations': validations
                    })
            
            # Calculate intra-operator kappa between rounds
            if len(expert_data['rounds']) >= 2:
                for i in range(len(expert_data['rounds'])):
                    for j in range(i + 1, len(expert_data['rounds'])):
                        round1 = expert_data['rounds'][i]
                        round2 = expert_data['rounds'][j]
                        
                        # Get common predictions (same vertebrae level and exam)
                        round1_vals = {}
                        round2_vals = {}
                        
                        for val in round1['validations']:
                            key = (val.pred_severity_id.exam_id.id, val.pred_severity_id.vertebrae_level)
                            round1_vals[key] = val.severity_name or val.pred_severity_id.severity_name
                        
                        for val in round2['validations']:
                            key = (val.pred_severity_id.exam_id.id, val.pred_severity_id.vertebrae_level)
                            round2_vals[key] = val.severity_name or val.pred_severity_id.severity_name
                        
                        # Find common predictions
                        common_keys = set(round1_vals.keys()).intersection(set(round2_vals.keys()))
                        
                        if len(common_keys) >= 2:
                            pred1_list = [round1_vals[key] for key in common_keys]
                            pred2_list = [round2_vals[key] for key in common_keys]
                            
                            try:
                                kappa = cohen_kappa_score(pred1_list, pred2_list)
                                expert_data['kappa_scores'].append({
                                    'round1': round1['run'].name,
                                    'round2': round2['run'].name,
                                    'kappa': round(kappa, 3),
                                    'common_predictions': len(common_keys)
                                })
                            except:
                                pass
            
            if expert_data['rounds']:
                intra_operator_data.append(expert_data)
    
    # Calculate overall study metrics
    study_metrics = {
        'total_runs': len(related_runs),
        'total_experts': len(all_experts),
        'has_inter_operator': any(data['kappa_scores'] for data in inter_operator_data.values()),
        'has_intra_operator': any(expert_data['kappa_scores'] for expert_data in intra_operator_data),
        'study_name': original_run.intra_operator_study_name or f"Study for {original_run.name}"
    }
    
    context = {
        'original_run': original_run,
        'related_runs': related_runs,
        'inter_operator_data': inter_operator_data,
        'intra_operator_data': intra_operator_data,
        'study_metrics': study_metrics,
        'all_experts': all_experts,
    }
    
    return render(request, 'validation/comprehensive_analytics.html', context)


@staff_member_required
def export_comprehensive_analytics_csv(request, run_id):
    """
    Export comprehensive analytics including both inter-operator and intra-operator metrics.
    """
    original_run = get_object_or_404(Run, id=run_id)
    related_runs = original_run.get_related_runs()
    
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="comprehensive_analytics_run_{run_id}_{original_run.name.replace(" ", "_")}_{timezone.now().strftime("%Y-%m-%d_%H_%M_%S")}.csv"'
    
    import csv
    writer = csv.writer(response)
    
    # Write header information
    writer.writerow(['Comprehensive Analytics Report'])
    writer.writerow(['Study Name', original_run.intra_operator_study_name or f"Study for {original_run.name}"])
    writer.writerow(['Original Run', original_run.name])
    writer.writerow(['Export Date', timezone.now().strftime('%Y-%m-%d %H:%M:%S')])
    writer.writerow(['Total Runs', len(related_runs)])
    writer.writerow([])
    
    # Inter-operator metrics section
    writer.writerow(['INTER-OPERATOR RELIABILITY (Between Different Experts)'])
    writer.writerow(['Run ID', 'Run Name', 'Expert 1', 'Expert 2', 'Cohen\'s Kappa', 'Common Predictions', 'Agreement Level'])
    
    for run in related_runs:
        run_validations = Validation.objects.filter(
            pred_severity_id__run_id=run
        ).select_related('user_id', 'pred_severity_id')
        
        expert_validations = defaultdict(list)
        for validation in run_validations:
            expert_validations[validation.user_id].append(validation)
        
        if len(expert_validations) >= 2:
            from sklearn.metrics import cohen_kappa_score
            experts_list = list(expert_validations.keys())
            
            for i in range(len(experts_list)):
                for j in range(i + 1, len(experts_list)):
                    expert1, expert2 = experts_list[i], experts_list[j]
                    
                    expert1_pred_ids = {v.pred_severity_id.id for v in expert_validations[expert1]}
                    expert2_pred_ids = {v.pred_severity_id.id for v in expert_validations[expert2]}
                    common_pred_ids = expert1_pred_ids.intersection(expert2_pred_ids)
                    
                    if len(common_pred_ids) >= 2:
                        expert1_vals = {v.pred_severity_id.id: v.severity_name or v.pred_severity_id.severity_name 
                                      for v in expert_validations[expert1] if v.pred_severity_id.id in common_pred_ids}
                        expert2_vals = {v.pred_severity_id.id: v.severity_name or v.pred_severity_id.severity_name 
                                      for v in expert_validations[expert2] if v.pred_severity_id.id in common_pred_ids}
                        
                        pred1_list = []
                        pred2_list = []
                        for pred_id in common_pred_ids:
                            if pred_id in expert1_vals and pred_id in expert2_vals:
                                pred1_list.append(expert1_vals[pred_id])
                                pred2_list.append(expert2_vals[pred_id])
                        
                        if len(pred1_list) >= 2:
                            try:
                                kappa = cohen_kappa_score(pred1_list, pred2_list)
                                
                                # Determine agreement level
                                if kappa >= 0.8:
                                    level = 'Excellent'
                                elif kappa >= 0.6:
                                    level = 'Good'
                                elif kappa >= 0.4:
                                    level = 'Moderate'
                                elif kappa >= 0.2:
                                    level = 'Fair'
                                else:
                                    level = 'Poor'
                                
                                writer.writerow([
                                    run.id,
                                    run.name,
                                    expert1.email,
                                    expert2.email,
                                    round(kappa, 3),
                                    len(pred1_list),
                                    level
                                ])
                            except:
                                pass
        elif len(expert_validations) == 1:
            expert = list(expert_validations.keys())[0]
            writer.writerow([
                run.id,
                run.name,
                expert.email,
                '-',
                'Single expert',
                '-',
                'N/A'
            ])
    
    writer.writerow([])
    
    # Intra-operator metrics section
    writer.writerow(['INTRA-OPERATOR RELIABILITY (Same Expert Across Time)'])
    writer.writerow(['Expert', 'Round 1', 'Round 2', 'Cohen\'s Kappa', 'Common Predictions', 'Agreement Level'])
    
    if len(related_runs) >= 2:
        all_experts = CustomUser.objects.filter(
            validations__pred_severity_id__run_id__in=related_runs
        ).distinct()
        
        for expert in all_experts:
            expert_rounds = []
            
            for run in related_runs:
                validations = Validation.objects.filter(
                    pred_severity_id__run_id=run,
                    user_id=expert
                ).select_related('pred_severity_id')
                
                if validations.exists():
                    expert_rounds.append({
                        'run': run,
                        'validations': validations
                    })
            
            if len(expert_rounds) >= 2:
                from sklearn.metrics import cohen_kappa_score
                
                for i in range(len(expert_rounds)):
                    for j in range(i + 1, len(expert_rounds)):
                        round1 = expert_rounds[i]
                        round2 = expert_rounds[j]
                        
                        round1_vals = {}
                        round2_vals = {}
                        
                        for val in round1['validations']:
                            key = (val.pred_severity_id.exam_id.id, val.pred_severity_id.vertebrae_level)
                            round1_vals[key] = val.severity_name or val.pred_severity_id.severity_name
                        
                        for val in round2['validations']:
                            key = (val.pred_severity_id.exam_id.id, val.pred_severity_id.vertebrae_level)
                            round2_vals[key] = val.severity_name or val.pred_severity_id.severity_name
                        
                        common_keys = set(round1_vals.keys()).intersection(set(round2_vals.keys()))
                        
                        if len(common_keys) >= 2:
                            pred1_list = [round1_vals[key] for key in common_keys]
                            pred2_list = [round2_vals[key] for key in common_keys]
                            
                            try:
                                kappa = cohen_kappa_score(pred1_list, pred2_list)
                                
                                if kappa >= 0.8:
                                    level = 'Excellent'
                                elif kappa >= 0.6:
                                    level = 'Good'
                                elif kappa >= 0.4:
                                    level = 'Moderate'
                                elif kappa >= 0.2:
                                    level = 'Fair'
                                else:
                                    level = 'Poor'
                                
                                writer.writerow([
                                    expert.email,
                                    round1['run'].name,
                                    round2['run'].name,
                                    round(kappa, 3),
                                    len(common_keys),
                                    level
                                ])
                            except:
                                pass
    
    return response


