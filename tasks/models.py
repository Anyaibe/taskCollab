from django.db import models
from django.contrib.auth.models import User
import os


class Project(models.Model):
    name        = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    created_by  = models.ForeignKey(User, on_delete=models.CASCADE, related_name='projects')
    created_at  = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class Task(models.Model):
    STATUS_CHOICES = [
        ('pending',     'Pending'),
        ('in_progress', 'In Progress'),
        ('completed',   'Completed'),
    ]

    title        = models.CharField(max_length=200)
    description  = models.TextField(blank=True)
    project      = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='tasks')
    assigned_to  = models.ManyToManyField(
                       User,
                       related_name='assigned_tasks',
                       blank=True
                   )
    created_by   = models.ForeignKey(
                       User,
                       on_delete=models.SET_NULL,
                       null=True,
                       related_name='created_tasks'
                   )
    PRIORITY_CHOICES = [
    ('low',    'Low'),
    ('medium', 'Medium'),
    ('high',   'High'),
    ]
    
    priority    = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='medium')

    status       = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    due_date     = models.DateField(blank=True, null=True)
    created_at   = models.DateTimeField(auto_now_add=True)
    updated_at   = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['due_date', 'created_at']

    def __str__(self):
        return f"{self.title} ({self.get_status_display()})"


class Comment(models.Model):
    task       = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='comments')
    author     = models.ForeignKey(User, on_delete=models.CASCADE)
    body       = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"Comment by {self.author.username} on {self.task.title}"


class ProjectMembership(models.Model):
    ROLE_CHOICES = [
        ('leader',    'Project Leader'),
        ('developer', 'Developer'),
        ('designer',  'Designer'),
        ('tester',    'Tester'),
        ('member',    'Member'),
    ]

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='memberships')
    user    = models.ForeignKey(User, on_delete=models.CASCADE, related_name='memberships')
    role    = models.CharField(max_length=20, choices=ROLE_CHOICES, default='member')
    joined  = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('project', 'user')

    def __str__(self):
        return f"{self.user.username} — {self.get_role_display()} on {self.project.name}"

class ActivityLog(models.Model):
    user       = models.ForeignKey(User, on_delete=models.CASCADE, related_name='activity_logs')
    task       = models.ForeignKey(Task, on_delete=models.SET_NULL, null=True, blank=True, related_name='logs')
    project    = models.ForeignKey(Project, on_delete=models.SET_NULL, null=True, blank=True, related_name='logs')
    action     = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.username}: {self.action}"

class Notification(models.Model):
    recipient  = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    message    = models.CharField(max_length=255)
    link       = models.CharField(max_length=255, blank=True)
    is_read    = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Notification for {self.recipient.username}: {self.message}"
    

import uuid

class ProjectInvitation(models.Model):
    STATUS_CHOICES = [
        ('pending',  'Pending'),
        ('accepted', 'Accepted'),
        ('declined', 'Declined'),
    ]

    project    = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='invitations')
    invited_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sent_invitations')
    email      = models.EmailField()
    token      = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    status     = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('project', 'email')
        ordering = ['-created_at']

    def __str__(self):
        return f"Invite to {self.project.name} → {self.email} ({self.status})"

def project_file_path(instance, filename):
    """Store files under media/projects/<project_id>/files/"""
    return f'projects/{instance.project.pk}/files/{filename}'


class SharedFile(models.Model):
    project     = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='files')
    uploaded_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='uploaded_files')
    file        = models.FileField(upload_to=project_file_path)
    filename    = models.CharField(max_length=255)
    description = models.CharField(max_length=255, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-uploaded_at']

    def __str__(self):
        return f"{self.filename} — {self.project.name}"

    def get_extension(self):
        _, ext = os.path.splitext(self.filename)
        return ext.lower()