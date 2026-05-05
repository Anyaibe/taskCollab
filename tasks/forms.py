from django import forms
from .models import Project, Task
from django.contrib.auth.models import User


class ProjectForm(forms.ModelForm):
    class Meta:
        model  = Project
        fields = ['name', 'description']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter project name'
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'placeholder': 'Describe the project (optional)',
                'rows': 3
            }),
        }


class TaskForm(forms.ModelForm):
    class Meta:
        model  = Task
        fields = ['title', 'description', 'project', 'assigned_to',
                  'priority', 'status', 'due_date']
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter task title'
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'placeholder': 'Describe the task (optional)',
                'rows': 3
            }),
            'project': forms.Select(attrs={
                'class': 'form-control'
            }),
            # Multiple select for assigning multiple users
            'assigned_to': forms.CheckboxSelectMultiple(),
            'status': forms.Select(attrs={
                'class': 'form-control'
            }),
            'due_date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        if user:
            self.fields['project'].queryset = Project.objects.filter(created_by=user)
        # Exclude superusers from assignable users
        self.fields['assigned_to'].queryset = User.objects.filter(
            is_active=True,
            is_superuser=False
        )