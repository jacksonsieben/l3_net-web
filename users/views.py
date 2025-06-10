from django.shortcuts import render, redirect
from django.contrib.auth import login, authenticate
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django import forms
from django.contrib import messages
from django.views import View
from django.urls import reverse_lazy
from django.contrib.auth.views import LoginView
from django.contrib.auth.decorators import login_required, user_passes_test
from django.utils.decorators import method_decorator
from django.http import Http404

User = get_user_model()

# Optional: Custom Registration Form using email instead of username
class CustomUserCreationForm(UserCreationForm):
    full_name = forms.CharField(max_length=255, required=True, help_text='Your full name')
    
    class Meta:
        model = User
        fields = ['email', 'full_name']  # Including the full_name field

def is_superuser(user):
    """Check if user is superuser"""
    return user.is_superuser

@method_decorator(login_required, name='dispatch')
@method_decorator(user_passes_test(is_superuser), name='dispatch')
class RegisterView(View):
    template_name = 'users/register.html'
    form_class = CustomUserCreationForm

    def get(self, request, *args, **kwargs):
        form = self.form_class()
        return render(request, self.template_name, {'form': form})
    
    def post(self, request, *args, **kwargs):
        form = self.form_class(request.POST)
        if form.is_valid():
            user = form.save()
            # Don't automatically log in the created user since admin is creating it
            messages.success(request, f"Account for {user.email} created successfully!")
            return redirect('users:register')  # Stay on registration page for creating more users
        else:
            # Clear any existing messages to avoid duplicates
            storage = messages.get_messages(request)
            storage.used = True
            
            # Add error messages for each field
            for field, error_list in form.errors.items():
                for error in error_list:
                    if field == '__all__':
                        messages.error(request, f"{error}")
                    else:
                        messages.error(request, f"{form.fields[field].label}: {error}")
        
        # Return to the form with errors as messages
        return render(request, self.template_name, {'form': form})

# Use class-based view for consistency with login
register = RegisterView.as_view()

class CustomLoginView(LoginView):
    template_name = 'users/login.html'
    success_url = '/'  # Redirect to home page after successful login
    redirect_authenticated_user = True
    
    def get_success_url(self):
        """Override to return the home page URL."""
        return '/'  # Redirect to the root URL (home page)
    
    def form_invalid(self, form):
        """If the form is invalid, render the invalid form with toast notifications."""
        # Add error messages for each field
        for field, error_list in form.errors.items():
            for error in error_list:
                if field == '__all__':
                    messages.error(self.request, f"{error}")
                else:
                    messages.error(self.request, f"{form.fields[field].label}: {error}")
        
        # Handle non-field errors (like invalid login credentials)
        for error in form.non_field_errors():
            messages.error(self.request, f"{error}")
        
        return self.render_to_response(self.get_context_data(form=form))
