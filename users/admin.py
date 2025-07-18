from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.forms import ReadOnlyPasswordHashField, UserCreationForm, UserChangeForm
from django.core.exceptions import ValidationError
from django import forms
from django.utils.translation import gettext_lazy as _
from .models import CustomUser

class CustomUserCreationForm(UserCreationForm):
    """A form for creating new users. Includes all the required
    fields, plus a repeated password."""
    email = forms.EmailField(required=True)
    full_name = forms.CharField(max_length=255, required=False)

    class Meta:
        model = CustomUser
        fields = ('email', 'full_name')

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if email and CustomUser.objects.filter(email=email).exists():
            raise ValidationError("A user with this email already exists.")
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password1"])
        if commit:
            user.save()
        return user

class CustomUserChangeForm(UserChangeForm):
    """A form for updating users. Includes all the fields on
    the user, but replaces the password field with admin's
    disabled password hash display field."""
    password = ReadOnlyPasswordHashField(
        label=_("Password"),
        help_text=_(
            'Raw passwords are not stored, so there is no way to see this '
            'user\'s password, but you can change the password using '
            '<a href="{}">this form</a>.'
        ),
    )

    class Meta:
        model = CustomUser
        fields = ('email', 'full_name', 'password', 'is_active', 'is_staff', 'is_superuser')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        password = self.fields.get('password')
        if password:
            password.help_text = password.help_text.format('../password/')

    def clean_password(self):
        # Regardless of what the user provides, return the initial value.
        # This is done here, rather than on the field, because the
        # field does not have access to the initial value
        return self.initial.get('password')

class CustomUserAdmin(BaseUserAdmin):
    # The forms to add and change user instances
    form = CustomUserChangeForm
    add_form = CustomUserCreationForm

    # The fields to be used in displaying the User model.
    # These override the definitions on the base UserAdmin
    # that reference specific fields on auth.User.
    list_display = ('email', 'full_name', 'is_staff', 'is_active', 'date_joined', 'last_login')
    list_filter = ('is_staff', 'is_superuser', 'is_active', 'date_joined')
    search_fields = ('email', 'full_name')
    ordering = ('email',)
    filter_horizontal = ('groups', 'user_permissions',)

    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        (_('Personal info'), {'fields': ('full_name',)}),
        (_('Permissions'), {
            'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions'),
        }),
        (_('Important dates'), {'fields': ('last_login', 'date_joined')}),
    )
    
    # add_fieldsets is not a standard ModelAdmin attribute. UserAdmin
    # overrides get_fieldsets to use this attribute when creating a user.
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'full_name', 'password1', 'password2'),
        }),
    )

    readonly_fields = ('date_joined', 'last_login')

    # Custom actions
    actions = ['activate_users', 'deactivate_users', 'make_staff', 'remove_staff']

    def activate_users(self, request, queryset):
        """Activate selected users"""
        updated = queryset.update(is_active=True)
        self.message_user(request, f'{updated} user(s) were successfully activated.')
    activate_users.short_description = "Activate selected users"

    def deactivate_users(self, request, queryset):
        """Deactivate selected users"""
        updated = queryset.update(is_active=False)
        self.message_user(request, f'{updated} user(s) were successfully deactivated.')
    deactivate_users.short_description = "Deactivate selected users"

    def make_staff(self, request, queryset):
        """Give staff status to selected users"""
        updated = queryset.update(is_staff=True)
        self.message_user(request, f'{updated} user(s) were given staff status.')
    make_staff.short_description = "Grant staff status to selected users"

    def remove_staff(self, request, queryset):
        """Remove staff status from selected users"""
        updated = queryset.update(is_staff=False)
        self.message_user(request, f'{updated} user(s) had staff status removed.')
    remove_staff.short_description = "Remove staff status from selected users"

    def get_queryset(self, request):
        """Customize the queryset to add additional annotations if needed"""
        return super().get_queryset(request).select_related()

# Register the new UserAdmin
admin.site.register(CustomUser, CustomUserAdmin)

# Customize admin site headers
admin.site.site_header = "L3Net Web Administration"
admin.site.site_title = "L3Net Admin"
admin.site.index_title = "Welcome to L3Net Administration"
