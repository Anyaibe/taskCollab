from django.contrib import admin
from .models import Project, Task, Comment, ProjectMembership, ActivityLog, Notification, ProjectInvitation



@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display  = ('name', 'created_by', 'created_at')
    search_fields = ('name',)


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    # assigned_to removed from list_display — it is now ManyToMany
    list_display  = ('title', 'project', 'status', 'due_date', 'created_by')
    list_filter   = ('status', 'project')
    search_fields = ('title',)
    list_editable = ('status',)

    # This adds a readable display of assigned users in the detail view
    def get_assigned_to(self, obj):
        return ", ".join([u.username for u in obj.assigned_to.all()])
    get_assigned_to.short_description = 'Assigned To'


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ('task', 'author', 'created_at')


@admin.register(ProjectMembership)
class ProjectMembershipAdmin(admin.ModelAdmin):
    list_display  = ('user', 'project', 'role', 'joined')
    list_filter   = ('role', 'project')
    list_editable = ('role',)

from .models import Project, Task, Comment, ProjectMembership, ActivityLog

@admin.register(ActivityLog)
class ActivityLogAdmin(admin.ModelAdmin):
    list_display  = ('user', 'action', 'project', 'task', 'created_at')
    list_filter   = ('project',)
    readonly_fields = ('user', 'task', 'project', 'action', 'created_at')

@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('recipient', 'message', 'is_read', 'created_at')
    list_filter  = ('is_read',)

@admin.register(ProjectInvitation)
class ProjectInvitationAdmin(admin.ModelAdmin):
    list_display  = ('project', 'email', 'invited_by', 'status', 'created_at')
    list_filter   = ('status',)
    readonly_fields = ('token',)