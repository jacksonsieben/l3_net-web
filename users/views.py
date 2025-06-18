from django.shortcuts import render, redirect
from django.contrib.auth import login, authenticate
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm, PasswordChangeForm
from django import forms
from django.contrib import messages
from django.views import View
from django.urls import reverse_lazy
from django.contrib.auth.views import LoginView
from django.contrib.auth.decorators import login_required, user_passes_test
from django.utils.decorators import method_decorator
from django.http import Http404
from django.contrib.auth import update_session_auth_hash

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

# Custom Change Password Form
class CustomPasswordChangeForm(PasswordChangeForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['old_password'].widget.attrs.update({
            'class': 'w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-blue-500 focus:border-blue-500',
            'placeholder': 'Enter current password'
        })
        self.fields['new_password1'].widget.attrs.update({
            'class': 'w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-blue-500 focus:border-blue-500',
            'placeholder': 'Enter new password'
        })
        self.fields['new_password2'].widget.attrs.update({
            'class': 'w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-blue-500 focus:border-blue-500',
            'placeholder': 'Confirm new password'
        })

@method_decorator(login_required, name='dispatch')
class PasswordChangeView(View):
    template_name = 'users/change_password.html'
    form_class = CustomPasswordChangeForm
    success_url = reverse_lazy('users:password_change_done')

    def get(self, request, *args, **kwargs):
        form = self.form_class(user=request.user)
        return render(request, self.template_name, {'form': form})
    
    def post(self, request, *args, **kwargs):
        form = self.form_class(request.user, request.POST)
        if form.is_valid():
            user = form.save()
            # Update the session with the new password hash
            update_session_auth_hash(request, user)
            messages.success(request, "Password changed successfully!")
            return redirect(self.success_url)
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
        
        return render(request, self.template_name, {'form': form})

@method_decorator(login_required, name='dispatch')
class ChangePasswordView(View):
    template_name = 'users/change_password.html'
    form_class = CustomPasswordChangeForm

    def get(self, request, *args, **kwargs):
        form = self.form_class(user=request.user)
        return render(request, self.template_name, {'form': form})
    
    def post(self, request, *args, **kwargs):
        form = self.form_class(user=request.user, data=request.POST)
        if form.is_valid():
            user = form.save()
            update_session_auth_hash(request, user)  # Important! Keep user logged in
            messages.success(request, "Your password has been successfully changed!")
            return redirect('users:change_password')
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
                        field_label = form.fields[field].label if field in form.fields else field.replace('_', ' ').title()
                        messages.error(request, f"{field_label}: {error}")
        
        return render(request, self.template_name, {'form': form})

# Function-based view for change password (to match URL pattern)
@login_required
def change_password(request):
    """Function-based view for changing password"""
    if request.method == 'POST':
        form = CustomPasswordChangeForm(user=request.user, data=request.POST)
        if form.is_valid():
            user = form.save()
            update_session_auth_hash(request, user)  # Keep user logged in
            messages.success(request, "Your password has been successfully changed!")
            return redirect('users:change_password')
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
                        field_label = form.fields[field].label if field in form.fields else field.replace('_', ' ').title()
                        messages.error(request, f"{field_label}: {error}")
    else:
        form = CustomPasswordChangeForm(user=request.user)
    
    return render(request, 'users/change_password.html', {'form': form})

# URL patterns
from django.urls import path

app_name = 'users'

urlpatterns = [
    path('register/', register, name='register'),
    path('login/', CustomLoginView.as_view(), name='login'),
    path('password_change/', PasswordChangeView.as_view(), name='password_change'),
    path('change_password/', change_password, name='change_password'),  # Function-based view
    # ... other URLs ...
]
