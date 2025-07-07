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
    class Meta:
        model = Exam
        fields = ['external_id', 'image_path']
        widgets = {
            'external_id': forms.TextInput(attrs={'placeholder': 'e.g., EXAM-2025-001'}),
            'image_path': forms.TextInput(attrs={'placeholder': 'e.g., /path/to/image.png or https://example.com/image.png'}),
        }


class ExamEditForm(forms.ModelForm):
    """Form for editing existing exams."""
    class Meta:
        model = Exam
        fields = ['external_id', 'image_path']
        widgets = {
            'external_id': forms.TextInput(attrs={'placeholder': 'e.g., EXAM-2025-001'}),
            'image_path': forms.TextInput(attrs={'placeholder': 'e.g., /path/to/image.png or https://example.com/image.png'}),
        }
    
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
    """Admin-only view for managing all runs."""
    model = Run
    template_name = 'validation/admin_run_list.html'
    context_object_name = 'runs'
    paginate_by = 20
    
    def get_queryset(self):
        queryset = Run.objects.prefetch_related(
            'exams',
            'assignments__user',
            'predicted_severities',
            'predicted_vertebrae'
        ).annotate(
            exam_count=Count('exams', distinct=True),
            assignment_count=Count('assignments', distinct=True),
            prediction_count=Count('predicted_severities', distinct=True) + Count('predicted_vertebrae', distinct=True)
        ).order_by('-run_date')
        
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
        
        # Get statistics
        context['total_runs'] = Run.objects.count()
        context['assigned_runs'] = Run.objects.filter(assignments__isnull=False).distinct().count()
        context['unassigned_runs'] = Run.objects.filter(assignments__isnull=True).count()
        
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

def stream_exam_image(request, exam_id, run_id):
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
        file_path = f"validation/{exam.external_id}.jpg"
        print("Attempting to download file:", file_path)
        # Download the image from Hugging Face
        repo_id = "sieben-ips/l3net"
        
        # Use hf_hub_download to get the file
        downloaded_file = hf_hub_download(
            repo_id=repo_id,
            filename=file_path,
            token=hf_token,
            repo_type="dataset",
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


